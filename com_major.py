from datetime import timedelta
import logging
import logging.handlers
import urllib

import discord
from discord.ext import commands
import yaml

from youtube import YoutubePlaylists


# Check message and call specific provider routine
async def check_message(message, allow_copies=True):
    # Check if the message is from a watched channel
    if message.channel.id not in discord_watched_channels:
        return

    # Check if the message contains an eligible link and execute corresponding routine
    provider = is_link(message.content)
    if provider:
        logger.debug(f'Detected video in {message.content}')
        # Check if the link has been already archived (optional)
        if allow_copies == False:
            global archive_history_content
            if clean_link(message.content) in archive_history_content:
                logger.debug(f'Video from {message.content} rejected (already in the archive)')
                return

        if provider == 'youtube':
            await process_youtube(message)
        elif provider == 'vimeo':
            await process_vimeo(message)
        else:
            logger.error(f'Unknown provider in {message.content}')


# Check if the message is a link to eligible service
def is_link(content):
    if 'youtube.com/watch' in content:
        return 'youtube'
    elif 'youtu.be/' in content:
        return 'youtube'
    elif 'vimeo.com/' in content:
        return 'vimeo'


# Extract only (first) eligible link from the the message
def clean_link(content):
    try:
        for word in content.split():
            if is_link(word):
                return word
    except:
        logger.error(f'Error extracting link from {content}')


# Copy video to archive channel
async def archive_video(message):
    channel = client.get_channel(archive_channel_id)
    message_time = message.created_at + timedelta(hours=utc_time_offset)
    time_posted = message_time.strftime('%Y-%m-%d %H:%M')
    link = clean_link(message.content)
    await channel.send(f"{message.author.name} at {time_posted}:")
    await channel.send(link)
    await update_archive_content(mode='add', link=link)
    logger.info(f'Video archived: {message.content}')


# Process youtube
async def process_youtube(message):
    # Extract link from possible surrounding text
    link = clean_link(message.content)
    # Get youtube video id
    video_id = get_id(link)
    # Check if video category is eligible and archive
    if is_eligible_category(video_id):
        await archive_video(message)


# Get youtube video id
def get_id(link):
    try:
        if 'youtube.com/watch?' in link:
            youtube_query = urllib.parse.urlparse(link).query
            return urllib.parse.parse_qs(youtube_query)['v'][0]
        elif 'youtu.be/' in link:
            youtube_path = urllib.parse.urlparse(link).path
            return youtube_path[1:]
        else:
            logger.error(f'Unknown url pattern at {link}')
    except:
        logger.error(f'Error getting video id from {link}')


# Check if youtube video category is eligible
def is_eligible_category(video_id):
    # Get video category from video info
    video_category = ''
    try:
        video_info = youtube.get_video_info(video_id)
        video_category = video_info['items'][0]['snippet']['categoryId']
    except:
        logger.error(f'Error checking category {video_id}')

    if video_category in eligible_video_categories:
        return True
    else:
        logger.info(f'Video rejected (wrong category): {video_id}')


# Process vimeo
async def process_vimeo(message):
    await archive_video(message)


async def update_archive_content(mode, depth=10000, link=''):
    # Load full archive from Discord
    global archive_history_content
    if mode == 'full':
        try:
            archive_channel = client.get_channel(archive_channel_id)
            archive_history = await archive_channel.history(limit=depth).flatten()
            archive_history_content = [message.content for message in archive_history]
            logger.debug(f'Loaded {len(archive_history_content)} archive entities')
        except:
            logger.error(f'Failed to load archive from Discord')

    # Add link to a archive_content list (we don't need to reload archive after each submission)
    elif mode == 'add':
        archive_history_content.append(link)

    else:
        logger.error('Unknown mode of archive update')

# Main
# Load config
with open('config.yaml', 'r') as configfile:
    cfg = yaml.safe_load(configfile)


# Setup logging
logging_level = cfg['debug']['debug level']
formatter = logging.Formatter('%(asctime)s: %(message)s')

handler = logging.handlers.RotatingFileHandler('comrade.log', mode='a', maxBytes=10485760, backupCount=0, encoding='utf-8')
handler.setLevel(logging_level)
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging_level)
logger.addHandler(handler)
logger.info('')
logger.info('Session started')


# Init youtube wrapper
client_secrets_file = cfg['youtube']['client secrets file']
credentials_file = cfg['youtube']['credentials file']

try:
    youtube = YoutubePlaylists(client_secrets_file, credentials_file)
except:
    logger.error('Youtube connection error')


# Init and configure discord bot
discord_token = cfg['discord']['bot token']
discord_watched_channels = cfg['discord']['watched channels']
archive_channel_id = cfg['discord']['target video channel']
eligible_video_categories = cfg['youtube']['eligible categories']
utc_time_offset = cfg['discord']['utc time offset']
command_prefix = cfg['bot']['command prefix']
ok_reply = cfg['bot']['ok reply']

client = commands.Bot(command_prefix=command_prefix)


@client.event
async def on_ready():
    # Log status on connect
    logger.info('Logged in as {0.user}'.format(client))
    for channel in discord_watched_channels:
        watched_channel = client.get_channel(channel)
        logger.info(f'Watching [{watched_channel.name}] on [{watched_channel.guild}]')
    video_channel = client.get_channel(archive_channel_id)
    logger.info(f'Will copy videos to [{video_channel.name}] on [{video_channel.guild}]')

    # Load messages from archive channel
    await update_archive_content(mode='full')


@client.event
async def on_message(message):
    # Re-enable commands
    await client.process_commands(message)

    # Ignore own messages
    if message.author == client.user:
        return

    # Check the new message and archive if it is eligible music video
    await check_message(message)


@client.command()
async def archive(ctx, depth):
    # Get channel history
    logger.debug('Got archive command')
    ctx_history = await ctx.history(limit=int(depth), oldest_first=True).flatten()
    logger.debug(f'Loaded {len(ctx_history)} historic messages from context channel')

    # Check all messages in channel and archive music videos which are not in the archive
    for message in ctx_history:
        await check_message(message, allow_copies=False)

    await ctx.send(ok_reply)


# WRYYYYY
try:
    client.run(discord_token)
except:
    logger.error('Failed to init discord bot', debug=True)