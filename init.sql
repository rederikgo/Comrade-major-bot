CREATE TABLE "Channels" (
	"id"	INTEGER NOT NULL UNIQUE,
	"is_watched"	TEXT NOT NULL,
	PRIMARY KEY("id")
)

CREATE TABLE "Congrats" (
	"id"	INTEGER NOT NULL UNIQUE,
	"text"	TEXT,
	PRIMARY KEY("id")
)

CREATE TABLE "Members" (
	"id"	INTEGER NOT NULL UNIQUE,
	"birthday"	TEXT,
	"last_reported"	INTEGER,
	PRIMARY KEY("id")
)

CREATE TABLE "Posted" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
	"video_id"	INTEGER NOT NULL,
	"archive_channel"	INTEGER NOT NULL,
	"source_channel"	INTEGER NOT NULL,
	"user_id"	INTEGER NOT NULL,
	"date_posted"	TEXT NOT NULL,
	FOREIGN KEY(video_id) REFERENCES Videos(id)
)

CREATE TABLE "Videos" (
	"id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
	"link"	TEXT NOT NULL,
	"artist"	TEXT,
	"title"	TEXT
)