import datetime
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
result_patt = re.compile(r"(\d+)$")

PoolConn = Union[asyncpg.pool.Pool, asyncpg.Connection]


def get_affected_count(result: str) -> int:
    """Gets the number of affected rows by a UPDATE, DELETE or INSERT queries."""
    m = result_patt.search(result.strip())
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

    async def get_level_ups(self, conn, minimum_level=0):
        """Gets an asynchronous generator of the character's levelups.

        :param conn: Connection to the database.
        :param minimum_level: The minimum level to show.
        :return: An asynchronous generator containing the levels.
        """
        async with conn.transaction():
            async for row in conn.cursor("""SELECT * ROM character_levelup l WHERE character_id = $1 AND level >= $2
                                            ORDER BY date DESC""", self.id, minimum_level):
                yield DbLevelUp(**row)

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
    async def get_chars_by_user(cls, conn: PoolConn, user_id=0, *, worlds: Union[List[str], str] = None) \
            -> List['DbChar']:
        """Gets a list of characters registered to a user

        :param conn: A connection pool or single connection to the database.
        :param user_id: The user or user id to check.
        :param worlds: Whether to filter out chars not in the provided worlds.
        :return: The list of characters registered to the user.
        """
        if isinstance(worlds, str):
            worlds = [worlds]
        if worlds is None:
            worlds = []
        rows = await conn.fetch("""SELECT * FROM "character"
                                   WHERE user_id = $1 AND (cardinality($2::text[]) = 0 OR world = any($2))""",
                                user_id, worlds)
        if not rows:
            return []
        return [cls(**row) for row in rows]


class DbLevelUp:
    """Represents a level up in the database."""
    char: Optional[DbChar]

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 0)
        self.char_id = kwargs.get("character_id", 0)
        self.level = kwargs.get("level", 0)
        self.date = kwargs.get("date")
        self.char = None

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

    @classmethod
    async def get_latest(cls, conn: PoolConn, minimum_level=0, *, user_id=0, worlds: Union[List[str], str] = None):
        """Gets an asynchronous generator of the character's levelups.

        :param conn: Connection to the database.
        :param minimum_level: The minimum level to show.
        :param user_id: The id of an user to only show level ups of characters they own.
        :param worlds: A list of worlds to only show level ups of characters in that world.
        :return: An asynchronous generator containing the levels.
        """
        if isinstance(worlds, str):
            worlds = [worlds]
        if not worlds:
            worlds = []
        async with conn.transaction():
            async for row in conn.cursor("""SELECT l.*, c.name, c.level as char_level, c.world, c.vocation, c.user_id,
                                            c.id as char_id, c.guild, c.sex
                                            FROM character_levelup l
                                            LEFT JOIN "character" c ON c.id = l.character_id
                                            WHERE ($1::bigint = 0 OR c.user_id = $1) AND 
                                            (cardinality($2::text[]) = 0 OR c.world = any($2))
                                            AND l.level >= $3 
                                            ORDER BY date DESC""", user_id, worlds, minimum_level):
                level_up = DbLevelUp(**row)
                level_up.char = DbChar(id=row["user_id"], name=row['name'], level=row['char_level'],
                                       user_id=row["user_id"], world=row["world"], sex=row["sex"],
                                       vocation=row["vocation"], guild=row["guild"])
                yield level_up


class DbKiller:
    """Represents a killer from the database."""
    def __init__(self, **kwargs):
        self.death_id = kwargs.get("death_id")
        self.position = kwargs.get("position")
        self.name = kwargs.get("name")
        self.player = kwargs.get("player")

    @classmethod
    def from_tibiapy(cls, killer: tibiapy.Killer) -> 'DbKiller':
        """Converts a Killer object from Tibia.py into a DbKiller object.

        :param killer: A killer object
        :return: The equivalent DbKiller object, without its positon and death_id set.
        """
        return cls(name=killer.name, player=killer.player)

    async def save(self, conn: PoolConn):
        """Saves the current killer to the database.

        An error will be returned if death_id has not been set.

        :param conn: Connection to the database.
        """
        await self.insert(conn, self.death_id, self.position, self.name, self.player)

    @classmethod
    async def insert(cls, conn: PoolConn, death_id, position, name, player) -> 'DbKiller':
        """Inserts a killer into the database.

        :param conn: Connection to the database,
        :param death_id: The id of the death the killer belongs to.
        :param position: The position of the killer in the death's list of killers.
        :param name: The name of the killer.
        :param player: Whether the killer is a player or not.
        :return: The inserted DbKiller object.
        """
        await conn.execute("""INSERT INTO character_death_killer(death_id, position, name, player)
                              VALUES($1, $2, $3, $4)""", death_id, position, name, player)
        return cls(death_id=death_id, position=position, name=name, player=player)


