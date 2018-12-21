import asyncio
import datetime as dt
import logging
from enum import Enum
from typing import Optional

import asyncpg
import discord
import tibiawikisql
from discord.ext import commands
from discord.ext.commands import clean_content

from cogs.utils.context import NabCtx
from cogs.utils.converter import TimeString
from cogs.utils.database import wiki_db
from cogs.utils.pages import Pages, CannotPaginate
from nabbot import NabBot


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


class Timers:
    def __init__(self, bot: NabBot):
        self.bot = bot
        self._timer_available = asyncio.Event(loop=bot.loop)
        self.timers_task = self.bot.loop.create_task(self.check_timers())
        self._next_timer = None

    async def check_timers(self):
        """Checks the first upcoming time and waits for it."""
        try:
            await self.bot.wait_until_ready()
            log.debug(f"[{self.__class__.__name__}] Starting await_timers task")
            while not self.bot.is_closed():
                timer = self._next_timer = await self.await_next_timer(days=40)
                log.debug(f"[{self.__class__.__name__}] Next timer: {timer}")
                now = dt.datetime.now(tz=dt.timezone.utc)
                if timer.expires >= now:
                    wait_time = (timer.expires-now)
                    log.debug(f"[{self.__class__.__name__}] Sleeping for {wait_time}")
                    await asyncio.sleep(wait_time.total_seconds())
                await self.run_timer(timer)
        except asyncio.CancelledError:
            pass
        except(OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())
        except:
            log.exception(f"[{self.__class__.__name__}] Error in task")

    async def run_timer(self, timer, short=False):
        """Dispatches an event for the timer."""
        if not short:
            query = "DELETE FROM timer WHERE id=$1;"
            await self.bot.pool.execute(query, timer.id)
        log.debug(f"[{self.__class__.__name__}] Executing timer {timer}")
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
                log.debug(f"[{self.__class__.__name__}] Timer in channel that no longer exists.")
                return
            guild_id = channel.guild.id if isinstance(channel, discord.TextChannel) else "@me"
            message_id = timer.extra["message"]

            await channel.send(f'{user.mention}, you asked me to remind you this: {timer.name}'
                               f'\n<https://discordapp.com/channels/{guild_id}/{channel.id}/{message_id}>')
        except KeyError:
            log.debug(f"[{self.__class__.__name__}] Corrupt custom timer.")

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
            log.debug(f"[{self.__class__.__name__}] Couldn't send boss timer to user {author} due to privacy settings.")

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
            log.debug(f"[{self.__class__.__name__}] Reminder is too short.")
            self.bot.loop.create_task(self.run_short_timer(delta, timer))
            return timer

        id = await conn.fetchval(query, name, type.value, extra, expires, created, user_id)
        timer.id = id
        log.debug(f"[{self.__class__.__name__}] Timer created {timer}")
        if delta <= (86400 * 40):  # 40 days
            self._timer_available.set()

        if self._next_timer and expires < self._next_timer.expires:
            log.debug(f"[{self.__class__.__name__}] Timer is newer than next timer, restarting task")
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())
        return timer

    async def delete_timer(self, timer_id: int, connection=None):
        """Deletes a timer.

        If the timer was the next timer, it restarts the task."""
        conn = connection or self.bot.pool
        await conn.execute("DELETE FROM timer WHERE id = $1", timer_id)
        log.debug(f"[{self.__class__.__name__}] Timer with id {timer_id} deleted.")
        if self._next_timer and self._next_timer.id == timer_id:
            log.debug(f"[{self.__class__.__name__}] Next timer was deleted, restarting task.")
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


def setup(bot):
    bot.add_cog(Timers(bot))
