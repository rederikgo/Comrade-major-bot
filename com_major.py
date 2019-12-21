from collections import Counter
from datetime import timedelta
from datetime import datetime
import asyncio
import logging
import logging.handlers
import os
import random
import re
import time
import urllib

from discord.ext.commands import HelpCommand
from discord.ext import commands
from pythonjsonlogger import jsonlogger
import sentry_sdk
import yaml

from comrade_db import AsyncDB
from lastfm import LastRequester
from videos_meta import parse_title, remove_brackets, remove_unicode
from youtube import YoutubePlaylists

# Check if the message contains valid link and process if it does
async def check_message(message, allow_copies=True, silent=False):
    if message.channel.id not in discord_watched_channels:
        if message.channel.id == archive_channel_id:
            await process_archive_channel_posting()
        return

    # Check if the message contains an eligible link and archive
    provider = is_link(message.content)
    if provider and provider != 'undefined link':
        logger.debug(f'Detected video in {message.content}')

        # Clean link
        link = extract_link(message.content)
        link, video_id = clean_link(link, provider)

        # Check if youtube category is eligible
        video_title = ''
        video_category = ''
        if provider == 'youtube':
            video_info = get_youtube_video_info(video_id)
            try:
                video_title = video_info['items'][0]['snippet']['title']
                video_category = video_info['items'][0]['snippet']['categoryId']
                if video_category not in eligible_video_categories:
                    logger.info(f"Video from {link} rejected (invalid category)")
                    return
            except:
                logger.info(f"Video from {link} rejected (no category, probably deleted)")
                return

        # Check if the link has been already archived
        is_posted = await db.has_it_been_posted(link, archive_channel_id)
        if is_posted:
            # Add emoji to duplicate links
            if not silent:
                for emoji in client.emojis:
                    if emoji.name == duplicate_emoji:
                        try:
                            await message.add_reaction(client.get_emoji(emoji.id))
                            break
                        except:
                            logger.error('Cant find emoji for duplicate links on the server')

            # Do nothing if copies are not allowed
            if not allow_copies:
                logger.debug(f'Video from {message.content} rejected (already in the archive)')
                return

        # Archive finally
        await archive_video(message, link, video_title, silent)


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
def extract_link(content):
    link = re.findall(url_pattern, content)
    if link:
        return link[0]
    else:
        logger.error(f'Error extracting link from {content}')

# Get video id and shorten it (for youtube now, but who knows)
def clean_link(link, provider):
    if provider == 'youtube':
        video_id = get_id(link)
        clean_url = 'https://www.youtube.com/watch?v=' + video_id
    else:
        video_id = ''
        clean_url = link
    return clean_url, video_id


# Add video to the database and copy to archive channel
async def archive_video(message, link, video_title, silent=False):
    video_id = await db.get_video_by_link(link)
    if not video_id:
        video_id = await db.add_video(link, video_title)
    posted_id = await db.archive_video(video_id, archive_channel_id, message.channel.id, message.author.id, time.strftime(db_timeformat_full))
    logger.info(f'Video archived: {link}')
    if not silent:
        await post_video_to_archive_channel(posted_id)


async def post_video_to_archive_channel(posted_id):
    channel = client.get_channel(archive_channel_id)
    post_info = await db.get_archived_video_by_id(posted_id)
    link = post_info[0]
    user_id = post_info[1]
    time_posted = post_info[2]
    time_posted_struct = datetime.strptime(time_posted, db_timeformat_full)
    time_posted_local = time_posted_struct + timedelta(hours=utc_time_offset)
    user_name = 'Someone'
    for user in channel.members:
        if user.id == user_id:
            user_name = user.display_name

    await channel.send(f"{user_name} at {time_posted_local}:")
    await channel.send(link)
    logger.info(f'Video posted to channel: {link}')


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

# Get video info
def get_youtube_video_info(video_id):
    try:
        return youtube.get_video_info(video_id)
    except:
        logger.error(f'Error retrieving video info {video_id}')


# Process vimeo
async def process_vimeo(message, silent):
    await archive_video(message, silent)


