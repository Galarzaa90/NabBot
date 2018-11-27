import asyncio
import datetime as dt
import json
import logging
from enum import Enum
from typing import Optional

import asyncpg
import discord
from discord.ext import commands
from discord.ext.commands import clean_content

from cogs.utils.context import NabCtx
from cogs.utils.converter import TimeString
from nabbot import NabBot


class ReminderType(Enum):
    CUSTOM = 0
    BOSS = 1
    TASK = 2


log = logging.getLogger("nabbot")


class Timer:
    def __init__(self, record):
        self.id = record["id"]
        self.name = record["name"]
        self.type = record["type"]
        if isinstance(self.type, int):
            self.type = ReminderType(self.type)
        self.extra = record["extra"]
        if isinstance(self.extra, str):
            self.extra = json.loads(self.extra)
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

    async def run_short_timer(self, seconds, timer: Timer):
        await asyncio.sleep(seconds)
        await self.run_timer(timer, True)

    async def on_custom_timer_complete(self, timer: Timer):
        try:
            channel = self.bot.get_channel(timer.extra["channel"])
            author: discord.User = self.bot.get_user(timer.extra["author"])
            if channel is None:
                # Check if it is a PM
                if author:
                    channel = author.dm_channel
                else:
                    log.debug(f"[{self.__class__.__name__}] Timer in channel that no longer exists.")
                    return
            guild_id = channel.guild.id if isinstance(channel, discord.TextChannel) else "@me"
            message_id = timer.extra["message"]

            await channel.send(f'{author.mention}, you asked me to remind you this: {timer.name}'
                               f'\n<https://discordapp.com/channels/{guild_id}/{channel.id}/{message_id}>')
        except KeyError:
            log.debug(f"[{self.__class__.__name__}] Corrupt custom timer.")

    @commands.command()
    async def remindme(self, ctx: NabCtx, when: TimeString, *, what: clean_content):
        expires = dt.datetime.now(tz=dt.timezone.utc)+dt.timedelta(seconds=when.seconds)
        await self.create_timer(expires, what, ReminderType.CUSTOM, {"message": ctx.message.id,
                                                                     "author": ctx.author.id,
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

    async def get_next_timer(self, connection=None, days=7) -> Optional[Timer]:
        """Gets the first upcoming timer, if any."""
        query = "SELECT * FROM timer WHERE expires < (CURRENT_DATE + $1::interval) ORDER BY expires ASC"
        conn = connection or self.bot.pool

        record = await conn.fetchrow(query, dt.timedelta(days=days))
        if record is None:
            return None
        timer = Timer(record)
        return timer

    async def create_timer(self, expires: dt.datetime, name: str, type: ReminderType, extra, connection=None) -> Timer:
        """Creates a new timer.

        If the created timer is the upcoming timer, it restarts the tasks."""
        conn = connection or self.bot.pool
        now = dt.datetime.now(dt.timezone.utc)
        delta = (expires-now).total_seconds()
        query = """INSERT INTO timer(name, type, extra, expires, created)
                   VALUES($1, $2, $3, $4, $5)
                   RETURNING id"""

        timer = Timer.build(name=name, expires=expires, type=type, extra=extra, created=now)
        if delta <= 60:
            log.debug(f"[{self.__class__.__name__}] Reminder is too short.")
            self.bot.loop.create_task(self.run_short_timer(delta, timer))
            return timer

        id = await conn.fetchval(query, name, type.value, json.dumps(extra), expires, now)
        timer.id = id
        log.debug(f"[{self.__class__.__name__}] Timer created {timer}")
        if delta <= (86400 * 40):  # 40 days
            self._timer_available.set()

        if self._next_timer and expires < self._next_timer.expires:
            log.debug(f"[{self.__class__.__name__}] Timer is newer than next timer, restarting task")
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())
        return timer



def setup(bot):
    bot.add_cog(Timers(bot))
