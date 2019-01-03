import datetime
import json
import logging
import os
import sqlite3
import time
from typing import Dict

import asyncpg

from cogs.utils.database import get_affected_count

LATEST_VERSION = 1
SQL_DB_LASTVERSION = 22

log = logging.getLogger("nabbot")


async def check_database(pool: asyncpg.pool.Pool):
    log.info("Checking database version...")
    try:
        async with pool.acquire() as con:
            version = await get_version(con)
            if version <= 0:
                log.info("Schema is empty, creating tables.")
                await create_database(con)
                await set_version(con, 1)
            else:
                log.info("\tVersion 1 found.")
    except asyncpg.InsufficientPrivilegeError as e:
        log.error(f"PostgreSQL error: {e}")
        return False
    return True


async def drop_tables(pool: asyncpg.pool.Pool):
    async with pool.acquire() as con:
        log.debug("Dropping tables")
        await con.execute("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema()) LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;""")
        await con.execute("""
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT routine_name FROM information_schema.routines 
                              WHERE routine_type='FUNCTION' AND specific_schema='public') LOOP
                        EXECUTE 'DROP FUNCTION ' || quote_ident(r.routine_name) || ' CASCADE';
                    END LOOP;
                END $$;""")
        log.debug("Tables dropped")


async def create_database(con: asyncpg.connection.Connection):
    log.info("Creating tables...")
    for create_query in tables:
        await con.execute(create_query)
    log.info("Creating functions...")
    for f in functions:
        await con.execute(f)
    log.info("Creating triggers...")
    for trigger in triggers:
        await con.execute(trigger)
    log.info("Setting version to 1...")
    await set_version(con, LATEST_VERSION)


async def set_version(con: asyncpg.connection.Connection, version):
    await con.execute("""
        INSERT INTO global_property (key, value) VALUES ('db_version',$1)
        ON CONFLICT (key)
        DO
         UPDATE
           SET value = EXCLUDED.value;
    """, version)


async def get_version(con: asyncpg.connection.Connection):
    try:
        return await con.fetchval("SELECT value FROM global_property WHERE key = 'db_version'")
    except asyncpg.UndefinedTableError:
        return 0


