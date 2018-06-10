import os
import shutil
import sqlite3
from contextlib import closing
from typing import Dict

# Databases filenames
USERDB = "data/users.db"
TIBIADB = "data/tibia_database.db"
LOOTDB = "data/loot.db"

userDatabase = sqlite3.connect(USERDB)
tibiaDatabase = sqlite3.connect(TIBIADB)

if os.path.isfile(LOOTDB):
    lootDatabase = sqlite3.connect(LOOTDB)
else:
    shutil.copyfile("data/loot_template.db", LOOTDB)
    lootDatabase = sqlite3.connect(LOOTDB)

DB_LASTVERSION = 20


def init_database():
    """Initializes and/or updates the database to the current version"""
    # Database file is automatically created with connect, now we have to check if it has tables
    print("Checking database version...")
    c = userDatabase.cursor()
    try:
        c.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type = 'table'")
        result = c.fetchone()
        # Database is empty
        if result is None or result["count"] == 0:
            c.execute("""CREATE TABLE discord_users (
                      id INTEGER NOT NULL,
                      weight INTEGER DEFAULT 5,
                      PRIMARY KEY(id)
                      )""")
            c.execute("""CREATE TABLE chars (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      name TEXT,
                      last_level INTEGER DEFAULT -1,
                      last_death_time TEXT
                      )""")
            c.execute("""CREATE TABLE char_levelups (
                      char_id INTEGER,
                      level INTEGER,
                      date INTEGER
                      )""")
        c.execute("SELECT tbl_name FROM sqlite_master WHERE type = 'table' AND name LIKE 'db_info'")
        result = c.fetchone()
        # If there's no version value, version 1 is assumed
        if result is None:
            c.execute("""CREATE TABLE db_info (
                      key TEXT,
                      value TEXT
                      )""")
            c.execute("INSERT INTO db_info(key,value) VALUES('version','1')")
            db_version = 1
            print("No version found, version 1 assumed")
        else:
            c.execute("SELECT value FROM db_info WHERE key LIKE 'version'")
            db_version = int(c.fetchone()["value"])
            print("Version {0}".format(db_version))
        if db_version == DB_LASTVERSION:
            print("Database is up to date.")
            return
        # Code to patch database changes
        if db_version == 1:
            # Added 'vocation' column to chars table, to display vocations when /check'ing users among other things.
            # Changed how the last_level flagging system works a little, a character of unknown level is now flagged as
            # level 0 instead of -1, negative levels are now used to flag of characters never seen online before.
            c.execute("ALTER TABLE chars ADD vocation TEXT")
            c.execute("UPDATE chars SET last_level = 0 WHERE last_level = -1")
            db_version += 1
        if db_version == 2:
            # Added 'events' table
            c.execute("""CREATE TABLE events (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      creator INTEGER,
                      name TEXT,
                      start INTEGER,
                      duration INTEGER,
                      active INTEGER DEFAULT 1
                      )""")
            db_version += 1
        if db_version == 3:
            # Added 'char_deaths' table
            # Added 'status column' to events (for event announces)
            c.execute("""CREATE TABLE char_deaths (
                      char_id INTEGER,
                      level INTEGER,
                      killer TEXT,
                      date INTEGER,
                      byplayer BOOLEAN
                      )""")
            c.execute("ALTER TABLE events ADD COLUMN status INTEGER DEFAULT 4")
            db_version += 1
        if db_version == 4:
            # Added 'name' column to 'discord_users' table to save their names for external use
            c.execute("ALTER TABLE discord_users ADD name TEXT")
            db_version += 1
        if db_version == 5:
            # Added 'world' column to 'chars', renamed 'discord_users' to 'users', created table 'user_servers'
            c.execute("ALTER TABLE chars ADD world TEXT")
            c.execute("ALTER TABLE discord_users RENAME TO users")
            c.execute("""CREATE TABLE user_servers (
                      id INTEGER,
                      server INTEGER,
                      PRIMARY KEY(id)
                      );""")
            db_version += 1
        if db_version == 6:
            # Added 'description', 'server' column to 'events', created table 'events_subscribers'
            c.execute("ALTER TABLE events ADD description TEXT")
            c.execute("ALTER TABLE events ADD server INTEGER")
            c.execute("""CREATE TABLE event_subscribers (
                      event_id INTEGER,
                      user_id INTEGER
                      );""")
            db_version += 1
        if db_version == 7:
            # Created 'server_properties' table
            c.execute("""CREATE TABLE server_properties (
                      server_id INTEGER,
                      name TEXT,
                      value TEXT
                      );""")
            db_version += 1
        if db_version == 8:
            # Added 'achievements', 'axe', 'club', 'distance', 'fishing', 'fist', 'loyalty', 'magic', 'shielding',
            # 'sword', 'achievements_rank', 'axe_rank', 'club_rank', 'distance_rank', 'fishing_rank', 'fist_rank',
            # 'loyalty_rank', 'magic_rank', 'shielding_rank', 'sword_rank',  columns to 'chars'
            c.execute("ALTER TABLE chars ADD achievements INTEGER")
            c.execute("ALTER TABLE chars ADD axe INTEGER")
            c.execute("ALTER TABLE chars ADD club INTEGER")
            c.execute("ALTER TABLE chars ADD distance INTEGER")
            c.execute("ALTER TABLE chars ADD fishing INTEGER")
            c.execute("ALTER TABLE chars ADD fist INTEGER")
            c.execute("ALTER TABLE chars ADD loyalty INTEGER")
            c.execute("ALTER TABLE chars ADD magic INTEGER")
            c.execute("ALTER TABLE chars ADD shielding INTEGER")
            c.execute("ALTER TABLE chars ADD sword INTEGER")
            c.execute("ALTER TABLE chars ADD achievements_rank INTEGER")
            c.execute("ALTER TABLE chars ADD axe_rank INTEGER")
            c.execute("ALTER TABLE chars ADD club_rank INTEGER")
            c.execute("ALTER TABLE chars ADD distance_rank INTEGER")
            c.execute("ALTER TABLE chars ADD fishing_rank INTEGER")
            c.execute("ALTER TABLE chars ADD fist_rank INTEGER")
            c.execute("ALTER TABLE chars ADD loyalty_rank INTEGER")
            c.execute("ALTER TABLE chars ADD magic_rank INTEGER")
            c.execute("ALTER TABLE chars ADD shielding_rank INTEGER")
            c.execute("ALTER TABLE chars ADD sword_rank INTEGER")
            db_version += 1
        if db_version == 9:
            # Added 'magic_ek', 'magic_rp', 'magic_ek_rank', 'magic_rp_rank' columns to 'chars'
            c.execute("ALTER TABLE chars ADD magic_ek INTEGER")
            c.execute("ALTER TABLE chars ADD magic_rp INTEGER")
            c.execute("ALTER TABLE chars ADD magic_ek_rank INTEGER")
            c.execute("ALTER TABLE chars ADD magic_rp_rank INTEGER")
            db_version += 1
        if db_version == 10:
            # Added 'guild' column to 'chars'
            c.execute("ALTER TABLE chars ADD guild TEXT")
            db_version += 1
        if db_version == 11:
            # Added 'deleted' column to 'chars'
            c.execute("ALTER TABLE chars ADD deleted INTEGER DEFAULT 0")
            db_version += 1
        if db_version == 12:
            # Added 'hunted' table
            c.execute("""CREATE TABLE hunted_list (
                name TEXT,
                is_guild BOOLEAN DEFAULT 0,
                server_id INTEGER
            );""")
            db_version += 1
        if db_version == 13:
            # Renamed table hunted_list to watched_list and related server properties
            c.execute("ALTER TABLE hunted_list RENAME TO watched_list")
            c.execute("UPDATE server_properties SET name = 'watched_channel' WHERE name LIKE 'hunted_channel'")
            c.execute("UPDATE server_properties SET name = 'watched_message' WHERE name LIKE 'hunted_message'")
            db_version += 1
        if db_version == 14:
            c.execute("""CREATE TABLE ignored_channels (
                server_id INTEGER,
                channel_id INTEGER
            );""")
            db_version += 1
        if db_version == 15:
            c.execute("""CREATE TABLE highscores (
                rank INTEGER,
                category TEXT,
                world TEXT,
                name TEXT,
                vocation TEXT,
                value INTEGER
            );""")
            c.execute("""CREATE TABLE highscores_times (
                world TEXT,
                last_scan INTEGER
            );""")
            db_version += 1
        if db_version == 16:
            c.execute("ALTER table highscores_times ADD category TEXT")
            db_version += 1
        if db_version == 17:
            # Cleaning up unused columns and renaming columns
            c.execute("""CREATE TABLE chars_temp(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                level INTEGER DEFAULT -1,
                vocation TEXT,
                world TEXT,
                guild TEXT
            );""")
            c.execute("INSERT INTO chars_temp SELECT id, user_id, name, last_level, vocation, world, guild FROM chars")
            c.execute("DROP TABLE chars")
            c.execute("ALTER table chars_temp RENAME TO chars")
            c.execute("DROP TABLE IF EXISTS user_servers")
            c.execute("""CREATE TABLE users_temp(
                id INTEGER NOT NULL,
                name TEXT,
                PRIMARY KEY(id)
            );""")
            c.execute("INSERT INTO users_temp SELECT id, name FROM users")
            c.execute("DROP TABLE users")
            c.execute("ALTER table users_temp RENAME TO users")
            db_version += 1
        if db_version == 18:
            # Adding event participants
            c.execute("ALTER TABLE events ADD joinable INTEGER DEFAULT 1")
            c.execute("ALTER TABLE events ADD slots INTEGER DEFAULT 0")
            c.execute("""CREATE TABLE event_participants(
                event_id INTEGER NOT NULL,
                char_id INTEGER NOT NULL
            );""")
            db_version += 1
        if db_version == 19:
            # Adding reason and author to watched-list
            c.execute("ALTER TABLE watched_list ADD reason TEXT")
            c.execute("ALTER TABLE watched_list ADD author INTEGER")
            c.execute("ALTER TABLE watched_list ADD added INTEGER")
            db_version += 1
        print("Updated database to version {0}".format(db_version))
        c.execute("UPDATE db_info SET value = ? WHERE key LIKE 'version'", (db_version,))
    finally:
        c.close()
        userDatabase.commit()


