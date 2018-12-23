import re
import sqlite3
from typing import Any, List, Union

import asyncpg
import discord
import tibiapy

WIKIDB = "data/tibiawiki.db"

# Open database in read only mode.
wiki_db = sqlite3.connect(f"file:{WIKIDB}?mode=ro", uri=True)
wiki_db.row_factory = sqlite3.Row

# Pattern to match the number of affected rows
result_patt = re.compile(r"\w+\s(\d+)")


def get_affected_count(result: str) -> int:
    """Gets the number of affected rows by a UPDATE or DELETE query."""
    m = result_patt.search(result)
    if not m:
        return 0
    return int(m.group(1))


async def get_prefixes(pool: asyncpg.pool.Pool, guild_id: int):
    """Gets the list of prefixes for a given server.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :return: The list of prefixes the guild has.
    """
    return await pool.fetchval("SELECT prefixes FROM server_prefixes WHERE server_id = $1", guild_id)


async def set_prefixes(pool: asyncpg.pool.Pool, guild_id: int, prefixes: List[str]):
    """Sets the new server prefixes.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :param prefixes: The list of prefixes to set.
    """
    await pool.execute("""INSERT INTO server_prefixes(server_id, prefixes) VALUES($1, $2)
                          ON CONFLICT(server_id) DO UPDATE SET prefixes = EXCLUDED.prefixes""", guild_id, prefixes)


async def get_server_property(pool: asyncpg.pool.Pool, guild_id: int, key: str, default=None) -> Any:
    """Gets the value of a server's property.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :param key: The property's key.
    :param default: The value to return if the key has no value.
    :return: The value of the key or the default value if specified.
    """
    value = await pool.fetchval("SELECT value FROM server_property WHERE server_id = $1 AND key = $2", guild_id, key)
    return value if value is not None else default


async def set_server_property(pool: asyncpg.pool.Pool, guild_id: int, key: str, value: Any):
    """Sets a server's property.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :param key: The property's key.
    :param value: The value to set to the property.
    """
    await pool.execute("""INSERT INTO server_property(server_id, key, value) VALUES($1, $2, $3::jsonb)
                          ON CONFLICT(server_id, key) DO UPDATE SET value = EXCLUDED.value""",
                       guild_id, key, value)


async def get_global_property(pool: asyncpg.pool.Pool, key: str, default=None) -> Any:
    """Gets the value of a global property.

    :param pool: An asyncpg Pool or Connection.
    :param key: The property's key
    :param default: The value to return if the property is undefined.
    :return: The value of the key or the default value if specified.
    """
    value = await pool.fetchval("SELECT value FROM global_property WHERE key = $1", key)
    return value if value is not None else default


async def set_global_property(pool: asyncpg.pool.Pool, key: str, value: Any):
    """Sets the value of a global property.

    :param pool: An asyncpg Pool or Connection.
    :param key: The property's key
    :param value: The new value the key will have.
    """
    await pool.execute("""INSERT INTO global_property(key, value) VALUES($1, $2::jsonb)
                          ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value""", key, value)


class DbChar(tibiapy.abc.BaseCharacter):
    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.level = kwargs.get("level")
        self.user_id = kwargs.get("user_id")
        self.vocation = kwargs.get("vocation")
        self.sex = kwargs.get("sex")
        self.guild = kwargs.get("guild")
        self.world = kwargs.get("world")
        self.deaths = []
        self.level_ups = []

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} user_id={self.user_id} name={self.name!r}, level={self.level}>"

    @classmethod
    async def get_by_id(cls, pool, char_id):
        row = await pool.fetchrow('SELECT * FROM "character" WHERE id = $1', char_id)
        if row:
            return cls(**row)

    @classmethod
    async def get_by_name(cls, pool, name: str):
        row = await pool.fetchrow('SELECT * FROM "character" WHERE lower(name) = $1', name.lower())
        if row:
            return cls(**row)

    @classmethod
    async def get_chars_by_user(cls, pool, user: Union[int, discord.User, discord.Member]):
        if not isinstance(user, int):
            user = user.id
        rows = await pool.fetchrow('SELECT * FROM "character" WHERE user_id = $1', user)
        if rows:
            return [cls(**row) for row in rows]



