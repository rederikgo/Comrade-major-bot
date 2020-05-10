import aiosqlite
import sqlite3
import os
import logging


class DatabaseError(Exception):
    def __init__(self, message):
        self.message = message


class DBConnection:
    def __init__(self, db_path, init_script):
        self.logger = logging.getLogger("comrade")
        self.db_path = db_path
        self.init_script = init_script
        if not os.path.isfile(self.db_path):
            self.logger.error('Cant find database file. Creating the new one')
            self._create_db()

    async def __aenter__(self):
        self.db = await aiosqlite.connect(self.db_path)
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        await self.db.close()

    def _create_db(self):
        connection = sqlite3.connect(self.db_path)
        cursor = connection.cursor()
        try:
            script = open(self.init_script).read()
        except:
            self.logger.error('Cant open init script file')
            raise DatabaseError('Cant open init script file')

        cursor.executescript(script)
        connection.close()
        self.logger.info('New database created')


class AsyncDB:
    def __init__(self, db_path, init_script):
        self.logger = logging.getLogger("comrade")
        self.database = DBConnection(db_path, init_script)

    async def add_member(self, member_id):
        async with self.database as db:
            await db.execute("""
                INSERT INTO Members (id, birthday)
                VALUES (?, NULL);
            """, (member_id,))
            await db.commit()

    async def get_members(self):
        async with self.database as db:
            cur = await db.execute("""
                SELECT id
                FROM Members
            """)
            result = await cur.fetchall()
        return [i[0] for i in result]

    async def update_birthday(self, member_id, birthday):
        async with self.database as db:
            await db.execute("""
                UPDATE Members 
                SET birthday = ?
                WHERE id = ?
            """, (birthday, member_id))
            await db.commit()

    async def get_birthdays(self):
        async with self.database as db:
            cur = await db.execute("""
                SELECT id, birthday, last_reported
                FROM Members
                WHERE birthday is not NULL
            """)
            result = await cur.fetchall()
        return result

    async def mark_congrated(self, member_id, last_reported):
        async with self.database as db:
            await db.execute("""
                UPDATE Members 
                SET last_reported = ?
                WHERE id = ?
            """, (last_reported, member_id))
            await db.commit()

    async def get_congrats(self):
        async with self.database as db:
            cur = await db.execute("""
                SELECT text
                FROM Congrats
            """)
            result = await cur.fetchall()
        return result

    async def add_video(self, link, video_title):
        async with self.database as db:
            cur = await db.execute("""
                INSERT INTO Videos(link, video_title)
                VALUES (?, ?);
            """, (link, video_title))
            await db.commit()
            last_row = cur.lastrowid
        return last_row

    # Temp, for old videos
    async def update_video_title(self, video_id, video_title=''):
        async with self.database as db:
            await db.execute("""
                UPDATE Videos
                SET video_title = ?
                WHERE id = ?;
            """, (video_title, video_id))
            await db.commit()

    async def enrich_video(self, video_id, artist, title):
        async with self.database as db:
            await db.execute("""
                UPDATE Videos
                SET artist = ?, title = ?
                WHERE id = ?;
            """, (artist, title, video_id))
            await db.commit()

    async def get_videos(self):
        async with self.database as db:
            cur = await db.execute("""
                SELECT id, link, video_title, artist, title
                FROM Videos;
            """)
            result = await cur.fetchall()
        return result

    async def get_video_by_link(self, link):
        async with self.database as db:
            cur = await db.execute("""
                SELECT id
                FROM Videos
                WHERE link = ?;
            """, (link,))
            result = await cur.fetchall()
        if result:
            return result[0][0]

    async def has_it_been_posted(self, url, archive_channel):
        async with self.database as db:
            cur = await db.execute("""
                SELECT P.date_posted
                FROM Posted P
                JOIN Videos V on P.video_id = V.id
                WHERE V.link = ? AND P.archive_channel = ?;
            """, (url, archive_channel))
            result = await cur.fetchall()
        if result:
            return result[0][0]

    async def archive_video(self, video_id, archive_channel, source_channel, user_id, date_posted):
        async with self.database as db:
            cur = await db.execute("""
                INSERT INTO Posted(video_id, archive_channel, source_channel, user_id, date_posted)
                VALUES (?, ?, ?, ?, ?);
            """, (video_id, archive_channel, source_channel, user_id, date_posted))
            await db.commit()
            last_row = cur.lastrowid
        return last_row

    async def get_archived_video_by_id(self, posted_id):
        async with self.database as db:
            cur = await db.execute("""
                SELECT V.link, P.user_id, P.date_posted
                FROM Posted P
                JOIN Videos V on P.video_id = V.id 
                WHERE P.id = ?;
            """, (posted_id, ))
            result = await cur.fetchall()
        if result:
            return result[0]

    async def add_tag(self, video_id, tag):
        async with self.database as db:
            await db.execute("""
                INSERT INTO Tags(video_id, tag)
                VALUES (?, ?);             
            """, (video_id, tag))
            await db.commit()

    async def check_video_tags(self, video_id):
        async with self.database as db:
            cur = await db.execute("""
                SELECT tag
                FROM Tags
                WHERE video_id = ?;
            """, (video_id, ))
            result = await cur.fetchall()
        return result

    async def add_stat(self, channel_id, date, user_id, post_count):
        async with self.database as db:
            await db.execute("""
                INSERT INTO Statistics(channel_id, date, user_id, post_count)
                VALUES (?, ?, ?, ?);             
            """, (channel_id, date, user_id, post_count))
            await db.commit()

    async def wipe_stats(self, channel_id):
        async with self.database as db:
            await db.execute("""
                DELETE FROM Statistics
                WHERE channel_id = ?;             
            """, (channel_id, ))
            await db.commit()
            await db.execute("VACUUM")

    async def wipe_stats_current_day(self, channel_id, date):
        async with self.database as db:
            await db.execute("""
                DELETE FROM Statistics
                WHERE channel_id = ? and date = ?;             
            """, (channel_id, date))
            await db.commit()
            await db.execute("VACUUM")

    async def check_stat_pk(self, channel_id, date, user_id):
        async with self.database as db:
            cur = await db.execute("""
                SELECT date, user_id
                FROM Statistics
                WHERE channel_id = ? AND date = ? AND user_id = ?;
            """, (channel_id, date, user_id))
            result = await cur.fetchall()
        return result

    async def check_stat_lastdate(self, channel_id):
        async with self.database as db:
            cur = await db.execute("""
                SELECT MAX(date)
                FROM Statistics
                WHERE channel_id = ?;
            """, (channel_id, ))
            result = await cur.fetchall()
        if result:
            return result[0][0]

    async def check_stat_firstdate(self, channel_id):
        async with self.database as db:
            cur = await db.execute("""
                SELECT MIN(date)
                FROM Statistics
                WHERE channel_id = ?;
            """, (channel_id, ))
            result = await cur.fetchall()
        if result:
            return result[0][0]

    async def get_stats(self, channel_id,  date_from, date_to):
        async with self.database as db:
            cur = await db.execute("""
                SELECT user_id, sum(post_count)
                FROM Statistics
                WHERE channel_id = ? AND date between date(?) AND date(?)
                GROUP by user_id;
            """, (channel_id, date_from, date_to))
            result = await cur.fetchall()
        return result
