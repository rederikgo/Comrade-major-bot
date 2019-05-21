from datetime import timedelta
import logging
import logging.handlers
import urllib

import discord
import yaml

from youtube import YoutubePlaylists


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
discord_video_channel = cfg['discord']['target video channel']

client = discord.Client()

@client.event
async def on_ready():
    # Log status
    logger.info('Logged in as {0.user}'.format(client))
    for channel in discord_watched_channels:
        watched_channel = client.get_channel(channel)
        logger.info(f'Watching [{watched_channel.name}] on [{watched_channel.guild}]')
    video_channel = client.get_channel(discord_video_channel)
    logger.info(f'Will copy videos to [{video_channel.name}] on [{video_channel.guild}]')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Check if a message on a watched channel is a link to a music video on youtube
    if 'www.youtube.com' in message.content and message.channel.id in discord_watched_channels:
        # Fish out video id
        youtube_query = urllib.parse.urlparse(message.content)[4]
        youtube_video_id = urllib.parse.parse_qs(youtube_query)['v'][0]
        # Get video category
        video_info = youtube.get_video_info(youtube_video_id)
        video_category = video_info['items'][0]['snippet']['categoryId']
        # Check against music categories and send copy of the message to the video archive channel
        if video_category in ['10', '24', '33']:
            channel = client.get_channel(discord_video_channel)
            message_time = message.created_at + timedelta(hours=3)
            time_string = message_time.strftime('%Y-%m-%d %H-%M')
            await channel.send(f"{message.author.name} at {time_string}:" )
            await channel.send(message.content)
            logger.debug(f'Video archived: {message.content}')
        else:
            logger.debug(f'Wrong video category: {message.content}')


# WRYYYYY
try:
    client.run(discord_token)
except:
    logger.error('Failed to init discord bot')