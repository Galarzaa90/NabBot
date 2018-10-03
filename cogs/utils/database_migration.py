import sqlite3
from operator import itemgetter

import asyncpg
import click

LATEST_VERSION = 1


async def check_database(pool: asyncpg.pool.Pool):
    async with pool.acquire() as con:
        version = await get_version(con)
        if version <= 0:
            await create_database(con)
            await set_version(con, 1)


async def create_database(con: asyncpg.connection.Connection):
    for create_query in tables:
        await con.execute(create_query)
    for f in functions:
        await con.execute(f)
    for trigger in triggers:
        await con.execute(trigger)
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
        modified timestamp without time zone DEFAULT now(),
        created timestamp without time zone DEFAULT now(),
        PRIMARY KEY (id),
        UNIQUE(name)
    );
    """,
    """
    CREATE TABLE character_death (
        id serial NOT NULL,
        character_id integer NOT NULL,
        level smallint,
        date timestamp without time zone,
        PRIMARY KEY (id),
        FOREIGN KEY (character_id) REFERENCES "character" (id)
    );
    """,
    """
    CREATE TABLE character_death_killer (
        death_id integer NOT NULL,
        position smallint NOT NULL,
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
        date timestamp without time zone,
        PRIMARY KEY (id),
        FOREIGN KEY (character_id) REFERENCES "character" (id)
    );
    """,
    """
    CREATE TABLE event (
        id serial NOT NULL,
        user_id integer NOT NULL,
        server_id integer NOT NULL,
        name text NOT NULL,
        description text,
        start timestamp without time zone,
        active boolean,
        status smallint,
        joinable boolean,
        slots smallint,
        modified timestamp without time zone DEFAULT now(),
        created timestamp without time zone DEFAULT now(),
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
        user_id integer NOT NULL,
        FOREIGN KEY (event_id) REFERENCES event (id),
        UNIQUE(event_id, user_id)
    );""",
    """
    CREATE TABLE highscores (
        world text NOT NULL,
        category text NOT NULL,
        last_scan timestamp without time zone DEFAULT now(),
        PRIMARY KEY (world, category)
    );""",
    """
    CREATE TABLE highscores_entry (
        rank text,
        category text,
        world text,
        name text,
        vocation text,
        value bigint
    );""",
    """
    CREATE TABLE role_auto (
        server_id bigint NOT NULL,
        role_id bigint NOT NULL,
        rule text NOT NULL,
        PRIMARY KEY (server_id, role_id)
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
    CREATE TABLE global_property (
        key text NOT NULL,
        value jsonb,
        PRIMARY KEY (key)
    );
    """,
    """
    CREATE TABLE watchlist_entry (
        id serial NOT NULL,
        name text NOT NULL,
        server_id bigint NOT NULL,
        is_guild bool DEFAULT FALSE,
        reason text,
        user_id bigint,
        created timestamp without time zone  DEFAULT now(),
        PRIMARY KEY(id),
        UNIQUE(name, server_id, is_guild)
    )
    """,
    """
    CREATE TABLE command (
        server_id bigint,
        channel_id bigint NOT NULL,
        user_id bigint NOT NULL,
        date timestamp without time zone NOT NULL DEFAULT now(),
        prefix text NOT NULL,
        command text NOT NULL
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
    legacy_conn = sqlite3.connect(path)
    c = legacy_conn.cursor()
    conn = await pool.acquire()
    try:
        rows = c.execute("SELECT id, user_id, name, level, vocation, world, guild FROM chars ORDER By id ASC").fetchall()
        levelups = []
        deaths = []
        with click.progressbar(rows, label="Migrating characters", show_pos=True) as bar:
            for row in bar:
                old_id, *char = row
                # Try to insert character, if it exist return existing chracter's ID
                char_id = await conn.fetchval("""
                    INSERT INTO "character" (user_id, name, level, vocation, world, guild)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id""", *char)
                c.execute("SELECT ?, level, date FROM char_levelups WHERE char_id = ? ORDER BY date ASC", (char_id, old_id, ))
                results = c.fetchall()
                levelups.extend(results)
                c.execute("SELECT ?, level, date, killer, byplayer FROM char_deaths WHERE char_id = ?", (char_id, old_id))
                results = c.fetchall()
                deaths.extend(results)
        deaths = sorted(deaths, key=itemgetter(2))
        with click.progressbar(deaths, label="Migrating deaths", show_pos=True) as bar:
            for death in bar:
                char_id, level, date, killer, byplayer = death
                byplayer = byplayer == 1
                death_id = await conn.fetchval("""INSERT INTO character_death(character_id, level, date)
                                                  VALUES ($1, $2, to_timestamp($3))
                                                  RETURNING id""", char_id, level, date)
                await conn.execute("""INSERT INTO character_death_killer(death_id, position, name, player)
                                      VALUES ($1, 1, $2, $3)""", death_id, killer, byplayer)

        levelups = sorted(levelups, key=itemgetter(2))
        with click.progressbar(levelups, label="Migrating level ups", show_pos=True) as bar:
            for levelup in bar:
                await conn.execute("""INSERT INTO character_levelup(character_id, position, level, date)
                                      VALUES ($1, $2, to_timestamp($3))""", *levelup)

    finally:
        await pool.release(conn)

