import sqlite3

# Databases filenames
from typing import Dict

USERDB = "users.db"
TIBIADB = "database.db"
LOOTDB = "utils/loot.db"

userDatabase = sqlite3.connect(USERDB)
tibiaDatabase = sqlite3.connect(TIBIADB)
lootDatabase = sqlite3.connect(LOOTDB)

DB_LASTVERSION = 11

# Dictionary of worlds tracked by nabbot, key:value = server_id:world
# Dictionary is populated from database
# A list version is created from the dictionary
tracked_worlds = {}
tracked_worlds_list = []

# Dictionaries of welcome messages per server
welcome_messages = {}

# Dictionaries of announce channels per server
announce_channels = {}


def init_database():
    """Initializes and/or updates the database to the current version"""

    # Database file is automatically created with connect, now we have to check if it has tables
    print("Checking database version...")
    try:
        c = userDatabase.cursor()
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
            c.execute("ALTER TABLE events ADD COLUMN status DEFAULT 4")
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
                      server_id TEXT,
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
        print("Updated database to version {0}".format(db_version))
        c.execute("UPDATE db_info SET value = ? WHERE key LIKE 'version'", (db_version,))

    finally:
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


def reload_worlds():
    """Refresh the world list from the database

    This is used to avoid reading the database everytime the world list is needed.
    A global variable holding the world list is loaded on startup and refreshed only when worlds are modified"""
    c = userDatabase.cursor()
    tibia_servers_dict_temp = {}
    try:
        c.execute("SELECT server_id, value FROM server_properties WHERE name = 'world' ORDER BY value ASC")
        result = c.fetchall()  # type: Dict
        del tracked_worlds_list[:]
        if len(result) > 0:
            for row in result:
                if row["value"] not in tracked_worlds_list:
                    tracked_worlds_list.append(row["value"])
                tibia_servers_dict_temp[int(row["server_id"])] = row["value"]

        tracked_worlds.clear()
        tracked_worlds.update(tibia_servers_dict_temp)
    finally:
        c.close()


def reload_welcome_messages():
    c = userDatabase.cursor()
    welcome_messages_temp = {}
    try:
        c.execute("SELECT server_id, value FROM server_properties WHERE name = 'welcome'")
        result = c.fetchall()  # type: Dict
        if len(result) > 0:
            for row in result:
                welcome_messages_temp[int(row["server_id"])] = row["value"]
        welcome_messages.clear()
        welcome_messages.update(welcome_messages_temp)
    finally:
        c.close()


def reload_announce_channels():
    c = userDatabase.cursor()
    announce_channels_temp = {}
    try:
        c.execute("SELECT server_id, value FROM server_properties WHERE name = 'announce_channel'")
        result = c.fetchall()  # type: Dict
        if len(result) > 0:
            for row in result:
                announce_channels_temp[int(row["server_id"])] = row["value"]
        announce_channels.clear()
        announce_channels.update(announce_channels_temp)
    finally:
        c.close()