# Warn user on archive channel posting and clean after delay
async def process_archive_channel_posting(message):
    my_msg = await message.channel.send(archive_posting_warning)
    await my_msg.delete(delay=5)
    await message.delete(delay=5)
    logger.info('Cleared random message to archive channel')


# Update video titles
async def update_video_titles():
    videos = await db.get_videos()
    for video in videos:
        id = video[0]
        link = video[1]
        video_title = video[2]

        # Skip videos with titles
        if video_title:
            continue

        if is_link(link) == 'youtube':
            video_id = get_id(link)
            video_info = get_youtube_video_info(video_id)
            try:
                video_title = video_info['items'][0]['snippet']['title']
                await db.update_video_title(id, video_title)
            except:
                logger.warning(f'No title for video {link}')


# Guess artist
async def guess_artist():
    try:
        lastfm = LastRequester(lastfm_token)
    except:
        logger.error('Cant init last.fm connection')
        return False

    videos = await db.get_videos()
    for video in videos:
        id = video[0]
        link = video[1]
        video_title = video[2]
        artist = video[3]

        # Skip videos which already have artist parsed
        if artist:
            continue
        # Skip videos without titles
        if not video_title:
            continue

        # Try to parse the title
        parsed_artist = parse_title(video_title)
        if not parsed_artist:
            logger.debug(f'Failed to parse {link}')
            continue

        # Clean the parsed title
        clean_artist = []
        for _ in parsed_artist:
            clean = remove_unicode(_)
            clean = remove_brackets(clean)
            clean = clean.strip()
            clean_artist.append(clean)
        artist = clean_artist[0]
        title = clean_artist[1]

        # Check if such artist exists on last.fm
        if not lastfm.check_artist(artist):
            logger.debug(f'Cant find {artist} on lastfm')
            continue

        # Update database finally
        await db.enrich_video(id, artist, title)
        logger.debug(f'Enriched {link} as {artist} - {title}')


# Get top tags for videos from lastfm
async def get_tags_lastfm():
    try:
        lastfm = LastRequester(lastfm_token)
    except:
        logger.error('Cant init last.fm connection')
        return False

    videos = await db.get_videos()
    for video in videos:
        video_id = video[0]
        artist = video[3]

        # Skip videos without artists
        if not artist:
            continue

        # Skip videos which have tags
        if await db.check_video_tags(video_id):
            continue

        top_tags = lastfm.check_artist(artist)
        for tag in top_tags:
            await db.add_tag(video_id, tag)


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


# MAIN
# Load config
with open('config.yaml', 'r', encoding="utf-8") as configfile:
    cfg = yaml.safe_load(configfile)

# Setup sentry.io reporting
sentry_dsn = cfg['debug']['sentry dsn']
sentry_app_name = cfg['debug']['sentry appname']
sentry_environment = cfg['debug']['sentry environment']
sentry_sdk.init(sentry_dsn, release=sentry_app_name, environment=sentry_environment)

# Enable debug for asyncio
os.environ['PYTHONASYNCIODEBUG'] = '1'

# Setup logging
logging_level = cfg['debug']['debug level']
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s: %(message)s')

handler = logging.handlers.RotatingFileHandler('comrade.log', mode='a', maxBytes=10485760, backupCount=0, encoding='utf-8')
handler.setLevel(logging_level)
handler.setFormatter(formatter)

logger = logging.getLogger("comrade")
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
archive_posting_warning = cfg['bot']['archive posting warning']
bot_admins = cfg['bot']['admin users']
allow_copies = cfg['bot']['allow copies in archive']
duplicate_emoji = cfg['bot']['duplicacte emoji']
archive_depth = cfg['bot']['archive depth']
url_pattern = cfg['bot']['url pattern']
max_pips = cfg['bot']['max pips in report']
db_path = cfg['database']['path']
db_init_script = cfg['database']['init_script']
db_timeformat_full = '%Y-%m-%d %H:%M:%S'
birthday_report_time = cfg['database']['birthday_report_time']
check_frequency = cfg['database']['check_frequency']
lastfm_token = cfg['lastfm']['token']

helpme = custom_help()
client = commands.Bot(command_prefix=command_prefix, help_command=helpme)
db = AsyncDB(db_path, db_init_script)


