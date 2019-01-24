import asyncio
import datetime as dt
import logging
import pickle
import re
import time
from collections import defaultdict
from typing import List, NamedTuple, Union, Optional, Dict

import asyncpg
import discord
import tibiapy
from discord.ext import commands
from tibiapy import Death, Guild, OnlineCharacter, OtherCharacter, World

from nabbot import NabBot
from .utils import CogUtils, EMBED_LIMIT, FIELD_VALUE_LIMIT, checks, config, get_user_avatar, is_numeric, join_list, \
    online_characters, safe_delete_message
from .utils.context import NabCtx
from .utils.database import DbChar, DbDeath, DbLevelUp, get_affected_count, get_server_property, PoolConn
from .utils.errors import CannotPaginate, NetworkError
from .utils.messages import death_messages_monster, death_messages_player, format_message, level_messages, \
    split_message, weighed_choice, DeathMessageCondition, LevelCondition
from .utils.pages import Pages, VocationPages
from .utils.tibia import HIGHSCORE_CATEGORIES, NabChar, get_character, get_current_server_save_time, get_guild, \
    get_highscores, get_share_range, get_voc_abb, get_voc_emoji, get_world, tibia_worlds, normalize_vocation

log = logging.getLogger("nabbot")

# Storage used to keep a cache of guilds for watchlists
GUILD_CACHE = defaultdict(dict)  # type: defaultdict[str, Dict[str, Guild]]

WATCHLIST_SEPARATOR = "·"


class CharactersResult(NamedTuple):
    skipped: List[OtherCharacter]
    no_user: List[DbChar]
    same_owner: List[DbChar]
    different_user: List[DbChar]
    new: List[NabChar]
    all_skipped: bool


# region Database Helper classes
class Watchlist:
    """Represents a Watchlist from the database"""
    def __init__(self, **kwargs):
        self.server_id: int = kwargs.get("server_id")
        self.channel_id: int = kwargs.get("channel_id")
        self.message_id: int = kwargs.get("message_id")
        self.user_id: int = kwargs.get("user_id")
        self.show_count: bool = kwargs.get("show_count", True)
        self.created: dt.datetime = kwargs.get("created")
        # Not columns
        self.entries: List['WatchlistEntry'] = []
        self.world = None
        self.content = ""
        self.online_characters: List[OnlineCharacter] = []
        self.online_guilds: List[Guild] = []
        self.disbanded_guilds: List[str] = []
        self.description = ""

    @property
    def online_count(self) -> int:
        """Total number of online characters across entries."""
        return len(self.online_characters) + sum(g.online_count for g in self.online_guilds)

    def __repr__(self):
        return "<{0.__class__.__name__} server_id={0.server_id} channel_id={0.channel_id} message_id={0.message_id}>"\
            .format(self)

    async def add_entry(self, conn: PoolConn, name: str, is_guild: bool, user_id: int, reason: Optional[str]) ->\
            Optional['WatchlistEntry']:
        """ Adds an entry to the watchlist.

        :param conn: Connection to the database.
        :param name: Name of the character or guild.
        :param is_guild: Whether the entry is a guild or not.
        :param user_id: The user that created the entry.
        :param reason: The reason for the entry.
        :return: The new created entry or None if it already exists.
        """
        try:
            return await WatchlistEntry.insert(conn, self.channel_id, name, is_guild, user_id, reason)
        except asyncpg.UniqueViolationError:
            return None

    async def get_entries(self, conn: PoolConn) -> List['WatchlistEntry']:
        """Gets all entries in this watchlist.

        :param conn: Connection to the database.
        :return: List of entries if any.
        """
        return await WatchlistEntry.get_entries_by_channel(conn, self.channel_id)

    async def update_message_id(self, conn: PoolConn, message_id: int):
        """Update's the message id.

        :param conn: Connection to the database.
        :param message_id: The new message id.
        """
        await conn.execute("UPDATE watchlist SET message_id = $1 WHERE channel_id = $2", message_id, self.channel_id)
        self.message_id = message_id

    async def update_show_count(self, conn: PoolConn, show_count: bool):
        """Update's the show_count property.

        If the property is True, the number of online entries will be shown in the channel's name.

        :param conn: Connection to the database.
        :param show_count: The property's new value.
        """
        await conn.execute("UPDATE watchlist SET show_count = $1 WHERE channel_id = $2", show_count, self.channel_id)
        self.show_count = show_count

    @classmethod
    async def insert(cls, conn: PoolConn, server_id: int, channel_id: int, user_id: int) -> 'Watchlist':
        """Adds a new watchlist to the database.

        :param conn: Connection to the database.
        :param server_id: The discord guild's id.
        :param channel_id: The channel's id.
        :param user_id: The user that created the watchlist.
        :return: The created watchlist.
        """
        row = await conn.fetchrow("INSERT INTO watchlist(server_id, channel_id, user_id) VALUES($1,$2,$3) RETURNING *",
                                  server_id, channel_id, user_id)
        return cls(**row)

    @classmethod
    async def get_by_channel_id(cls, conn: PoolConn, channel_id: int) -> Optional['Watchlist']:
        """Gets a watchlist corresponding to the channel id.

        :param conn: Connection to the database.
        :param channel_id: The id of the channel.
        :return: The found watchlist, if any."""
        row = await conn.fetchrow("SELECT * FROM watchlist WHERE channel_id = $1", channel_id)
        if row is None:
            return None
        return cls(**row)

    @classmethod
    async def get_by_world(cls, conn: PoolConn, world: str) -> List['Watchlist']:
        """
        Gets all watchlist from a Tibia world.

        :param conn: Connection to the database.
        :param world: The name of the world.
        :return: A list of watchlists from the world.
        """
        query = """SELECT t0.* FROM watchlist t0
                   LEFT JOIN server_property t1 ON t1.server_id = t0.server_id AND key = 'world'
                   WHERE value ? $1"""
        rows = await conn.fetch(query, world)
        return [cls(**row) for row in rows]

    @classmethod
    def sort_by_voc_and_level(cls):
        """Sorting function to order by vocation and then by level."""
        return lambda char: (normalize_vocation(char.vocation), -char.level)


class WatchlistEntry:
    """Represents a watchlist entry."""
    def __init__(self, **kwargs):
        self.channel_id: int = kwargs.get("channel_id")
        self.name: str = kwargs.get("name")
        self.is_guild: bool = kwargs.get("is_guild", False)
        self.reason: Optional[str] = kwargs.get("reason")
        self.user_id: int = kwargs.get("user_id")
        self.created: dt.datetime = kwargs.get("created")

    async def remove(self, conn: PoolConn):
        """Removes a watchlist entry from the database.

        :param conn: Connection to the database.
        """
        await self.delete(conn, self.channel_id, self.name, self.is_guild)

    @classmethod
    async def delete(cls, conn: PoolConn, channel_id: int, name: str, is_guild: bool):
        """

        :param conn: Connection to the databse.
        :param channel_id: The id of the watchlist's channel.
        :param name: The name of the entry.
        :param is_guild: Whether the entry is a guild or a character.
        """
        await conn.execute("DELETE FROM watchlist_entry WHERE channel_id = $1 AND lower(name) = $2 AND is_guild = $3",
                           channel_id, name.lower().strip(), is_guild)

    @classmethod
    async def get_by_name(cls, conn: PoolConn, channel_id: int, name: str, is_guild: bool) -> \
            Optional['WatchlistEntry']:
        """Gets an entry by its name.

        :param conn: Connection to the database.
        :param channel_id: The id of the channel.
        :param name: Name of the entry.
        :param is_guild: Whether the entry is a guild or a character.
        :return: The entry if found.
        """
        row = await conn.fetchrow("SELECT * FROM watchlist_entry "
                                  "WHERE channel_id = $1 AND lower(name) = $2 AND is_guild = $3",
                                  channel_id, name.lower().strip(), is_guild)
        if row is None:
            return None
        return cls(**row)

    @classmethod
    async def get_entries_by_channel(cls, conn, channel_id) -> List['WatchlistEntry']:
        """Gets entries related to a watchlist channel.

        :param conn: Connection to the database.
        :param channel_id: Id of the channel.
        :return: A list of entries corresponding to the channel.
        """
        rows = await conn.fetch("SELECT * FROM watchlist_entry WHERE channel_id = $1", channel_id)
        return [cls(**row) for row in rows]

    @classmethod
    async def insert(cls, conn: PoolConn, channel_id: int, name: str, is_guild: bool, user_id: int, reason=None)\
            -> Optional['WatchlistEntry']:
        """Inserts a watchlist entry into the database.

        :param conn: Connection to the database.
        :param channel_id: The id of the watchlist's channel.
        :param name: Name of the entry.
        :param is_guild:  Whether the entry is a guild or a character.
        :param user_id: The id of the user that added the entry.
        :param reason: The reason for the entry.
        :return: The inserted entry.
        """
        row = await conn.fetchrow("INSERT INTO watchlist_entry(channel_id, name, is_guild, reason, user_id) "
                                  "VALUES($1, $2, $3, $4, $5) RETURNING *", channel_id, name, is_guild, reason, user_id)
        if row is None:
            return None
        return cls(**row)

