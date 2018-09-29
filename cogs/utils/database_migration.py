import asyncpg


LATEST_VERSION = 1


async def check_database(pool: asyncpg.pool.Pool):
    async with pool.acquire() as con:
        await create_database(con)


async def create_database(conn: asyncpg.Connection):
    for create_query in tables:
        await conn.execute(create_query)
    for f in functions:
        await conn.execute(f)
    for trigger in triggers:
        await conn.execute(trigger)
    await set_version(conn, LATEST_VERSION)


async def set_version(conn, version):
    await conn.execute("""
        INSERT INTO global_property (key, value) VALUES ('db_version',$1) 
        ON CONFLICT (key) 
        DO
         UPDATE
           SET value = EXCLUDED.value;
    """, version)


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
        PRIMARY KEY (id)
    );
    """,
    """
    CREATE TABLE character_death (
        id serial NOT NULL,
        character_id integer NOT NULL,
        level smallint,
        killer text,
        player bool,
        date timestamp without time zone,
        PRIMARY KEY (id),
        FOREIGN KEY (character_id) REFERENCES "character" (id)
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
        reason TEXT,
        user_id bigint,
        created timestamp without time zone  DEFAULT now(),
        PRIMARY KEY(id),
        UNIQUE(name, server_id, is_guild)
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