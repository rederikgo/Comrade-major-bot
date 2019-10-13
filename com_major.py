from collections import Counter
from datetime import timedelta
from datetime import datetime
from operator import itemgetter
import asyncio
import logging
import logging.handlers
import random
import re
import time
import urllib

import discord
from discord.ext.commands import HelpCommand
from discord.ext import commands
from pythonjsonlogger import jsonlogger
import sentry_sdk
import yaml

from youtube import YoutubePlaylists
from comrade_db import DB

async def update_archive_content(depth=10000):
    # Load full archive from Discord
    global archive_history_full
    try:
        archive_channel = client.get_channel(archive_channel_id)
        archive_history_full = await archive_channel.history(limit=depth).flatten()
    except:
        logger.error(f'Failed to load archive from Discord')
        return

    # Get the list of messages
    global archive_history_content
    archive_history_content = [message.content for message in archive_history_full]
    logger.debug(f'Loaded {len(archive_history_content)} archive entities')


# Add the message to the archive list manually (to avoid full reload of archive list)
async def add_to_archive_content(link):
    global archive_history_content
    archive_history_content.append(link)


# Check message and call specific provider routine
async def check_message(message, allow_copies=True):
    # Check if the message is from a watched channel
    if message.channel.id not in discord_watched_channels:
        return

    # Check if the message contains an eligible link and execute corresponding routine
    provider = is_link(message.content)
    if provider and provider != 'undefined link':
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


# Check if the message contains an (eligible) link
def is_link(content):
    if 'youtube.com/watch' in content:
        return 'youtube'
    elif 'youtu.be/' in content:
        return 'youtube'
    elif 'vimeo.com/' in content:
        return 'vimeo'
    # At least location + path should be present, eg. 'youtube.com/a'
    elif re.findall(url_pattern, content):
        return 'undefined link'


# Extract first eligible link from the the message
def clean_link(content):
    link = re.findall(url_pattern, content)
    if link:
        return link[0]
    else:
        logger.error(f'Error extracting link from {content}')


# Copy video to archive channel
async def archive_video(message):
    channel = client.get_channel(archive_channel_id)
    message_time = message.created_at + timedelta(hours=utc_time_offset)
    time_posted = message_time.strftime('%Y-%m-%d %H:%M')
    link = clean_link(message.content)
    await channel.send(f"{message.author.name} at {time_posted}:")
    await channel.send(link)
    await add_to_archive_content(link=link)
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


# Load custom help file 'help.txt'
class custom_help(HelpCommand):
    async def send_bot_help(self, mapping):
        logger.info('Got help command')
        try:
            with open('help.txt', encoding='utf-8') as file:
                help_text = file.read()
        except:
            logger.error('Error opening help file')

        await self.context.send(help_text)


# Main
# Load config
with open('config.yaml', 'r') as configfile:
    cfg = yaml.safe_load(configfile)

# Setup sentry.io reporting
sentry_dsn = cfg['debug']['sentry dsn']
sentry_app_name = cfg['debug']['sentry appname']
sentry_environment = cfg['debug']['sentry environment']
sentry_sdk.init(sentry_dsn, release=sentry_app_name, environment=sentry_environment)

# Setup logging
logging_level = cfg['debug']['debug level']
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s: %(message)s')

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
discord_token = cfg['bot']['bot token']
discord_watched_channels = cfg['bot']['watched channels']
archive_channel_id = cfg['bot']['target video channel']
eligible_video_categories = cfg['youtube']['eligible categories']
utc_time_offset = cfg['bot']['utc time offset']
command_prefix = cfg['bot']['command prefix']
ok_reply = cfg['bot']['ok reply']
bot_admins = cfg['bot']['admin users']
allow_copies = cfg['bot']['allow copies in archive']
archive_depth = cfg['bot']['archive depth']
url_pattern = cfg['bot']['url pattern']
max_pips = cfg['bot']['max pips in report']
db_path = cfg['database']['path']
db_init_script = cfg['database']['init_script']
birthday_report_time = cfg['database']['birthday_report_time']
check_frequency = cfg['database']['check_frequency']

helpme = custom_help()
client = commands.Bot(command_prefix=command_prefix, help_command=helpme)

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
    await update_archive_content(depth=archive_depth)


@client.event
async def on_message(message):
    # Re-enable commands
    await client.process_commands(message)

    # Ignore own messages
    if message.author == client.user:
        return

    # Check the new message and archive if it is eligible music video
    await check_message(message, allow_copies=allow_copies)


