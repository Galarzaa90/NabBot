import asyncpg
import json
import sqlite3
from typing import Any, List

TIBIADB = "data/tibia_database.db"

tibiaDatabase = sqlite3.connect(TIBIADB)


def dict_factory(cursor, row):
    """Makes values returned by cursor fetch functions return a dictionary instead of a tuple.

    To implement this, the connection's row_factory method must be replaced by this one."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


tibiaDatabase.row_factory = dict_factory


async def get_prefixes(pool: asyncpg.pool.Pool, guild_id: int):
    return await pool.fetchval("SELECT prefixes FROM server_prefixes WHERE server_id = $1", guild_id)


async def set_prefixes(pool: asyncpg.pool.Pool, guild_id: int, prefixes: List[str]):
    await pool.execute("""INSERT INTO server_prefixes(server_id, prefixes) VALUES($1, $2)
                          ON CONFLICT(server_id) DO UPDATE SET prefixes = EXCLUDED.prefixes""", guild_id, prefixes)


async def get_server_property(pool: asyncpg.pool.Pool, guild_id: int, key: str, default=None) -> Any:
    value = await pool.fetchval("SELECT value FROM server_property WHERE server_id = $1 AND key = $2", guild_id, key)
    try:
        return json.loads(value) if value is not None else default
    except json.JSONDecodeError:
        return default


async def set_server_property(pool: asyncpg.pool.Pool, guild_id: int, key: str, value: Any):
    await pool.execute("""INSERT INTO server_property(server_id, key, value) VALUES($1, $2, $3)
                          ON CONFLICT(server_id, key) DO UPDATE SET value = EXCLUDED.value""",
                       guild_id, key, json.dumps(value))
