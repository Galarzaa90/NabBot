import asyncio
import datetime as dt
import logging
from enum import Enum
from typing import Any, Dict, Optional

import asyncpg
import discord
import tibiawikisql
from discord.ext import commands
from discord.ext.commands import clean_content

from nabbot import NabBot
from .utils import CogUtils, checks, clean_string, config, get_user_avatar, single_line
from .utils.context import NabCtx
from .utils.converter import BadTime, TimeString
from .utils.database import get_server_property, wiki_db
from .utils.errors import CannotPaginate
from .utils.pages import Pages, VocationPages
from .utils.tibia import get_voc_abb, get_voc_emoji

EVENT_NAME_LIMIT = 50
EVENT_DESCRIPTION_LIMIT = 400
MAX_EVENTS = 3
RECENT_THRESHOLD = dt.timedelta(minutes=30)

BOSS_ALIASES = {
    "tenebris": "Lady Tenebris",
    "lady tenebris": "Lady Tenebris",
    "kroazur": "Kroazur",
    "lloyd": "Lloyd",
    "melting frozen horror": "Melting Frozen Horror",
    "solid frozen horror": "Solid Frozen Horror",
    "frozen horror": "Frozen Horror",
    "the enraged thorn knight": "The Enraged Thorn Knight",
    "mounted thorn knight": "The Enraged Thorn Knight",
    "the shielded thorn knight": "The Enraged Thorn Knight",
    "thorn knight": "The Enraged Thorn Knight",
    "soul of dragonking zyrtarch": "Dragonking Zyrtarch",
    "dragonking zyrtarch": "Dragonking Zyrtarch",
    "zyrtarch": "Dragonking Zyrtarch",
    "the time guardian": "The Time Guardian",
    "the freezing time guardian": "The Time Guardian",
    "the blazing time guardian": "The Time Guardian",
    "the last lore keeper": "The Last Lore Keeper",
    "last lore keeper": "The Last Lore Keeper",
    "lore keeper": "The Last Lore Keeper",
    "anomaly": "Anomaly",
    "rupture": "Rupture",
    "realityquake": "realityquake",
    "eradicator": "Eradicator",
    "outburst": "Outburst",
    "world devourer": "World Devourer",
    "ravennous hunger": "ravennous hunger",
    "the souldespoiler": "The Souldespoiler",
    "souldespoiler": "The Souldespoiler",
    "the armored voidborn": "The Armored Voidborn",
    "the unarmored voidborn": "The Armored Voidborn",
    "armored voidborn": "The Armored Voidborn",
    "unarmored voidborn": "The Armored Voidborn",
    "the sandking": "The Sandking",
    "sandking": "The Sandking",
    "the false god": "The False God",
    "false god": "The False God",
    "essence of malice": "Essence of Malice",
    "the source of corruption": "The Source of Corruption",
    "source of corruption": "The Source of Corruption",
    "bloodback": "Bloodback",
    "darkfang": "Darkfang",
    "sharpclaw": "Sharpclaw",
    "black vixen": "Black Vixen",
    "shadowpelt": "Shadowpelt",
    "plagirath": "Plagirath",
    "zamulosh": "Zamulosh",
    "mazoran": "Mazoran",
    "razzagorn": "Razzagorn",
    "shulgrax": "Shulgrax",
    "tarbaz": "Tarbaz",
    "ragiaz": "Ragiaz",
    "ferumbras mortal shell": "Ferumbras Mortal Shell",
    "ferumbras": "Ferumbras Mortal Shell",
    "grand master oberon": "Grand Master Oberon",
    "master oberon": "Grand Master Oberon",
    "oberon": "Grand Master Oberon",
    "deathstrike": "Deathstrike",
    "warzone 1": "Deathstrike",
    "warzone1": "Deathstrike",
    "wz1": "Deathstrike",
    "gnomevil": "Gnomevil",
    "warzone 2": "Gnomevil",
    "warzone2": "Gnomevil",
    "wz2": "Gnomevil",
    "versperoth": "Versperoth",
    "warzone 3": "Versperoth",
    "warzone3": "Versperoth",
    "wz3": "Versperoth",
    "baron from below": "The Baron from Below",
    "the baron from below": "The Baron from Below",
    "warzone 4": "The Baron from Below",
    "warzone4": "The Baron from Below",
    "wz4": "The Baron from Below",
    "the count of the core": "The Count of The Core",
    "count of the core": "The Count of The Core",
    "warzone 5": "The Count of The Core",
    "warzone5": "The Count of The Core",
    "wz5": "The Count of The Core",
    "morgathla": "Ancient Spawn of Morgathla",
    "ancient spawn of morgathla": "Ancient Spawn of Morgathla",
    "warzone 6": "Ancient Spawn of Morgathla",
    "warzone6": "Ancient Spawn of Morgathla",
    "wz6": "Ancient Spawn of Morgathla",
}

BOSS_COOLDOWNS = {
    "Lloyd": 20*60*60,
    "Lady Tenebris": 20*60*60,
    "Melting Frozen Horror": 20*60*60,
    "The Enraged Thorn Knight": 20*60*60,
    "Dragonking Zyrtarch": 20*60*60,
    "The Time Guardian": 20*60*60,
    "The Last Lore Keeper": 24*60*60*14,
    "Anomaly": 20*60*60,
    "Rupture": 20*60*60,
    "Realityquake": 20*60*60,
    "Eradicator": 20*60*60,
    "Outburst": 20*60*60,
    "World Devourer": 24*60*60*14,
    "Ravennous Hunger": 20*60*60,
    "The Souldespoiler": 20*60*60,
    "The Armored Voidborn": 20*60*60,
    "The Sandking": 20*60*60,
    "The False God": 20*60*60,
    "Essence of Malice": 20*60*60,
    "The Source of Corruption": 20*60*60,
    "Kroazur": 2*60*60,
    "Bloodback": 20*60*60,
    "Darkfang": 20*60*60,
    "Sharpclaw": 20*60*60,
    "Black Vixen": 20*60*60,
    "Shadowpelt": 20*60*60,
    "Plagirath": 2*24*60*60,
    "Zamulosh": 2*24*60*60,
    "Mazoran": 2*24*60*60,
    "Razzagorn": 2*24*60*60,
    "Shulgrax": 2*24*60*60,
    "Tarbaz": 2*24*60*60,
    "Ragiaz": 2*24*60*60,
    "Ferumbras Mortal Shell": 14*24*60*60,
    "Grand Master Oberon": 20*60*60,
    "Deathstrike": 20*60*60,
    "Gnomevil": 20*60*60,
    "Versperoth": 20*60*60,
    "The Baron from Below": 4*60*60,
    "The Count of The Core": 4*60*60,
    "Ancient Spawn Of Morgathla": 4*60*60
}


log = logging.getLogger("nabbot")


class ReminderType(Enum):
    CUSTOM = 0
    BOSS = 1
    TASK = 2


