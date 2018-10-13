import datetime
import json
import os
import sqlite3
from operator import itemgetter

import asyncpg
import click

LATEST_VERSION = 1
SQL_DB_LASTVERSION = 22


def _progressbar(*args, **kwargs):
    return click.progressbar(*args, **kwargs, fill_char="█", empty_char=" ", show_pos=True)


async def check_database(pool: asyncpg.pool.Pool):
    print("Checking database version...")
    async with pool.acquire() as con:
        version = await get_version(con)
        if version <= 0:
            print("Schema is empty, creating tables.")
            await create_database(con)
            await set_version(con, 1)
        else:
            print("\tVersion 1 found.")


async def create_database(con: asyncpg.connection.Connection):
    print("Creating tables...")
    for create_query in tables:
        await con.execute(create_query)
    print("Creating functions...")
    for f in functions:
        await con.execute(f)
    print("Creating triggers...")
    for trigger in triggers:
        await con.execute(trigger)
    print("Setting version to 1...")
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
    );""",
    """
    CREATE TABLE highscores (
        world text NOT NULL,
        category text NOT NULL,
        last_scan timestamptz DEFAULT now(),
        PRIMARY KEY (world, category)
    );""",
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
    CREATE TABLE watchlist_entry (
        name text NOT NULL,
        server_id bigint NOT NULL,
        is_guild bool DEFAULT FALSE,
        reason text,
        user_id bigint,
        created timestamptz DEFAULT now(),
        PRIMARY KEY(name, server_id, is_guild)
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
    )
    """,
    """
    CREATE TABLE channel_ignored (
        server_id bigint NOT NULL,
        channel_id bigint NOT NULL,
        PRIMARY KEY(server_id, channel_id)
    )
    """
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
        print("Database file doesn't exist or path is invalid.")
        return
    legacy_conn = sqlite3.connect(path)
    print("Checking old database...")
    check_sql_database(legacy_conn)

    c = legacy_conn.cursor()
    async with pool.acquire() as conn:
        await import_characters(conn, c)
        await import_server_properties(conn, c)
        await import_roles(conn, c)
        await import_events(conn, c)
        await import_ignored_channels(conn, c)
        await import_watch_list(conn, c)


async def import_characters(conn: asyncpg.Connection, c: sqlite3.Cursor):
    c.execute("""SELECT id, user_id, name, level, vocation, world, guild FROM chars ORDER By id ASC""")
    rows = c.fetchall()
    levelups = []
    deaths = []
    with _progressbar(rows, label="Migrating characters") as bar:
        for row in bar:
            old_id, *char = row
            # Try to insert character, if it exist return existing character's ID
            char_id = await conn.fetchval("""
                    INSERT INTO "character" (user_id, name, level, vocation, world, guild)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id""", *char)
            c.execute("SELECT ?, level, date FROM char_levelups WHERE char_id = ? ORDER BY date ASC",
                      (char_id, old_id))
            levelups.extend(c.fetchall())
            c.execute("SELECT ?, level, date, killer, byplayer FROM char_deaths WHERE char_id = ?",
                      (char_id, old_id))
            deaths.extend(c.fetchall())
    deaths = sorted(deaths, key=itemgetter(2))
    skipped_deaths = 0
    with _progressbar(deaths, label="Migrating deaths") as bar:
        for death in bar:
            char_id, level, date, killer, byplayer = death
            byplayer = byplayer == 1
            date = datetime.datetime.utcfromtimestamp(date)
            # If there's another death at the exact same timestamp by the same character, we ignore it
            exists = await conn.fetchrow("""SELECT id FROM character_death
                                                WHERE date = $1 AND character_id = $2""", date, char_id)
            if exists:
                skipped_deaths += 1
                continue
            death_id = await conn.fetchval("""INSERT INTO character_death(character_id, level, date)
                                              VALUES ($1, $2, $3) RETURNING id""", char_id, level, date)
            await conn.execute("""INSERT INTO character_death_killer(death_id, name, player)
                                  VALUES ($1, $2, $3)""", death_id, killer, byplayer)
    if skipped_deaths:
        print(f"Skipped {skipped_deaths:,} duplicate deaths.")
    levelups = sorted(levelups, key=itemgetter(2))
    skipped_levelups = 0
    with _progressbar(levelups, label="Migrating level ups") as bar:
        for levelup in bar:
            char_id, level, date = levelup
            date = datetime.datetime.utcfromtimestamp(date)
            # If there's another levelup within a 15 seconds margin, we ignore it
            exists = await conn.fetchrow("""SELECT id FROM character_levelup
                                                WHERE character_id = $1 AND
                                                GREATEST($2-date,date-$2) <= interval '15' second""", char_id, date)
            if exists:
                skipped_levelups += 1
                continue
            await conn.execute("""INSERT INTO character_levelup(character_id, level, date)
                                      VALUES ($1, $2, $3)""", char_id, level, date)
    if skipped_levelups:
        print(f"Skipped {skipped_levelups:,} duplicate level ups.")


