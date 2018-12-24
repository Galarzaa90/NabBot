import re
import sqlite3
from typing import Any, List, Union, Optional

import asyncpg
import discord
import tibiapy

WIKIDB = "data/tibiawiki.db"

# Open database in read only mode.
wiki_db = sqlite3.connect(f"file:{WIKIDB}?mode=ro", uri=True)
wiki_db.row_factory = sqlite3.Row

# Pattern to match the number of affected rows
result_patt = re.compile(r"\w+\s(\d+)")

PoolConn = Union[asyncpg.pool.Pool, asyncpg.Connection]


def get_affected_count(result: str) -> int:
    """Gets the number of affected rows by a UPDATE or DELETE query."""
    m = result_patt.search(result)
    if not m:
        return 0
    return int(m.group(1))


async def get_prefixes(pool: PoolConn, guild_id: int):
    """Gets the list of prefixes for a given server.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :return: The list of prefixes the guild has.
    """
    return await pool.fetchval("SELECT prefixes FROM server_prefixes WHERE server_id = $1", guild_id)


async def set_prefixes(pool: PoolConn, guild_id: int, prefixes: List[str]):
    """Sets the new server prefixes.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :param prefixes: The list of prefixes to set.
    """
    await pool.execute("""INSERT INTO server_prefixes(server_id, prefixes) VALUES($1, $2)
                          ON CONFLICT(server_id) DO UPDATE SET prefixes = EXCLUDED.prefixes""", guild_id, prefixes)


async def get_server_property(pool: PoolConn, guild_id: int, key: str, default=None) -> Any:
    """Gets the value of a server's property.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :param key: The property's key.
    :param default: The value to return if the key has no value.
    :return: The value of the key or the default value if specified.
    """
    value = await pool.fetchval("SELECT value FROM server_property WHERE server_id = $1 AND key = $2", guild_id, key)
    return value if value is not None else default


async def set_server_property(pool: PoolConn, guild_id: int, key: str, value: Any):
    """Sets a server's property.

    :param pool: An asyncpg Pool or Connection.
    :param guild_id: The id of the guild.
    :param key: The property's key.
    :param value: The value to set to the property.
    """
    await pool.execute("""INSERT INTO server_property(server_id, key, value) VALUES($1, $2, $3::jsonb)
                          ON CONFLICT(server_id, key) DO UPDATE SET value = EXCLUDED.value""",
                       guild_id, key, value)


async def get_global_property(pool: PoolConn, key: str, default=None) -> Any:
    """Gets the value of a global property.

    :param pool: An asyncpg Pool or Connection.
    :param key: The property's key
    :param default: The value to return if the property is undefined.
    :return: The value of the key or the default value if specified.
    """
    value = await pool.fetchval("SELECT value FROM global_property WHERE key = $1", key)
    return value if value is not None else default


async def set_global_property(pool: PoolConn, key: str, value: Any):
    """Sets the value of a global property.

    :param pool: An asyncpg Pool or Connection.
    :param key: The property's key
    :param value: The new value the key will have.
    """
    await pool.execute("""INSERT INTO global_property(key, value) VALUES($1, $2::jsonb)
                          ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value""", key, value)


class DbChar(tibiapy.abc.BaseCharacter):
    """Represents a character from the database."""

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

    async def update_level(self, conn: PoolConn, level: int, update_self=True) -> bool:
        """Updates the level of the character on the database.

        :param conn: Connection to the database.
        :param level: The new level to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the level was updated in the database or not.
        """
        result = await self.update_level_by_id(conn, self.id, level)
        if result and update_self:
            self.level = level
        return result

    @classmethod
    async def update_level_by_id(cls, conn: PoolConn, char_id: int, level: int) -> bool:
        """Updates the level of a character with a given id.

        :param conn: Connection to the database.
        :param char_id: The id of the character.
        :param level:  The new level to set.
        :return: Whether the database was updated or not.
        """
        result = await conn.execute('UPDATE "character" SET level = $1 WHERE id = $2', level, char_id)
        return bool(get_affected_count(result))

    @classmethod
    async def get_by_id(cls, conn: PoolConn, char_id: int) -> Optional['DbChar']:
        """Gets a character with a given ID.

        :param conn: Connection to the database.
        :param char_id: The id of the character to look for.
        :return: The found character or None.
        """
        row = await conn.fetchrow('SELECT * FROM "character" WHERE id = $1', char_id)
        if row:
            return cls(**row)

    @classmethod
    async def get_by_name(cls, conn: PoolConn, name: str) -> Optional['DbChar']:
        """Gets a character with a given ID.

        :param conn: Connection to the database.
        :param name: The name of the character to look for.
        :return: The found character or None.
        """
        row = await conn.fetchrow('SELECT * FROM "character" WHERE lower(name) = $1', name.lower())
        if row:
            return cls(**row)

    @classmethod
    async def get_chars_by_user(cls, conn: PoolConn, user: Union[int, discord.User, discord.Member],
                                worlds: Union[List[str], str] = None) -> List['DbChar']:
        """Gets a list of characters registered to a user

        :param conn: A connection pool or single connection to the database.
        :param user: The user or user id to check.
        :param worlds: Whether to filter out chars not in the provided worlds.
        :return: The list of characters registered to the user.
        """
        if not isinstance(user, int):
            user = user.id
        rows = await conn.fetch('SELECT * FROM "character" WHERE user_id = $1', user)
        if not rows:
            return []
        chars = [cls(**row) for row in rows]
        if isinstance(worlds, str):
            worlds = [worlds]
        if worlds:
            return list(filter(lambda c: c.world in worlds, chars))
        return chars


class DbLevelUp:
    """Represents a level up in the database."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 0)
        self.char_id = kwargs.get("character_id", 0)
        self.level = kwargs.get("level", 0)
        self.date = kwargs.get("date")

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} char_id={self.char_id} level={self.level}, date={self.date!r}>"

    @classmethod
    async def insert(cls, conn: PoolConn, char_id, level, date=None) -> 'DbLevelUp':
        """

        :param conn: The connection to the database.
        :param char_id: The id of the character the level up belongs to
        :param level: The level up to register.
        :param date: The date of the levelup. By default it will use the database's default time.
        :return: The inserted entry.
        """
        if not date:
            row_id, date = await conn.fetchrow("""INSERT INTO character_levelup(character_id, level) VALUES($1, $2)
                                         RETURNING id, date""", char_id, level)
        else:
            row_id = await conn.fetchval("""INSERT INTO character_levelup(character_id, level, date) VALUES($1, $2, $3)
                                            RETURNING id""", char_id, level, date)
        return cls(id=row_id, character_id=char_id, level=level, date=date)

