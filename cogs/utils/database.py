import datetime
import re
import sqlite3
from typing import Any, List, Optional, Union, TypeVar, Tuple

import asyncpg
import tibiapy

WIKIDB = "data/tibiawiki.db"

# Open database in read only mode.
wiki_db = sqlite3.connect(f"file:{WIKIDB}?mode=ro", uri=True)
wiki_db.row_factory = sqlite3.Row

# Pattern to match the number of affected rows
result_patt = re.compile(r"(\d+)$")

PoolConn = Union[asyncpg.pool.Pool, asyncpg.Connection]
"""A type alias for an union of Pool and Connection."""
T = TypeVar('T')


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
        self.id: int = kwargs.get("id")
        """The unique id of the character in the database."""
        self.name: str = kwargs.get("name")
        """The name of the character."""
        self.level: int = kwargs.get("level")
        """The last registered level on the database."""
        self.user_id: int = kwargs.get("user_id")
        """The id of the discord user that owns this character."""
        self.vocation: str = kwargs.get("vocation")
        """The last seen vocation of the character."""
        self.sex: str = kwargs.get("sex")
        """The last seen sex of the character."""
        self.guild: Optional[str] = kwargs.get("guild")
        """The last seen guild of the character."""
        self.world: str = kwargs.get("world")
        """The last seen world of the character."""

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} user_id={self.user_id} name={self.name!r}, level={self.level}>"

    # region Instance methods
    async def get_deaths(self, conn: PoolConn):
        """An async generator of the character's deaths, from newest to oldest.

        Note that the yielded deaths won't have the char attribute set.

        :param conn: Connection to the database.
        """
        async for death in DbDeath.get_from_character(conn, self.id):
            yield death

    async def get_level_ups(self, conn: PoolConn):
        """Gets an asynchronous generator of the character's level ups.

        Note that the yielded deaths won't have the char attribute set.

        :param conn: Connection to the database.
        :return: An asynchronous generator containing the entries.
        """
        async for level_up in DbLevelUp.get_from_character(conn, self.id):
            yield level_up

    async def get_timeline(self, conn: PoolConn):
        """Gets an asynchronous generator of character's recent deaths and level ups.

        :param conn: Connection to the database.
        :return: An asynchronous generator containing the entries.
        """
        async with conn.transaction():
            async for row in conn.cursor("""
                    (
                        SELECT d.*, json_agg(k)::jsonb as killers, 'd' AS type
                        FROM character_death d
                        LEFT JOIN character_death_killer k ON k.death_id = d.id
                        WHERE d.character_id = $1
                        GROUP BY d.id
                    )
                    UNION
                    (
                        SELECT l.*, NULL, 'l' AS type
                        FROM character_levelup l
                        WHERE l.character_id = $1
                        GROUP BY l.id
                    )
                    ORDER by date DESC
                    """, self.id):
                if row["type"] == "l":
                    yield DbLevelUp(**row)
                else:
                    yield DbDeath(**row)

    async def update_guild(self, conn: PoolConn, guild: str, update_self=True) -> bool:
        """Updates the guild of the character on the database.

        :param conn: Connection to the database.
        :param guild: The new guild to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the guild was updated in the database or not.
        """
        result = await self.update_field_by_id(conn, self.id, "guild", guild)
        if result and update_self:
            self.guild = guild
        return result is not None

    async def update_level(self, conn: PoolConn, level: int, update_self=True) -> bool:
        """Updates the level of the character on the database.

        :param conn: Connection to the database.
        :param level: The new level to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the level was updated in the database or not.
        """
        result = await self.update_field_by_id(conn, self.id, "level", level)
        if result and update_self:
            self.level = level
        return result is not None

    async def update_name(self, conn: PoolConn, name: str, update_self=True) -> bool:
        """Updates the name of the character on the database.

        :param conn: Connection to the database.
        :param name: The new name to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the name was updated in the database or not.
        """
        result = await self.update_field_by_id(conn, self.id, "name", name)
        if result and update_self:
            self.name = name
        return result is not None

    async def update_sex(self, conn: PoolConn, sex: str, update_self=True) -> bool:
        """Updates the sex of the character on the database.

        :param conn: Connection to the database.
        :param sex: The new sex to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the sex was updated in the database or not.
        """
        result = await self.update_field_by_id(conn, self.id, "sex", sex)
        if result and update_self:
            self.sex = sex
        return result is not None

    async def update_user(self, conn: PoolConn, user_id: int, update_self=True) -> bool:
        """Updates the user of the character on the database.

        :param conn: Connection to the database.
        :param user_id: The new user_id to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the level was updated in the database or not.
        """
        result = await self.update_field_by_id(conn, self.id, "user_id", user_id)
        if result and update_self:
            self.user_id = user_id
        return result is not None

    async def update_vocation(self, conn: PoolConn, vocation: str, update_self=True) -> bool:
        """Updates the vocation of the character on the database.

        :param conn: Connection to the database.
        :param vocation: The new vocation to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the vocation was updated in the database or not.
        """
        result = await self.update_field_by_id(conn, self.id, "vocation", vocation)
        if result and update_self:
            self.vocation = vocation
        return result is not None

    async def update_world(self, conn: PoolConn, world: str, update_self=True) -> bool:
        """Updates the world of the character on the database.

        :param conn: Connection to the database.
        :param world: The new world to set.
        :param update_self: Whether to also update the object or not.
        :return: Whether the world was updated in the database or not.
        """
        result = await self.update_field_by_id(conn, self.id, "world", world)
        if result and update_self:
            self.world = world
        return result is not None

    # endregion

    # region Class methods
    @classmethod
    async def insert(cls, conn: PoolConn, name: str, level: int, vocation: str, user_id: int, world: str,
                     guild: str = None) -> 'DbChar':
        """Inserts a new level up into the database.

        :param conn: The connection to the database.
        :param name: The name of the character.
        :param level: The current level of the character. It will always be inserted as a negative.
        :param user_id: The discord id of the user owning the character.
        :param vocation: The current vocation of the character.
        :param world: The world where the character currently is.
        :param guild: The name of the guild the character belongs to.
        :return: The inserted entry.
        """
        row_id = await conn.fetchval("""INSERT INTO "character"(name, level, vocation, user_id, world, guild)
                                        VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                                     name, level*-1, vocation, user_id, world, guild)
        return cls(id=row_id, name=name, level=level, vocation=vocation, user_id=user_id, world=world, guild=guild)

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
        row = await conn.fetchrow('SELECT * FROM "character" WHERE lower(name) = $1 ORDER BY id', name.lower())
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

    @classmethod
    async def get_chars_in_range(cls, conn: PoolConn, minimum: int, maximum: int, world: str):
        """Gets a generator with characters in a level range and world, from highest level to lowest.

        :param conn: A connection pool or single connection to the database.
        :param minimum: The minimum level to find.
        :param maximum: The maximum level to find.
        :param world: Only characters in this world will be shown.
        :return: A generator containing the characters.
        """
        async with conn.transaction():
            async for row in conn.cursor("""SELECT * FROM "character" WHERE level >= $1 AND level <= $2 AND world = $3
                                            ORDER BY level DESC""", minimum, maximum, world):
                yield DbChar(**row)

    @classmethod
    async def update_field_by_id(cls, conn: PoolConn, char_id: int, column: str, value: T) -> Optional[Tuple[T, T]]:
        """Updates a field of a character with a given id.

        This may result in an exception if an invalid column is provided.

        Warning: The column parameter should NEVER be open to user input, as it may lead to SQL injection.

        :param conn: Connection to the database.
        :param char_id: The id of the character.
        :param column: The field or column that will be updated.
        :param value: The new value to store.
        :return: A tuple containing the old value and the new value or None if nothing was affected.
        """
        result = await conn.fetchrow(f"""
            UPDATE "character" new SET {column} = $2 FROM "character" old
            WHERE new.id = old.id AND new.id = $1
            RETURNING old.level as old_value, new.level as new_value
        """, char_id, value)
        if not result:
            return None
        return result["old_value"], result["new_value"]

    # endregion


class DbLevelUp:
    """Represents a level up in the database."""
    char: Optional[DbChar]

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id", 0)
        """The id of the level up entry."""
        self.character_id: int = kwargs.get("character_id", 0)
        """The id of the character this level up belongs to."""
        self.level = kwargs.get("level", 0)
        """The level obtained in this entry."""
        self.date = kwargs.get("date")
        """The date when this level up was detected."""
        self.char: Optional[DbChar] = DbChar(**kwargs["char"]) if "char" in kwargs else None
        """The character this entry belongs to."""

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} character_id={self.character_id} level={self.level} " \
            f"date={self.date!r}>"

    @classmethod
    async def insert(cls, conn: PoolConn, char_id, level, date:datetime.datetime = None) -> 'DbLevelUp':
        """Inserts a new level up into the database.

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
    async def get_from_character(cls, conn: PoolConn, character_id: int):
        """Gets an asynchronous generator of the level ups of a character, from most recent.

        :param conn: Connection to the database.
        :param character_id: The id of the character.
        :return: An asynchronous generator containing the level ups.
        """
        async with conn.transaction():
            async for row in conn.cursor("SELECT * FROM character_levelup WHERE character_id = $1 ORDER BY date DESC",
                                         character_id):
                yield cls(**row)

    @classmethod
    async def get_latest(cls, conn: PoolConn, *, minimum_level=0, user_id=0, worlds: Union[List[str], str] = None):
        """Gets an asynchronous generator of the character's level ups.

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
            async for row in conn.cursor("""
                    SELECT l.*, (json_agg(c)->>0)::jsonb as char FROM character_levelup l
                    LEFT JOIN "character" c ON c.id = l.character_id
                    WHERE ($1::bigint = 0 OR c.user_id = $1) AND (cardinality($2::text[]) = 0 OR c.world = any($2))
                    AND l.level >= $3
                    GROUP BY l.id
                    ORDER BY date DESC""", user_id, worlds, minimum_level):
                yield cls(**row)


class DbKiller:
    """Represents a killer from the database."""
    def __init__(self, **kwargs):
        self.death_id = kwargs.get("death_id")
        self.position = kwargs.get("position")
        self.name = kwargs.get("name")
        self.player = kwargs.get("player")

    def __repr__(self):
        return f"<{self.__class__.__name__} death_id={self.death_id} position={self.position} name={self.name!r} " \
            f"player={self.player}>"

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

    def __repr__(self):
        return f"<{self.__class__.__name__} death_id={self.death_id} position={self.position} name={self.name!r}>"

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
        self.id: int = kwargs.get("id")
        """The id of the entry in the database."""
        self.character_id: int = kwargs.get("character_id")
        """The id of the character this death belongs to."""
        self.level = kwargs.get("level")
        """The level the  character had when the death occured."""
        self.date = kwargs.get("date")
        """The date when the death occurred."""
        self.char: Optional[DbChar] = DbChar(**kwargs["char"]) if "char" in kwargs else None
        """The character this deaths belongs to."""

        killers = []
        for killer in kwargs.get("killers", []):
            if killer is None:
                break
            killers.append(DbKiller(**killer))
        assists = []
        for assist in kwargs.get("assists", []):
            if assist is None:
                break
            assists.append(DbAssist(**assist))

        self.killers: List[DbKiller] = killers
        """List of killers involved in the death."""
        self.assists: List[DbAssist] = assists
        """List of assists involved in the death."""

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} character_id={self.character_id} level={self.level}" \
            f"date={self.date!r} killers={self.killers!r} assists={self.assists!r}>"

    @property
    def killer(self) -> DbKiller:
        """Returns the first killer"""
        return self.killers[0] if self.killers else None

    async def save(self, conn: PoolConn):
        """Saves the current death to the database.

        This will fail if character_id is not set.

        :param conn: A connection to the database.
        :return: Whether the death was saved or not."""
        death = await self.insert(conn, self.character_id, self.level, self.date, self.killers, self.assists)
        if death:
            self.id = death.id
            return True
        return False

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
                 AND position = 0""", char_id, date, killer, level)
        if _id:
            return True
        return False

    @classmethod
    async def get_from_character(cls, conn: PoolConn, character_id: int):
        """Gets an asynchronous generator of the deaths of a character, from most recent.

        :param conn: Connection to the database.
        :param character_id: The id of the character.
        :return: An asynchronous generator containing the deaths.
        """
        async with conn.transaction():
            async for row in conn.cursor("""
                    SELECT d.*, json_agg(dk)::jsonb as killers, json_agg(da)::jsonb as assists FROM character_death d
                    LEFT JOIN character_death_killer dk ON dk.death_id = d.id
                    LEFT JOIN character_death_assist da ON da.death_id = d.id
                    WHERE character_id = $1
                    GROUP BY d.id
                    ORDER BY date DESC
                    """, character_id):
                yield DbDeath(**row)

    @classmethod
    async def get_latest(cls, conn: PoolConn, minimum_level=0, *, user_id=0, worlds: Union[List[str], str] = None):
        """Gets an asynchronous generator of recent level ups.

        :param conn: Connection to the database.
        :param minimum_level: The minimum level to show.
        :param user_id: The id of an user to only show deaths of characters they own.
        :param worlds: A list of worlds to only show deaths of characters in that world.
        :return: An asynchronous generator containing the deaths.
        """
        if isinstance(worlds, str):
            worlds = [worlds]
        if not worlds:
            worlds = []
        async with conn.transaction():
            async for row in conn.cursor("""
                    SELECT (json_agg(c)->>0)::jsonb as char, d.*, 
                    json_agg(dk)::jsonb as killers, json_agg(da)::jsonb as assists
                    FROM character_death d
                    LEFT JOIN character_death_killer dk ON dk.death_id = d.id
                    LEFT JOIN character_death_assist da ON da.death_id = d.id
                    LEFT JOIN "character" c ON c.id = d.character_id
                    WHERE ($1::bigint = 0 OR c.user_id = $1) AND
                    (cardinality($2::text[]) = 0 OR c.world = any($2)) AND d.level >= $3
                    GROUP BY d.id ORDER BY date DESC
                    """, user_id, worlds, minimum_level):
                death = DbDeath(**row)
                yield death

    @classmethod
    async def get_by_killer(cls, conn: PoolConn, killer, minimum_level=0, *, worlds: Union[List[str], str] = None):
        """Gets an asynchronous generator of recent level ups.

        :param conn: Connection to the database.
        :param killer: Name of the killer to filter deaths from.
        :param minimum_level: The minimum level to show.
        :param worlds: A list of worlds to only show deaths of characters in that world.
        :return: An asynchronous generator containing the deaths.
        """
        if isinstance(worlds, str):
            worlds = [worlds]
        if not worlds:
            worlds = []
        async with conn.transaction():
            async for row in conn.cursor("""
                        SELECT (json_agg(c)->>0)::jsonb as char, d.*, 
                        json_agg(dk)::jsonb as killers, json_agg(da)::jsonb as assists
                        FROM character_death d
                        LEFT JOIN character_death_killer dk ON dk.death_id = d.id
                        LEFT JOIN character_death_assist da ON da.death_id = d.id
                        LEFT JOIN "character" c ON c.id = d.character_id
                        WHERE lower(dk.name) SIMILAR TO $1 AND
                        (cardinality($2::text[]) = 0 OR c.world = any($2)) AND d.level >= $3
                        GROUP BY d.id ORDER BY date DESC
                        """, f"[a|an]?\\s?{killer.lower()}", worlds, minimum_level):
                death = DbDeath(**row)
                yield death

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


