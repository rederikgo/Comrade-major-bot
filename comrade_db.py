import sqlite3
import os
import logging

class DatabaseError(Exception):
    def __init__(self, message):
        self.message = message


class DB:
    # Init and connect
    def __init__(self, db_path, init_script_path):
        self.logger = logging.getLogger()
        self.db_path = db_path
        self.init_script_path = init_script_path
        self._connect()

    # Test if the db file exists, try to connect and check if db is locked
    def _connect(self):
        if not os.path.isfile(self.db_path):
            self.logger.error('Cant find database file. Creating the new one')
            self._create_db()

        try:
            self.connection = sqlite3.connect(self.db_path)
            self.cursor = self.connection.cursor()
        except:
            self.logger.error('Cant connect to the database')
            raise DatabaseError('Cant connect to the database')

        try:
            self.connection.execute('VACUUM')
        except:
            self.logger.error('Database is locked')
            raise DatabaseError('Database is locked')

    # Create the new db
    def _create_db(self):
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.cursor = self.connection.cursor()
            self.init_script = open(self.init_script_path).read()
        except:
            self.logger.error('Cant open init script file')
            raise DatabaseError('Cant open init script file')

        self.cursor.executescript(self.init_script)
        self.connection.close()
        self.logger.info('New database created')

    def close(self):
        self.connection.close()

    # Add member
    def add_member(self, id):
        self.cursor.execute("""
            INSERT INTO Members (id, birthday)
            VALUES (?, NULL);
        """, (id,))
        self.connection.commit()

    def get_members(self):
        self.cursor.execute("""
            SELECT id
            FROM Members
        """)
        result = self.cursor.fetchall()
        return [i[0] for i in result]

    def update_birthday(self, member_id, birthday):
        self.cursor.execute("""
            UPDATE Members 
            SET birthday = ?
            WHERE id = ?
        """, (birthday, member_id))
        self.connection.commit()

    def get_birthdays(self):
        self.cursor.execute("""
            SELECT id, birthday, last_reported
            FROM Members
            WHERE birthday is not NULL
        """)
        return self.cursor.fetchall()

    def mark_congrated(self, member_id, last_reported):
        self.cursor.execute("""
            UPDATE Members 
            SET last_reported = ?
            WHERE id = ?
        """, (last_reported, member_id))
        self.connection.commit()

    def get_congrats(self):
        self.cursor.execute("""
            SELECT text
            FROM Congrats
        """)
        return self.cursor.fetchall()