tables = [
    """
    CREATE TABLE "character" (
        id serial NOT NULL,
        user_id bigint NOT NULL,
        name text NOT NULL,
        level smallint,
        world text,
        vocation text,
        guild text,
        sex text NOT NULL DEFAULT 'male',
        modified timestamptz DEFAULT now(),
        created timestamptz DEFAULT now(),
        PRIMARY KEY (id),
        UNIQUE(name)
    );
    """,
    """
    CREATE TABLE character_death (
        id serial NOT NULL,
        character_id integer NOT NULL,
        level smallint,
        date timestamptz,
        PRIMARY KEY (id),
        FOREIGN KEY (character_id) REFERENCES "character" (id),
        UNIQUE(character_id, date)
    );
    """,
    """
    CREATE TABLE character_death_killer (
        death_id integer NOT NULL,
        position smallint NOT NULL DEFAULT 0,
        name text NOT NULL,
        player boolean,
        FOREIGN KEY (death_id) REFERENCES character_death (id)
    );
    """,
    """
    CREATE TABLE character_death_assist (
        death_id integer NOT NULL,
        position smallint NOT NULL DEFAULT 0,
        name text NOT NULL,
        FOREIGN KEY (death_id) REFERENCES character_death (id)
    );
    """,
    """
    CREATE TABLE character_levelup (
        id serial NOT NULL,
        character_id integer NOT NULL,
        level smallint,
        date timestamptz DEFAULT now(),
        PRIMARY KEY (id),
        FOREIGN KEY (character_id) REFERENCES "character" (id)
    );
    """,
    """
    CREATE TABLE character_history (
        character_id integer,
        change_type text NOT NULL,
        before jsonb,
        after jsonb,
        user_id bigint,
        date timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY (character_id) REFERENCES "character" (id)
    );
    """,
    """
    CREATE TABLE event (
        id serial NOT NULL,
        user_id bigint NOT NULL,
        server_id bigint NOT NULL,
        name text NOT NULL,
        description text,
        start timestamptz NOT NULL,
        active boolean NOT NULL DEFAULT true,
        reminder smallint NOT NULL DEFAULT 0,
        joinable boolean NOT NULL DEFAULT true,
        slots smallint NOT NULL DEFAULT 0,
        modified timestamptz NOT NULL DEFAULT now(),
        created timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (id)
    );
    """,
    """
    CREATE TABLE event_participant (
        event_id integer NOT NULL,
        character_id integer NOT NULL,
        FOREIGN KEY (event_id) REFERENCES event (id),
        FOREIGN KEY (character_id) REFERENCES "character" (id),
        UNIQUE(event_id, character_id)
    );
    """,
    """
    CREATE TABLE event_subscriber (
        event_id integer NOT NULL,
        user_id bigint NOT NULL,
        FOREIGN KEY (event_id) REFERENCES event (id),
        UNIQUE(event_id, user_id)
    );
    """,
    """
    CREATE TABLE highscores (
        world text NOT NULL,
        category text NOT NULL,
        last_scan timestamptz DEFAULT now(),
        PRIMARY KEY (world, category)
    );
    """,
    """
    CREATE TABLE highscores_entry (
        rank text,
        category text,
        world text,
        name text,
        vocation text,
        value bigint,
        PRIMARY KEY(rank,category, world)
    );""",
    """
    CREATE TABLE role_auto (
        server_id bigint NOT NULL,
        role_id bigint NOT NULL,
        rule text NOT NULL,
        PRIMARY KEY (server_id, role_id, rule)
    );
    """,
    """
    CREATE TABLE role_joinable (
        server_id bigint NOT NULL,
        role_id bigint NOT NULL,
        PRIMARY KEY (server_id, role_id)
    );
    """,
    """
    CREATE TABLE server_property (
        server_id bigint NOT NULL,
        key text NOT NULL,
        value jsonb,
        PRIMARY KEY (server_id, key)
    );
    """,
    """
    CREATE TABLE server_prefixes(
        server_id bigint NOT NULL,
        prefixes text[] NOT NULL,
        PRIMARY KEY (server_id)
    );
    """,
    """
    CREATE TABLE global_property (
        key text NOT NULL,
        value jsonb,
        PRIMARY KEY (key)
    );
    """,
    """
    CREATE TABLE watchlist(
        server_id bigint NOT NULL,
        channel_id bigint NOT NULL,
        message_id bigint,
        show_count boolean DEFAULT true,
        user_id bigint NOT NULL,
        created timestamptz DEFAULT now(),
        PRIMARY KEY(channel_id)
    );
    """,
    """
    CREATE TABLE watchlist_entry (
        channel_id bigint NOT NULL,
        name text NOT NULL,
        is_guild bool DEFAULT FALSE,
        reason text,
        user_id bigint NOT NULL,
        created timestamptz DEFAULT now(),
        FOREIGN KEY (channel_id) REFERENCES watchlist(channel_id) ON DELETE CASCADE,
        UNIQUE(channel_id, name, is_guild)
    )
    """,
    """
    CREATE TABLE command (
        server_id bigint,
        channel_id bigint NOT NULL,
        user_id bigint NOT NULL,
        date timestamptz NOT NULL DEFAULT now(),
        prefix text NOT NULL,
        command text NOT NULL
    );
    """,
    """
    CREATE TABLE channel_ignored (
        server_id bigint NOT NULL,
        channel_id bigint NOT NULL,
        PRIMARY KEY(server_id, channel_id)
    );
    """,
    """
    CREATE TABLE user_server (
        user_id bigint NOT NULL,
        server_id bigint NOT NULL,
        PRIMARY KEY(user_id, server_id)
    );
    """,
    """
    CREATE TABLE server_history (
        server_id bigint NOT NULL,
        event_type text NOT NULL,
        server_count int NOT NULL,
        date timestamptz default now()
    );""",
    """
    CREATE TABLE server_timezone (
        server_id bigint NOT NULL,
        zone text NOT NULL,
        name text NOT NULL,
        created timestamptz DEFAULT now(),
        PRIMARY KEY(server_id, zone)
    );""",
    """
    CREATE TABLE timer (
        id serial NOT NULL,
        name text NOT NULL,
        user_id bigint NOT NULL,
        type smallint NOT NULL DEFAULT 0,
        extra jsonb,
        created timestamptz NOT NULL DEFAULT now(),
        expires timestamptz NOT NULL
    );"""
]
functions = [
    """
    CREATE FUNCTION update_modified_column() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
    BEGIN
        NEW.modified = now();
        RETURN NEW;
    END;
    $$;
    """
]
triggers = [
    """
    CREATE TRIGGER update_character_modified
    BEFORE UPDATE ON "character"
    FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
    """,
    """
    CREATE TRIGGER update_event_modified
    BEFORE UPDATE ON event
    FOR EACH ROW EXECUTE PROCEDURE update_modified_column();
    """
]