# TRIGGERS AND COMMANDS
@client.event
async def on_ready():
    # Log status on connect
    logger.info('Logged in as {0.user}'.format(client))
    for channel in discord_watched_channels:
        watched_channel = client.get_channel(channel)
        logger.info(f'Watching [{watched_channel.name}] on [{watched_channel.guild}]')
    video_channel = client.get_channel(archive_channel_id)
    logger.info(f'Will copy videos to [{video_channel.name}] on [{video_channel.guild}]')


@client.event
async def on_message(message):
    # Re-enable commands
    await client.process_commands(message)

    # Ignore own messages
    if message.author == client.user:
        return

    # Process random posts to archive channel
    if message.channel.id == archive_channel_id:
        await process_archive_channel_posting(message)
        return

    # Check the new message and archive if it is eligible music video
    await check_message(message, allow_copies=allow_copies)


# Scan X last messages and archive eligible, which have not been archived before
@client.command()
async def archive(ctx, depth=10000, mode=''):
    # Get channel history
    logger.debug('Got archive command')
    ctx_history = await ctx.history(limit=int(depth), oldest_first=True).flatten()
    logger.debug(f'Loaded {len(ctx_history)} historic messages from context channel')

    # Check all messages in channel and archive music videos which are not in the archive
    silent = False
    if mode.lower() == 'silent':
        silent = True
    for message in ctx_history:
        await check_message(message, allow_copies=False, silent=silent)

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
            link = extract_link(message.content)
            logger.debug(f'Force-archiving message {link}')
            await archive_video(message, link)


# Post simple report (total links in archive and user contribution)
@client.command()
async def report(ctx, target='this', sorting_order='count'):
    logger.info('Got archive report command')

    # !!!Rewrite to check from the db!!!
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


# Lots of fun!
@client.command()
async def slap(ctx, target):
    await ctx.send(f'{ctx.author.mention} slaps {target} around a bit with a large trout')


# Check for birthdays and congratulate member
async def report_birthdays():
    await client.wait_until_ready()
    while not client.is_closed():
        for watched_channel in discord_watched_channels:
            channel = client.get_channel(watched_channel)
            birthdays = await db.get_birthdays()
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
                        await db.mark_congrated(user_id, datetime.now().year)
        await asyncio.sleep(check_frequency)


async def congrat(channel, user_id):
    congrats = [i[0] for i in await db.get_congrats()]
    message = random.choice(congrats)
    user_name = get_user_mention(channel, user_id)
    await channel.send(message.format(user_name=user_name))


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

    members = await db.get_members()
    if target_user_id not in members:
        await db.add_member(target_user_id)
        report_text = f'Added birthday date for {ctx.message.mentions[0].display_name}'
    else:
        report_text = f'Updated birthday date for {ctx.message.mentions[0].display_name}'
    await db.update_birthday(target_user_id, date_raw)
    logger.info(report_text)
    await ctx.send(report_text)


def convert_to_structdate(date_raw):
    try:
        if len(date_raw.split('.')) == 3:
            frmt = '%d.%m.%Y'
        else:
            frmt = '%d.%m'
        return time.strptime(date_raw, frmt)
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
    birthdays = await db.get_birthdays()
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
        return

    # Compose and send the reply
    reply = ['```', 'Birthdays:']
    longest_name = max([len(i[0]) for i in eligible_birthdays])
    for birthday in eligible_birthdays:
        spaces = longest_name - len(birthday[0]) + 5
        reply.append(f'- {birthday[0]}{spaces*" "}{birthday[1]}')
    reply.append('```')
    reply_string = '\n'.join(reply)
    await ctx.send(reply_string)


@client.command()
async def update_titles(ctx):
    await update_video_titles()
    await ctx.send(ok_reply)

@client.command()
async def enrich_titles(ctx):
    await guess_artist()
    await ctx.send(ok_reply)

@client.command()
async def get_tags(ctx):
    await get_tags_lastfm()
    await ctx.send(ok_reply)

# WRYYYYY
try:
    client.loop.create_task(report_birthdays())
    client.run(discord_token)
except:
    logger.error('Failed to init discord bot')