async def import_server_properties(conn: asyncpg.Connection, c: sqlite3.Cursor):
    c.execute("SELECT server_id, name, value FROM server_properties")
    rows = c.fetchall()
    with _progressbar(rows, label="Migrating server properties") as bar:
        for row in bar:
            server, key, value = row
            server = int(server)
            if key == "prefixes":
                await conn.execute("""INSERT INTO server_prefixes(server_id, prefixes) VALUES($1, $2)
                                          ON CONFLICT DO NOTHING""", server, json.loads(value))
                continue

            if key in ["times"]:
                value = json.dumps(json.loads(value))
            elif key in ["events_channel", "levels_channel", "watched_channel", "news_channel", "welcome_channel",
                         "ask_channel", "watched_message"]:
                value = json.dumps(int(value))
            elif key == "commandsonly":
                value = json.dumps(bool(value))
            else:
                value = json.dumps(value)
            await conn.execute("""INSERT INTO server_property(server_id, key, value) VALUES($1, $2, $3)
                                      ON CONFLICT(server_id, key) DO NOTHING""", server, key, value)


async def import_events(conn: asyncpg.Connection, c: sqlite3.Cursor):
    c.execute("SELECT id, creator, name, start, active, status, description, server, joinable, slots FROM events")
    rows = c.fetchall()
    event_subscribers = []
    event_participants = []
    with _progressbar(rows, label="Migrating events") as bar:
        for row in bar:
            old_id, creator, name, start, active, status, description, server, joinable, slots = row
            start = datetime.datetime.utcfromtimestamp(start)
            active = bool(active)
            joinable = bool(joinable)
            status = 4 - status
            event_id = await conn.fetchval("""INSERT INTO event(user_id, name, start, active, description, server_id,
                                              joinable, slots, reminder)
                                              VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id""",
                                           creator, name, start, active, description, server, joinable, slots, status)
            c.execute("SELECT ?, user_id FROM event_subscribers WHERE event_id = ?", (event_id, old_id))
            event_subscribers.extend(c.fetchall())
            c.execute("SELECT ?, name FROM event_participants LEFT JOIN chars ON id = char_id WHERE event_id = ?",
                      (event_id, old_id))
            event_participants.extend(c.fetchall())
    with _progressbar(event_subscribers, label="Migrating event subscribers") as bar:
        for row in bar:
            await conn.execute("""INSERT INTO event_subscriber(event_id, user_id) VALUES($1, $2)
                                  ON CONFLICT(event_id, user_id) DO NOTHING""", *row)
    with _progressbar(event_participants, label="Migrating event participants") as bar:
        for row in bar:
            event_id, name = row
            char_id = await conn.fetchval('SELECT id FROM "character" WHERE name = $1', name)
            if char_id is None:
                continue
            await conn.execute("""INSERT INTO event_participant(event_id, character_id) VALUES($1, $2)
                                  ON CONFLICT(event_id, character_id) DO NOTHING""", event_id, char_id)


async def import_roles(conn: asyncpg.Connection, c: sqlite3.Cursor):
    c.execute("SELECT server_id, role_id, guild FROM auto_roles")
    rows = c.fetchall()
    with _progressbar(rows, label="Migrating auto roles") as bar:
        for row in bar:
            await conn.execute("""INSERT INTO role_auto(server_id, role_id, rule) VALUES($1, $2, $3)
                                  ON CONFLICT(server_id, role_id, rule) DO NOTHING""", *row)
    c.execute("SELECT server_id, role_id FROM joinable_roles")
    rows = c.fetchall()
    with _progressbar(rows, label="Migrating joinable roles") as bar:
        for row in bar:
            await conn.execute("""INSERT INTO role_joinable(server_id, role_id) VALUES($1, $2)
                                  ON CONFLICT(server_id, role_id) DO NOTHING""", *row)


async def import_ignored_channels(conn: asyncpg.Connection, c: sqlite3.Cursor):
    c.execute("SELECT server_id, channel_id FROM ignored_channels")
    rows = c.fetchall()
    with _progressbar(rows, label="Migrating ignored channels") as bar:
        for row in bar:
            await conn.execute("""INSERT INTO channel_ignored(server_id, channel_id) VALUES($1, $2)
                                  ON CONFLICT(server_id, channel_id) DO NOTHING""", *row)


async def import_watch_list(conn: asyncpg.Connection, c: sqlite3.Cursor):
    c.execute("SELECT name, is_guild, server_id, reason, author, added FROM watched_list")
    rows = c.fetchall()
    with _progressbar(rows, label="Migrating watchlist entries") as bar:
        for row in bar:
            name, is_guild, server_id, reason, author, added = row
            if added is not None:
                added = datetime.datetime.now(datetime.timezone.utc)
            is_guild = bool(is_guild)
            await conn.execute("""INSERT INTO watchlist_entry(name, is_guild, server_id, reason, user_id, created)
                                  VALUES($1, $2, $3, $4, $5, $6)
                                  ON CONFLICT(name, server_id, is_guild) DO NOTHING""",
                               name, is_guild, server_id, reason, author, added)


def check_sql_database(conn: sqlite3.Connection):
    """Initializes and/or updates the database to the current version"""
    # Database file is automatically created with connect, now we have to check if it has tables
    print("Checking database version...")
    c = conn.cursor()
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
        if db_version == SQL_DB_LASTVERSION:
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
        print("Updated database to version {0}".format(db_version))
        c.execute("UPDATE db_info SET value = ? WHERE key LIKE 'version'", (db_version,))
    finally:
        c.close()
        conn.commit()