# Scan X last messages and archive eligible, which have not been archived before
@client.command()
async def archive(ctx, depth=10000):
    # Get channel history
    logger.debug('Got archive command')
    ctx_history = await ctx.history(limit=int(depth), oldest_first=True).flatten()
    logger.debug(f'Loaded {len(ctx_history)} historic messages from context channel')

    # Check all messages in channel and archive music videos which are not in the archive
    for message in ctx_history:
        await check_message(message, allow_copies=False)

    await ctx.send(ok_reply)


# Wipe all messages from the archive channel
@client.command()
async def wipe_archive(ctx):
    logger.info('Got wipe archive command')
    if ctx.author.id not in bot_admins:
        logger.info('Not an admin, rejected')
    chan = client.get_channel(archive_channel_id)
    hist = await chan.history(limit=archive_depth).flatten()
    for message in hist:
        logger.info(f'Deleting message: {message.content}')
        await message.delete()
    await update_archive_content(depth=archive_depth)

    await ctx.send(ok_reply)


# Scan last messages and force-archive all urls
@client.command()
async def force(ctx, depth):
    logger.info('Got force command')
    if depth == 'last':
        depth = 1
    if ctx.channel.id not in discord_watched_channels:
        logger.info('Channel is not watched, rejected')
        return

    ctx_history = await ctx.history(limit=int(depth)+1).flatten()
    for message in ctx_history:
        if is_link(message.content):
            logger.debug(f'Force-archiving message {message.content}')
            await archive_video(message)


# Post simple report (total links in archive and user contribution)
@client.command()
async def report(ctx, target='archive', sorting_order='name'):
    logger.info('Got archive report command')

    if target == 'archive':
        archive_channel = client.get_channel(archive_channel_id)
        archive_messages = await archive_channel.history(limit=archive_depth).flatten()
        posters = []
        for message in archive_messages:
            if message.author == client.user and not is_link(message.content):
                poster = message.content.split()[0]
                posters.append(poster)
        alive_delta = datetime.now() - archive_messages[-1].created_at

        report = ['```']
        report.append('Archive channel report:')
        report.append('')
        report.append(f'Created {alive_delta.days} days ago')
        report.append(f'Total messages: {len(posters)}')
        report.append('')
        report.append('Posters:')
        report += format_members_list(posters, sorting_order)
        report.append('```')
        report_string = '\n'.join(report)
        await ctx.send(report_string)

    elif target == 'this':
        messages = await ctx.channel.history(limit=archive_depth).flatten()
        active_members = [member.id for member in ctx.channel.members]
        posters = []
        for message in messages:
            if message.author != client.user:
                if message.author.id in active_members:
                    posters.append(message.author.display_name)
                else:
                    posters.append('Inactive members')

        if ctx.channel.id in discord_watched_channels:
            channel_type = 'watched'
        else:
            channel_type = 'unwatched'
        alive_delta = datetime.now() - messages[-1].created_at
        days_alive = alive_delta.days + alive_delta.seconds / 60 / 60 / 24
        average_messages = round(len(messages) / days_alive, 2)

        report = ['```']
        report.append(f'Current channel report:')
        report.append('')
        report.append(f'Created {int(days_alive)} days ago')
        report.append(f'Total messages: {len(posters)}')
        report.append(f'Average messages per day: {average_messages}')
        report.append(f'Channel type: {channel_type}')
        report.append('')
        report.append('Posters:')
        report += format_members_list(posters, sorting_order)
        report.append('```')
        report_string = '\n'.join(report)
        await ctx.send(report_string)


# Get formatted and sorted list of posters for the report
def format_members_list(posters, sorting_order):
    # Count post for each poster, calculate some figures for formatting
    poster_stats = Counter(posters)
    max_value = max(poster_stats.values())
    longest_name = max([len(x) for x in poster_stats.keys()])
    step = int(max_value / max_pips) + 1

    # Convert dict to list and sort
    poster_stats_list = []
    for key in poster_stats:
        poster_stats_list.append([key, poster_stats[key]])
    if sorting_order == 'name':
        poster_stats_list.sort(key=lambda x: x[0].lower())
    elif sorting_order == 'count':
        poster_stats_list.sort(key=lambda x: x[1], reverse=True)
    else:
        logging.error('Unsupported sorting order')

    # Return the list of formatted strings for the report
    report = []
    for poster in poster_stats_list:
        poster_name = poster[0]
        poster_message_count = poster[1]
        spaces = longest_name - len(poster_name)
        pips = max(1, int(poster_message_count / step))
        report.append(f'{poster_name}:{" " * spaces} {"-" * pips} {poster_message_count}')
    return report


