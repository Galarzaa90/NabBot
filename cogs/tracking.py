import asyncio
import datetime as dt
import logging
import pickle
import re
import time
import urllib.parse
from typing import List

import asyncpg
import discord
from discord.ext import commands

from nabbot import NabBot
from .utils import EMBED_LIMIT, FIELD_VALUE_LIMIT, config, get_user_avatar, is_numeric, join_list, online_characters
from .utils import checks
from .utils.context import NabCtx
from .utils.database import get_affected_count, get_server_property
from .utils.messages import death_messages_monster, death_messages_player, format_message, level_messages, \
    split_message, weighed_choice
from .utils.pages import CannotPaginate, Pages, VocationPages
from .utils.tibia import Character, Death, ERROR_NETWORK, HIGHSCORE_CATEGORIES, NetworkError, World, get_character, \
    get_character_url, get_guild, get_highscores, get_share_range, get_tibia_time_zone, get_voc_abb, get_voc_emoji, \
    get_world, tibia_worlds, url_guild

log = logging.getLogger("nabbot")


class Tracking:
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
        await self.bot.wait_until_ready()
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
                log.exception("Task: scan_deaths")
                continue

    async def scan_highscores(self):
        """Scans the highscores, storing the results in the database.

        The task checks if the last stored data is from the current server save or not."""
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        await self.bot.wait_until_ready()
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
                                               category,  world)
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
                    log.exception("Task: scan_highscores")
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
        try:
            with open("data/online_list.dat", "rb") as f:
                saved_list, timestamp = pickle.load(f)
                if (time.time() - timestamp) < config.online_list_expiration:
                    online_characters.clear()
                    online_characters.update(saved_list)
                    log.info(f"[{self.__class__.__name__}] Loaded cached online list")
                else:
                    log.info("Cached online list is too old, discarding")
        except FileNotFoundError:
            pass
        except (ValueError, pickle.PickleError):
            log.info("Couldn't read cached online list.")
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
                current_world_online = world.players_online
                if len(current_world_online) == 0:
                    await asyncio.sleep(0.1)
                    continue
                log.debug(f"Scanning online characters for '{world.name}'")
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
                    online_characters[current_world].remove(offline_char)
                    try:
                        _char = await get_character(self.bot, offline_char.name)
                        await self.compare_levels(_char)
                        await self.compare_deaths(_char)
                    except NetworkError:
                        continue
                # Add new online chars and announce level differences
                for server_char in current_world_online:
                    async with self.bot.pool.acquire() as conn:
                        row = await conn.fetchrow('SELECT id, name, level FROM "character" WHERE name = $1',
                                                  server_char.name)
                    if row:
                        if server_char not in online_characters[current_world]:
                            # If the character wasn't in the online list we add them
                            # (We insert them at the beginning of the list to avoid messing with the death checks order)
                            server_char.last_check = time.time()
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
            log.debug(f"[{self.__class__.__name__}] Checking entries for watchlist"
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
                    if len(tibia_guild.online):
                        guild_online[tibia_guild.name] = tibia_guild.online
                # If it is a character, check if he's in the online list
                for online_char in scanned_world.players_online:
                    if online_char.name == watched["name"]:
                        # Add to online list
                        currently_online.append(online_char)
            # We try to get the watched message, if the bot can't find it, we just create a new one
            # This may be because the old message was deleted or this is the first time the list is checked
            try:
                watchlist_message = await watchlist_channel.get_message(watchlist_message_id)
            except discord.HTTPException:
                watchlist_message = None
            items = [f"\t{x.name} - Level {x.level} {get_voc_emoji(x.vocation)}" for x in currently_online]
            online_count = len(items)
            if len(items) > 0 or len(guild_online.keys()) > 0:
                description = ""
                content = "\n".join(items)
                for tibia_guild, members in guild_online.items():
                    content += f"\nGuild: **{tibia_guild}**\n"
                    if members is None:
                        content += "\t*Guild was disbanded.*"
                        continue
                    content += "\n".join(
                        [f"\t{x['name']} - Level {x['level']} {get_voc_emoji(x['vocation'])}"
                         for x in members])
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
            log.info(f"Watchlist channel deleted (Channel ID: {channel.id}, Guild ID: {channel.guild.id})")
            self.bot.dispatch("watchlist_deleted", channel, deleted_entries)

    # endregion

    # region Commands
    @commands.command()
    @checks.is_in_tracking_world()
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

        # List of servers the user shares with the self.bot
        user_guilds = self.bot.get_user_guilds(user.id)
        # List of Tibia worlds tracked in the servers the user is
        user_tibia_worlds = [world for guild, world in self.bot.tracked_worlds.items() if
                             guild in [g.id for g in user_guilds]]
        # Remove duplicate entries from list
        user_tibia_worlds = list(set(user_tibia_worlds))

        if not ctx.is_private and self.bot.tracked_worlds.get(ctx.guild.id) is None:
            return await ctx.send("This server is not tracking any tibia worlds.")

        if len(user_tibia_worlds) == 0:
            return

        if char_name is None:
            await ctx.send(f"To use this command, add `/NB-{user_code}/` to the comment of the character you want to"
                           f"claim, and then use `/claim character_name`.")
            return

        await ctx.trigger_typing()
        try:
            char = await get_character(ctx.bot, char_name)
            if char is None:
                await ctx.send("That character doesn't exist.")
                return
        except NetworkError:
            await ctx.send("I couldn't fetch the character, please try again.")
            return
        match = claim_pattern.search(char.comment if char.comment is not None else "")
        if not match:
            await ctx.send(f"Couldn't find verification code on character's comment.\n"
                           f"Add `/NB-{user_code}/` to the comment to authenticate.")
            return
        code = match.group(1)
        if code != user_code:
            await ctx.send(f"The verification code on the character's comment doesn't match yours.\n"
                           f"Use `/NB-{user_code}/` to authenticate.")
            return

        chars = char.other_characters
        check_other = False
        if len(chars) > 1:
            message = await ctx.send("Do you want to attempt to add the other visible characters in this account?")
            check_other = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if check_other is None:
            return await ctx.send("You ran out of time, try again."
                                  "Remember you have to react or click on the reactions.")
        if not check_other:
            chars = [char]

        skipped = []
        updated = []
        added: List[Character] = []
        existent = []
        with ctx.typing():
            for char in chars:
                # Skip chars in non-tracked worlds
                if char.world not in user_tibia_worlds:
                    skipped.append(char)
                    continue
                db_char = await ctx.pool.fetchrow("""SELECT name, guild, user_id as owner, vocation, abs(level) as 
                                                     level, guild FROM, id "character" WHERE lower(name) = $1""",
                                                  char.name.lower())
                if db_char is not None:
                    owner = self.bot.get_member(db_char["owner"])
                    # Char already registered to this user
                    if owner and owner.id == user.id:
                        existent.append(f"{char.name} ({char.world})")
                        continue
                    else:
                        updated.append({'name': char.name, 'world': char.world, 'prevowner': db_char["owner"],
                                        'vocation': db_char["vocation"], 'level': db_char['level'],
                                        'guild': db_char['guild'], 'id': db_char['id']
                                        })
                # If we only have one char, it already contains full data
                if len(chars) > 1:
                    try:
                        await ctx.channel.trigger_typing()
                        char = await get_character(self.bot, char.name)
                    except NetworkError:
                        await ctx.send("I'm having network troubles, please try again.")
                        return
                if char.deleted is not None:
                    skipped.append(char)
                    continue
                added.append(char)

        if len(skipped) == len(chars):
            await ctx.send( f"Sorry, I couldn't find any characters from the servers I track "
                            f"({join_list(user_tibia_worlds, ', ', ' and ')}).")
            return

        reply = ""
        if len(existent) > 0:
            reply += f"\nThe following characters were already registered to you: {join_list(existent, ', ', ' and ')}"

        if len(added) > 0:
            reply += "\nThe following characters were added to your account: {0}" \
                .format(join_list(["{0.name} ({0.world})".format(c) for c in added], ", ", " and "))
            for char in added:
                log.info(f"Character {char.name} was assigned to {user.display_name} (ID: {user.id})")

        if len(updated) > 0:
            reply += "\nThe following characters were reassigned to you: {0}" \
                .format(join_list(["{name} ({world})".format(**c) for c in updated], ", ", " and "))
            for char in updated:
                log.info(f"Character {char['name']} was reassigned to {user.display_name} (ID: {user.id})")

        async with ctx.pool.acquire() as conn:
            for char in updated:
                await conn.execute('UPDATE "character" SET user_id = $1 WHERE name = $2', user.id, char['name'])
            for char in added:
                await conn.execute("""INSERT INTO "character"(name,level,vocation,user_id, world, guild)
                                      VALUES ($1, $2, $3, $4, $5, $6)""",
                                   char.name, char.level * -1, char.vocation, user.id, char.world, char.guild_name)
        await ctx.send(reply)
        self.bot.dispatch("characters_registered", ctx.author, added, updated)
        self.bot.dispatch("character_change", ctx.author.id)

    @checks.is_in_tracking_world()
    @commands.command(aliases=["i'm", "iam"])
    async def im(self, ctx: NabCtx, *, char_name: str):
        """Lets you add your tibia character(s) for the bot to track.

        If there are other visible characters, the bot will ask for confirmation to add them too.

        Characters in other worlds other than the currently tracked world are skipped.
        If it finds a character owned by another user, the whole process will be stopped.

        If a character is already registered to someone else, `claim` can be used."""
        user = ctx.author
        # List of servers the user shares with the bot
        user_guilds = self.bot.get_user_guilds(user.id)
        # List of Tibia worlds tracked in the servers the user is
        user_tibia_worlds = [world for guild, world in self.bot.tracked_worlds.items() if
                             guild in [g.id for g in user_guilds]]
        # Remove duplicate entries from list
        user_tibia_worlds = list(set(user_tibia_worlds))

        if not ctx.is_private and ctx.world is None:
            return await ctx.send("This server is not tracking any tibia worlds.")

        if len(user_tibia_worlds) == 0:
            return

        msg = await ctx.send(f"{config.loading_emoji} Fetching character...")
        try:
            char = await get_character(ctx.bot, char_name)
            if char is None:
                return await msg.edit(content="That character doesn't exist.")
        except NetworkError:
            return await msg.edit(content="I couldn't fetch the character, please try again.")
        chars = char.other_characters
        check_other = False
        if len(chars) > 1:
            message = await ctx.send("Do you want to attempt to add the other visible characters in this account?")
            check_other = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if check_other is None:
            return await ctx.send("You didn't reply in time, try again."
                                  "Remember that you have to react or click on the icons.")
        if not check_other:
            chars = [char]

        if check_other:
            await msg.delete()
            msg = await ctx.send(f"{config.loading_emoji} Fetching characters...")

        skipped = []
        updated = []
        added: List[Character] = []
        existent = []
        for char in chars:
            # Skip chars in non-tracked worlds
            if char.world not in user_tibia_worlds:
                skipped.append(char)
                continue
            db_char = await ctx.pool.fetchrow("""SELECT name, guild, user_id as owner, vocation, ABS(level) as level, 
                                                 guild, id  FROM "character"
                                                 WHERE lower(name) = $1""", char.name.lower())
            if db_char is not None:
                owner = self.bot.get_member(db_char["owner"])
                # Previous owner doesn't exist anymore
                if owner is None:
                    updated.append({'name': char.name, 'world': char.world, 'prevowner': db_char["owner"],
                                    'vocation': db_char["vocation"], 'level': db_char['level'],
                                    'guild': db_char['guild'], 'id': db_char['id']
                                    })
                    continue
                # Char already registered to this user
                elif owner.id == user.id:
                    existent.append(f"{char.name} ({char.world})")
                    continue
                # Character is registered to another user, we stop the whole process
                else:
                    reply = "Sorry, a character in that account ({0}) is already registered to **{1}**.\n" \
                            "If the character really belongs to you, try using `{2}claim {0}`."
                    return await msg.edit(content=reply.format(db_char["name"], owner, ctx.clean_prefix))
            # If we only have one char, it already contains full data
            if len(chars) > 1:
                try:
                    char = await get_character(ctx.bot, char.name)
                except NetworkError:
                    return await msg.edit("I'm having network issues, please try again.")
            if char.deleted is not None:
                skipped.append(char)
                continue
            added.append(char)

        if len(skipped) == len(chars):
            reply = "Sorry, I couldn't find any characters from the servers I track ({0})."
            return await msg.edit(content=reply.format(join_list(user_tibia_worlds, ", ", " and ")))

        reply = ""
        if len(existent) > 0:
            reply += f"\nThe following characters were already registered to you: {join_list(existent, ', ', ' and ')}"

        if len(added) > 0:
            reply += "\nThe following characters are now registered to you: {0}" \
                .format(join_list(["{0.name} ({0.world})".format(c) for c in added], ", ", " and "))
            for char in added:
                log.info(f"Character {char.name} was assigned to {user.display_name} (ID: {user.id})")

        if len(updated) > 0:
            reply += "\nThe following characters were reassigned to you: {0}" \
                .format(join_list(["{name} ({world})".format(**c) for c in updated], ", ", " and "))
            for char in updated:
                log.info(f"Character {char['name']} was reassigned to {user.display_name} (ID: {user.id})")
        async with ctx.pool.acquire() as conn:
            for char in updated:
                await conn.execute('UPDATE "character" SET user_id = $1 WHERE name = $2', user.id, char['name'])
            for char in added:
                await conn.execute("""INSERT INTO "character"(name, level, vocation, user_id, world, guild)
                                      VALUES ($1, $2, $3, $4, $5, $6)""",
                                   char.name, char.level * -1, char.vocation, user.id, char.world, char.guild_name)
        await msg.edit(content=reply)
        self.bot.dispatch("characters_registered", ctx.author, added, updated)
        self.bot.dispatch("character_change", ctx.author.id)

    @checks.is_in_tracking_world()
    @commands.command(aliases=["i'mnot"])
    async def imnot(self, ctx: NabCtx, *, name):
        """Removes a character assigned to you.

        All registered level ups and deaths will be lost forever."""
        char = await ctx.pool.fetchrow("""SELECT id, name, ABS(level) as level, user_id, vocation, world, guild
                                          FROM "character" WHERE lower(name) = $1""", name.lower())
        if char is None or char["user_id"] == 0:
            await ctx.send("There's no character registered with that name.")
            return
        user = ctx.author
        if char["user_id"] != user.id:
            await ctx.send(f"The character **{char['name']}** is not registered to you.")
            return

        message = await ctx.send("Are you sure you want to unregister **{name}** ({level} {vocation})?"
                                 .format(**char))
        confirm = await ctx.react_confirm(message, timeout=50)
        if confirm is None:
            await ctx.send("I guess you changed your mind.")
            return
        if not confirm:
            await ctx.send("No then? Ok.")

        await ctx.pool.execute('UPDATE "character" SET user_id = 0 WHERE id = $1', char["id"])
        await ctx.send(f"**{char['name']}** is no longer registered to you.")

        self.bot.dispatch("character_change", ctx.author.id)
        self.bot.dispatch("character_unregistered", ctx.author, char)

    @commands.command()
    @checks.can_embed()
    @checks.is_tracking_world()
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
            row = await ctx.pool.fetchrow('SELECT user_id FROM "character" WHERE name = $1', name)
            if row is None:
                continue
            # Skip characters of members not in the server
            owner = ctx.guild.get_member(row["user_id"])
            if owner is None:
                continue
            owner = owner.display_name
            emoji = get_voc_emoji(char.vocation)
            vocations.append(char.vocation)
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
    @checks.is_tracking_world()
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
            async with conn.transaction():
                async for row in conn.cursor("""SELECT name, user_id, abs(level) as level, vocation FROM "character"
                                                WHERE level >= $1 AND level <= $2 AND world = $3
                                                ORDER BY level DESC""", low, high, ctx.world):
                    if char is not None and char.name == row["name"]:
                        continue
                    owner = ctx.guild.get_member(row["user_id"])
                    if owner is None:
                        continue
                    count += 1
                    row = dict(row)
                    row["owner"] = owner.display_name
                    row["online"] = ""
                    row["emoji"] = get_voc_emoji(row["vocation"])
                    row["voc"] = get_voc_abb(row["vocation"])
                    line_format = "**{name}** - Level {level} {voc}{emoji} - @**{owner}** {online}"
                    if row["name"] in online_list:
                        row["online"] = config.online_emoji
                        online_entries.append(line_format.format(**row))
                        online_vocations.append(row["vocation"])
                    else:
                        entries.append(line_format.format(**row))
                        vocations.append(row["vocation"])
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

    @checks.is_mod()
    @checks.is_tracking_world()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def watchlist(self, ctx: NabCtx):
        """Create or manage watchlists.

        Watchlists are channels where the online status of selected characters are shown.
        You can create multiple watchlists and characters and guilds to each one separately.

        Try the subcommands."""
        await ctx.send("To manage watchlists, use one of the subommands.\n"
                       f"Try `{ctx.clean_prefix}help {ctx.invoked_with}`.")

    @checks.is_tracking_world()
    @checks.is_channel_mod_somewhere()
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

    @checks.is_tracking_world()
    @checks.is_channel_mod_somewhere()
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

    @checks.is_mod()
    @checks.is_tracking_world()
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

    @checks.is_mod_somewhere()
    @checks.is_tracking_world()
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

    @checks.is_mod_somewhere()
    @checks.is_tracking_world()
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

    @checks.is_mod_somewhere()
    @checks.is_tracking_world()
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

        entries = [f"[{r['name']}]({get_character_url(r['name'])})" for r in results]

        pages = Pages(ctx, entries=entries)
        pages.embed.title = "Watched Characters"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.is_mod_somewhere()
    @checks.is_tracking_world()
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

        entries = [f"[{r['name']}]({url_guild+urllib.parse.quote(r['name'])})" for r in results]
        pages = Pages(ctx, entries=entries)
        pages.embed.title = "Watched Guilds"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.is_mod_somewhere()
    @checks.is_tracking_world()
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

    @checks.is_mod()
    @checks.is_tracking_world()
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
    async def announce_death(self, char: Character, death: Death, levels_lost=0):
        """Announces a level up on the corresponding servers."""
        # Don't announce for low level players
        if char is None:
            return

        # Find killer article (a/an)
        killer_article = ""
        if not death.by_player:
            killer_article = death.killer.split(" ", 1)
            if killer_article[0] in ["a", "an"] and len(killer_article) > 1:
                death.killer = killer_article[1]
                killer_article = killer_article[0] + " "
            else:
                killer_article = ""

        if death.killer.lower() in ["death", "energy", "earth", "fire", "pit battler", "pit berserker",
                                    "pit blackling",
                                    "pit brawler", "pit condemned", "pit demon", "pit destroyer", "pit fiend",
                                    "pit groveller", "pit grunt", "pit lord", "pit maimer", "pit overlord",
                                    "pit reaver",
                                    "pit scourge"] and levels_lost == 0:
            # Skip element damage deaths unless player lost a level to avoid spam from arena deaths
            # This will cause a small amount of deaths to not be announced but it's probably worth the tradeoff
            return

        guilds = [s for s, w in self.bot.tracked_worlds.items() if w == char.world]
        for guild_id in guilds:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            min_level = await get_server_property(self.bot.pool, guild_id, "announce_level", config.announce_threshold)
            if death.level < min_level:
                continue
            if guild.get_member(char.owner) is None:
                continue
            # Select a message
            if death.by_player:
                message = weighed_choice(death_messages_player, vocation=char.vocation, level=death.level,
                                         levels_lost=levels_lost, min_level=min_level)
            else:
                message = weighed_choice(death_messages_monster, vocation=char.vocation, level=death.level,
                                         levels_lost=levels_lost, killer=death.killer, min_level=min_level)
            # Format message with death information
            death_info = {'name': char.name, 'level': death.level, 'killer': death.killer,
                          'killer_article': killer_article, 'he_she': char.he_she.lower(),
                          'his_her': char.his_her.lower(), 'him_her': char.him_her.lower()}
            message = message.format(**death_info)
            # Format extra stylization
            message = f"{config.pvpdeath_emoji if death.by_player else config.death_emoji} {format_message(message)}"
            try:
                channel_id = await get_server_property(self.bot.pool, guild.id, "levels_channel")
                channel = self.bot.get_channel_or_top(guild, channel_id)
                await channel.send(message[:1].upper() + message[1:])
            except discord.Forbidden:
                log.warning("announce_death: Missing permissions.")
            except discord.HTTPException:
                log.warning("announce_death: Malformed message.")

    async def announce_level(self, char: Character, level: int):
        """Announces a level up on corresponding servers."""
        if char is None:
            return

        guilds = [s for s, w in self.bot.tracked_worlds.items() if w == char.world]
        for guild_id in guilds:
            guild: discord.Guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            min_level = await get_server_property(self.bot.pool, guild_id, "announce_level", config.announce_threshold)
            if char.level < min_level:
                continue
            if guild.get_member(char.owner) is None:
                continue
            try:
                channel_id = await get_server_property(self.bot.pool, guild.id, "levels_channel")
                channel = self.bot.get_channel_or_top(guild, channel_id)
                # Select a message
                message = weighed_choice(level_messages, vocation=char.vocation, level=level, min_level=min_level)
                level_info = {'name': char.name, 'level': level, 'he_she': char.he_she.lower(),
                              'his_her': char.his_her.lower(), 'him_her': char.him_her.lower()}
                # Format message with level information
                message = message.format(**level_info)
                # Format extra stylization
                message = f"{config.levelup_emoji} {format_message(message)}"
                await channel.send(message)
            except discord.Forbidden:
                log.warning("announce_level: Missing permissions.")
            except discord.HTTPException:
                log.warning("announce_level: Malformed message.")

    async def compare_deaths(self, char: Character):
        """Checks if the player has new deaths."""
        if char is None:
            return
        async with self.bot.pool.acquire() as conn:
            char_id = await conn.fetchval('SELECT id FROM "character" WHERE name = $1', char.name)
            if char_id is None:
                return
            pending_deaths = []
            for death in char.deaths:
                # Check if we have a death that matches the time
                _id = await conn.fetchval("""SELECT id FROM character_death d
                                             INNER JOIN character_death_killer dk ON dk.death_id = d.id
                                             WHERE character_id = $1 AND date = $2 AND name = $3 AND level = $4
                                             AND position = 0""",
                                          char_id, death.time, death.killer, death.level)
                if _id is not None:
                    # We already have this death, we're assuming we already have older deaths
                    break
                pending_deaths.append(death)
            # Announce and save deaths from older to new
            for death in reversed(pending_deaths):
                death_id = await conn.fetchval("""INSERT INTO character_death(character_id, level, date)
                                                  VALUES($1, $2, $3) ON CONFLICT DO NOTHING RETURNING id""",
                                               char_id, death.level, death.time)
                if death_id is None:
                    continue
                await conn.execute("INSERT INTO character_death_killer(death_id, name, player) VALUES($1, $2, $3)",
                                   death_id, death.killer, death.by_player)
                log_msg = f"Death detected: {char.name}({death.level}) | {death.killer}"
                if self.is_old_death(death):
                    log_msg += ", but it is too old to announce."
                else:
                    log.info(log_msg)
                    await self.announce_death(char, death, max(death.level - char.level, 0))

    @staticmethod
    def is_old_death(death):
        """Deaths older than 30 minutes will not be announced."""
        return time.time() - death.time.timestamp() >= (30 * 60)

    async def compare_levels(self, char: Character):
        """Compares the character's level with the stored level in database.

        This should only be used on online characters or characters that just became offline."""
        # Check for deaths and level ups when removing from online list
        if char is None:
            return
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT id, name, level, user_id FROM "character" WHERE name = $1', char.name)
            if not row:
                return
            char.owner = row["user_id"]
            await conn.execute('UPDATE "character" SET level = $1 WHERE id = $2', char.level, row["id"])
            if char.level > row["level"] > 0:
                # Saving level up date in database
                await conn.execute("INSERT INTO character_levelup(character_id, level) VALUES($1, $2)",
                                   row["id"], char.level)
                # Announce the level up
                log.info(f"Level up detected: {char.name} ({char.level})")
                await self.announce_level(char, char.level)

    @staticmethod
    async def is_watchlist(ctx: NabCtx, channel: discord.TextChannel):
        """Checks if a channel is a watchlist channel."""
        exists = await ctx.pool.fetchval("SELECT true FROM watchlist WHERE channel_id = $1", channel.id)
        return bool(exists)
    # endregion

    def __unload(self):
        log.info("Unloading cogs.tracking...")
        self.scan_highscores_task.cancel()
        self.scan_online_chars_task.cancel()


def setup(bot):
    bot.add_cog(Tracking(bot))
