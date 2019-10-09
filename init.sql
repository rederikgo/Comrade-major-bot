CREATE TABLE "Channels" (
	"id"	INTEGER NOT NULL UNIQUE,
	"is_watched"	TEXT NOT NULL,
	PRIMARY KEY("id")
);

CREATE TABLE "Members" (
	"id"	INTEGER NOT NULL UNIQUE,
	"birthday"	TEXT,
	"last_reported"	INTEGER,
	PRIMARY KEY("id")
);

CREATE TABLE "Congrats" (
	"id"	INTEGER NOT NULL UNIQUE,
	"text"	TEXT,
	PRIMARY KEY("id")
);