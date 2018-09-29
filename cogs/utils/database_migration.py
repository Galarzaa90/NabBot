import asyncpg


async def check_database(pool: asyncpg.pool.Pool):
    async with pool.acquire() as con:
        await create_database(con)


async def create_database(conn: asyncpg.Connection):
    await conn.execute("""
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
    """)
