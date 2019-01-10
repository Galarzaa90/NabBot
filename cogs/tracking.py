import asyncio
import datetime as dt
import logging
import pickle
import re
import time
from typing import List, NamedTuple, Union

import asyncpg
import discord
from discord.ext import commands
from tibiapy import Death, Guild, OnlineCharacter, OtherCharacter, World

from nabbot import NabBot
from .utils import CogUtils, EMBED_LIMIT, FIELD_VALUE_LIMIT, config, get_user_avatar, is_numeric, join_list, \
    online_characters, safe_delete_message
from .utils import checks
from .utils.context import NabCtx
from .utils.database import DbChar, DbDeath, DbLevelUp, get_affected_count, get_server_property
from .utils.errors import CannotPaginate, NetworkError
from .utils.messages import death_messages_monster, death_messages_player, format_message, level_messages, \
    split_message, weighed_choice
from .utils.pages import Pages, VocationPages
from .utils.tibia import ERROR_NETWORK, HIGHSCORE_CATEGORIES, NabChar, get_character, \
    get_guild, get_highscores, get_share_range, get_tibia_time_zone, get_voc_abb, get_voc_emoji, get_world, \
    tibia_worlds, normalize_vocation

log = logging.getLogger("nabbot")


class CharactersResult(NamedTuple):
    skipped: List[OtherCharacter]
    no_user: List[DbChar]
    same_owner: List[DbChar]
    different_user: List[DbChar]
    new: List[NabChar]
    all_skipped: bool


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
        task_tag = f"[{world}] Task: scan_deaths |"
        await self.bot.wait_until_ready()
        log.info(f"{self.tag}{task_tag} Started")
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
            except Exception:
                log.exception(f"{self.tag}{task_tag} scan_deaths")
                continue

    async def scan_highscores(self):
        """Scans the highscores, storing the results in the database.

        The task checks if the last stored data is from the current server save or not."""
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        task_tag = f"Task: scan_highscores |"
        await self.bot.wait_until_ready()
        log.info(f"{self.tag}{task_tag} Started")
        while not self.bot.is_closed():
            if len(self.bot.tracked_worlds_list) == 0:
                # If no worlds are tracked, just sleep, worlds might get registered later
                await asyncio.sleep(config.highscores_delay)
                continue
            for world in self.bot.tracked_worlds_list:
                if world not in tibia_worlds:
                    await asyncio.sleep(0.1)
                try:
                    for category in HIGHSCORE_CATEGORIES:
                        # Check the last scan time, highscores are updated every server save
                        last_scan: dt.datetime = await self.bot.pool.fetchval(
                            "SELECT last_scan FROM highscores WHERE world = $1 AND category = $2", world, category)
                        if last_scan:
                            now = dt.datetime.now(dt.timezone.utc)
                            # Current day's server save, could be in the past or the future, an extra hour is added
                            # as margin
                            today_ss = dt.datetime.now(dt.timezone.utc).replace(hour=11 - get_tibia_time_zone())
                            if not now > today_ss > last_scan:
                                continue
                        highscore_data = []
                        for pagenum in range(1, 13):
                            # Special cases (ek/rp mls)
                            if category == "magic_ek":
                                scores = await get_highscores(world, "magic", pagenum, 1)
                            elif category == "magic_rp":
                                scores = await get_highscores(world, "magic", pagenum, 2)
                            else:
                                scores = await get_highscores(world, category, pagenum)
                            if scores == ERROR_NETWORK:
                                continue
                            for entry in scores:
                                highscore_data.append(
                                    (entry["rank"], category, world, entry["name"], entry["vocation"], entry["value"]))
                            await asyncio.sleep(config.highscores_page_delay)
                        async with self.bot.pool.acquire() as conn:
                            # Delete old records
                            await conn.execute("DELETE FROM highscores_entry WHERE category = $1 AND world = $2",
                                               category, world)
                            # Add current entries
                            await conn.executemany("""INSERT INTO highscores_entry(rank, category, world, name, 
                                                      vocation, value) 
                                                      VALUES ($1, $2, $3, $4, $5, $6)""", highscore_data)
                            # Update scan times
                            await conn.execute("""INSERT INTO highscores(world, category, last_scan)
                                                  VALUES($1, $2, $3)
                                                  ON CONFLICT (world,category)
                                                  DO UPDATE SET last_scan = EXCLUDED.last_scan""",
                                               world, category, dt.datetime.now(dt.timezone.utc))
                except asyncio.CancelledError:
                    # Task was cancelled, so this is fine
                    break
                except Exception:
                    log.exception(f"{self.tag}{task_tag}")
                    continue
                await asyncio.sleep(10)

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
        cache_guild = dict()

        async def _get_guild(guild_name):
            """
            Used to cache guild info, to avoid fetching the same guild multiple times if they are in multiple lists
            """
            if guild_name in cache_guild:
                return cache_guild[guild_name]
            _guild = await get_guild(guild_name)
            cache_guild[guild_name] = _guild
            return _guild

        # Schedule Scan Deaths task for this world
        if scanned_world.name not in self.world_tasks:
            self.world_tasks[scanned_world.name] = self.bot.loop.create_task(self.scan_deaths(scanned_world.name))
        query = """SELECT t0.server_id, channel_id, message_id FROM watchlist t0
                   LEFT JOIN server_property t1 ON t1.server_id = t0.server_id AND key = 'world'
                   WHERE value ? $1"""
        rows = await self.bot.pool.fetch(query, scanned_world.name)
        for guild_id, watchlist_channel_id, watchlist_message_id in rows:
            log.debug(f"{self.tag}[{scanned_world.name}] Checking entries for watchlist"
                      f" (Guild ID: {guild_id}, Channel ID: {watchlist_channel_id}, World: {scanned_world.name})")
            guild: discord.Guild = self.bot.get_guild(guild_id)
            if guild is None:
                await asyncio.sleep(0.01)
                continue
            watchlist_channel: discord.TextChannel = guild.get_channel(watchlist_channel_id)
            if watchlist_channel is None:
                await asyncio.sleep(0.1)
                continue
            entries = await self.bot.pool.fetch("""SELECT name, is_guild FROM watchlist_entry WHERE channel_id = $1
                                                   ORDER BY is_guild, name""", watchlist_channel_id)
            if not entries:
                await asyncio.sleep(0.1)
                continue
            # Online watched characters
            currently_online = []
            # Watched guilds
            guild_online = dict()
            for watched in entries:
                if watched["is_guild"]:
                    try:
                        tibia_guild = await _get_guild(watched["name"])
                    except NetworkError:
                        continue
                    # If the guild doesn't exist, add it as empty to show it was disbanded
                    if tibia_guild is None:
                        guild_online[watched["name"]] = None
                        continue
                    # If there's at least one member online, add guild to list
                    if tibia_guild.online_count:
                        guild_online[tibia_guild.name] = tibia_guild.online_members
                # If it is a character, check if he's in the online list
                for online_char in scanned_world.online_players:
                    if online_char.name == watched["name"]:
                        # Add to online list
                        currently_online.append(online_char)
            # We try to get the watched message, if the bot can't find it, we just create a new one
            # This may be because the old message was deleted or this is the first time the list is checked
            try:
                watchlist_message = await watchlist_channel.get_message(watchlist_message_id)
            except discord.HTTPException:
                watchlist_message = None
            currently_online.sort(key=self._sort_by_voc_and_level())
            items = self.get_watchlist_msg_entries(currently_online)
            online_count = len(items)
            if len(items) > 0 or len(guild_online.keys()) > 0:
                description = ""
                content = "\n".join(items)
                for tibia_guild, members in guild_online.items():
                    content += f"\nGuild: **{tibia_guild}**\n"
                    if members is None:
                        content += "\t*Guild was disbanded.*"
                        continue
                    members.sort(key=self._sort_by_voc_and_level())
                    content += "\n".join(self.get_watchlist_msg_entries(members))
                    online_count += len(members)
            else:
                description = "There are no watched characters online."
                content = ""
            # Send new watched message or edit last one
            embed = discord.Embed(description=description)
            embed.set_footer(text="Last updated")
            embed.timestamp = dt.datetime.utcnow()
            if content:
                if len(content) >= EMBED_LIMIT - 50:
                    content = split_message(content, EMBED_LIMIT - 50)[0]
                    content += "\n*And more...*"
                fields = split_message(content, FIELD_VALUE_LIMIT)
                for s, split_field in enumerate(fields):
                    name = "Watched List" if s == 0 else "\u200F"
                    embed.add_field(name=name, value=split_field, inline=False)
            try:
                if watchlist_message is None:
                    new_message = await watchlist_channel.send(embed=embed)
                    await self.bot.pool.execute("""UPDATE watchlist SET message_id = $1 WHERE channel_id = $2""",
                                                new_message.id, watchlist_channel_id)
                else:
                    await watchlist_message.edit(embed=embed)
                await watchlist_channel.edit(name=f"{watchlist_channel.name.split('·', 1)[0]}·{online_count}")
            except discord.HTTPException:
                pass

    @staticmethod
    def _sort_by_voc_and_level():
        return lambda char: (normalize_vocation(char.vocation), -char.level)

    @staticmethod
    def get_watchlist_msg_entries(characters):
        return [f"\t{char.name} - Level {char.level} {get_voc_emoji(char.vocation)}" for char in characters]

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
    @checks.owner_only()
    @checks.tracking_world_only()
    @commands.command(name="addchar", aliases=["registerchar"], usage="<user>,<character>")
    async def add_char(self, ctx: NabCtx, *, params):
        """Register a character and optionally all other visible characters to a discord user.

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

        Once you had set the code, you can use the command with that character, if the code matches, it will be reassigned to you.
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
        user = ctx.author
        # List of Tibia worlds tracked in the servers the user is
        if ctx.is_private:
            user_tibia_worlds = [ctx.world]
        else:
            user_tibia_worlds = ctx.bot.get_user_worlds(ctx.author.id)

        if len(user_tibia_worlds) == 0:
            return

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

    @checks.server_admin_only()
    @checks.tracking_world_only()
    @commands.command(name="removechar", aliases=["deletechar", "unregisterchar"])
    async def remove_char(self, ctx: NabCtx, *, name):
        """Removes a registered character from someone.

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

    @commands.command()
    @checks.can_embed()
    @checks.tracking_world_only()
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
            try:
                char = await get_character(ctx.bot, params[0])
                if char is None:
                    await ctx.send("I couldn't find a character with that name.")
                    return
            except NetworkError:
                await ctx.send("I couldn't fetch that character.")
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
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def watchlist(self, ctx: NabCtx):
        """Create or manage watchlists.

        Watchlists are channels where the online status of selected characters are shown.
        You can create multiple watchlists and characters and guilds to each one separately.

        Try the subcommands."""
        await ctx.send("To manage watchlists, use one of the subommands.\n"
                       f"Try `{ctx.clean_prefix}help {ctx.invoked_with}`.")

    @checks.tracking_world_only()
    @checks.channel_mod_somewhere()
    @watchlist.command(name="add", aliases=["addplayer", "addchar"], usage="<channel> <name>[,reason]")
    async def watchlist_add(self, ctx: NabCtx, channel: discord.TextChannel, *, params=None):
        """Adds a character to a watchlist.

        A reason can be specified by adding it after the character's name, separated by a comma."""
        if params is None:
            return await ctx.error(f"Missing required parameters."
                                   f"Syntax is:  {ctx.clean_prefix}watchlist {ctx.invoked_with} {ctx.usage}`")

        if not await self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist channel.")

        if not channel.permissions_for(ctx.author).manage_channels:
            return await ctx.error(f"You need `Manage Channel` permissions in {channel.mention} to add entries.")

        params = params.split(",", 1)
        name = params[0]
        reason = None
        if len(params) > 1:
            reason = params[1]

        try:
            char = await get_character(ctx.bot, name)
            if char is None:
                await ctx.error("A character with that name doesn't exist.")
                return
        except NetworkError:
            await ctx.error(f"I couldn't fetch that character right now, please try again.")
            return

        world = ctx.world
        if char.world != world:
            await ctx.error(f"This character is not in **{world}**.")
            return

        message = await ctx.send(
            f"Do you want to add **{char.name}** (Level {char.level} {char.vocation}) to this watchlist?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return
        try:
            await ctx.pool.execute("""INSERT INTO watchlist_entry(name, channel_id, is_guild, reason, user_id)
                                      VALUES($1, $2, false, $3, $4)""", char.name, channel.id, reason, ctx.author.id)
            await ctx.success("Character added to the watchlist.")
        except asyncpg.UniqueViolationError:
            await ctx.error(f"**{char.name}** is already registered to {channel.mention}")

    @checks.tracking_world_only()
    @checks.channel_mod_somewhere()
    @watchlist.command(name="addguild", usage="<channel> <name>[,reason]")
    async def watchlist_addguild(self, ctx: NabCtx, channel: discord.TextChannel, *, params=None):
        """Adds an entire guild to a watchlist.

        Guilds are displayed in the watchlist as a group."""
        if params is None:
            return await ctx.error("Missing required parameters. Syntax is: "
                                   f"`{ctx.clean_prefix}watchlist {ctx.invoked_with} {ctx.usage}`")

        if not await self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist channel.'")

        if not channel.permissions_for(ctx.author).manage_channels:
            return await ctx.error(f"You need `Manage Channel` permissions in {channel.mention} to add entries.")

        params = params.split(",", 1)
        name = params[0]
        reason = None
        if len(params) > 1:
            reason = params[1]

        world = ctx.world
        try:
            guild = await get_guild(name)
            if guild is None:
                await ctx.error("There's no guild with that name.")
                return
        except NetworkError:
            await ctx.error("I couldn't fetch that guild right now, please try again.")
            return

        if guild.world != world:
            await ctx.error(f"This guild is not in **{world}**.")
            return

        message = await ctx.send(f"Do you want to add the guild **{guild.name}** to this watchlist?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return

        try:
            await ctx.pool.execute("""INSERT INTO watchlist_entry(name, channel_id, is_guild, reason, user_id)
                                      VALUES($1, $2, true, $3, $4)""", guild.name, channel.id, reason, ctx.author.id)
            await ctx.success("Guild added to the watchlist.")
        except asyncpg.UniqueViolationError:
            await ctx.error(f"**{guild.name}** is already registered to {channel.mention}")

    @checks.server_mod_only()
    @checks.tracking_world_only()
    @watchlist.command(name="create")
    async def watchlist_create(self, ctx: NabCtx, *, name):
        """Creates a watchlist channel.

        Creates a new text channel for the watchlist to be posted.

        The watch list shows which characters from it are online. Entire guilds can be added too.

        The channel can be renamed at anytime. If the channel is deleted, all its entries are deleted too.
        """
        if "·" in name:
            await ctx.error(f"Channel name cannot contain the special character **·**")
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
            channel = await ctx.guild.create_text_channel(name, overwrites=overwrites)
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
                               f"Example: {ctx.clean_prefix}{ctx.invoked_with} add {channel.mention} Galarzaa Fidera\n"
                               "If this channel is deleted, all related entries will be lost.\n"
                               "**It is important to not allow anyone to write in here**\n"
                               "*This message can be deleted now.*")
            await ctx.pool.execute("INSERT INTO watchlist(server_id, channel_id, user_id) VALUES($1, $2, $3)",
                                   ctx.guild.id, channel.id, ctx.author.id)

    @checks.server_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="info", aliases=["details", "reason"])
    async def watchlist_info(self, ctx: NabCtx, channel: discord.TextChannel, *, name: str):
        """Shows information about a watchlist entry.

        This shows who added the player, when, and if there's a reason why they were added."""
        if not self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        row = await ctx.pool.fetchrow("""SELECT name, reason, user_id, created FROM watchlist_entry
                                         WHERE channel_id = $1 AND NOT is_guild AND lower(name) = $2""",
                                      channel.id, name.lower())
        if not row:
            return await ctx.error(f"There's no character with that name registered to {channel.mention}.")

        embed = discord.Embed(title=row["name"])
        if row["reason"]:
            embed.description = f"**Reason:** {row['reason']}"
        author = ctx.guild.get_member(row["user_id"])
        if author:
            embed.set_footer(text=f"{author.name}#{author.discriminator}",
                             icon_url=get_user_avatar(author))
        if row["created"]:
            embed.timestamp = row["created"]
        await ctx.send(embed=embed)

    @checks.server_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="infoguild", aliases=["detailsguild", "reasonguild"])
    async def watchlist_infoguild(self, ctx: NabCtx, channel: discord.TextChannel, *, name: str):
        """"Shows details about a guild entry in the watchlist.

        This shows who added the player, when, and if there's a reason why they were added."""
        if not await self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist.")

        row = await ctx.pool.fetchrow("""SELECT name, reason, user_id, created FROM watchlist_entry
                                         WHERE channel_id = $1 AND is_guild AND lower(name) = $2""",
                                      channel.id, name.lower())
        if not row:
            return await ctx.error(f"There's no guild with that name registered in {channel.mention}")

        embed = discord.Embed(title=row["name"])
        if row["reason"]:
            embed.description = f"**Reason:** {row['reason']}"
        author = ctx.guild.get_member(row["user_id"])
        if author:
            embed.set_footer(text=f"{author.name}#{author.discriminator}",
                             icon_url=get_user_avatar(author))
        if row["created"]:
            embed.timestamp = row["created"]
        await ctx.send(embed=embed)

    @checks.server_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="list")
    async def watchlist_list(self, ctx: NabCtx, channel: discord.TextChannel):
        """Shows characters belonging to that watchlist.

        Note that this lists all characters, not just online characters."""
        if not await self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist channel.")

        results = await ctx.pool.fetch("""SELECT name FROM watchlist_entry
                                          WHERE channel_id = $1 AND NOT is_guild ORDER BY name ASC""", channel.id)
        if not results:
            return await ctx.error(f"This watchlist has no registered characters.")

        entries = [f"[{r['name']}]({NabChar.get_url(r['name'])})" for r in results]

        pages = Pages(ctx, entries=entries)
        pages.embed.title = "Watched Characters"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.server_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="listguilds", aliases=["guilds", "guildlist"])
    async def watchlist_list_guild(self, ctx: NabCtx, channel: discord.TextChannel):
        """Shows a list of guilds in the watchlist

        Note that this lists all characters, not just online characters."""
        if not await self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist channel.'")

        results = await ctx.pool.fetch("""SELECT name FROM watchlist_entry
                                          WHERE channel_id = $1 AND is_guild ORDER BY name ASC""", channel.id)
        if not results:
            return await ctx.error(f"This watchlist has no guilds registered.")

        entries = [f"[{r['name']}]({Guild.get_url(r['name'])})" for r in results]
        pages = Pages(ctx, entries=entries)
        pages.embed.title = "Watched Guilds"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.server_mod_somewhere()
    @checks.tracking_world_only()
    @watchlist.command(name="remove", aliases=["removeplayer", "removechar"])
    async def watchlist_remove(self, ctx: NabCtx, channel: discord.TextChannel, *, name):
        """Removes a character from a watchlist."""
        if not await self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist channel.'")

        result = await ctx.pool.fetchrow("""SELECT true FROM watchlist_entry
                                            WHERE channel_id = $1 AND lower(name) = $2 AND NOT is_guild""",
                                         channel.id, name.lower())
        if result is None:
            return await ctx.error(f"There's no character with that name registered to {channel.mention}.")

        message = await ctx.send(f"Do you want to remove **{name}** from this watchlist?")

        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return
        await ctx.pool.execute("DELETE FROM watchlist_entry WHERE channel_id = $1 and lower(name) = $2 AND NOT is_guild",
                               channel.id, name.lower())
        await ctx.success("Character removed from the watchlist.")

    @checks.server_mod_only()
    @checks.tracking_world_only()
    @watchlist.command(name="removeguild")
    async def watchlist_removeguild(self, ctx: NabCtx, channel: discord.TextChannel, *, name):
        """Removes a guild from the watchlist."""
        if not await self.is_watchlist(ctx, channel):
            return await ctx.error(f"{channel.mention} is not a watchlist channel.'")

        result = await ctx.pool.fetchrow("""SELECT true FROM watchlist_entry
                                            WHERE channel_id = $1 AND lower(name) = $2 AND is_guild""",
                                         channel.id, name.lower())
        if result is None:
            return await ctx.error(f"There's no guild with that name registered to {channel.mention}.")

        message = await ctx.send(f"Do you want to remove **{name}** from the watchlist?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then, guess you changed your mind.")
            return

        await ctx.pool.execute("DELETE FROM watchlist_entry WHERE channel_id = $1 and lower(name) = $2 AND is_guild",
                               channel.id, name.lower())
        await ctx.success("Guild removed from the watchlist.")
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
            # Select a message
            if death.by_player:
                message = weighed_choice(death_messages_player, vocation=char.vocation.value, level=death.level,
                                         levels_lost=levels_lost, min_level=min_level)
            else:
                message = weighed_choice(death_messages_monster, vocation=char.vocation.value, level=death.level,
                                         levels_lost=levels_lost, killer=death.killer.name, min_level=min_level)
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
                message = weighed_choice(level_messages, vocation=char.vocation.value, level=level, min_level=min_level)
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
                exists = await DbDeath.exists(conn, db_char.id, death.level, death.time, death.killer.name)
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
                if self.is_old_death(death):
                    log.info(f"{log_msg} | Too old to announce.")
                # Only try to announce if character has an owner
                elif char.owner_id:
                    log.info(log_msg)
                    await self.announce_death(char, death, max(death.level - char.level, 0))

    @staticmethod
    def is_old_death(death):
        """Deaths older than 30 minutes will not be announced."""
        return time.time() - death.time.timestamp() >= (30 * 60)

    @classmethod
    async def check_char_availability(cls, ctx: NabCtx, user_id: int, char: NabChar, worlds: List[str], check_other=False):
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

    @staticmethod
    async def is_watchlist(ctx: NabCtx, channel: discord.TextChannel):
        """Checks if a channel is a watchlist channel."""
        exists = await ctx.pool.fetchval("SELECT true FROM watchlist WHERE channel_id = $1", channel.id)
        return bool(exists)
    # endregion

    def __unload(self):
        log.info(f"{self.tag} Unloading cog")
        self.scan_highscores_task.cancel()
        self.scan_online_chars_task.cancel()


def setup(bot):
    bot.add_cog(Tracking(bot))