class Timer:
    def __init__(self, record):
        self.id = record["id"]
        self.name = record["name"]
        self.type = record["type"]
        self.user_id = record["user_id"]
        if isinstance(self.type, int):
            self.type = ReminderType(self.type)
        self.extra = record["extra"]
        self.expires = record["expires"]
        self.created = record["created"]

    @classmethod
    def build(cls, **kwargs):
        kwargs["id"] = None
        return cls(kwargs)

    def __eq__(self, other):
        try:
            return self.id == other.id
        except AttributeError:
            return False

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f'<Timer id={self.id} name={self.name} expires={self.expires} type={self.type}>'


class Timers(CogUtils):
    def __init__(self, bot: NabBot):
        self.bot = bot
        self._timer_available = asyncio.Event(loop=bot.loop)
        self.timers_task = self.bot.loop.create_task(self.check_timers())
        self.events_announce_task = self.bot.loop.create_task(self.events_announce())
        self._next_timer = None

# region Tasks
    async def check_timers(self):
        """Checks the first upcoming time and waits for it."""
        try:
            await self.bot.wait_until_ready()
            log.debug(f"{self.tag} Starting await_timers task")
            while not self.bot.is_closed():
                timer = self._next_timer = await self.await_next_timer(days=40)
                log.debug(f"{self.tag} Next timer: {timer}")
                now = dt.datetime.now(tz=dt.timezone.utc)
                if timer.expires >= now:
                    wait_time = (timer.expires-now)
                    log.debug(f"{self.tag} Sleeping for {wait_time}")
                    await asyncio.sleep(wait_time.total_seconds())
                await self.run_timer(timer)
        except asyncio.CancelledError:
            pass
        except(OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())
        except:
            log.exception(f"{self.tag} Error in task")

    async def events_announce(self):
        """Announces upcoming events"""
        task_tag = " Task: events_announce |"
        await self.bot.wait_until_ready()
        log.info(f"{self.tag}{task_tag} Started")
        while not self.bot.is_closed():
            """Announces when an event is close to starting."""
            first_announce = dt.timedelta(hours=1)
            second_announce = dt.timedelta(minutes=30)
            third_announce = dt.timedelta(minutes=10)
            time_margin = dt.timedelta(minutes=1)
            try:
                # Current time
                date = dt.datetime.now(dt.timezone.utc)
                events = await self.bot.pool.fetch("""SELECT user_id, start, name, id, server_id, reminder FROM event
                                                      WHERE start >= now() AND active AND reminder < 4
                                                      ORDER BY start ASC""")
                if not events:
                    await asyncio.sleep(20)
                    continue
                for event in events:
                    event = dict(event)
                    await asyncio.sleep(0.1)
                    if abs(date + first_announce - event["start"]) < time_margin and event["reminder"] < 1:
                        new_status = 1
                    elif abs(date + second_announce - event["start"]) < time_margin and event["reminder"] < 2:
                        new_status = 2
                    elif abs(date + third_announce - event["start"]) < time_margin and event["reminder"] < 3:
                        new_status = 3
                    elif abs(date - event["start"]) < time_margin and event["reminder"] < 4:
                        new_status = 4
                    else:
                        continue
                    guild = self.bot.get_guild(event["server_id"])
                    if guild is None:
                        continue
                    author = self.bot.get_member(event["user_id"], guild)
                    if author is None:
                        continue
                    event["author"] = author.display_name
                    time_diff = event["start"] - date
                    days, hours, minutes = time_diff.days, time_diff.seconds // 3600, (time_diff.seconds // 60) % 60
                    if days:
                        event["start"] = 'in {0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                    elif hours:
                        event["start"] = 'in {0} hours and {1} minutes'.format(hours, minutes)
                    elif minutes > 1:
                        event["start"] = 'in {0} minutes'.format(minutes)
                    else:
                        event["start"] = 'now'
                    message = "**{name}** (by **@{author}**,*ID:{id}*) - Is starting {start}!".format(**event)
                    await self.bot.pool.execute("UPDATE event SET reminder = $1 WHERE id = $2", new_status, event["id"])
                    announce_channel_id = await get_server_property(self.bot.pool, guild.id, "events_channel",
                                                                    default=0)
                    if announce_channel_id == 0:
                        continue
                    announce_channel = self.bot.get_channel_or_top(guild, announce_channel_id)
                    if announce_channel is not None:
                        await announce_channel.send(message)
                    await self.notify_subscribers(event["id"], message)
            except asyncio.CancelledError:
                log.info(f"{self.tag}{task_tag} Stopped")
                return
            except Exception:
                log.exception(f"{self.tag} Exception")
                continue
            await asyncio.sleep(20)