# Legacy SQlite migration
# This may be removed in later versions or kept separate
async def import_legacy_db(pool: asyncpg.pool.Pool, path):
    if not os.path.isfile(path):
        log.error("Database file doesn't exist or path is invalid.")
        return
    legacy_conn = sqlite3.connect(path)
    log.info("Checking old database...")
    if not check_sql_database(legacy_conn):
        log.error("Can't import sqlite database.")
        return
    log.info("Importing SQLite rows")
    start = time.time()
    c = legacy_conn.cursor()
    clean_up_old_db(c)

    # Dictionary that maps SQL IDs to their PSQL ID
    new_ids = {}
    async with pool.acquire() as conn:
        await import_characters(conn, c, new_ids)
        await import_server_properties(conn, c)
        await import_roles(conn, c)
        await import_events(conn, c, new_ids)
        await import_ignored_channels(conn, c)
    log.info(f"Importing finished in {time.time()-start:,.2f} seconds.")


async def import_characters(conn: asyncpg.Connection, c: sqlite3.Cursor, new_ids: Dict[int, int]):
    log.info("Importing characters...")
    # Dictionary that maps character names to their SQL ID
    old_ids = {}
    chars = []
    log.debug("Gathering character records from sqlite...")
    c.execute("""SELECT id, user_id, name, level, vocation, world, guild FROM chars ORDER By id ASC""")
    rows = c.fetchall()
    for char_id, user_id, name, level, vocation, world, guild in rows:
        chars.append((user_id, name, level, vocation, world, guild))
        old_ids[name] = char_id
    log.debug(f"Collected {len(chars):,} records from old database.")
    log.info("Copying records to character table")
    res = await conn.copy_records_to_table("character", records=chars,
                                           columns=["user_id", "name", "level", "vocation", "world", "guild"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")
    new_chars = await conn.fetch('SELECT id, name FROM "character"')
    log.debug("Generating old id to new id mapping...")
    new_ids.clear()
    for new_id, name in new_chars:
        new_ids[old_ids[name]] = new_id
    log.debug("Old id to new id mapping generated.")

    ids = 1
    deaths = []
    killers = []
    log.debug("Gathering death records from sqlite...")
    c.execute("""SELECT char_id, level, killer, date, byplayer FROM char_deaths ORDER BY date ASC""")
    rows = c.fetchall()
    # This doesn't seem very safe to do, maybe it would be better to import deaths the old way
    for char_id, level, killer, date, byplayer in rows:
        byplayer = byplayer == 1
        date = datetime.datetime.utcfromtimestamp(date)
        deaths.append((new_ids[char_id], level, date))
        killers.append((ids, killer, byplayer))
        ids += 1
    log.debug(f"Collected {len(deaths):,} records from old database.")
    log.info("Copying records to deaths table.")
    res = await conn.copy_records_to_table("character_death", records=deaths, columns=["character_id", "level", "date"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")

    log.info("Copying records to death killers table.")
    res = await conn.copy_records_to_table("character_death_killer", records=killers,
                                           columns=["death_id", "name", "player"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")

    log.debug("Gathering level up records from sqlite...")
    c.execute("""SELECT char_id, level, date FROM char_levelups ORDER BY date ASC""")
    rows = c.fetchall()
    levelups = []
    for char_id, level, date in rows:
        date = datetime.datetime.utcfromtimestamp(date)
        levelups.append((new_ids[char_id], level, date))
    log.debug(f"Collected {len(levelups):,} records from old database.")
    log.info("Copying records to level ups table.")
    res = await conn.copy_records_to_table("character_levelup", records=levelups,
                                           columns=["character_id", "level", "date"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")
    log.info("Finished importing characters.")


async def import_server_properties(conn: asyncpg.Connection, c: sqlite3.Cursor):
    properties = []
    prefixes = []
    times = []
    log.debug("Gathering server property records from sqlite...")
    log.info("Importing server properties...")
    c.execute("SELECT server_id, name, value FROM server_properties")
    rows = c.fetchall()
    for server_id, key, value in rows:
        server_id = int(server_id)
        if key == "prefixes":
            prefixes.append((server_id, json.loads(value)))
            continue
        if key == "times":
            value = json.loads(value)
            for entry in value:
                times.append((server_id, entry["timezone"], entry["name"]))
            continue
        elif key in ["events_channel", "levels_channel", "watched_channel", "news_channel", "welcome_channel",
                     "ask_channel", "watched_message"]:
            value = int(value)
        elif key == "commandsonly":
            value = bool(value)
        properties.append((server_id, key, value))
    log.debug(f"Collected {len(properties):,} properties, {len(times):,} timezones and {len(prefixes):,} prefixes"
              f" from old database.")
    log.info("Copying records to server property table")
    res = await conn.copy_records_to_table("server_property", records=properties, columns=["server_id", "key", "value"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")

    log.info("Copying records to server prefixes table")
    res = await conn.copy_records_to_table("server_prefixes", records=prefixes, columns=["server_id", "prefixes"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")

    log.info("Copying records to server timezone table")
    res = await conn.copy_records_to_table("server_timezone", records=times, columns=["server_id", "zone", "name"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")
    log.info("Finished importing server properties.")


async def import_events(conn: asyncpg.Connection, c: sqlite3.Cursor, new_char_ids: Dict[int, int]):
    log.info("Importing events...")
    events = []
    subscribers = []
    participants = []
    new_event_ids = {}
    i = 1
    log.debug("Gathering event records from sqlite...")
    c.execute("SELECT id, creator, name, start, active, status, description, server, joinable, slots FROM events")
    rows = c.fetchall()
    for event_id, creator, name, start, active, status, description, server, joinable, slots in rows:
        new_event_ids[event_id] = i
        start = datetime.datetime.utcfromtimestamp(start)
        active = bool(active)
        joinable = bool(joinable)
        status = 4 - status
        events.append((creator, name, start, active, description, server, joinable, slots, status))
        i += 1
    log.debug(f"Collected {len(events):,} records from old database.")
    log.info("Copying records to events table")
    res = await conn.copy_records_to_table("event", records=events,
                                           columns=["user_id", "name", "start", "active", "description", "server_id",
                                                    "joinable", "slots", "reminder"])
    log.debug(f"Copied {get_affected_count(res):,} records successfully.")

    log.debug("Gathering event subscribers from sqlite...")
    c.execute("SELECT event_id, user_id FROM event_subscribers")
    rows = c.fetchall()
    for event_id, user_id in rows:
        subscribers.append((new_event_ids[event_id], user_id))
    log.debug(f"Collected {len(subscribers):,} records from old database.")

    log.info("Copying records to event subscribers table")
    res = await conn.copy_records_to_table("event_subscriber", records=subscribers, columns=["event_id", "user_id"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")

    log.debug("Gathering event participants from sqlite...")
    c.execute("SELECT event_id, char_id FROM event_participants")
    rows = c.fetchall()
    for event_id, char_id in rows:
        participants.append((new_event_ids[event_id], new_char_ids[char_id]))
    log.debug(f"Collected {len(participants):,} records from old database.")

    log.info("Copying records to event participants table")
    res = await conn.copy_records_to_table("event_participant", records=participants,
                                           columns=["event_id", "character_id"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")
    log.info("Finished importing events.")


async def import_roles(conn: asyncpg.Connection, c: sqlite3.Cursor):
    log.info("Importing roles...")
    auto_roles = []
    joinable_roles = []
    log.debug("Gathering auto roles from sqlite...")
    c.execute("SELECT server_id, role_id, guild FROM auto_roles")
    rows = c.fetchall()
    for server_id, role_id, guild in rows:
        auto_roles.append((server_id, role_id, guild))
    log.debug(f"Collected {len(auto_roles):,} records from old database.")
    log.info("Copying records to auto roles table")
    res = await conn.copy_records_to_table("role_auto", records=auto_roles, columns=["server_id", "role_id", "rule"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")

    log.debug("Gathering joinable roles from sqlite...")
    c.execute("SELECT server_id, role_id FROM joinable_roles")
    rows = c.fetchall()
    for server_id, role_id in rows:
        joinable_roles.append((server_id, role_id))
    log.debug(f"Collected {len(joinable_roles):,} records from old database.")
    log.info("Copying records to joinable roles table")
    res = await conn.copy_records_to_table("role_joinable", records=joinable_roles, columns=["server_id", "role_id"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")
    log.info("Finished importing roles.")


async def import_ignored_channels(conn: asyncpg.Connection, c: sqlite3.Cursor):
    log.info("Importing ignored channels...")
    channels = []
    log.debug("Gathering ignored channels from sqlite...")
    c.execute("SELECT server_id, channel_id FROM ignored_channels")
    rows = c.fetchall()
    for server_id, channel_id in rows:
        channels.append((server_id, channel_id))
    log.debug(f"Collected {len(channels):,} records from old database.")
    log.info("Copying records to ignored channels table")
    res = await conn.copy_records_to_table("channel_ignored", records=channels, columns=["server_id", "channel_id"])
    log.info(f"Copied {get_affected_count(res):,} records successfully.")
    log.info("Finished importing channels.")


def check_sql_database(conn: sqlite3.Connection):
    """Initializes and/or updates the database to the current version"""
    # Database file is automatically created with connect, now we have to check if it has tables
    log.info("Checking sqlite database version...")
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type = 'table'")
        result = c.fetchone()
        # Database is empty
        if result[0] == 0:
            log.warning("\tDatabase is empty.")
            return False
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
            log.warning("\tNo version found, version 1 assumed")
        else:
            c.execute("SELECT value FROM db_info WHERE key LIKE 'version'")
            db_version = int(c.fetchone()[0])
            log.info("\tVersion {0}".format(db_version))
        if db_version == SQL_DB_LASTVERSION:
            log.info("\tDatabase is up to date.")
            return True
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
        if db_version == 20:
            # Joinable ranks
            c.execute("""CREATE TABLE joinable_roles(
                server_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL
            );""")
            db_version += 1
        if db_version == 21:
            # Autoroles
            c.execute("""CREATE TABLE auto_roles(
                server_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                guild TEXT NOT NULL
            );""")
            db_version += 1
        log.info("\tUpdated database to version {0}".format(db_version))
        c.execute("UPDATE db_info SET value = ? WHERE key LIKE 'version'", (db_version,))
        return True
    except Exception as e:
        log.error(f"\tError reading sqlite database: {e}")
        return False
    finally:
        c.close()
        conn.commit()


def clean_up_old_db(c: sqlite3.Cursor):
    log.info("Cleaning up old database")
    # Clean up characters
    c.execute("SELECT min(id), name as id FROM chars GROUP BY name HAVING COUNT(*) > 1")
    rows = c.fetchall()
    log.debug("Removing duplicate characters...")
    for char_id, name in rows:
        c.execute("""UPDATE char_levelups SET char_id = ?
                     WHERE char_id IN 
                        (SELECT id FROM chars WHERE name = ? ORDER BY id LIMIT 1)""", (char_id, name))
        c.execute("""UPDATE char_deaths SET char_id = ?
                     WHERE char_id IN 
                        (SELECT id FROM chars WHERE name = ? ORDER BY id LIMIT 1)""", (char_id, name))
        c.execute("""UPDATE event_participants SET char_id = ?
                     WHERE char_id IN 
                        (SELECT id FROM chars WHERE name = ? ORDER BY id LIMIT 1)""", (char_id, name))
        c.execute("DELETE FROM chars WHERE name = ? AND id != ?", (name, char_id))
    log.info(f"Removed {len(rows):,} duplicate characters")

    # Clean up deaths
    log.debug("Removing duplicate deaths...")
    c.execute("""DELETE FROM char_deaths
                 WHERE rowid NOT IN 
                    (SELECT min(rowid) FROM char_deaths GROUP BY char_id, date)""")
    log.info(f"Removed {c.rowcount:,} duplicate deaths")

    log.debug("Removing orphaned  deaths...")
    c.execute("""DELETE FROM char_deaths
                     WHERE char_id NOT IN 
                        (SELECT id FROM chars)""")
    log.info(f"Removed {c.rowcount:,} orphaned deaths")

    # Clean up level ups
    log.debug("Removing duplicate level ups...")
    c.execute("""SELECT min(rowid), min(date), max(date)-min(date) as diff, count() as c, char_id, level
                 FROM char_levelups
                 GROUP BY char_id, level HAVING c > 1 AND diff < 30""")
    rows = c.fetchall()
    count = 0
    for rowid, date, diff, _count, char_id, level in rows:
        c.execute("""DELETE FROM char_levelups
                     WHERE rowid != ? AND char_id = ? AND level = ? AND date-30 < ? AND date+30 > ?""",
                  (rowid, char_id, level, date, date))
        count += c.rowcount
    log.info(f"Removed {count:,} duplicate level ups")

    log.debug("Removing orphaned level ups...")
    c.execute("""DELETE FROM char_levelups
                     WHERE char_id NOT IN 
                        (SELECT id FROM chars)""")
    log.info(f"Removed {c.rowcount:,} orphaned levelups")

    # Clean up event participants
    log.debug("Removing duplicate event participants...")
    c.execute("""DELETE FROM event_participants
                     WHERE rowid NOT IN 
                        (SELECT min(rowid) FROM event_participants GROUP BY event_id, char_id)""")
    log.info(f"Removed {c.rowcount:,} duplicate event participants")

    log.debug("Removing orphaned event participants...")
    c.execute("""DELETE FROM event_participants
                         WHERE char_id NOT IN 
                            (SELECT id FROM chars)""")
    log.info(f"Removed {c.rowcount:,} orphaned event participants")

    # Clean up event subscribers
    log.debug("Removing duplicate event subscribers...")
    c.execute("""DELETE FROM event_subscribers
                     WHERE rowid NOT IN 
                        (SELECT min(rowid) FROM event_subscribers GROUP BY event_id, user_id)""")
    log.info(f"Removed {c.rowcount:,} duplicate event subscribers")

    # Remove server properties
    log.debug("Removing duplicate server properties...")
    c.execute("""DELETE FROM server_properties
                         WHERE rowid NOT IN 
                            (SELECT min(rowid) FROM server_properties GROUP BY server_id, name)""")
    log.info(f"Removed {c.rowcount:,} duplicate server properties")