def dict_factory(cursor, row):
    """Makes values returned by cursor fetch functions return a dictionary instead of a tuple.

    To implement this, the connection's row_factory method must be replaced by this one."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


userDatabase.row_factory = dict_factory
tibiaDatabase.row_factory = dict_factory
lootDatabase.row_factory = dict_factory


def get_server_property(guild_id: int, key: str, default=None, is_int=None):
    """Returns a guild's property

    :param key: The key of the property to search for
    :param guild_id: The discord server's id
    :param default: A default value to return in case the key is not found
    :param is_int: If true, the return value will be casted to int
    :return: the property's value or the default value passed
    """
    with closing(userDatabase.cursor()) as c:
        c.execute("SELECT value FROM server_properties WHERE name = ? and server_id = ?", (key, guild_id))
        result = c.fetchone()  # type: Dict[str]
        if is_int:
            try:
                return int(result["value"]) if result is not None else default
            except ValueError:
                return default
        return result["value"] if result is not None else default


def set_server_property(guild_id: int, key: str, value) -> None:
    """Edits a server property

    :param key: The name of the property to change
    :param guild_id: The discord server's id
    :param value: The new value for the property, if None, it will be deleted
    """
    with userDatabase as con:
        con.execute("DELETE FROM server_properties WHERE server_id = ? AND name = ?", (guild_id, key))
        if value is None:
            return
        con.execute("INSERT INTO server_properties(name, server_id, value) VALUES(?,?,?)", (key, guild_id, value))
