from datetime import timedelta
import logging
import logging.handlers
import urllib

import discord
from discord.ext import commands
import yaml

from youtube import YoutubePlaylists

# Check if the message is a youtube link
def is_link(message):
    if 'www.youtube.com/watch' in message:
        return True

# Check if video category is eligible
def is_eligible_category(link):
    # Get video id
    logger.debug(f'Parsing link {link}')
    try:
        youtube_query = urllib.parse.urlparse(link)[4]
        video_id = urllib.parse.parse_qs(youtube_query)['v'][0]
    except:
        logger.error(f'Error parsing {link}')

    # Get video category from video info
    video_info = youtube.get_video_info(video_id)
    try:
        video_category = video_info['items'][0]['snippet']['categoryId']
    except:
        logger.error(f'Error checking category {link}')

    if video_category in eligible_video_categories:
        return True
    else:
        logger.info(f'Video rejected (wrong category): {link}')

# Copy video to archive channel
async def archive_video(message):
    channel = client.get_channel(archive_channel_id)
    message_time = message.created_at + timedelta(hours=utc_time_offset)
    time_posted = message_time.strftime('%Y-%m-%d %H:%M')
    await channel.send(f"{message.author.name} at {time_posted}:")
    await channel.send(message.content)
    logger.debug(f'Video archived: {message.content}')


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

    # Will leave this in case silent testing is required in future
    # archive_channel = client.get_channel(archive_channel_id)
    # archive_history = await archive_channel.history().flatten()
    # archive_history_content = [message.content for message in archive_history]
    #
    # chan_id = 544615694470217728
    # chan = client.get_channel(chan_id)
    # hist = await chan.history(limit=100000, oldest_first=True).flatten()
    # for message in hist:
    #     if is_link(message.content) and \
    #             is_eligible_category(message.content) and \
    #             message.content not in archive_history_content:
    #         await archive_video(message)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Check new message and archive if it is eligible music video
    if is_link(message.content) and \
        message.channel.id in discord_watched_channels and \
        is_eligible_category(message.content):
            await archive_video(message)

    await client.process_commands(message)

@client.command()
async def archive(ctx, depth):
    # Get channel history
    logger.debug('Got archive command')
    ctx_history = await ctx.history(limit=int(depth), oldest_first=True).flatten()
    logger.debug(f'Loaded {len(ctx_history)} historic messages from context channel')

    # Get archive
    archive_channel = client.get_channel(archive_channel_id)
    archive_history = await archive_channel.history(limit=10000).flatten()
    archive_history_content = [message.content for message in archive_history]
    logger.debug(f'Loaded {len(archive_history_content)} messages from archive')

    # Check all messages in channel and archive music videos which are not in the archive
    for message in ctx_history:
        if is_link(message.content) and \
                is_eligible_category(message.content) and \
                message.content not in archive_history_content:
            await archive_video(message)

    await ctx.send(ok_reply)

# WRYYYYY
try:
    client.run(discord_token)
except:
    logger.error('Failed to init discord bot', debug=True)