# endregion


class Tracking(CogUtils):
    """Commands related to NabBot's tracking system."""

    def __init__(self, bot: NabBot):
        self.bot = bot
        self.scan_online_chars_task = bot.loop.create_task(self.scan_online_chars())
        self.scan_highscores_task = bot.loop.create_task(self.scan_highscores())
        self.world_tasks = {}

        self.world_times = {}

    # region Tasks
    async def scan_deaths(self, world):
        """Iterates through online characters, checking if they have new deaths.

        This task is created for every tracked world.
        On every iteration, the last element is checked and reinserted at the beginning."""
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        tag = f"{self.tag}[{world}][scan_deaths]"
        await self.bot.wait_until_ready()
        log.info(f"{tag} Started")
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(config.death_scan_interval)
                if len(online_characters[world]) == 0:
                    await asyncio.sleep(0.5)
                    continue
                skip = False
                # Pop last char in queue, reinsert it at the beginning
                current_char = online_characters[world].pop()
                if hasattr(current_char, "last_check") and time.time() - current_char.last_check < 45:
                    skip = True
                current_char.last_check = time.time()
                online_characters[world].insert(0, current_char)
                if not skip:
                    # Check for new death
                    char = await get_character(self.bot, current_char.name)
                    await self.compare_deaths(char)
                else:
                    await asyncio.sleep(0.5)
            except NetworkError:
                await asyncio.sleep(0.3)
                continue
            except asyncio.CancelledError:
                # Task was cancelled, so this is fine
                break
            except KeyError:
                continue
            except Exception as e:
                log.exception(f"{tag} Exception: {e}")
                continue

    async def scan_highscores(self):
        """Scans the highscores, storing the results in the database.

        The task checks if the last stored data is from the current server save or not."""
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        tag = f"{self.tag}[scan_highscores]"
        await self.bot.wait_until_ready()
        log.info(f"{tag} Started")
        while not self.bot.is_closed():
            if len(self.bot.tracked_worlds_list) == 0:
                # If no worlds are tracked, just sleep, worlds might get registered later
                await asyncio.sleep(10*60)
                continue
            for world in self.bot.tracked_worlds_list:
                tag = f"{self.tag}[{world}](scan_highscores)"
                world_count = 0
                if world not in tibia_worlds:
                    log.warning(f"{tag} Tracked world is no longer a valid world.")
                    await asyncio.sleep(0.1)
                try:
                    for key, values in HIGHSCORE_CATEGORIES.items():
                        # Check the last scan time, highscores are updated every server save
                        last_scan = await self.bot.pool.fetchval(
                            "SELECT last_scan FROM highscores WHERE world = $1 AND category = $2", world, key)
                        if last_scan:
                            last_scan_ss = get_current_server_save_time(last_scan)
                            current_ss = get_current_server_save_time()
                            # If the saved results are from the current server save, saving is skipped
                            if last_scan_ss >= current_ss:
                                log.debug(f"{tag} {values[0].name} | {values[1].name} | Already saved")
                                await asyncio.sleep(0.1)
                                continue
                        try:
                            highscores = await get_highscores(world, *values)
                        except NetworkError:
                            continue
                        await self.save_highscores(world, key, highscores)
                except asyncio.CancelledError:
                    # Task was cancelled, so this is fine
                    break
                except Exception:
                    log.exception(f"{tag}")
                    continue
                if world_count:
                    log.info(f"{tag} {world_count:,} entries saved.")
                await asyncio.sleep(5)
            await asyncio.sleep(60*30)

    async def scan_online_chars(self):
        """Scans tibia.com's character lists to store them locally.

        A online list per world is created, with the online registered characters.
        When a character enters the online list, their deaths are checked.
        On every cycle, their levels are compared.
        When a character leaves the online list, their levels and deaths are compared."""
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        await self.bot.wait_until_ready()
        log.info(f"{self.tag} scan_online_chars task started")
        try:
            with open("data/online_list.dat", "rb") as f:
                saved_list, timestamp = pickle.load(f)
                if (time.time() - timestamp) < config.online_list_expiration:
                    online_characters.clear()
                    online_characters.update(saved_list)
                    count = len([c for v in online_characters.values() for c in v])
                    log.info(f"{self.tag} Loaded cached online list | {count:,} players")
                else:
                    log.info(f"{self.tag} Cached online list is too old, discarding")
        except FileNotFoundError:
            pass
        except (ValueError, pickle.PickleError):
            log.info(f"{self.tag} Couldn't read cached online list.")
        while not self.bot.is_closed():
            try:
                # Pop last server in queue, reinsert it at the beginning
                current_world = tibia_worlds.pop()
                tibia_worlds.insert(0, current_world)

                if current_world.capitalize() not in self.bot.tracked_worlds_list:
                    await asyncio.sleep(0.1)
                    continue

                if time.time() - self.world_times.get(current_world.capitalize(), 0) < config.online_scan_interval:
                    await asyncio.sleep(0.2)
                    continue

                # Get online list for this server
                try:
                    world = await get_world(current_world)
                    if world is None:
                        await asyncio.sleep(0.1)
                        continue
                except NetworkError:
                    await asyncio.sleep(0.1)
                    continue
                current_world_online = world.online_players
                if len(current_world_online) == 0:
                    await asyncio.sleep(0.1)
                    continue
                log_msg = f"{self.tag}[{world.name}]"
                log.debug(f"{log_msg} Scanning online players")
                self.world_times[world.name] = time.time()
                self.bot.dispatch("world_scanned", world)
                # Save the online list in file
                with open("data/online_list.dat", "wb") as f:
                    pickle.dump((online_characters, time.time()), f, protocol=pickle.HIGHEST_PROTOCOL)
                if current_world not in online_characters:
                    online_characters[current_world] = []

                # List of characters that are now offline
                offline_list = [c for c in online_characters[current_world] if c not in current_world_online]
                for offline_char in offline_list:
                    # Check if characters got level ups when they went offline
                    log.debug(f"{log_msg} Character no longer online | {offline_char.name}")
                    online_characters[current_world].remove(offline_char)
                    try:
                        _char = await get_character(self.bot, offline_char.name)
                        await self.compare_levels(_char)
                        await self.compare_deaths(_char)
                    except NetworkError:
                        continue
                # Add new online chars and announce level differences
                for server_char in current_world_online:
                    db_char = await DbChar.get_by_name(self.bot.pool, server_char.name)
                    if db_char:
                        if server_char not in online_characters[current_world]:
                            # If the character wasn't in the online list we add them
                            # (We insert them at the beginning of the list to avoid messing with the death checks order)
                            server_char.last_check = time.time()
                            log.debug(f"{log_msg} Character added to online list | {server_char.name}")
                            online_characters[current_world].insert(0, server_char)
                            _char = await get_character(self.bot, server_char.name)
                            await self.compare_deaths(_char)
                        else:
                            # Do not check levels for characters that were just added.
                            await self.compare_levels(server_char)
                        try:
                            # Update character in the list
                            _char_index = online_characters[current_world].index(server_char)
                            online_characters[current_world][_char_index].level = server_char.level
                        except NetworkError:
                            continue
                        except (ValueError, IndexError):
                            continue
            except asyncio.CancelledError:
                # Task was cancelled, so this is fine
                break
            except Exception:
                log.exception("scan_online_chars")
                continue
    # endregion

    # region Custom Events
    async def on_world_scanned(self, scanned_world: World):
        """Event called each time a world is checked.

        Updates the watchlists

        :param scanned_world: The scanned world's information.
        """
        # Schedule Scan Deaths task for this world
        if scanned_world.name not in self.world_tasks:
            self.world_tasks[scanned_world.name] = self.bot.loop.create_task(self.scan_deaths(scanned_world.name))

        GUILD_CACHE[scanned_world.name].clear()
        await self._run_watchlist(scanned_world)

    async def _run_watchlist(self, scanned_world: World):
        watchlists = await Watchlist.get_by_world(self.bot.pool, scanned_world.name)
        for watchlist in watchlists:
            watchlist.world = scanned_world.name
            log.debug(f"{self.tag}[{scanned_world.name}] Checking entries for watchlist | "
                      f"Guild ID: {watchlist.server_id} | Channel ID: {watchlist.channel_id} "
                      f"| World: {scanned_world.name}")
            guild: discord.Guild = self.bot.get_guild(watchlist.server_id)
            if guild is None:
                await asyncio.sleep(0.01)
                continue
            discord_channel: discord.TextChannel = guild.get_channel(watchlist.channel_id)
            if discord_channel is None:
                await asyncio.sleep(0.1)
                continue
            watchlist.entries = await watchlist.get_entries(self.bot.pool)
            if not watchlist.entries:
                await asyncio.sleep(0.1)
                continue
            await self._watchlist_scan_entries(watchlist, scanned_world)
            await self._watchlist_build_content(watchlist)
            await self._watchlist_update_content(watchlist, discord_channel)

    async def _watchlist_scan_entries(self, watchlist: Watchlist, scanned_world: World):
        for entry in watchlist.entries:
            if entry.is_guild:
                await self._watchlist_check_guild(watchlist, entry)
            # If it is a character, check if he's in the online list
            else:
                self._watchlist_add_characters(watchlist, entry, scanned_world)
        watchlist.online_characters.sort(key=Watchlist.sort_by_voc_and_level())

    @classmethod
    async def _watchlist_check_guild(cls, watchlist, watched_guild: WatchlistEntry):
        try:
            tibia_guild = await cls.cached_get_guild(watched_guild.name, watchlist.world)
        except NetworkError:
            return
        # Save disbanded guilds separately
        if tibia_guild is None:
            watchlist.disbanded_guilds.append(watched_guild.name)
            return
        # If there's at least one member online, add guild to list
        if tibia_guild.online_count:
            watchlist.online_guilds.append(tibia_guild)

    @staticmethod
    def _watchlist_add_characters(watchlist, watched_char: WatchlistEntry, scanned_world: World):
        for online_char in scanned_world.online_players:
            if online_char.name == watched_char.name:
                # Add to online list
                watchlist.online_characters.append(online_char)
                return

    @staticmethod
    def _watchlist_get_msg_entries(characters):
        return [f"\t{char.name} - Level {char.level} {get_voc_emoji(char.vocation)}" for char in characters]

    async def _watchlist_build_content(self, watchlist):
        if watchlist.online_count > 0:
            msg_entries = self._watchlist_get_msg_entries(watchlist.online_characters)
            watchlist.content = "\n".join(msg_entries)
            self._watchlist_build_guild_content(watchlist)
        else:
            watchlist.description = "There are no watched characters online."

    def _watchlist_build_guild_content(self, watchlist):
        for guild_name in watchlist.disbanded_guilds:
            watchlist.content += f"\n__Guild: **{guild_name}**__\n"
            watchlist.content += "\t*Guild was disbanded.*"
        for tibia_guild in watchlist.online_guilds:
            watchlist.content += f"\n__Guild: **{tibia_guild.name}**__\n"
            online_members = tibia_guild.online_members[:]
            online_members.sort(key=Watchlist.sort_by_voc_and_level())
            watchlist.content += "\n".join(self._watchlist_get_msg_entries(online_members))

    async def _watchlist_update_content(self, watchlist: Watchlist, channel: discord.TextChannel):
        # Send new watched message or edit last one
        embed = discord.Embed(description=watchlist.description, timestamp=dt.datetime.utcnow())
        embed.set_footer(text="Last updated")
        if watchlist.content:
            if len(watchlist.content) >= EMBED_LIMIT - 50:
                watchlist.content = split_message(watchlist.content, EMBED_LIMIT - 50)[0]
                watchlist.content += "\n*And more...*"
            fields = split_message(watchlist.content, FIELD_VALUE_LIMIT)
            for s, split_field in enumerate(fields):
                name = "Watchlist" if s == 0 else "\u200F"
                embed.add_field(name=name, value=split_field, inline=False)
        try:
            await self._watchlist_update_message(self.bot.pool, watchlist, channel, embed)
            await self._watchlist_update_name(watchlist, channel)
        except discord.HTTPException:
            log.exception("wathchlist")

    @staticmethod
    async def _watchlist_update_name(watchlist: Watchlist, channel: discord.TextChannel):
        original_name = channel.name.split(WATCHLIST_SEPARATOR, 1)[0]
        if original_name != channel.name and not watchlist.show_count:
            await channel.edit(name=original_name, reason="Removing online count")
        elif watchlist.show_count:
            new_name = f"{original_name}{WATCHLIST_SEPARATOR}{watchlist.online_count}"
            # Reduce unnecessary API calls and Audit log spam
            if new_name != channel.name:
                await channel.edit(name=new_name, reason="Online count changed")

    @staticmethod
    async def _watchlist_update_message(conn, watchlist, channel, embed):
        # We try to get the watched message, if the bot can't find it, we just create a new one
        # This may be because the old message was deleted or this is the first time the list is checked
        try:
            message = await channel.get_message(watchlist.message_id)
        except discord.HTTPException:
            message = None
        if message is None:
            new_message = await channel.send(embed=embed)
            await watchlist.update_message_id(conn, new_message.id)
        else:
            await message.edit(embed=embed)

    # endregion

    # region Discord Events
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Called when a guild channel is deleted.

        Deletes associated watchlist and entries."""
        if not isinstance(channel, discord.TextChannel):
            return
        result = await self.bot.pool.execute("DELETE FROM watchlist_entry WHERE channel_id = $1", channel.id)
        deleted_entries = get_affected_count(result)
        result = await self.bot.pool.execute("DELETE FROM watchlist WHERE channel_id = $1", channel.id)
        deleted = get_affected_count(result)
        if deleted:
            # Dispatch event so ServerLog cog can handle it.
            log.info(f"{self.tag} Watchlist channel deleted | Channel {channel.id} | Guild {channel.guild.id}")
            self.bot.dispatch("watchlist_deleted", channel, deleted_entries)

    # endregion

    # region Commands
    @checks.server_mod_only()
    @checks.tracking_world_only()
    @commands.command(name="addchar", aliases=["registerchar"], usage="<user>,<character>")
    async def add_char(self, ctx: NabCtx, *, params):
        """Register a character and optionally all other visible characters to a discord user.

        This command can only be used by server moderators.

        If a character is hidden, only that character will be added. Characters in other worlds are skipped."""
        params = params.split(",")
        if len(params) != 2:
            raise commands.BadArgument()
        target_name, char_name = params

        target = self.bot.get_member(target_name, ctx.guild)
        if target is None:
            return await ctx.error(f"I couldn't find any users named `{target_name}`")
        if target.bot:
            return await ctx.error("You can't register characters to discord bots!")

        msg = await ctx.send(f"{config.loading_emoji} Fetching characters...")
        try:
            char = await get_character(ctx.bot, char_name)
            if char is None:
                return await msg.edit(content="That character doesn't exist.")
        except NetworkError:
            return await msg.edit(content="I couldn't fetch the character, please try again.")

        check_other = False
        if len(char.other_characters) > 1:
            message = await ctx.send("Do you want to attempt to add the other visible characters in this account?")
            check_other = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if check_other is None:
            await safe_delete_message(msg)
            return await ctx.error("You ran out of time, try again."
                                   "Remember you have to react or click on the reactions.")
        if check_other:
            await safe_delete_message(msg)
            msg = await ctx.send(f"{config.loading_emoji} Fetching characters...")

        try:
            results = await self.check_char_availability(ctx, ctx.author.id, char, [ctx.world], check_other)
        except NetworkError:
            return await msg.edit("I'm having network issues, please try again.")

        if results.all_skipped:
            await safe_delete_message(msg)
            await ctx.error(f"Sorry, I couldn't find any characters in **{ctx.world}**.")
            return

        reply = await self.process_character_assignment(ctx, results, target, ctx.author)
        await safe_delete_message(msg)
        await ctx.send(reply)

    @commands.command()
    @checks.tracking_world_somewhere()
    async def claim(self, ctx: NabCtx, *, char_name: str = None):
        """Claims a character registered as yours.

        Claims a character as yours, even if it is already registered to someone else.

        In order for this to work, you have to put a special code in the character's comment.
        You can see this code by using the command with no parameters. The code looks like this: `/NB-23FC13AC7400000/`

        Once you had set the code, you can use the command with that character, if the code matches,
        it will be reassigned to you.
        Note that it may take some time for the code to be visible to NabBot because of caching.

        This code is unique for your discord user, so the code will only work for your discord account and no one else.
        No one can claim a character of yours unless you put **their** code on your character's comment.
        """
        user = ctx.author
        claim_pattern = re.compile(r"/NB-([^/]+)/")
        user_code = hex(user.id)[2:].upper()

        # List of Tibia worlds tracked in the servers the user is
        if ctx.is_private:
            user_tibia_worlds = [ctx.world]
        else:
            user_tibia_worlds = ctx.bot.get_user_worlds(user.id)

        if not ctx.is_private and self.bot.tracked_worlds.get(ctx.guild.id) is None:
            return await ctx.send("This server is not tracking any tibia worlds.")

        if len(user_tibia_worlds) == 0:
            return

        if char_name is None:
            await ctx.send(f"To use this command, add `/NB-{user_code}/` to the comment of the character you want to"
                           f"claim, and then use `/claim character_name`.")
            return

        msg = await ctx.send(f"{config.loading_emoji} Fetching character...")
        try:
            char = await get_character(ctx.bot, char_name)
            if char is None:
                return await msg.edit(content=f"{ctx.tick(False)} That character doesn't exist.")
        except NetworkError:
            return await msg.edit(content=f"{ctx.tick(False)} I couldn't fetch the character, please try again.")

        match = claim_pattern.search(char.comment if char.comment is not None else "")
        if not match:
            await ctx.error(f"Couldn't find verification code on character's comment.\n"
                            f"Add `/NB-{user_code}/` to the comment to authenticate.")
            return
        code = match.group(1)
        if code != user_code:
            await ctx.error(f"The verification code on the character's comment doesn't match yours.\n"
                            f"Use `/NB-{user_code}/` to authenticate.")
            return

        check_other = False
        if len(char.other_characters) > 1:
            message = await ctx.send("Do you want to attempt to add the other visible characters in this account?")
            check_other = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if check_other is None:
            await safe_delete_message(msg)
            return await ctx.send("You ran out of time, try again."
                                  "Remember you have to react or click on the reactions.")
        if check_other:
            await safe_delete_message(msg)
            msg = await ctx.send(f"{config.loading_emoji} Fetching characters...")

        try:
            results = await self.check_char_availability(ctx, ctx.author.id, char, user_tibia_worlds, check_other)
        except NetworkError:
            return await msg.edit("I'm having network issues, please try again.")

        if results.all_skipped:
            reply = "Sorry, I couldn't find any characters from the worlds in the context ({0})."
            return await msg.edit(content=reply.format(join_list(user_tibia_worlds)))

        reply = await self.process_character_assignment(ctx, results, ctx.author, claim=True)
        await safe_delete_message(msg)
        await ctx.send(reply)

    @checks.tracking_world_somewhere()
    @commands.command(aliases=["i'm", "iam"])
    async def im(self, ctx: NabCtx, *, char_name: str):
        """Lets you add your tibia character(s) for the bot to track.

        If there are other visible characters, the bot will ask for confirmation to add them too.

        Characters in other worlds other than the currently tracked world are skipped.
        If it finds a character owned by another user, the whole process will be stopped.

        If a character is already registered to someone else, `claim` can be used."""
        # List of Tibia worlds tracked in the servers the user is
        if ctx.is_private:
            user_tibia_worlds = [ctx.world]
        else:
            user_tibia_worlds = ctx.bot.get_user_worlds(ctx.author.id)

        msg = await ctx.send(f"{config.loading_emoji} Fetching character...")
        try:
            char = await get_character(ctx.bot, char_name)
            if char is None:
                return await msg.edit(content=f"{ctx.tick(False)} That character doesn't exist.")
        except NetworkError:
            return await msg.edit(content=f"{ctx.tick(False)} I couldn't fetch the character, please try again.")

        check_other = False
        if len(char.other_characters) > 1:
            await msg.edit(content="Do you want to attempt to add the other visible characters in this account?")
            check_other = await ctx.react_confirm(msg, timeout=60, delete_after=True)
        if check_other is None:
            await safe_delete_message(msg)
            return await ctx.send("You didn't reply in time, try again."
                                  "Remember that you have to react or click on the icons.")
        if check_other:
            await safe_delete_message(msg)
            msg = await ctx.send(f"{config.loading_emoji} Fetching characters...")

        try:
            results = await self.check_char_availability(ctx, ctx.author.id, char, user_tibia_worlds, check_other)
        except NetworkError:
            return await msg.edit("I'm having network issues, please try again.")

        if results.all_skipped:
            reply = "Sorry, I couldn't find any characters from the worlds in the context ({0})."
            return await msg.edit(content=reply.format(join_list(user_tibia_worlds)))

        reply = await self.process_character_assignment(ctx, results, ctx.author)
        await safe_delete_message(msg)
        await ctx.send(reply)

    @checks.tracking_world_somewhere()
    @commands.command(aliases=["i'mnot"])
    async def imnot(self, ctx: NabCtx, *, name):
        """Removes a character assigned to you.

        All registered level ups and deaths will be lost forever."""
        db_char = await DbChar.get_by_name(ctx.pool, name)
        if db_char is None or db_char.user_id == 0:
            return await ctx.error("There's no character registered with that name.")
        if db_char.user_id != ctx.author.id:
            return await ctx.error(f"The character **{db_char.name}** is not registered to you.")

        message = await ctx.send(f"Are you sure you want to unregister "
                                 f"**{db_char.name}** ({abs(db_char.level)} {db_char.vocation})?")
        confirm = await ctx.react_confirm(message, timeout=50)
        if confirm is None:
            return await ctx.send("I guess you changed your mind.")
        if not confirm:
            return await ctx.send("No then? Ok.")

        await db_char.update_user(ctx.pool, 0)
        await ctx.success(f"**{db_char.name}** is no longer registered to you.")

        self.bot.dispatch("character_change", ctx.author.id)
        self.bot.dispatch("character_unregistered", ctx.author, db_char)

    @checks.can_embed()
    @checks.tracking_world_only()
    @commands.command()
    async def online(self, ctx: NabCtx):
        """Tells you which users are online on Tibia.

        This list gets updated based on Tibia.com online list, so it takes a couple minutes to be updated."""
        world = ctx.world
        per_page = 20 if await ctx.is_long() else 5
        now = dt.datetime.utcnow()
        uptime = (now - self.bot.start_time).total_seconds()
        count = 0
        entries = []
        vocations = []
        for char in online_characters.get(world, []):
            name = char.name
            db_char = await DbChar.get_by_name(ctx.pool, name)
            if not db_char:
                continue
            # Skip characters of members not in the server
            owner = ctx.guild.get_member(db_char.user_id)
            if owner is None:
                continue
            owner = owner.display_name
            emoji = get_voc_emoji(char.vocation)
            vocations.append(char.vocation.value)
            vocation = get_voc_abb(char.vocation)
            entries.append(f"{char.name} (Lvl {char.level} {vocation}{emoji}, **@{owner}**)")
            count += 1

        if count == 0:
            if uptime < 90:
                await ctx.send("I just started, give me some time to check online lists...⌛")
            else:
                await ctx.send("There is no one online from Discord.")
            return
        pages = VocationPages(ctx, entries=entries, vocations=vocations, per_page=per_page)
        pages.embed.title = "Users online"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command(name="searchteam", aliases=["whereteam", "findteam"], usage="<params>")
    @checks.tracking_world_only()
    @checks.can_embed()
    async def search_team(self, ctx: NabCtx, *, params=None):
        """Searches for a registered character that meets the criteria

        There are 3 ways to use this command:

        - Show characters in share range with a specific character. (`searchteam <name>`)
        - Show characters in share range with a specific level. (`searchteam <level>`)
        - Show characters in a level range. (`searchteam <min>,<max>`)

        Online characters are shown first on the list, they also have an icon."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        invalid_arguments = "Invalid arguments used, examples:\n" \
                            "```/searchteam charname\n" \
                            "/searchteam level\n" \
                            "/searchteam minlevel,maxlevel```"

        if ctx.world is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        if params is None:
            await ctx.send(invalid_arguments)
            return

        entries = []
        vocations = []
        online_entries = []
        online_vocations = []

        per_page = 20 if await ctx.is_long() else 5

        char = None
        params = params.split(",")
        if len(params) < 1 or len(params) > 2:
            await ctx.send(invalid_arguments)
            return

        # params[0] could be a character's name, a character's level or one of the level ranges
        # If it's not a number, it should be a player's name
        if not is_numeric(params[0]):
            # We shouldn't have another parameter if a character name was specified
            if len(params) == 2:
                await ctx.send(invalid_arguments)
                return
            char = await get_character(ctx.bot, params[0])
            if char is None:
                await ctx.send("I couldn't find a character with that name.")
                return
            low, high = get_share_range(char.level)
            title = f"Characters in share range with {char.name}({low}-{high}):"
            empty = f"I didn't find anyone in share range with **{char.name}**({low}-{high})"
        else:
            # Check if we have another parameter, meaning this is a level range
            if len(params) == 2:
                try:
                    level1 = int(params[0])
                    level2 = int(params[1])
                except ValueError:
                    await ctx.send(invalid_arguments)
                    return
                if level1 <= 0 or level2 <= 0:
                    await ctx.send("You entered an invalid level.")
                    return
                low = min(level1, level2)
                high = max(level1, level2)
                title = f"Characters between level {low} and {high}"
                empty = f"I didn't find anyone between levels **{low}** and **{high}**"
            # We only got a level, so we get the share range for it
            else:
                if int(params[0]) <= 0:
                    await ctx.send("You entered an invalid level.")
                    return
                low, high = get_share_range(int(params[0]))
                title = f"Characters in share range with level {params[0]} ({low}-{high})"
                empty = f"I didn't find anyone in share range with level **{params[0]}** ({low}-{high})"

        async with ctx.pool.acquire() as conn:
            count = 0
            online_list = [x.name for v in online_characters.values() for x in v]
            async for db_char in DbChar.get_chars_in_range(conn, low, high, ctx.world):
                if char is not None and char.name == db_char.name:
                    continue
                owner = ctx.guild.get_member(db_char.user_id)
                if owner is None:
                    continue
                count += 1
                owner = owner.display_name
                emoji = get_voc_emoji(db_char.vocation)
                voc_abb = get_voc_abb(db_char.vocation)
                entry = f"**{db_char.name}** - Level {abs(db_char.level)} {voc_abb}{emoji} - @**{owner}**"
                if db_char.name in online_list:
                    entry = f"{config.online_emoji}{entry}"
                    online_entries.append(entry)
                    online_vocations.append(db_char.vocation)
                else:
                    entries.append(entry)
                    vocations.append(db_char.vocation)
            if count < 1:
                await ctx.send(empty)
                return
        pages = VocationPages(ctx, entries=online_entries + entries, per_page=per_page,
                              vocations=online_vocations + vocations)
        pages.embed.title = title
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.server_mod_only()
    @checks.tracking_world_only()
    @commands.command(name="removechar", aliases=["deletechar", "unregisterchar"])
    async def remove_char(self, ctx: NabCtx, *, name):
        """Removes a registered character from someone.

        This can only be used by server moderators.

        Note that you can only remove chars if they are from users exclusively in your server.
        You can't remove any characters that would alter other servers NabBot is in."""
        # This could be used to remove deleted chars so we don't need to check anything
        # Except if the char exists in the database...
        db_char = await DbChar.get_by_name(ctx.pool, name.strip())
        if db_char is None or db_char.user_id == 0:
            return await ctx.error("There's no character with that name registered.")
        if db_char.world != ctx.world:
            return await ctx.error(f"The character **{db_char.name}** is in a different world.")

        user = self.bot.get_user(db_char.user_id)
        if user is not None:
            user_guilds = self.bot.get_user_guilds(user.id)
            # Iterating every world where the user is, to check if it wouldn't affect other admins.
            for guild in user_guilds:
                if guild == ctx.guild:
                    continue
                if self.bot.tracked_worlds.get(guild.id, None) != ctx.world:
                    continue
                author: discord.Member = guild.get_member(ctx.author.id)
                if author is None or not author.guild_permissions.manage_guild:
                    await ctx.error(f"The user of this server is also in another server tracking "
                                    f"**{ctx.world}**, where you are not an admin. You can't alter other servers.")
                    return
        username = "unknown" if user is None else user.display_name
        await db_char.update_user(ctx.pool, 0)
        await ctx.send("**{0}** was removed successfully from **@{1}**.".format(db_char.name, username))
        self.bot.dispatch("character_unregistered", user, db_char, ctx.author)

    @checks.server_mod_only()
    @checks.tracking_world_only()
    @commands.group(invoke_without_command=True, case_insensitive=True, aliases=["huntedlist"])
    async def watchlist(self, ctx: NabCtx):
        """Create or manage watchlists.

        Watchlists are channels where the online status of selected characters are shown.
        You can create multiple watchlists and characters and guilds to each one separately.

        Try the subcommands."""
        await ctx.send("To manage watchlists, use one of the subcommands.\n"
                       f"Try `{ctx.clean_prefix}help {ctx.invoked_with}`.")

    @checks.tracking_world_only()
    @checks.channel_mod_somewhere()
    @watchlist.command(name="add", aliases=["addplayer", "addchar"], usage="<channel> <name>[,reason]")
    async def watchlist_add(self, ctx: NabCtx, channel: discord.TextChannel, *, params):
        """Adds a character to a watchlist.

        A reason can be specified by adding it after the character's name, separated by a comma."""
        watchlist = await Watchlist.get_by_channel_id(ctx.pool, channel.id)

        if not watchlist:
            return await ctx.error(f"{channel.mention} is not a watchlist channel.")

        if not channel.permissions_for(ctx.author).manage_channels:
            return await ctx.error(f"You need `Manage Channel` permissions in {channel.mention} to add entries.")

        params = params.split(",", 1)
        name = params[0]
        reason = None
        if len(params) > 1:
            reason = params[1]

        char = await get_character(ctx.bot, name)
        if char is None:
            await ctx.error("A character with that name doesn't exist.")
            return
        world = ctx.world
        if char.world != world:
            await ctx.error(f"This character is not in **{world}**.")
            return

        message = await ctx.send(f"Do you want to add **{char.name}** (Level {char.level} {char.vocation}) "
                                 f"to the watchlist {channel.mention}")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return
        entry = await watchlist.add_entry(ctx.pool, char.name, False, ctx.author.id, reason)
        if entry:
            await ctx.success(f"Character **{char.name}** added to the watchlist {channel.mention}.")
        else:
            await ctx.error(f"**{char.name}** is already registered in {channel.mention}")

    @checks.tracking_world_only()
    @checks.channel_mod_somewhere()
    @watchlist.command(name="addguild", usage="<channel> <name>[,reason]")
    async def watchlist_addguild(self, ctx: NabCtx, channel: discord.TextChannel, *, params):
        """Adds an entire guild to a watchlist.

        Guilds are displayed in the watchlist as a group."""
        watchlist = await Watchlist.get_by_channel_id(ctx.pool, channel.id)

        if not watchlist:
            return await ctx.error(f"{channel.mention} is not a watchlist channel.")

        if not channel.permissions_for(ctx.author).manage_channels:
            return await ctx.error(f"You need `Manage Channel` permissions in {channel.mention} to add entries.")

        params = params.split(",", 1)
        name = params[0]
        reason = None
        if len(params) > 1:
            reason = params[1]

        guild = await get_guild(name)
        if guild is None:
            await ctx.error("There's no guild with that name.")
            return

        if guild.world != ctx.world:
            await ctx.error(f"This guild is not in **{ctx.world}**.")
            return

        message = await ctx.send(f"Do you want to add the guild **{guild.name}** to the watchlist {channel.mention}?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return

        entry = await watchlist.add_entry(ctx.pool, guild.name, True, ctx.author.id, reason)
        if entry:
            await ctx.success(f"Guild **{guild.name}** added to the watchlist {channel.mention}.")
        else:
            await ctx.error(f"**{guild.name}** is already registered in {channel.mention}")

    @checks.tracking_world_only()
    @checks.channel_mod_somewhere()
    @watchlist.command(name="adduser", usage="<channel> <user>[,reason]")
    async def watchlist_adduser(self, ctx: NabCtx, channel: discord.TextChannel, *, params):
        """Adds the currently registered characters of a user to the watchlist.

        A reason can be specified by adding it after the character's name, separated by a comma."""
        watchlist = await Watchlist.get_by_channel_id(ctx.pool, channel.id)

        if not watchlist:
            return await ctx.error(f"{channel.mention} is not a watchlist channel.")

        if not channel.permissions_for(ctx.author).manage_channels:
            return await ctx.error(
                f"You need `Manage Channel` permissions in {channel.mention} to add entries.")

        params = params.split(",", 1)
        name = params[0]
        reason = None
        if len(params) > 1:
            reason = params[1]

        user = ctx.bot.get_member(name, ctx.guild)
        if user is None:
            await ctx.error("I don't see any users with that name.")
        characters = await DbChar.get_chars_by_user(ctx.pool, user.id, worlds=ctx.world)
        if not characters:
            await ctx.error(f"This user doesn't have any registered characters in {ctx.world}.")
            return

        char_list = "\n".join(f"• {c.name}" for c in characters)
        message = await ctx.send(f"Do you want to add currently registered characters of `{user}` to this watchlist?\n"
                                 f"{char_list}")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return

        results = ""
        for char in characters:
            entry = await watchlist.add_entry(ctx.pool, char.name, False, ctx.author.id, reason)
            if entry:
                results += f"\n• {char.name}"
        if results:
            await ctx.success(f"I added the following characters to the list {channel.mention}, "
                              f"duplicates where skipped:{results}")
        else:
            await ctx.error("No characters where added, as they were all duplicates.")

    @checks.server_mod_only()
    @checks.tracking_world_only()
    @watchlist.command(name="create")
    async def watchlist_create(self, ctx: NabCtx, *, name):
        """Creates a watchlist channel.

        Creates a new text channel for the watchlist to be posted.

        The watch list shows which characters from it are online. Entire guilds can be added too.

        The channel can be renamed at anytime. If the channel is deleted, all its entries are deleted too.
        """
        if WATCHLIST_SEPARATOR in name:
            await ctx.error(f"Channel name cannot contain the special character **{WATCHLIST_SEPARATOR}**")
            return

        if not ctx.bot_permissions.manage_channels:
            return await ctx.error(f"I need `Manage Channels` permission to use this command.")

        message = await ctx.send(f"Do you want to create a new watchlist named `{name}`?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if not confirm:
            return

        try:
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True),
                ctx.guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True)
            }
            channel = await ctx.guild.create_text_channel(name, overwrites=overwrites, category=ctx.channel.category)
        except discord.Forbidden:
            await ctx.error(f"Sorry, I don't have permissions to create channels.")
        except discord.HTTPException:
            await ctx.error(f"Something went wrong, the channel name you chose is probably invalid.")
        else:
            log.info(f"Watchlist created (Channel ID: {channel.id}, Guild ID: {channel.guild.id})")
            await ctx.success(f"Channel created successfully: {channel.mention}\n")
            await channel.send("This is where I will post a list of online watched characters.\n"
                               "Edit this channel's permissions to allow the roles you want.\n"
                               "This channel can be renamed freely.\n"
                               "Anyone with `Manage Channel` permission here can add entries.\n"
                               f"Example: {ctx.clean_prefix}{ctx.command.full_parent_name} add {channel.mention} "
                               f"Galarzaa Fidera\n"
                               "If this channel is deleted, all related entries will be lost.\n"
                               "**It is important to not allow anyone to write in here**\n"
                               "*This message can be deleted now.*")
            watchlist = await Watchlist.insert(ctx.pool, ctx.guild.id, channel.id, ctx.author.id)
            log.debug(f"{self.tag} Watchlist created | {watchlist}")

    @checks.channel_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="info", aliases=["details", "reason"])
    async def watchlist_info(self, ctx: NabCtx, channel: discord.TextChannel, *, name: str):
        """Shows information about a watchlist entry.

        This shows who added the player, when, and if there's a reason why they were added."""
        if not await Watchlist.get_by_channel_id(ctx.pool, channel.id):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        entry = await WatchlistEntry.get_by_name(ctx.pool, channel.id, name, False)
        if not entry:
            return await ctx.error(f"There's no character with that name registered to {channel.mention}.")

        embed = discord.Embed(title=entry.name, url=tibiapy.Character.get_url(entry.name), timestamp=entry.created,
                              description=f"**Reason:** {entry.reason}" if entry.reason else "No reason provided.")
        embed.set_author(name=f"In #{channel}")
        author = ctx.guild.get_member(entry.user_id)
        if author:
            embed.set_footer(text=f"Added by {author.name}#{author.discriminator}",
                             icon_url=get_user_avatar(author))
        await ctx.send(embed=embed)

    @checks.channel_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="infoguild", aliases=["detailsguild", "reasonguild"])
    async def watchlist_infoguild(self, ctx: NabCtx, channel: discord.TextChannel, *, name: str):
        """"Shows details about a guild entry in a watchlist.

        This shows who added the player, when, and if there's a reason why they were added."""
        if not await Watchlist.get_by_channel_id(ctx.pool, channel.id):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        entry = await WatchlistEntry.get_by_name(ctx.pool, channel.id, name, True)
        if not entry:
            return await ctx.error(f"There's no guild with that name registered to {channel.mention}.")

        embed = discord.Embed(title=entry.name, timestamp=entry.created, url=tibiapy.Guild.get_url(entry.name),
                              description=f"**Reason:** {entry.reason}" if entry.reason else "No reason provided.")
        embed.set_author(name=f"In #{channel}")
        author = ctx.guild.get_member(entry.user_id)
        if author:
            embed.set_footer(text=f"Added by {author.name}#{author.discriminator}",
                             icon_url=get_user_avatar(author))
        await ctx.send(embed=embed)

    @checks.tracking_world_only()
    @watchlist.command(name="list")
    async def watchlist_list(self, ctx: NabCtx, channel: discord.TextChannel):
        """Shows characters belonging to that watchlist.

        Note that this lists all characters, not just online characters."""
        if not await Watchlist.get_by_channel_id(ctx.pool, channel.id):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        if not channel.permissions_for(ctx.author).read_messages:
            return await ctx.error("You can't see the list of a watchlist you can't see.")

        entries = await WatchlistEntry.get_entries_by_channel(ctx.pool, channel.id)
        entries = [entry for entry in entries if not entry.is_guild]

        if not entries:
            return await ctx.error(f"This watchlist has no registered characters.")

        pages = Pages(ctx, entries=[f"[{r.name}]({NabChar.get_url(r.name)})" for r in entries])
        pages.embed.title = f"Watched Characters in #{channel.name}"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.error(e)

    @checks.tracking_world_only()
    @watchlist.command(name="listguilds", aliases=["guilds", "guildlist"])
    async def watchlist_list_guild(self, ctx: NabCtx, channel: discord.TextChannel):
        """Shows a list of guilds in the watchlist."""
        if not await Watchlist.get_by_channel_id(ctx.pool, channel.id):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        entries = await WatchlistEntry.get_entries_by_channel(ctx.pool, channel.id)
        entries = [entry for entry in entries if entry.is_guild]

        if not channel.permissions_for(ctx.author).read_messages:
            return await ctx.error("You can't see the list of a watchlist you can't see.")

        if not entries:
            return await ctx.error(f"This watchlist has no registered characters.")

        pages = Pages(ctx, entries=[f"[{r.name}]({Guild.get_url(r.name)})" for r in entries])
        pages.embed.title = f"Watched Guilds in #{channel.name}"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.error(e)

    @checks.channel_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="remove", aliases=["removeplayer", "removechar"])
    async def watchlist_remove(self, ctx: NabCtx, channel: discord.TextChannel, *, name):
        """Removes a character from a watchlist."""
        if not await Watchlist.get_by_channel_id(ctx.pool, channel.id):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        entry = await WatchlistEntry.get_by_name(ctx.pool, channel.id, name, False)
        if entry is None:
            return await ctx.error(f"There's no character with that name registered in {channel.mention}.")

        message = await ctx.send(f"Do you want to remove **{name}** from this watchlist?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return
        await entry.remove(ctx.pool)
        await ctx.success("Character removed from the watchlist.")

    @checks.channel_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="removeguild")
    async def watchlist_removeguild(self, ctx: NabCtx, channel: discord.TextChannel, *, name):
        """Removes a guild from the watchlist."""
        if not await Watchlist.get_by_channel_id(ctx.pool, channel.id):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        entry = await WatchlistEntry.get_by_name(ctx.pool, channel.id, name, True)
        if entry is None:
            return await ctx.error(f"There's no guild with that name registered in {channel.mention}.")

        message = await ctx.send(f"Do you want to remove **{name}** from this watchlist?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return
        await entry.remove(ctx.pool)
        await ctx.success("Guild removed from the watchlist.")

    @checks.channel_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="showcount", usage="<channel> <yes|no>")
    async def watchlist_showcount(self, ctx: NabCtx, channel: discord.TextChannel, yes_no):
        """Changes whether the online count will be displayed in the watchlist's channel's name or not."""
        watchlist = await Watchlist.get_by_channel_id(ctx.pool, channel.id)
        if not watchlist:
            return await ctx.error(f"{channel.mention} is not a watchlist.")
        if yes_no.lower().strip() == ["yes", "true"]:
            await watchlist.update_show_count(ctx.pool, True)
            await ctx.success("Showing online count is now enabled. The name will be updated on the next cycle.")
        elif yes_no.lower().strip() == ["no", "false"]:
            await watchlist.update_show_count(ctx.pool, False)
            await ctx.success("Showing online count is now disabled. The name will be updated on the next cycle.")
        else:
            await ctx.error("That's not a valid option, try `yes` or `no`.")
    # endregion

    # region Methods
    async def announce_death(self, char: NabChar, death: Death, levels_lost=0):
        """Announces a level up on the corresponding servers."""
        log_msg = f"{self.tag}[{char.world}] announce_death: {char.name} | {death.level} | {death.killer.name}"
        # Find killer article (a/an)
        killer_article = ""
        if not death.by_player:
            killer_article = death.killer.name.split(" ", 1)
            if killer_article[0] in ["a", "an"] and len(killer_article) > 1:
                death.killer.name = killer_article[1]
                killer_article = killer_article[0] + " "
            else:
                killer_article = ""

        if death.killer.name.lower() in ["death", "energy", "earth", "fire", "pit battler", "pit berserker",
                                         "pit blackling",
                                         "pit brawler", "pit condemned", "pit demon", "pit destroyer", "pit fiend",
                                         "pit groveller", "pit grunt", "pit lord", "pit maimer", "pit overlord",
                                         "pit reaver",
                                         "pit scourge"] and levels_lost == 0:
            # Skip element damage deaths unless player lost a level to avoid spam from arena deaths
            # This will cause a small amount of deaths to not be announced but it's probably worth the tradeoff
            log.debug(f"{log_msg} | Skipping arena death")
            return

        guilds = [s for s, w in self.bot.tracked_worlds.items() if w == char.world]
        for guild_id in guilds:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            min_level = await get_server_property(self.bot.pool, guild_id, "announce_level", config.announce_threshold)
            if death.level < min_level:
                log.debug(f"{log_msg} | Guild skipped {guild_id} | Level under limit")
                continue
            if guild.get_member(char.owner_id) is None:
                log.debug(f"{log_msg} | Guild skipped  {guild_id} | Owner not in server")
                continue
            condition = DeathMessageCondition(char=char, death=death, levels_lost=levels_lost, min_level=min_level)
            # Select a message
            if death.by_player:
                message = weighed_choice(death_messages_player, condition)
            else:
                message = weighed_choice(death_messages_monster, condition)
            # Format message with death information
            death_info = {'name': char.name, 'level': death.level, 'killer': death.killer.name,
                          'killer_article': killer_article, 'he_she': char.he_she.lower(),
                          'his_her': char.his_her.lower(), 'him_her': char.him_her.lower()}
            message = message.format(**death_info)
            # Format extra stylization
            message = f"{config.pvpdeath_emoji if death.by_player else config.death_emoji} {format_message(message)}"
            channel_id = await get_server_property(self.bot.pool, guild.id, "levels_channel")
            channel = self.bot.get_channel_or_top(guild, channel_id)
            try:
                await channel.send(message[:1].upper() + message[1:])
                log.debug(f"{log_msg} | Announced in {guild_id}")
            except discord.Forbidden:
                log.warning(f"{log_msg} | Forbidden error | Channel {channel.id} | Server {guild.id}")
            except discord.HTTPException:
                log.exception(f"{log_msg}")

    async def announce_level(self, char: NabChar, level: int):
        """Announces a level up on corresponding servers."""
        log_msg = f"{self.tag}[{char.world}] announce_level: : {char.name} | {level}"
        guilds = [s for s, w in self.bot.tracked_worlds.items() if w == char.world]
        for guild_id in guilds:
            guild: discord.Guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            min_level = await get_server_property(self.bot.pool, guild_id, "announce_level", config.announce_threshold)
            if char.level < min_level:
                log.debug(f"{log_msg} | Guild skipped {guild_id} | Level under limit")
                continue
            if guild.get_member(char.owner_id) is None:
                log.debug(f"{log_msg} | Guild skipped  {guild_id} | Owner not in server")
                continue
            channel_id = await get_server_property(self.bot.pool, guild.id, "levels_channel")
            channel = self.bot.get_channel_or_top(guild, channel_id)
            try:
                # Select a message
                message = weighed_choice(level_messages, LevelCondition(char=char, level=level, min_level=min_level))
                level_info = {'name': char.name, 'level': level, 'he_she': char.he_she.lower(),
                              'his_her': char.his_her.lower(), 'him_her': char.him_her.lower()}
                # Format message with level information
                message = message.format(**level_info)
                # Format extra stylization
                message = f"{config.levelup_emoji} {format_message(message)}"
                await channel.send(message)
                log.debug(f"{log_msg} | Announced in {guild_id}")
            except discord.Forbidden:
                log.warning(f"{log_msg} | Forbidden error | Channel {channel.id} | Server {guild.id}")
            except discord.HTTPException:
                log.exception(f"{log_msg}")

    async def compare_deaths(self, char: NabChar):
        """Checks if the player has new deaths.

        New deaths are announced if they are not older than 30 minutes."""
        if char is None:
            return
        async with self.bot.pool.acquire() as conn:
            db_char = await DbChar.get_by_name(conn, char.name)
            if db_char is None:
                return
            pending_deaths = []
            for death in char.deaths:
                # Check if we have a death that matches the time
                exists = await DbDeath.exists(conn, db_char.id, death.level, death.time)
                if exists:
                    # We already have this death, we're assuming we already have older deaths
                    break
                pending_deaths.append(death)
            # Announce and save deaths from older to new
            for death in reversed(pending_deaths):
                db_death = DbDeath.from_tibiapy(death)
                db_death.character_id = db_char.id
                await db_death.save(conn)
                log_msg = f"{self.tag}[{char.world}] Death detected: {char.name} | {death.level} |" \
                    f" {death.killer.name}"
                if (dt.datetime.now(dt.timezone.utc)- death.time) >= dt.timedelta(minutes=30):
                    log.info(f"{log_msg} | Too old to announce.")
                # Only try to announce if character has an owner
                elif char.owner_id:
                    log.info(log_msg)
                    await self.announce_death(char, death, max(death.level - char.level, 0))


    @staticmethod
    async def cached_get_guild(guild_name: str, world: str) -> Optional[Guild]:
        """
        Used to cache guild info, to avoid fetching the same guild multiple times if they are in multiple lists
        """
        if guild_name in GUILD_CACHE[world]:
            return GUILD_CACHE[world][guild_name]
        guild = await get_guild(guild_name)
        GUILD_CACHE[world][guild_name] = guild
        return guild

    @classmethod
    async def check_char_availability(cls, ctx: NabCtx, user_id: int, char: NabChar, worlds: List[str],
                                      check_other=False):
        """Checks the availability of a character and other visible characters optionally.

        :param ctx: The command context where this is called.
        :param user_id: The id of the user against which the characters will be checked for.
        :param char: The character to be checked.
        :param worlds: The worlds to filter characters from.
        :param check_other: Whether other characters in the same account should be processed to or not.
        :return: A named tuple containing the different categories of characters found.
        """
        skipped = []  # type: List[OtherCharacter]
        """Characters that were skipped due to being in another world or scheduled for deletion."""
        no_user = []  # type: List[DbChar]
        """Characters that belong to users no longer visible to NabBot, most of the time abandoned temporal users."""
        same_owner = []  # type: List[DbChar]
        """Characters that already belong to the user."""
        different_user = []  # type: List[DbChar]
        """Characters belonging to a different user."""
        unregistered = []  # type: List[NabChar]
        """Characters that have never been registered."""
        if check_other and not char.hidden:
            chars: List[Union[OtherCharacter, NabChar]] = char.other_characters
            _char = next((x for x in chars if x.name == char.name))
            chars[chars.index(_char)] = char
        else:
            chars = [char]

        for char in chars:
            if char.world not in worlds or char.deleted:
                skipped.append(char)
                continue
            db_char = await DbChar.get_by_name(ctx.pool, char.name)
            if db_char:
                owner = ctx.bot.get_user(db_char.user_id)
                if owner is None:
                    no_user.append(db_char)
                    continue
                elif db_char.user_id == user_id:
                    same_owner.append(db_char)
                    continue
                different_user.append(db_char)
                continue
            if isinstance(char, OtherCharacter):
                char = await get_character(ctx.bot, char.name)
            unregistered.append(char)
        return CharactersResult._make((skipped, no_user, same_owner, different_user, unregistered,
                                       len(skipped) == len(chars)))

    @classmethod
    async def process_character_assignment(cls, ctx: NabCtx, results: CharactersResult, user: discord.User,
                                           author: discord.User = None, claim=False):
        """Processes the results of a character check and applies the changes

        :param ctx: The command context
        :param results: The character results
        :param user:  The user that will get the characters assigned.
        :param author: The user that did the action, None if it was the same user.
        :param claim: Whether the operation is a claim.
        :return: A summary of the applied actions.
        """
        recipient = f"**@{user.display_name}**" if author else "you"
        author_log = f"| By {author}" if author else ""

        reply = ""
        if results.different_user and not claim:
            first = results.different_user[0].name
            reply = f"{ctx.tick(False)} Sorry, a character in that account ({first}) is already registered to " \
                f"someone else.\n" \
                f"If the character really belongs to {recipient}, `{ctx.clean_prefix}claim {first}` should be used."
            return reply

        if results.same_owner:
            existent_names = [e.name for e in results.same_owner]
            reply += f"\n⚫ The following characters were already registered to {recipient}: {join_list(existent_names)}"

        if results.new:
            added_names = [a.name for a in results.new]
            reply += f"\n🔵 The following characters were added to {recipient}: {join_list(added_names)}"

        if results.no_user:
            updated_names = [r.name for r in results.no_user]
            reply += f"\n⚪ The following characters were reassigned to {recipient}: {join_list(updated_names)}"

        if results.different_user:
            reclaimed_chars = [c.name for c in results.different_user]
            reply += f"\n🔴 The following characters were reclaimed by you: {join_list(reclaimed_chars)}"

        async with ctx.pool.acquire() as conn:
            for char in results.different_user:
                await char.update_user(conn, user.id)
                log.info(f"{cls.get_tag()} Character Claimed | {char.name} | {user} ({user.id}){author_log}")
            for char in results.no_user:
                await char.update_user(conn, user.id)
                log.info(f"{cls.get_tag()} Character Reassigned | {char.name} | {user} ({user.id}){author_log}")
            for char in results.new:
                db_char = await DbChar.insert(conn, char.name, char.level, char.vocation.value, user.id, char.world,
                                              char.guild_name)
                char.id = db_char.id
                log.info(f"{cls.get_tag()} Character Registered | {char.name} | {user} ({user.id}){author_log}")
        # If we are claiming, different user characters are also passed
        if claim:
            results.no_user.extend(results.different_user)
        ctx.bot.dispatch("characters_registered", user, results.new, results.no_user, author)
        ctx.bot.dispatch("character_change", user.id)
        return reply

    async def compare_levels(self, char: Union[NabChar, OnlineCharacter]):
        """Compares the character's level with the stored level in database.

        This should only be used on online characters or characters that just became offline."""
        if char is None:
            return
        async with self.bot.pool.acquire() as conn:
            db_char = await DbChar.get_by_name(conn, char.name)
            if not db_char:
                return
            # OnlineCharacter has no sex attribute, so we get it from database and convert to NabChar
            if isinstance(char, OnlineCharacter):
                char = NabChar.from_online(char, db_char.sex, db_char.user_id)
            await db_char.update_level(conn, char.level, False)
            if not (char.level > db_char.level > 0):
                return
            # Saving level up date in database
            await DbLevelUp.insert(conn, db_char.id, char.level)
        # Announce the level up
        log.info(f"{self.tag}[{char.world}] Level up detected: {char.name} | {char.level}")
        # Only try to announce level if char has an owner.
        if char.owner_id:
            await self.announce_level(char, char.level)
        else:
            log.debug(f"{self.tag}[{char.world}] Character has no owner, skipping")

    async def save_highscores(self, world: str, key: str, highscores: tibiapy.Highscores) -> int:
        """Saves the highscores of a world and category to the database."""
        if highscores is None:
            return 0
        rows = [(e.rank, key, world, e.name, e.vocation.value, e.value) for e in highscores.entries]
        async with self.bot.pool.acquire() as conn:  # type: asyncpg.Connection
            async with conn.transaction():
                # Delete old records
                await conn.execute("DELETE FROM highscores_entry WHERE category = $1 AND world = $2", key, world)
                # Add current entries
                await conn.copy_records_to_table("highscores_entry", records=rows,
                                                 columns=["rank", "category", "world", "name", "vocation", "value"])
                log.debug(f"{self.tag}[{world}][save_highscores] {key} | {len(rows)} entries saved")
                # Update scan times
                await conn.execute("""INSERT INTO highscores(world, category, last_scan)
                                      VALUES($1, $2, $3)
                                      ON CONFLICT (world,category)
                                      DO UPDATE SET last_scan = EXCLUDED.last_scan""",
                                   world, key, dt.datetime.now(dt.timezone.utc))
                return len(rows)
    # endregion

    def __unload(self):
        log.info(f"{self.tag} Unloading cog")
        self.scan_highscores_task.cancel()
        self.scan_online_chars_task.cancel()


def setup(bot):
    bot.add_cog(Tracking(bot))