async def get_recent_timeline(conn: PoolConn, *, minimum_level=0, user_id=0, worlds: Union[List[str], str] = None):
    """Gets an asynchronous generator of recent deaths and level ups

    :param conn: Connection to the database.
    :param minimum_level: The minimum level to show.
    :param user_id: The id of an user to only show entries of characters they own.
    :param worlds: A list of worlds to only show entries of characters in that world.
    :return: An asynchronous generator containing the entries.
    """
    if isinstance(worlds, str):
        worlds = [worlds]
    if not worlds:
        worlds = []
    async with conn.transaction():
        async for row in conn.cursor("""
                (
                    SELECT d.*, (json_agg(c)->>0)::jsonb as char, json_agg(k)::jsonb as killers, 'd' AS type
                    FROM character_death d
                    LEFT JOIN character_death_killer k ON k.death_id = d.id
                    LEFT JOIN "character" c ON c.id = d.character_id
                    WHERE ($1::bigint = 0 OR c.user_id = $1) AND
                    (cardinality($2::text[]) = 0 OR c.world = any($2)) AND d.level >= $3
                    GROUP BY d.id
                )
                UNION
                (
                    SELECT l.*, (json_agg(c)->>0)::jsonb as char, NULL, 'l' AS type
                    FROM character_levelup l
                    LEFT JOIN "character" c ON c.id = l.character_id
                    WHERE ($1::bigint = 0 OR c.user_id = $1) AND
                    (cardinality($2::text[]) = 0 OR c.world = any($2)) AND l.level >= $3
                    GROUP BY l.id
                )
                ORDER by date DESC
                """, user_id, worlds, minimum_level):
            if row["type"] == "l":
                yield DbLevelUp(**row)
            else:
                yield DbDeath(**row)