# endregion


    async def __error(self, ctx: NabCtx, error):
        if isinstance(error, BadTime):
            await ctx.send(error)
            return

    async def run_timer(self, timer, short=False):
        """Dispatches an event for the timer."""
        if not short:
            query = "DELETE FROM timer WHERE id=$1;"
            await self.bot.pool.execute(query, timer.id)
        log.debug(f"{self.tag} Executing timer {timer}")
        if timer.type == ReminderType.CUSTOM:
            self.bot.dispatch("custom_timer_complete", timer)
        if timer.type == ReminderType.BOSS:
            self.bot.dispatch("boss_timer_complete", timer)

    async def run_short_timer(self, seconds, timer: Timer):
        await asyncio.sleep(seconds)
        await self.run_timer(timer, True)

    async def on_custom_timer_complete(self, timer: Timer):
        try:
            channel = self.bot.get_channel(timer.extra["channel"])
            user: discord.User = self.bot.get_user(timer.user_id)
            if user is None:
                return
            if channel is None:
                # Check if it is a PM
                channel = user.dm_channel
                if channel is None:
                    log.debug(f"{self.tag} Timer in channel that no longer exists.")
                    return
            guild_id = channel.guild.id if isinstance(channel, discord.TextChannel) else "@me"
            message_id = timer.extra["message"]

            await channel.send(f'{user.mention}, you asked me to remind you this: {timer.name}'
                               f'\n<https://discordapp.com/channels/{guild_id}/{channel.id}/{message_id}>')
        except KeyError:
            log.debug(f"{self.tag} Corrupt custom timer.")

    async def on_boss_timer_complete(self, timer: Timer):
        author: discord.User = self.bot.get_user(timer.user_id)
        char = await self.bot.pool.fetchrow('SELECT name FROM "character" WHERE id = $1', timer.extra["char_id"])
        if author is None or char is None:
            return
        embed = discord.Embed(title=timer.name, colour=discord.Colour.green(),
                              description=f"The cooldown for **{timer.name}** is over now for **{char['name']}**.")
        monster = tibiawikisql.models.Creature.get_by_field(wiki_db, "name", timer.name)
        try:
            if monster:
                filename = f"thumbnail.gif"
                embed.set_thumbnail(url=f"attachment://{filename}")
                await author.send(file=discord.File(monster.image, f"{filename}"), embed=embed)
            else:
                await author.send(embed=embed)
        except discord.Forbidden:
            log.debug(f"{self.tag} Couldn't send boss timer to user {author} due to privacy settings.")

    @commands.group(invoke_without_command=True, case_insensitive=True, usage="<boss>[,character]")
    async def boss(self, ctx: NabCtx, *, params: str=None):
        """Shows the remaining cooldown time for a specific boss."""
        if not params:
            await ctx.error(f"Tell me the name of the boss you want to check.\n"
                            f"For a list of your active cooldowns, try: `{ctx.clean_prefix}{ctx.invoked_with} list`")
            return
        param = params.split(",", 2)
        name = param[0]
        now = dt.datetime.now(dt.timezone.utc)
        if name.lower() in BOSS_ALIASES:
            name = BOSS_ALIASES[name]
        if name not in BOSS_COOLDOWNS:
            return await ctx.error(f"There's no boss with that name.\nFor a list of supported bosses, "
                                   f"try: `{ctx.clean_prefix}{ctx.invoked_with} bosslist`")
        if len(param) > 1:
            char = param[1]
            db_char = await ctx.pool.fetchrow("""SELECT id, world, name FROM "character"
                                                 WHERE lower(name) = $1 AND user_id = $2""",
                                              char.lower(), ctx.author.id)
            if db_char is None:
                return await ctx.error(f"You don't have any registered character named `{char}`.")
            record = await ctx.pool.fetchrow("""SELECT * FROM timer WHERE type = $1 AND name = $2 AND user_id = $3
                                               AND extra->>'char_id' = $4""",
                                             ReminderType.BOSS.value, name, ctx.author.id, str(db_char["id"]))
            if not record:
                return await ctx.send(f"**{db_char['name']}** doesn't have any active cooldowns for **{name}**.")
            timer = Timer(record)
            return await ctx.send(f"Your cooldown for **{name}** will be over in {timer.expires-now}.")
        rows = await ctx.pool.fetch("""SELECT timer.*, "character".name AS char_name, "character".world FROM timer
                                       JOIN "character" ON "character".id = (extra->>'char_id')::int
                                       WHERE type = $1 AND timer.name = $2 AND timer.user_id = $3
                                       ORDER BY expires ASC""",
                                    ReminderType.BOSS.value, name, ctx.author.id)
        entries = []
        world_skipped = False
        for row in rows:
            if ctx.world and ctx.world != row["world"]:
                world_skipped = True
                continue
            entries.append(f"**{row['char_name']}** - {row['expires']-now}")
        if not entries:
            return await ctx.send(f"You don't have any active cooldowns for **{name}**.")
        header = f"Only characters in {ctx.world} are show. Use on PM to see more." if world_skipped else ""
        pages = Pages(ctx, entries=entries, header=header)
        pages.embed.title = f"Your active {name} cooldowns"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.error(e)

    @boss.command(name="bosslist")
    async def boss_bosslist(self, ctx: NabCtx):
        """Shows a list of supported boss cooldowns."""
        entries = [f"**{k}** - {dt.timedelta(seconds=v)}" for k, v in BOSS_COOLDOWNS.items()]
        pages = Pages(ctx, entries=entries)
        pages.embed.title = "Supported Boss Cooldowns"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.error(e)

    @boss.command(name="list")
    async def boss_list(self, ctx: NabCtx):
        """Shows a list of all your active cooldowns.

        For privacy reasons, only characters matching the tracked world of the current server will be shown.
        To see all your characters, try it on a private message."""
        rows = await ctx.pool.fetch("""SELECT timer.*, "character".name AS char_name, "character".world FROM timer
                                       JOIN "character" ON "character".id = (extra->>'char_id')::int
                                       WHERE type = $1 AND timer.user_id = $2
                                       ORDER BY expires ASC""", ReminderType.BOSS.value, ctx.author.id)
        entries = []
        now = dt.datetime.now(dt.timezone.utc)
        world_skipped = False
        for row in rows:
            if ctx.world and ctx.world != row["world"]:
                world_skipped = True
                continue
            entries.append(f"**{row['name']}** - **{row['char_name']}** - {row['expires']-now}")
        if not entries:
            return await ctx.send(f"You don't have any active cooldowns.")
        header = f"Only characters in {ctx.world} are show. Use on PM to see more." if world_skipped else ""
        pages = Pages(ctx, entries=entries, header=header)
        pages.embed.title = "Your active cooldowns"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.error(e)

    @boss.command(name="set", usage="<boss>,<character>")
    async def boss_set(self, ctx: NabCtx, *, params):
        """Sets the cooldown for a boss.

        The cooldown is set as if you had just killed the boss."""
        param = params.split(",", 2)
        if len(param) < 2:
            return await ctx.error("You must specify for which of your character is the cooldown for.\n"
                                   f"e.g. `{ctx.clean_prefix}{ctx.invoked_with} set Kroazur,Bubble`")
        name, char = param
        if name.lower() in BOSS_ALIASES:
            name = BOSS_ALIASES[name]
        if name in BOSS_COOLDOWNS:
            cooldown = BOSS_COOLDOWNS[name]
        else:
            return await ctx.error(f"There's no boss with that name.\nFor a list of supported bosses, "
                                   f"try: `{ctx.clean_prefix}{ctx.invoked_with} bosslist`")

        db_char = await ctx.pool.fetchrow("""SELECT id, user_id, name FROM "character" WHERE lower(name) = $1""",
                                          char.lower())
        if db_char is None:
            return await ctx.error("There's no character registered with that name.")
        if db_char["user_id"] != ctx.author.id:
            return await ctx.error("That character is not registered to you.")
        now = dt.datetime.now(tz=dt.timezone.utc)
        expires = now + dt.timedelta(seconds=cooldown)
        # Check if this char already has a pending cooldown
        exists = await ctx.pool.fetchval("SELECT true FROM timer WHERE extra->>'char_id' = $1 AND name = $2",
                                         str(db_char["id"]), name)
        if exists:
            return await ctx.error(f"This character already has a running timer for this boss.\n"
                                   f"You can delete it using `{ctx.clean_prefix}{ctx.command.full_parent_name} clear "
                                   f"{name},{db_char['name']}`")
        await self.create_timer(now, expires, name, ReminderType.BOSS, ctx.author.id, {"char_id": db_char["id"]})
        await ctx.success(f"Timer saved for `{name}`, I will let you know when the cooldown is over via pm.\n"
                          f"Use `{ctx.clean_prefix}checkdm` to make sure you can receive PMs by me.")

    @boss.command(name="remove", aliases=["unset", "clear"], usage="<boss>,<character>")
    async def boss_remove(self, ctx: NabCtx, *, params):
        """Sets the cooldown for a boss.

        The cooldown is set as if you had just killed the boss."""
        param = params.split(",", 2)
        if len(param) < 2:
            return await ctx.error("You must specify for which of your character is the cooldown for.\n"
                                   f"e.g. `{ctx.clean_prefix}{ctx.invoked_with} remove Kroazur,Bubble`")
        name, char = param
        if name.lower() in BOSS_ALIASES:
            name = BOSS_ALIASES[name]
        if name not in BOSS_COOLDOWNS:
            return await ctx.error(f"There's no boss with that name.\nFor a list of supported bosses, "
                                   f"try: `{ctx.clean_prefix}{ctx.invoked_with} bosslist`")

        db_char = await ctx.pool.fetchrow("""SELECT id, user_id, name FROM "character" WHERE lower(name) = $1""",
                                          char.lower())
        if db_char is None:
            return await ctx.error("There's no character registered with that name.")
        if db_char["user_id"] != ctx.author.id:
            return await ctx.error("That character is not registered to you.")
        # Check if this char already has a pending cooldown
        timer_id = await ctx.pool.fetchval("SELECT id FROM timer WHERE extra->>'char_id' = $1 AND name = $2",
                                           str(db_char["id"]), name)
        if timer_id is None:
            return await ctx.error(f"There's no active timer for boss {name} for {db_char['name']}")

        await self.delete_timer(timer_id)
        await ctx.success("Boss timer deleted.")

    @commands.guild_only()
    @checks.can_embed()
    @commands.group(aliases=["event"], invoke_without_command=True, case_insensitive=True, usage="[event id]")
    async def events(self, ctx: NabCtx, event_id: int = None):
        """Shows a list of upcoming and recent events.

        If a number is specified, it will show details for that event. Same as using `events info`"""
        if event_id is not None:
            await ctx.invoke(self.bot.all_commands.get('events').get_command("info"), event_id)
            return
        embed = discord.Embed(description="For more info about an event, use `/event info (id)`"
                                          "\nTo receive notifications for an event, use `/event sub (id)`")
        async with ctx.pool.acquire() as conn:
            recent_events = await conn.fetch("""SELECT user_id, start, name, id FROM event
                                                    WHERE active AND server_id = $1 AND start < now() AND
                                                    now()-start < $2
                                                    ORDER BY start ASC""", ctx.guild.id, RECENT_THRESHOLD)
            upcoming_events = await conn.fetch("""SELECT user_id, start, name, id FROM event
                                                      WHERE active AND server_id = $1 AND start > now()
                                                      ORDER BY start ASC""", ctx.guild.id)
        if len(recent_events) + len(upcoming_events) == 0:
            await ctx.send("There are no upcoming events.")
            return
        # Recent events
        if recent_events:
            field_name = "Recent events"
            value = ""
            for event in recent_events:
                user_id, start, name, event_id = event
                user = ctx.guild.get_member(user_id)
                author = "unknown" if user is None else user.display_name
                time_diff = dt.datetime.now(tz=dt.timezone.utc) - event["start"]
                starts_in = f"Started {round((time_diff.seconds / 60) % 60)} minutes ago"
                value += f"\n**{name}** (*ID: {event_id}*) - by **@{author}** - {starts_in}"
            embed.add_field(name=field_name, value=value, inline=False)
        # Upcoming events
        if upcoming_events:
            field_name = "Upcoming events"
            value = ""
            for event in upcoming_events:
                user_id, start, name, event_id = event
                user = ctx.guild.get_member(user_id)
                author = "unknown" if user is None else user.display_name
                time_diff = event["start"] - dt.datetime.now(tz=dt.timezone.utc)
                days, hours, minutes = time_diff.days, time_diff.seconds // 3600, (time_diff.seconds // 60) % 60
                if days:
                    starts_in = f'In {days} days, {hours} hours and {minutes} minutes'
                elif hours:
                    starts_in = f'In {hours} hours and {minutes} minutes'
                elif minutes > 0:
                    starts_in = f'In {minutes} minutes'
                else:
                    starts_in = 'Starting now!'
                value += f"\n**{name}** (*ID:{event_id}*) -  by **@{author}** - {starts_in}"
            embed.add_field(name=field_name, value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="add", usage="<starts in> <name>[,description]")
    async def event_add(self, ctx: NabCtx, starts_in: TimeString, *, params):
        """Creates a new event.

        `starts in` is in how much time the event will start from the moment of creation.
        This is done to avoid dealing with different timezones.
        Just say in how many days/hours/minutes the event is starting.

        The time can be set using units such as 'd' for days, 'h' for hours, 'm' for minutes and 'd' for seconds.
        Examples: 1d20h5m, 1d30m, 1h40m, 40m

        The event description is optional, you can also use links like: `[link title](link url)`.

        Once the event is created, the id of the event will be returned. This is used for further edits.
        """
        creator = ctx.author.id
        start = dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(seconds=starts_in.seconds)
        params = params.split(",", 1)
        name = single_line(clean_string(ctx, params[0]))
        if len(name) > EVENT_NAME_LIMIT:
            await ctx.send(f"{ctx.tick(False)} The event's name can't be longer than {EVENT_NAME_LIMIT} characters.")
            return

        event_description = ""
        if len(params) > 1:
            event_description = clean_string(ctx, params[1])

        event_count = await ctx.pool.fetchval("""SELECT count(*) FROM event
                                                     WHERE user_id = $1 AND start > now() AND active""", creator)

        if event_count >= MAX_EVENTS and not await checks.check_guild_permissions(ctx, {'manage_guild': True}):
            return await ctx.send(f"{ctx.tick(False)} You can only have {MAX_EVENTS} active events simultaneously."
                                  f"Delete or edit an active event.")

        embed = discord.Embed(title=name, description=event_description, timestamp=start)
        embed.set_footer(text="Start time")

        message = await ctx.send("Is this correct?", embed=embed)
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            return await ctx.send("You took too long!")
        if not confirm:
            return await ctx.send("Alright, no event for you.")
        event_id = await ctx.pool.fetchval("""INSERT INTO event(user_id, server_id, start, name, description)
                                                  VALUES($1, $2, $3, $4, $5)""",
                                           creator, ctx.guild.id, start, name, event_description)
        await ctx.send(f"{ctx.tick()} Event created successfully.\n\t**{name}** in *{starts_in.original}*.\n"
                       f"*To edit this event use ID {event_id}*")

    @commands.guild_only()
    @events.command(name="addplayer", aliases=["addchar"])
    async def event_addplayer(self, ctx: NabCtx, event_id: int, *, character):
        """Adds a character to an event.

        Only the creator can add characters to an event.
        If the event is joinable, anyone can join an event using `event join`"""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only add people to your own events.")
            return
        char = await ctx.pool.fetchrow(
            'SELECT id, user_id, name, world FROM "character" WHERE lower(name) = $1 AND user_id != 0',
            character.lower())

        if event["slots"] != 0 and len(event["participants"]) >= event["slots"]:
            await ctx.send(f"{ctx.tick(False)} All the slots for this event has been filled. "
                           f"You can change them by using `/event edit slots {event_id} newSlots`.")
            return

        if char is None:
            await ctx.send(f"{ctx.tick(False)} That character is not registered.")
            return
        owner = ctx.guild.get_member(char["user_id"])
        if owner is None:
            await ctx.send(f"{ctx.tick(False)} That character is not registered.")
            return
        if ctx.world != char["world"]:
            await ctx.send(f"{ctx.tick(False)} You can't add a character from another world.")
            return
        if any(owner.id == participant["user_id"] for participant in event["participants"]):
            await ctx.send(f"{ctx.tick(False)} A character of @{owner.display_name} is already participating.")
            return

        message = await ctx.send(f"Do you want to add **{char['name']}** (@{owner.display_name}) "
                                 f"to **{event['name']}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        async with ctx.pool.acquire() as conn:
            await conn.execute("INSERT INTO event_participant(event_id, character_id) VALUES($1,$2)",
                               event_id, char["id"])
            await ctx.send(f"{ctx.tick()} You successfully added **{char['name']}** to this event.")
            return

    @commands.guild_only()
    @events.group(name="edit", invoke_without_command=True, case_insensitive=True)
    async def event_edit(self, ctx):
        """Edits an event.

        Use one of the subcommands to edit the event.
        Only the creator of the event or mods can edit an event.
        Past events can't be edited."""
        content = "To edit an event, use the subcommands:```"
        for command in ctx.command.commands:  # type: commands.Command
            content += f"{ctx.clean_prefix}{command.qualified_name} {command.usage}\n"
        content += "```"
        await ctx.send(content)

    @commands.guild_only()
    @checks.can_embed()
    @event_edit.command(name="description", aliases=["desc", "details"], usage="<id> [new description]")
    async def event_edit_description(self, ctx: NabCtx, event_id: int, *, new_description=None):
        """Edits an event's description.

        If no new description is provided initially, the bot will ask for one.
        To remove the description, say `blank`."""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only edit your own events.")
            return

        if new_description is None:
            msg = await ctx.send(f"What would you like to be the new description of **{event['name']}**?"
                                 f"You can `cancel` this or set a `blank` description.")
            new_description = await ctx.input(timeout=120, delete_response=True)
            await msg.delete()
            if new_description is None:
                await ctx.send("Guess you don't want to change the description...")
                return
            if new_description.strip().lower() == "cancel":
                await ctx.send("Alright, operation cancelled.")
                return

        if new_description.strip().lower() == "blank":
            new_description = ""
        new_description = clean_string(ctx, new_description)

        embed = discord.Embed(title=event["name"], description=new_description, timestamp=event["start"])
        embed.set_footer(text="Start time")
        embed.set_author(name=ctx.author.display_name, icon_url=get_user_avatar(ctx.author))

        message = await ctx.send("Do you want this to be the new description?", embed=embed)
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, no changes will be done.")
            return

        await ctx.pool.execute("UPDATE event SET description = $1 WHERE id = $2", new_description, event_id)

        if event["user_id"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event's description was changed successfully.")
        else:
            await ctx.send(f"{ctx.tick()} Event's description changed successfully.")
            creator = self.bot.get_member(event["user_id"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** had its description changed by "
                                   f"{ctx.author.mention}", embed=embed)
        await self.notify_subscribers(event_id, f"The description of event **{event['name']}** was changed.",
                                      embed=embed, skip_creator=True)

    @commands.guild_only()
    @event_edit.command(name="joinable", aliases=["open"], usage="<id> [yes/no]")
    async def event_edit_joinable(self, ctx: NabCtx, event_id: int, *, yes_no: str = None):
        """Changes whether anyone can join an event or only the owner may add people.

        If an event is joinable, anyone can join using `event join id`  .
        Otherwise, the event creator has to add people with `event addplayer id`.
        """
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only edit your own events.")
            return

        if yes_no is None:
            msg = await ctx.send(f"Do you want **{event['name']}** to be joinable? `yes/no/cancel`")
            new_joinable = await ctx.input(timeout=120, delete_response=True)
            await msg.delete()
            if new_joinable is None:
                await ctx.send("Guess you don't want to change the time...")
                return
            if new_joinable.strip().lower() == "cancel":
                await ctx.send("Alright, operation cancelled.")
                return
            joinable = new_joinable.lower() in ["yes", "yeah"]
        else:
            joinable = yes_no.lower() in ["yes", "yeah"]
        joinable_string = "joinable" if joinable else "not joinable"

        await ctx.pool.execute("UPDATE event SET joinable = $1 WHERE id = $2", joinable, event_id)

        if event["user_id"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()}Your event's was changed succesfully to **{joinable_string}**.")
        else:
            await ctx.send(f"{ctx.tick} Event is now **{joinable_string}**.")
            creator = self.bot.get_member(event["user_id"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was changed to **{joinable_string}** "
                                   f"by {ctx.author.mention}.")

    @commands.guild_only()
    @event_edit.command(name="name", aliases=["title"], usage="<id> [new name]")
    async def event_edit_name(self, ctx: NabCtx, event_id: int, *, new_name=None):
        """Edits an event's name.

        If no new name is provided initially, the bot will ask for one."""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only edit your own events.")
            return

        if new_name is None:
            msg = await ctx.send(f"What would you like to be the new name of **{event['name']}**?"
                                 f"You can `cancel` this.")
            new_name = await ctx.input(timeout=120, delete_response=True)
            await msg.delete()
            if new_name is None:
                await ctx.send("Guess you don't want to change the name...")
                return
            if new_name.strip().lower() == "cancel":
                await ctx.send("Alright, operation cancelled.")
                return

        new_name = single_line(clean_string(ctx, new_name))
        if len(new_name) > EVENT_NAME_LIMIT:
            await ctx.send(f"{ctx.tick(False)} The name can't be longer than {EVENT_NAME_LIMIT} characters.")
            return
        message = await ctx.send(f"Do you want to change the name of **{event['name']}** to **{new_name}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, name remains the same.")
            return

        await ctx.pool.execute("UPDATE event SET name = $1 WHERE id = $2", new_name, event_id)

        if event["user_id"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event was renamed successfully to **{new_name}**.")
        else:
            await ctx.send(f"{ctx.tick()} Event renamed successfully to **{new_name}**.")
            creator = self.bot.get_member(event["user_id"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was renamed to **{new_name}** by "
                                   f"{ctx.author.mention}")
        await self.notify_subscribers(event_id, f"The event **{event['name']}** was renamed to **{new_name}**.",
                                      skip_creator=True)

    @commands.guild_only()
    @event_edit.command(name="slots", aliases=["size"], usage="<id> [new slots]")
    async def event_edit_slots(self, ctx: NabCtx, event_id: int, slots: int = None):
        """Edits an event's number of slots

        Slots is the number of characters an event can have. By default this is 0, which means no limit."""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only edit your own events.")
            return

        if slots is None:
            msg = await ctx.send(f"What would you like to be the new number of slots for  **{event['name']}**? "
                                 f"You can `cancel` this.\n Note that `0` means no slot limit.")
            slots = await ctx.input(timeout=120, delete_response=True)
            await msg.delete()
            if slots is None:
                await ctx.send("Guess you don't want to change the name...")
                return
            if slots.strip().lower() == "cancel":
                await ctx.send("Alright, operation cancelled.")
                return
        try:
            slots = int(slots)
            if slots < 0:
                await ctx.send(f"{ctx.tick(False)} You can't have negative slots!")
                return
        except ValueError:
            await ctx.send(f"{ctx.tick(False)}That's not a number...")
            return
        message = await ctx.send(f"Do you want the number of slots of **{event['name']}** to **{slots}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, slots remain unchanged.")
            return

        await ctx.pool.execute("UPDATE event SET slots = $1 WHERE id = $2", slots, event_id)

        if event["user_id"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event slots were changed to **{slots}**.")
        else:
            await ctx.send(f"{ctx.tick()} Event slots changed to **{slots}**.")
            creator = self.bot.get_member(event["user_id"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** slots were changed to **{slots}** by "
                                   f"{ctx.author.mention}")

    @commands.guild_only()
    @checks.can_embed()
    @event_edit.command(name="time", aliases=["start"], usage="<id> [new start time]")
    async def event_edit_time(self, ctx: NabCtx, event_id: int, starts_in: TimeString = None):
        """Edit's an event's start time.

        If no new time is provided initially, the bot will ask for one."""
        now = dt.datetime.now(dt.timezone.utc)
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only edit your own events.")
            return

        if starts_in is None:
            msg = await ctx.send(f"When would you like the new start time of **{event['name']}** be?"
                                 f"You can `cancel` this.\n Examples: `1h20m`, `2d10m`")

            new_time = await ctx.input(timeout=120, delete_response=True)
            await msg.delete()
            if new_time is None:
                await ctx.send("Guess you don't want to change the time...")
                return
            if new_time.strip().lower() == "cancel":
                await ctx.send("Alright, operation cancelled.")
                return

            try:
                starts_in = TimeString(new_time)
            except commands.BadArgument as e:
                await ctx.send(str(e))
                return
        new_time = now + dt.timedelta(seconds=starts_in.seconds)
        embed = discord.Embed(title=event["name"], timestamp=new_time)
        embed.set_footer(text="Start time")
        message = await ctx.send(f"This will be the new time of your event in your local time. Is this correct?",
                                 embed=embed)
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, event remains the same.")
            return

        await ctx.pool.execute("UPDATE event SET start = $1 WHERE id = $2", new_time, event_id)

        if event["user_id"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()}Your event's start time was changed successfully to **{starts_in.original}**.")
        else:
            await ctx.send(f"{ctx.tick()}Event's time changed successfully.")
            creator = self.bot.get_member(event["user_id"])
            if creator is not None:
                await creator.send(f"The start time of your event **{event['name']}** was changed to "
                                   f"**{starts_in.original}** by {ctx.author.mention}.")
        await self.notify_subscribers(event_id, f"The start time of **{event['name']}** was changed:", embed=embed,
                                      skip_creator=True)

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="info", aliases=["show"])
    async def event_info(self, ctx: NabCtx, event_id: int):
        """Displays an event's info.

        The start time shown in the footer is always displayed in your device's timezone."""
        event = await self.get_event(ctx, event_id)
        if not event:
            await ctx.send(f"{ctx.tick(False)} There's no event with that id.")
            return
        guild = self.bot.get_guild(event["server_id"])
        author = self.bot.get_member(event["user_id"], guild)
        embed = discord.Embed(title=event["name"], description=event["description"], timestamp=event["start"])
        if author is not None:
            if guild is None:
                author_name = author.name
            else:
                author_name = author.display_name
            author_icon = author.avatar_url if author.avatar_url else author.default_avatar_url
            embed.set_author(name=author_name, icon_url=author_icon)
        embed.set_footer(text="Start time")
        if len(event["participants"]) > 0:
            slots = ""
            if event["slots"] > 0:
                slots = f"/{event['slots']}"
            embed.add_field(name="Participants", value=f"{len(event['participants'])}{slots}")

        await ctx.send(embed=embed)

    @commands.guild_only()
    @events.command(name="join")
    async def event_join(self, ctx, event_id: int, *, character: str):
        """Join an event with a specific character

        You can only join an event with a character at a time.
        Some events may not be joinable and require the creator to add characters themselves."""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        async with ctx.pool.acquire() as conn:
            char = await conn.fetchrow('SELECT id, user_id, name, world FROM "character" WHERE lower(name) = $1',
                                       character.lower())
        if event["joinable"] != 1:
            await ctx.send(f"{ctx.tick(False)} You can't join this event."
                           f"Maybe you meant to subscribe? Try `/event sub {event_id}`.")
            return
        if event["slots"] != 0 and len(event["participants"]) >= event["slots"]:
            await ctx.send(f"{ctx.tick(False)} All the slots for this event has been filled.")
            return
        if char is None:
            await ctx.send(f"{ctx.tick(False)} That character is not registered.")
            return
        if char["user_id"] != ctx.author.id:
            await ctx.send(f"{ctx.tick(False)} You can only join with characters registered to you.")
            return
        world = self.bot.tracked_worlds.get(event["server_id"])
        if world != char["world"]:
            await ctx.send(f"{ctx.tick(False)} You can't join with a character from another world.")
            return
        if any(ctx.author.id == participant["user_id"] for participant in event["participants"]):
            await ctx.send(f"{ctx.tick(False)} A character of yours is already in this event.")
            return

        message = await ctx.send(f"Do you want to join the event '**{event['name']}**' as **{char['name']}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        await ctx.pool.execute("""INSERT INTO event_participant(event_id, character_id) VALUES($1, $2)
                                      ON CONFLICT(event_id, character_id) DO NOTHING""", event_id, char["id"])
        await ctx.send(f"{ctx.tick()} You successfully joined this event.")

    @commands.guild_only()
    @events.command(name="leave")
    async def event_leave(self, ctx, event_id: int):
        """Leave an event you were participating in."""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        joined_char = next((participant["character_id"] for participant in event["participants"]
                            if ctx.author.id == participant["user_id"]), None)
        if joined_char is None:
            await ctx.send(f"{ctx.tick(False)} You haven't joined this event.")
            return

        message = await ctx.send(f"Do you want to leave **{event['name']}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        await ctx.pool.execute("DELETE FROM event_participant WHERE event_id = $1 AND character_id = $2",
                               event_id, joined_char)
        await ctx.send(f"{ctx.tick()} You successfully left this event.")

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="make", aliases=["creator", "maker"])
    async def event_make(self, ctx: NabCtx):
        """Creates an event guiding you step by step

        Instead of using confusing parameters, commas and spaces, this commands has the bot ask you step by step."""

        event_count = await ctx.pool.fetchval("""SELECT count(*) FROM event
                                                     WHERE user_id = $1 AND start > now() AND active""", ctx.author.id)
        if event_count >= MAX_EVENTS and not await checks.check_guild_permissions(ctx, {'manage_guild': True}):
            await ctx.send(f"{ctx.tick(False)} You can only have {MAX_EVENTS} active events simultaneously."
                           f"Delete or edit an active event.")
            return
        msg = await ctx.send("Let's create an event. What would you like the name to be? You can `cancel` at any time.")
        cancel = False
        while True:
            name = await ctx.input(timeout=120.0, clean=True, delete_response=True)
            if name is None:
                await ctx.send("Nevermind then.")
                cancel = True
                break
            name = single_line(name)
            if len(name) > EVENT_NAME_LIMIT:
                await ctx.send(f"The name cannot be longer than {EVENT_NAME_LIMIT} characters. Tell me another name.")
                continue
            elif name.strip().lower() == "cancel":
                await ctx.send("Alright, event making cancelled.")
                cancel = True
                break
            else:
                break
        await msg.delete()
        if cancel:
            return

        embed = discord.Embed(title=name)
        embed.set_author(name=ctx.author.display_name, icon_url=get_user_avatar(ctx.author))
        msg = await ctx.send(f"Your event will be named **{name}**.\nNow, what description would you like your event "
                             f"to have? `none/blank` to leave it empty. Bold, italics and links are supported."
                             f"\nThis is your event so far:", embed=embed)

        while True:
            description = await ctx.input(timeout=120.0, delete_response=True)
            if description is None:
                await ctx.send(f"You took too long {ctx.author.mention}, event making cancelled.")
                cancel = True
                break
            elif description.strip().lower() == "cancel":
                await ctx.send("Alright, event making cancelled.")
                cancel = True
                break
            if description.strip().lower() in ["blank", "none"]:
                description = ""
            embed.description = description
            await msg.delete()
            msg = await ctx.send("Is this right?", embed=embed)
            confirm = await ctx.react_confirm(msg, timeout=60)
            if confirm is None:
                await ctx.send(f"Where did you go {ctx.author.mention}? Ok, event making cancelled.")
                cancel = True
                break
            if confirm is False:
                await msg.delete()
                msg = await ctx.send(f"Alright, again, tell me the description you want for your event.\nRemember you "
                                     f"can `cancel` the process or tell me `blank` to have no description.")
            else:
                break

        await msg.delete()
        if cancel:
            return

        msg = await ctx.send(f"Alright, now tell me in how many time will the event start from now. `e.g. 2d1h20m, 4h`"
                             f"\nThis is your event so far:", embed=embed)
        while True:
            start_time = dt.datetime.now(dt.timezone.utc)
            start_str = await ctx.input(timeout=60, delete_response=True)
            if start_str is None:
                await ctx.send(f"You took too long {ctx.author.mention}, event making cancelled.")
                cancel = True
                break
            if start_str.lower() == "cancel":
                await ctx.send("Alright, event making cancelled.")
                cancel = True
                break
            try:
                starts_in = TimeString(start_str)
                start_time += dt.timedelta(seconds=starts_in.seconds)
            except commands.BadArgument as e:
                await msg.delete()
                msg = await ctx.send(f'{e}\nAgain, tell me the start time of the event from now.\n'
                                     f'You can `cancel` if you want.')
                continue
            await msg.delete()
            msg = await ctx.send("Is this correct in your local timezone?", embed=discord.Embed(timestamp=start_time))
            confirm = await ctx.react_confirm(msg, timeout=60, )
            if confirm is None:
                await ctx.send(f"Where did you go {ctx.author.mention}? Ok, event making cancelled.")
                cancel = True
                return
            if confirm is False:
                await msg.delete()
                msg = await ctx.send(f"Ok, again, tell me when will the event start.\nRemember you "
                                     f"can `cancel` the process.")
            else:
                break

        await msg.delete()
        if cancel:
            return

        embed.timestamp = start_time
        msg = await ctx.send("This will be your event, confirm that everything is correct and we will be done.",
                             embed=embed)
        confirm = await ctx.react_confirm(msg, timeout=120, delete_after=True)
        if not confirm:
            await ctx.send("Alright, guess all this was for nothing. Goodbye!")
            return

        event_id = await ctx.pool.fetchval("""INSERT INTO event(user_id, server_id, start, name, description)
                                                  VALUES($1, $2, $3, $4, $5)""",
                                           ctx.author.id, ctx.guild.id, start_time, name, description)
        await ctx.send(f"{ctx.tick()} Event registered successfully.\n\t**{name}** in *{starts_in.original}*.\n"
                       f"*To edit this event use ID {event_id}*")

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="participants")
    async def event_participants(self, ctx: NabCtx, event_id: int):
        """Shows the list of characters participating in this event."""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if len(event["participants"]) == 0:
            join_prompt = ""
            if event["joinable"] != 0:
                join_prompt = f" To join, use `/event join {event_id} characterName`."
            await ctx.send(f"{ctx.tick(False)} There are no participants in this event.{join_prompt}")
            return
        entries = []
        vocations = []
        for char in event["participants"]:  # type: Dict[str, Any]
            char["level"] = abs(char["level"])
            char["emoji"] = get_voc_emoji(char["vocation"])
            vocations.append(char["vocation"])
            char["vocation"] = get_voc_abb(char["vocation"])
            owner = ctx.guild.get_member(int(char["user_id"]))
            char["owner"] = "unknown" if owner is None else owner.display_name
            entries.append("**{name}** - {level} {vocation}{emoji} - **@{owner}**".format(**char))
        author = ctx.guild.get_member(int(event["user_id"]))
        author_name = None
        author_icon = None
        if author is not None:
            author_name = author.display_name
            author_icon = author.avatar_url if author.avatar_url else author.default_avatar_url
        pages = VocationPages(ctx, entries=entries, per_page=15, vocations=vocations)
        pages.embed.title = event["name"]
        pages.embed.set_author(name=author_name, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @events.command(name="remove", aliases=["delete", "cancel"])
    async def event_remove(self, ctx: NabCtx, event_id: int):
        """Deletes or cancels an event."""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only delete your own events.")
            return

        message = await ctx.send("Do you want to delete the event **{0}**?".format(event["name"]))
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, event remains active.")
            return

        await ctx.pool.execute("UPDATE event SET active = false WHERE id = $1", event_id)
        if event["user_id"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event was deleted successfully.")
        else:
            await ctx.send(f"{ctx.tick()} Event deleted successfully.")
            creator = ctx.guild.get_member(event["user_id"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was deleted by {ctx.author.mention}.")
        await self.notify_subscribers(event_id, f"The event **{event['name']}** was deleted by {ctx.author.mention}.",
                                      skip_creator=True)

    @commands.guild_only()
    @events.command(name="removeplayer", aliases=["removechar"])
    async def event_removeplayer(self, ctx: NabCtx, event_id: int, *, character):
        """Removes a player from an event.

        Players can remove themselves using `event leave`"""
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["user_id"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only add people to your own events.")
            return
        char = await ctx.pool.fetchrow('SELECT id, user_id, name FROM "character" WHERE lower(name) = $1',
                                       character.lower())
        if char is None:
            return await ctx.send(f"{ctx.tick(False)} This character doesn't exist.")
        joined_char = next((participant["character_id"] for participant in event["participants"]
                            if char["id"] == participant["character_id"]), None)
        if joined_char is None:
            await ctx.send(f"{ctx.tick(False)} This character is not in this event.")
            return
        owner = ctx.guild.get_member(char["user_id"])
        owner_name = "unknown" if owner is None else owner.display_name
        message = await ctx.send(f"Do you want to remove **{char['name']}** (@**{owner_name}**) "
                                 f"from **{event['name']}**?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        await ctx.pool.execute("DELETE FROM event_participant WHERE event_id = $1 AND character_id = $2",
                               event_id, char["id"])
        await ctx.send(f"{ctx.tick()} You successfully left this event.")

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="subscribe", aliases=["sub"])
    async def event_subscribe(self, ctx, event_id: int):
        """Subscribe to receive a PM when an event is happening."""
        author = ctx.author
        event = await self.get_event(ctx, event_id)
        if event is None:
            return await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
        if ctx.author.id in event["subscribers"]:
            return await ctx.send(f"{ctx.tick(False)} You're already subscribed to this event.")
        message = await ctx.send(f"Do you want to subscribe to **{event['name']}**")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then.")
            return

        await ctx.pool.execute("INSERT INTO event_subscriber(event_id, user_id) VALUES($1, $2)", event_id, author.id)
        await ctx.send(f"{ctx.tick()} You have subscribed successfully to this event. "
                       f"I'll let you know when it's happening.")

    @commands.guild_only()
    @events.command(name="unsubscribe", aliases=["unsub"])
    async def event_unsubscribe(self, ctx, event_id: int):
        """Unsubscribe to an event."""
        author = ctx.author
        event = await self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        print(ctx.author.id, event["subscribers"])
        if ctx.author.id not in event["subscribers"]:
            return await ctx.send(f"{ctx.tick(False)} You are not subscribed to this event.")
        message = await ctx.send(f"Do you want to unsubscribe to **{event['name']}**")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then.")
            return

        await ctx.pool.execute("DELETE FROM event_subscriber WHERE event_id = $1 AND user_id = $2", event_id, author.id)
        await ctx.send(f"{ctx.tick()} You have unsubscribed from this event.")

    @commands.command()
    async def remindme(self, ctx: NabCtx, when: TimeString, *, what: clean_content):
        """Creates a personal reminder.

        You will be notified in the same channel when the time is over."""
        now = dt.datetime.now(tz=dt.timezone.utc)
        expires = now+dt.timedelta(seconds=when.seconds)
        await self.create_timer(now, expires, what, ReminderType.CUSTOM, ctx.author.id, {"message": ctx.message.id,
                                                                                         "channel": ctx.channel.id})
        await ctx.success(f"Ok, I will remind you in {when.original} about: {what}")

    async def await_next_timer(self, connection=None, days=7) -> Timer:
        """Finds the next upcoming timer

        If there's no upcoming timer in the specified days, it will keep waiting until there's one.
        It returns the timer when found."""
        timer = await self.get_next_timer(connection=connection,days=days)
        if timer is not None:
            self._timer_available.set()
            return timer

        self._timer_available.clear()
        self._next_timer = None
        await self._timer_available.wait()
        return await self.get_next_timer(connection=connection, days=7)

    async def create_timer(self, created: dt.datetime, expires: dt.datetime, name: str, type: ReminderType,
                           user_id: int, extra, connection=None) -> Optional[Timer]:
        """Creates a new timer.

        If the created timer is the upcoming timer, it restarts the tasks."""
        conn = connection or self.bot.pool
        delta = (expires - created).total_seconds()
        query = """INSERT INTO timer(name, type, extra, expires, created, user_id)
                   VALUES($1, $2, $3::jsonb, $4, $5, $6)
                   RETURNING id"""

        timer = Timer.build(name=name, expires=expires, type=type, extra=extra, user_id=user_id, created=created)
        if delta <= 60:
            log.debug(f"{self.tag} Reminder is too short.")
            self.bot.loop.create_task(self.run_short_timer(delta, timer))
            return timer

        id = await conn.fetchval(query, name, type.value, extra, expires, created, user_id)
        timer.id = id
        log.debug(f"{self.tag} Timer created {timer}")
        if delta <= (86400 * 40):  # 40 days
            self._timer_available.set()

        if self._next_timer and expires < self._next_timer.expires:
            log.debug(f"{self.tag} Timer is newer than next timer, restarting task")
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())
        return timer

    async def delete_timer(self, timer_id: int, connection=None):
        """Deletes a timer.

        If the timer was the next timer, it restarts the task."""
        conn = connection or self.bot.pool
        await conn.execute("DELETE FROM timer WHERE id = $1", timer_id)
        log.debug(f"{self.tag} Timer with id {timer_id} deleted.")
        if self._next_timer and self._next_timer.id == timer_id:
            log.debug(f"{self.tag} Next timer was deleted, restarting task.")
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())

    async def get_next_timer(self, connection=None, days=7) -> Optional[Timer]:
        """Gets the first upcoming timer, if any."""
        query = "SELECT * FROM timer WHERE expires < (CURRENT_DATE + $1::interval) ORDER BY expires ASC"
        conn = connection or self.bot.pool

        record = await conn.fetchrow(query, dt.timedelta(days=days))
        if record is None:
            return None
        timer = Timer(record)
        return timer

    async def get_event(self, ctx: NabCtx, event_id: int) -> Optional[Dict[str, Any]]:
        # If this is used on a PM, show events for all shared servers
        if ctx.is_private:
            guilds = self.bot.get_user_guilds(ctx.author.id)
        else:
            guilds = [ctx.guild]
        guild_ids = [s.id for s in guilds]
        async with ctx.pool.acquire() as conn:
            event = await conn.fetchrow("""SELECT id, name, description, active, reminder, slots, user_id,
                                           server_id, start, joinable
                                           FROM event WHERE id = $1 AND start > now() AND server_id = any($2)""",
                                        event_id, guild_ids)
            if event is None:
                return None
            event = dict(event)
            participants = await conn.fetch("""SELECT name, abs(level) as level, vocation, world, user_id,
                                               c.id as character_id
                                               FROM event_participant ep
                                               LEFT JOIN "character" c on c.id = ep.character_id
                                               WHERE event_id = $1""", event_id)
            subscribers = await conn.fetch("SELECT user_id FROM event_subscriber WHERE event_id = $1", event_id)
            event["subscribers"] = [s[0] for s in subscribers]
            event["participants"] = [dict(p) for p in participants]
        return event

    async def notify_subscribers(self, event_id: int, content, *, embed: discord.Embed = None, skip_creator=False):
        """Sends a message to all users subscribed to an event"""
        async with self.bot.pool.acquire() as conn:
            creator = await conn.fetchval("SELECT user_id FROM event WHERE id = $1", event_id)
            if creator is None:
                return
            _subscribers = await conn.fetch("SELECT user_id FROM event_subscriber WHERE event_id = $1", event_id)
            subscribers = [s[0] for s in _subscribers]
        if not subscribers:
            return
        for subscriber in subscribers:
            if subscriber == creator and skip_creator:
                continue
            member = self.bot.get_user(subscriber)
            if member is None:
                continue
            await member.send(content, embed=embed)

    def __unload(self):
        log.info(f"{self.tag} Unloading cog")
        self.timers_task.cancel()
        self.events_announce_task.cancel()


def setup(bot):
    bot.add_cog(Timers(bot))