class DbAssist:
    """Represents an assister from the database."""
    def __init__(self, **kwargs):
        self.death_id = kwargs.get("death_id")
        self.position = kwargs.get("position")
        self.name = kwargs.get("name")

    @classmethod
    def from_tibiapy(cls, killer: tibiapy.Killer):
        """Converts a Killer object from Tibia.py into a DbAssist object.

        :param killer: A killer object
        :return: The equivalent DbAssist object, without its positon and death_id set.
        """
        return cls(name=killer.name)

    async def save(self, conn):
        """Saves the current assister to the database.

        An error will be returned if death_id has not been set.

        :param conn: Connection to the database.
        """
        await self.insert(conn, self.death_id, self.position, self.name)

    @classmethod
    async def insert(cls, conn: PoolConn, death_id, position, name) -> 'DbAssist':
        """Inserts an assister into the database.

        :param conn: Connection to the database,
        :param death_id: The id of the death the assister belongs to.
        :param position: The position of the assisters in the death's list of assists.
        :param name: The name of the assister.
        :return: The inserted DbAssist object.
        """
        await conn.execute("""INSERT INTO character_death_assist(death_id, position, name)
                              VALUES($1, $2, $3)""", death_id, position, name)
        return cls(death_id=death_id, position=position, name=name)


class DbDeath:
    """Represents a death in the database."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.character_id = kwargs.get("character_id")
        self.level = kwargs.get("level")
        self.date = kwargs.get("date")
        self.killers = []
        self.assists = []

    async def save(self, conn: PoolConn):
        """Saves the current death to the database.

        This will fail if id or character_id is not set.

        :param conn: A connection to the database."""
        await self.insert(conn, self.character_id, self.level, self.date, self.killers, self.assists)

    @classmethod
    async def exists(cls, conn: PoolConn, char_id: int, level: int, date: datetime.datetime, killer) -> bool:
        """Checks if a death matching the provided parameters exists.

        :param conn: Connection to the database.
        :param char_id: The id of the character.
        :param level: The level of the death.
        :param date: The date when the death happened.
        :param killer: The main killer of the death.
        :return: True if it exists, False otherwise.
        """
        _id = await conn.fetchval("""SELECT id FROM character_death d
                                                     INNER JOIN character_death_killer dk ON dk.death_id = d.id
                                                     WHERE character_id = $1 AND date = $2 AND name = $3 AND level = $4
                                                     AND position = 0""",
                                  char_id, date, killer, level)
        if _id:
            return True
        return False

    @classmethod
    def from_tibiapy(cls, death: tibiapy.Death) -> 'DbDeath':
        """Creates a DbDeath object from a Tibia.py death.

        :param death: The Tibia.py death object.
        :return: A DbDeath object.
        """
        db_death = cls(level=death.level, date=death.time)
        db_death.killers = [DbKiller.from_tibiapy(k) for k in death.killers]
        db_death.assists = [DbAssist.from_tibiapy(a) for a in death.assists]
        return db_death

    @classmethod
    async def insert(cls, conn: PoolConn, char_id: int, level: int, date: datetime.date,
                     killers: List[DbKiller], assists: List[DbAssist]) -> 'DbDeath':
        """

        :param conn: The connection to the database.
        :param char_id: The id of the character the death belongs to
        :param level: The death to register.
        :param date: The date of the death.
        :param killers: List of players or creatures that contributed to the death
        :param assists: List of players that contributed to the death indirectly.
        :return: The inserted entry.
        """
        row_id = await conn.fetchval("""INSERT INTO character_death(character_id, level, date) VALUES($1, $2, $3)
                                                RETURNING id""", char_id, level, date)
        for pos, killer in enumerate(killers):
            killer.death_id = row_id
            killer.position = pos
            await killer.save(conn)
        for pos, assist in enumerate(assists):
            assist.death_id = row_id
            assist.position = pos
            await assist.save(conn)
        death = cls(id=row_id, character_id=char_id, level=level, date=date)
        death.killers = killers
        death.assists = assists
        return death