@client.command()
async def slap(ctx, target):
    await ctx.send(f'{ctx.author.mention} slaps {target} around a bit with a large trout')


# Check for birthdays and congratulate member
async def report_birthdays():
    await client.wait_until_ready()
    while not client.is_closed():
        db = DB(db_path, db_init_script)
        for watched_channel in discord_watched_channels:
            channel = client.get_channel(watched_channel)
            birthdays = db.get_birthdays()
            current_str_time = time.gmtime(time.time())
            if current_str_time[3] >= birthday_report_time:
                for birthday in birthdays:
                    user_id = birthday[0]
                    date = convert_to_structdate(birthday[1])
                    last_reported = birthday[2]
                    if not date:
                        continue
                    if last_reported == datetime.now().year:
                        continue
                    if date[1:3] == current_str_time[1:3]:
                        await congrat(channel, user_id)
                        db.mark_congrated(user_id, datetime.now().year)
        await asyncio.sleep(check_frequency)
        db.close()


async def congrat(channel, user_id):
    db = DB(db_path, db_init_script)
    congrats = [i[0] for i in db.get_congrats()]
    message = random.choice(congrats)
    user_name = get_user_mention(channel, user_id)
    await channel.send(message.format(user_name=user_name))
    db.close()


# Set or replace birthday
@client.command()
async def set_birthday(ctx):
    try:
        target_user_id = ctx.message.mentions[0].id
    except:
        logger.error('Cant find mention in set_birthday command')
        return
    message = ctx.message.clean_content.split(' ')
    date_raw = message[-1]
    if not convert_to_structdate(date_raw):
        return

    db = DB(db_path, db_init_script)
    members = db.get_members()
    if target_user_id not in members:
        db.add_member(target_user_id)
        report_text = f'Added birthday date for {ctx.message.mentions[0].display_name}'
    else:
        report_text = f'Updated birthday date for {ctx.message.mentions[0].display_name}'
    db.update_birthday(target_user_id, date_raw)
    logger.info(report_text)
    await ctx.send(report_text)
    db.close()


def convert_to_structdate(date_raw):
    try:
        if len(date_raw.split('.')) == 3:
            format = '%d.%m.%Y'
        else:
            format = '%d.%m'
        return time.strptime(date_raw, format)
    except:
        logger.error('No date or wrong date format')
        return


def get_user_mention(channel, user_id):
    for user in channel.members:
        if user.id == user_id:
            return user.mention


# Send report on stored birthdays sorted by user name
@client.command()
async def show_birthdays(ctx, sorting_key='name'):
    # Get the list of current members with birthdays from the database
    db = DB(db_path, db_init_script)
    birthdays = db.get_birthdays()
    members_list = [[member.id, member.display_name] for member in ctx.channel.members]
    members_id = [member.id for member in ctx.channel.members]
    members_dict = {i[0]: i[1] for i in members_list}
    eligible_birthdays = []
    for birthday in birthdays:
        if birthday[0] in members_id:
            eligible_birthdays.append([members_dict[birthday[0]], birthday[1]])
    if not eligible_birthdays:
        logger.debug('No eligible birthdays found for reply')
        return

    # Sort the list
    if sorting_key == 'name':
        eligible_birthdays.sort(key=lambda x: x[0].lower())
    elif sorting_key == 'date':
        eligible_birthdays.sort(key=lambda x: convert_to_structdate(x[1]))
    else:
        logging.error('Unsupported sorting method')
        db.close()
        return

    # Compose and send the reply
    reply = ['```']
    reply.append('Birthdays:')
    longest_name = max([len(i[0]) for i in eligible_birthdays])
    for birthday in eligible_birthdays:
        spaces = longest_name - len(birthday[0]) + 5
        reply.append(f'- {birthday[0]}{spaces*" "}{birthday[1]}')
    reply.append('```')
    reply_string = '\n'.join(reply)
    await ctx.send(reply_string)
    db.close()

# WRYYYYY
try:
    client.loop.create_task(report_birthdays())
    client.run(discord_token)
except:
    logger.error('Failed to init discord bot')