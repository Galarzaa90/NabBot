import asyncio
import datetime as dt
import logging
from enum import Enum
from typing import List, Optional

import asyncpg
import discord
import tibiawikisql
from discord.ext import commands
from discord.ext.commands import clean_content

from cogs.utils import errors
from cogs.utils.timing import HumanDelta
from nabbot import NabBot
from .utils import CogUtils, checks, clean_string, get_user_avatar, single_line
from .utils.context import NabCtx
from .utils.converter import TimeString
from .utils.database import DbChar, PoolConn, get_server_property, wiki_db
from .utils.errors import CannotPaginate
from .utils.pages import Pages, VocationPages
from .utils.tibia import get_voc_abb, get_voc_emoji

EVENT_NAME_LIMIT = 50
EVENT_DESCRIPTION_LIMIT = 400
MAX_EVENTS = 3
RECENT_THRESHOLD = dt.timedelta(minutes=30)

FIRST_NOTIFICATION = dt.timedelta(hours=1)
SECOND_NOTIFICATION = dt.timedelta(minutes=30)
THIRD_NOTIFICATION = dt.timedelta(minutes=10)
NOTIFICATIONS = [FIRST_NOTIFICATION, SECOND_NOTIFICATION, THIRD_NOTIFICATION, dt.timedelta()]
TIME_MARGIN = dt.timedelta(minutes=1)

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
    "Lloyd": dt.timedelta(hours=20),
    "Lady Tenebris": dt.timedelta(hours=20),
    "Melting Frozen Horror": dt.timedelta(hours=20),
    "The Enraged Thorn Knight": dt.timedelta(hours=20),
    "Dragonking Zyrtarch": dt.timedelta(hours=20),
    "The Time Guardian": dt.timedelta(hours=20),
    "The Last Lore Keeper": dt.timedelta(days=14),
    "Anomaly": dt.timedelta(hours=20),
    "Rupture": dt.timedelta(hours=20),
    "Realityquake": dt.timedelta(hours=20),
    "Eradicator": dt.timedelta(hours=20),
    "Outburst": dt.timedelta(hours=20),
    "World Devourer": dt.timedelta(days=14),
    "Ravennous Hunger": dt.timedelta(hours=20),
    "The Souldespoiler": dt.timedelta(hours=20),
    "The Armored Voidborn": dt.timedelta(hours=20),
    "The Sandking": dt.timedelta(hours=20),
    "The False God": dt.timedelta(hours=20),
    "Essence of Malice": dt.timedelta(hours=20),
    "The Source of Corruption": dt.timedelta(hours=20),
    "Kroazur": dt.timedelta(hours=2),
    "Bloodback": dt.timedelta(hours=20),
    "Darkfang": dt.timedelta(hours=20),
    "Sharpclaw": dt.timedelta(hours=20),
    "Black Vixen": dt.timedelta(hours=20),
    "Shadowpelt": dt.timedelta(hours=20),
    "Plagirath": dt.timedelta(days=2),
    "Zamulosh": dt.timedelta(days=2),
    "Mazoran": dt.timedelta(days=2),
    "Razzagorn": dt.timedelta(days=2),
    "Shulgrax": dt.timedelta(days=2),
    "Tarbaz": dt.timedelta(days=2),
    "Ragiaz": dt.timedelta(days=2),
    "Ferumbras Mortal Shell": dt.timedelta(days=14),
    "Grand Master Oberon": dt.timedelta(hours=20),
    "Deathstrike": dt.timedelta(hours=20),
    "Gnomevil": dt.timedelta(hours=20),
    "Versperoth": dt.timedelta(hours=20),
    "The Baron from Below": dt.timedelta(hours=4),
    "The Count of The Core": dt.timedelta(hours=4),
    "Ancient Spawn Of Morgathla": dt.timedelta(hours=4)
}


log = logging.getLogger("nabbot")


class ReminderType(Enum):
    CUSTOM = 0
    BOSS = 1
    TASK = 2
    EVENT = 3


class Event:
    """Represents a user created event."""
    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id", 0)
        self.user_id: int = kwargs.get("user_id")
        self.server_id: int = kwargs.get("server_id")
        self.name: str = kwargs.get("name")
        self.description: Optional[str] = kwargs.get("description")
        self.start: dt.datetime = kwargs.get("start")
        self.active: bool = kwargs.get("active")
        self.reminder: int = kwargs.get("reminder")
        self.joinable: bool = kwargs.get("joinable")
        self.slots: int = kwargs.get("slots", 0)
        self.modified: dt.datetime = kwargs.get("modified")
        self.created: dt.datetime = kwargs.get("created")
        # Populated
        self.subscribers:  List[int] = kwargs.get("subscribers", [])
        self.participants: List[DbChar] = kwargs.get("participants")
        # Not a SQL row
        self.notification: dt.datetime = kwargs.get("notification")

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.id} name={self.name!r} user_id={self.user_id} " \
            f"server_id={self.server_id} reminder={self.reminder} start='{self.start}'>"

    @property
    def participant_users(self) -> List[int]:
        """A list of the owners of currently registered participants."""
        return [c.user_id for c in self.participants]

    async def add_participant(self, conn: PoolConn, char: DbChar):
        """Adds a character to the participants list."""
        await conn.execute("INSERT INTO event_participant(event_id, character_id) VALUES($1,$2)",
                           self.id, char.id)
        self.participants.append(char)

    async def remove_participant(self, conn: PoolConn, char: DbChar):
        """Removes a character from the participant list."""
        await conn.execute("DELETE FROM event_participant WHERE event_id = $1 AND character_id = $2",
                           self.id, char.id)
        try:
            self.participants.remove(char)
        except ValueError:
            pass

    async def add_subscriber(self, conn: PoolConn, user_id: int):
        """Adds a user to the event's subscribers"""
        await conn.execute("INSERT INTO event_subscriber(event_id, user_id) VALUES($1,$2)",
                           self.id, user_id)
        self.subscribers.append(user_id)

    async def remove_subscriber(self, conn: PoolConn, user_id: int):
        """Removes a user from the event's subscribers"""
        await conn.execute("DELETE FROM event_subscriber WHERE event_id = $1 AND user_id = $2",
                           self.id, user_id)
        try:
            self.subscribers.remove(user_id)
        except ValueError:
            pass

    async def edit_name(self, conn: PoolConn, name: str):
        """Edits the event's name in the database."""
        await conn.execute("UPDATE event SET name = $1 WHERE id = $2", name, self.id)
        self.name = name
        
    async def edit_description(self, conn: PoolConn, description: Optional[str]):
        """Edits the event's description in the database."""
        await conn.execute("UPDATE event SET description = $1 WHERE id = $2", description, self.id)
        self.description = description

    async def edit_joinable(self, conn: PoolConn, joinable: bool):
        """Edits the event's joinable in the database."""
        await conn.execute("UPDATE event SET joinable = $1 WHERE id = $2", joinable, self.id)
        self.joinable = joinable

    async def edit_slots(self, conn: PoolConn, slots: int):
        """Edits the event's slots in the database."""
        await conn.execute("UPDATE event SET slots = $1 WHERE id = $2", slots, self.id)
        self.slots = slots

    async def edit_active(self, conn: PoolConn, active: bool):
        """Edits the event's active status in the database."""
        await conn.execute("UPDATE event SET active = $1 WHERE id = $2", active, self.id)
        self.active = active

    async def edit_reminder(self, conn: PoolConn, reminder: int):
        """Edits the event's reminder status in the database."""
        await conn.execute("UPDATE event SET reminder = $1 WHERE id = $2", reminder, self.id)
        self.reminder = reminder

    async def edit_start(self, conn: PoolConn, start: dt.datetime):
        """Edits the event's start time in the database."""
        new_reminder = self._get_reminder(start)
        await conn.execute("UPDATE event SET start = $1 reminder = $3 WHERE id = $2", start, self.id, new_reminder)
        self.start = start

    async def save(self, conn: PoolConn):
        """Saves the current event to the database."""
        event = await self.insert(conn, self.user_id, self.server_id, self.start, self.name, self.description)
        self.id = event.id

    @classmethod
    def _get_reminder(cls, start: dt.datetime):
        now = dt.datetime.now(dt.timezone.utc)
        reminder = 0
        for i, notification in enumerate(NOTIFICATIONS, 1):
            if (start-now) > notification:
                return reminder
            reminder = i
        return reminder

    @classmethod
    async def get_by_id(cls, conn: PoolConn, event_id: int, only_active=False) -> Optional['Event']:
        """Gets a event by a specified id

        :param conn: Connection to the database.
        :param event_id: The event's id.
        :param only_active: Whether to only show current events or not.
        :return: The event if found.
        """
        row = await conn.fetchrow("SELECT * FROM event WHERE id = $1 AND status", event_id)
        if row is None:
            return None
        event = cls(**row)
        if only_active and (not event.active or event.start > dt.datetime.now(event.start.tzinfo)):
            return None
        rows = await conn.fetch('SELECT character_id FROM event_participant WHERE event_id = $1', event_id)
        for row in rows:
            event.participants.append(await DbChar.get_by_id(conn, row[0]))
        rows = await conn.fetch('SELECT user_id FROM event_subscriber WHERE event_id = $1', event_id)
        for row in rows:
            event.subscribers.append(row[0])
        return event

    @classmethod
    async def insert(cls, conn: PoolConn, user_id, server_id, start, name, description=None):
        reminder = cls._get_reminder(start)
        row = await conn.fetchrow("""INSERT INTO event(user_id, server_id, start, name, description, reminder)
                                     VALUES($1, $2, $3, $4, $5, $6) RETURNING *""",
                                  user_id, server_id, start, name, description, reminder)
        return cls(**row)

    @classmethod
    async def get_recent_by_server_id(cls, conn: PoolConn, server_id):
        rows = await conn.fetch("""SELECT * FROM event
                                   WHERE active AND server_id = $1 AND start < now() AND now()-start < $2
                                   ORDER BY start ASC""", server_id, RECENT_THRESHOLD)
        events = []
        for row in rows:
            events.append(cls(**row))
        return events

    @classmethod
    async def get_upcoming_by_server_id(cls, conn: PoolConn, server_id):
        rows = await conn.fetch("""SELECT * FROM event
                                   WHERE active AND server_id = $1 AND start > now()
                                   ORDER BY start ASC""", server_id)
        events = []
        for row in rows:
            events.append(cls(**row))
        return events


class Timer:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id")
        self.name = kwargs.get("name")
        self.type = kwargs.get("type")
        self.user_id = kwargs.get("user_id")
        if isinstance(self.type, int):
            self.type = ReminderType(self.type)
        self.extra = kwargs.get("extra")
        self.expires = kwargs.get("expires")
        self.created = kwargs.get("created")

    @classmethod
    def build(cls, **kwargs):
        kwargs["id"] = None
        return cls(**kwargs)

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
        # Timers
        self._timer_available = asyncio.Event(loop=bot.loop)
        self.timers_task = self.bot.loop.create_task(self.check_timers())
        self._next_timer = None
        # Events
        self._event_available = asyncio.Event(loop=bot.loop)
        self.events_announce_task = None  # This task is created after clean_events
        self._next_event = None

        self.bot.loop.create_task(self.clean_events())

    # region Tasks
    async def check_timers(self):
        """Checks the first upcoming time and waits for it."""
        tag = f"{self.tag}[check_timers]"
        try:
            await self.bot.wait_until_ready()
            log.debug(f"{tag} Started")
            while not self.bot.is_closed():
                timer = self._next_timer = await self.await_next_timer(days=40)
                log.debug(f"{tag} Next timer: {timer}")
                now = dt.datetime.now(tz=dt.timezone.utc)
                if timer.expires >= now:
                    wait_time = (timer.expires-now)
                    log.debug(f"{tag} Sleeping for {wait_time}")
                    await asyncio.sleep(wait_time.total_seconds())
                await self.run_timer(timer)
        except asyncio.CancelledError:
            pass
        except(OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())
        except Exception as e:
            log.exception(f"{tag} {e}")

    async def check_events(self):
        """Checks upcoming events and waits for notifications."""
        tag = f"{self.tag}[check_events]"
        try:
            await self.bot.wait_until_ready()
            log.debug(f"{tag} Started")
            while not self.bot.is_closed():
                event = self._next_event = await self.await_next_event(days=40)
                log.debug(f"{tag} Next event: {event}")
                now = dt.datetime.now(tz=dt.timezone.utc)
                if event.notification >= now:
                    wait_time = (event.notification-now)
                    log.debug(f"{tag} Sleeping for {wait_time}")
                    await asyncio.sleep(wait_time.total_seconds())
                await self.run_event(event)
        except asyncio.CancelledError:
            pass
        except(OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
            self.events_announce_task.cancel()
            self.events_announce_task = self.bot.loop.create_task(self.check_events())
        except Exception as e:
            log.exception(f"{tag} {e}")

    async def clean_events(self):
        """Checks upcoming events and waits for notifications."""
        tag = f"{self.tag}[clean_events]"
        try:
            await self.bot.wait_until_ready()
            log.debug(f"{tag} Started")
            async with self.bot.pool.acquire() as conn:
                res = await conn.execute("UPDATE event SET reminder = 1 "
                                         "WHERE (start-($1::interval))-($2::interval) < now() AND reminder < 1",
                                         FIRST_NOTIFICATION, TIME_MARGIN)
                log.debug(res)
                res = await conn.execute("UPDATE event SET reminder = 2 "
                                         "WHERE (start-($1::interval))-($2::interval) < now() AND reminder < 2",
                                         SECOND_NOTIFICATION, TIME_MARGIN)
                log.debug(res)
                res = await conn.execute("UPDATE event SET reminder = 3 "
                                         "WHERE (start-($1::interval))-($2::interval) < now() AND reminder < 3",
                                         THIRD_NOTIFICATION, TIME_MARGIN)
                log.debug(res)
                res = await conn.execute("UPDATE event SET reminder = 4 "
                                         "WHERE (start-($1::interval)) < now()  AND reminder < 4", TIME_MARGIN)
                log.debug(res)
            self.events_announce_task = self.bot.loop.create_task(self.check_events())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.exception(f"{tag} {e}")
    # endregion

    # task Custom Events
    async def on_event_notification(self, event: Event, reminder):
        """Announces upcoming events"""
        log.info(f"{self.tag} Sending event notification | Event '{event.name}' | ID: {event.id}")
        guild: Optional[discord.Guild] = self.bot.get_guild(event.server_id)
        if guild is None:
            return
        author = guild.get_member(event.user_id)
        author_name = author.display_name if author else "unknown"
        delta = HumanDelta(NOTIFICATIONS[reminder])
        message = f"Event: **{event.name}** (ID: {event.id} | by **@{author_name}**) - Is starting {delta.long(1)}"
        announce_channel_id = await get_server_property(self.bot.pool, guild.id, "events_channel", default=0)
        if announce_channel_id == 0:
            return
        announce_channel = self.bot.get_channel_or_top(guild, announce_channel_id)
        if announce_channel is not None:
            try:
                await announce_channel.send(message)
            except discord.HTTPException:
                log.debug(f"{self.tag} Could not send event event notification "
                          f"| Channel {announce_channel.id} | Server {announce_channel.guild.id}")
        await self.notify_subscribers(event, message)

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
        char = await DbChar.get_by_id(self.bot.pool, timer.extra["char_id"])
        if author is None or char is None:
            return
        embed = discord.Embed(title=timer.name, colour=discord.Colour.green(),
                              description=f"The cooldown for **{timer.name}** is over now for **{char.name}**.")
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

    # endregion

    # region Commands

    @commands.group(invoke_without_command=True, case_insensitive=True, usage="<boss>[,character]")
    async def boss(self, ctx: NabCtx, *, params: str = None):
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
            db_char = await DbChar.get_by_name(ctx.pool, char)
            if db_char is None or db_char.user_id != ctx.author.id:
                return await ctx.error(f"You don't have any registered character named `{char}`.")
            record = await ctx.pool.fetchrow("""SELECT * FROM timer WHERE type = $1 AND name = $2 AND user_id = $3
                                               AND extra->>'char_id' = $4""",
                                             ReminderType.BOSS.value, name, ctx.author.id, str(db_char.id))
            if not record:
                return await ctx.send(f"**{db_char.name}** doesn't have any active cooldowns for **{name}**.")
            timer = Timer(**record)
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
            entries.append(f"**{row['char_name']}** - Expires {HumanDelta(row['expires']-now).long(2)}")
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
        entries = [f"**{k}** - {HumanDelta(v, True).long(1)}" for k, v in BOSS_COOLDOWNS.items()]
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
        world_skipped = False
        for row in rows:
            if ctx.world and ctx.world != row["world"]:
                world_skipped = True
                continue
            entries.append(f"**{row['name']}** - **{row['char_name']}** "
                           f"- Expires {HumanDelta.from_date(row['expires']).long(2)}")
        if not entries:
            if world_skipped:
                return await ctx.send(f"You don't have any active cooldowns on characters in {ctx.world}.\n"
                                      f"Try on PM to see all your characters.")
            return await ctx.error(f"You don't have any active cooldowns.")
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

        The cooldown is set as if you had just killed the boss.
        You will receive a private message when the cooldown is over."""
        param = params.split(",", 1)
        if len(param) < 2:
            return await ctx.error("You must specify for which of your character is the cooldown for.\n"
                                   f"e.g. `{ctx.clean_prefix}{ctx.invoked_with} set Kroazur,Bubble`")
        name, char = param
        if name.lower() in BOSS_ALIASES:
            name = BOSS_ALIASES[name.lower()]
        if name in BOSS_COOLDOWNS:
            cooldown = BOSS_COOLDOWNS[name]
        else:
            return await ctx.error(f"There's no boss with that name.\nFor a list of supported bosses, "
                                   f"try: `{ctx.clean_prefix}{ctx.invoked_with} bosslist`")

        db_char = await DbChar.get_by_name(ctx.pool, char)
        if db_char is None:
            return await ctx.error("There's no character registered with that name.")
        if db_char.user_id != ctx.author.id:
            return await ctx.error("That character is not registered to you.")
        now = dt.datetime.now(tz=dt.timezone.utc)
        expires = now + cooldown
        # Check if this char already has a pending cooldown
        exists = await ctx.pool.fetchval("SELECT true FROM timer WHERE extra->>'char_id' = $1 AND name = $2",
                                         str(db_char.id), name)
        if exists:
            return await ctx.error(f"This character already has a running timer for this boss.\n"
                                   f"You can delete it using `{ctx.clean_prefix}{ctx.command.full_parent_name} clear "
                                   f"{name},{db_char.name}`")
        await self.create_timer(now, expires, name, ReminderType.BOSS, ctx.author.id, {"char_id": db_char.id})
        await ctx.success(f"Timer saved for `{name}`, I will let you know when the cooldown is over via pm.\n"
                          f"Use `{ctx.clean_prefix}checkdm` to make sure you can receive PMs by me.")

    @boss.command(name="remove", aliases=["unset", "clear"], usage="<boss>,<character>")
    async def boss_remove(self, ctx: NabCtx, *, params):
        """Removes an active boss cooldown."""
        param = params.split(",", 1)
        if len(param) < 2:
            return await ctx.error("You must specify for which of your character is the cooldown for.\n"
                                   f"e.g. `{ctx.clean_prefix}{ctx.invoked_with} remove Kroazur,Bubble`")
        name, char = param
        if name.lower() in BOSS_ALIASES:
            name = BOSS_ALIASES[name]
        if name not in BOSS_COOLDOWNS:
            return await ctx.error(f"There's no boss with that name.\nFor a list of supported bosses, "
                                   f"try: `{ctx.clean_prefix}{ctx.invoked_with} bosslist`")

        db_char = await DbChar.get_by_name(ctx.pool, char)
        if db_char is None:
            return await ctx.error("There's no character registered with that name.")
        if db_char.user_id != ctx.author.id:
            return await ctx.error("That character is not registered to you.")
        # Check if this char already has a pending cooldown
        timer_id = await ctx.pool.fetchval("SELECT id FROM timer WHERE extra->>'char_id' = $1 AND name = $2",
                                           str(db_char.id), name)
        if timer_id is None:
            return await ctx.error(f"There's no active timer for boss {name} for {db_char.name}")

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
            recent_events = await Event.get_recent_by_server_id(conn, ctx.guild.id)
            upcoming_events = await Event.get_upcoming_by_server_id(conn, ctx.guild.id)
        if len(recent_events) + len(upcoming_events) == 0:
            await ctx.send("There are no upcoming events.")
            return
        # Recent events
        if recent_events:
            value = ""
            for event in recent_events:
                user = ctx.guild.get_member(event.user_id)
                author = "unknown" if user is None else user.display_name
                starts_in = HumanDelta.from_date(event.start)
                value += f"\n**{event.name}** (*ID: {event.id}*) - by **@{author}** - Started {starts_in.long()} ago"
            embed.add_field(name="Recent events", value=value, inline=False)
        # Upcoming events
        if upcoming_events:
            value = ""
            for event in upcoming_events:
                user = ctx.guild.get_member(event.user_id)
                author = "unknown" if user is None else user.display_name
                start_time = HumanDelta.from_date(event.start)
                value += f"\n**{event.name}** (*ID:{event.id}*) -  by **@{author}** - {start_time.long()}"
            embed.add_field(name="Upcoming events", value=value, inline=False)
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
            await ctx.error(f"The event's name can't be longer than {EVENT_NAME_LIMIT} characters.")
            return

        event_description = ""
        if len(params) > 1:
            event_description = clean_string(ctx, params[1])

        event_count = await ctx.pool.fetchval("""SELECT count(*) FROM event
                                                     WHERE user_id = $1 AND start > now() AND active""", creator)

        if event_count >= MAX_EVENTS and not await checks.check_guild_permissions(ctx, {'manage_guild': True}):
            return await ctx.error(f"You can only have {MAX_EVENTS} active events simultaneously."
                                   f"Delete or edit an active event.")

        embed = discord.Embed(title=name, description=event_description, timestamp=start)
        embed.set_footer(text="Start time")

        message = await ctx.send("Is this correct?", embed=embed)
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            return await ctx.send("You took too long!")
        if not confirm:
            return await ctx.send("Alright, no event for you.")
        event = await Event.insert(ctx.pool, ctx.author.id, ctx.guild.id, start, name, event_description)
        log.debug(f"{self.tag} Event created: {event!r}")
        await ctx.success(f"Event created successfully."
                          f"\n\t**{name}** in *{starts_in.original}*.\n"
                          f"*To edit this event use ID {event.id}*")
        self.event_time_changed(event)

    @commands.guild_only()
    @events.command(name="addplayer", aliases=["addchar"])
    async def event_addplayer(self, ctx: NabCtx, event_id: int, *, character):
        """Adds a character to an event.

        Only the creator can add characters to an event.
        If the event is joinable, anyone can join an event using `event join`"""
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)

        char = await DbChar.get_by_name(ctx.pool, character)
        if char is None or ctx.guild.get_member(char.user_id) is None:
            return await ctx.error(f"Character not registered to anyone in this server..")
        if char.world != ctx.world:
            return await ctx.error("You can't add characters from another world.")
        owner = ctx.guild.get_member(char.user_id)
        if char.user_id in event.participant_users:
            return await ctx.error(f"A character of @{owner.display_name} is already participating.")

        if event.slots != 0 and len(event.participants) >= event.slots:
            return await ctx.error(f"All the slots for this event has been filled. "
                                   f"You can change them by using `/event edit slots {event.id} newSlots`.")

        message = await ctx.send(f"Do you want to add **{char.name}** (@{owner.display_name}) "
                                 f"to **{event.name}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            return await ctx.error("You took too long!")
        if not confirm:
            return await ctx.send("Nevermind then.")

        await event.add_participant(ctx.pool, char)
        await ctx.success(f"You successfully added **{char.name}** to this event.")

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
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)

        if new_description is None:
            msg = await ctx.send(f"What would you like to be the new description of **{event.name}**?"
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

        embed = discord.Embed(title=event.name, description=new_description, timestamp=event.start)
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

        await event.edit_description(ctx.pool, new_description)

        if event.user_id == ctx.author.id:
            await ctx.success("Your event's description was changed successfully.")
        else:
            await ctx.success(f"Event's description changed successfully.")
            creator = ctx.guild.get_member(event.user_id)
            if creator is not None:
                try:
                    await creator.send(f"Your event **{event.name}** had its description changed by "
                                       f"{ctx.author.mention}", embed=embed)
                except discord.HTTPException:
                    pass
        await self.notify_subscribers(event, f"The description of event **{event.name}** was changed.",
                                      embed=embed)

    @commands.guild_only()
    @event_edit.command(name="joinable", aliases=["open"], usage="<id> [yes/no]")
    async def event_edit_joinable(self, ctx: NabCtx, event_id: int, *, yes_no: str = None):
        """Changes whether anyone can join an event or only the owner may add people.

        If an event is joinable, anyone can join using `event join id`  .
        Otherwise, the event creator has to add people with `event addplayer id`.
        """
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)

        if yes_no is None:
            msg = await ctx.send(f"Do you want **{event.name}** to be joinable? `yes/no/cancel`")
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

        await event.edit_joinable(ctx.pool, joinable)

        if event.user_id == ctx.author.id:
            await ctx.success(f"Your event's was changed succesfully to **{joinable_string}**.")
        else:
            await ctx.success(f"Event is now **{joinable_string}**.")
            creator = ctx.guild.get_member(event.user_id)
            if creator is not None:
                try:
                    await creator.send(f"Your event **{event.name}** was changed to **{joinable_string}** "
                                       f"by {ctx.author.mention}.")
                except discord.HTTPException:
                    pass

    @commands.guild_only()
    @event_edit.command(name="name", aliases=["title"], usage="<id> [new name]")
    async def event_edit_name(self, ctx: NabCtx, event_id: int, *, new_name=None):
        """Edits an event's name.

        If no new name is provided initially, the bot will ask for one."""
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)

        if new_name is None:
            msg = await ctx.send(f"What would you like to be the new name of **{event.name}**?"
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
            await ctx.error(f"The name can't be longer than {EVENT_NAME_LIMIT} characters.")
            return
        message = await ctx.send(f"Do you want to change the name of **{event.name}** to **{new_name}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, name remains the same.")
            return

        await event.edit_name(ctx.pool, new_name)

        if event.user_id == ctx.author.id:
            await ctx.success(f"Your event was renamed successfully to **{new_name}**.")
        else:
            await ctx.success(f"Event renamed successfully to **{new_name}**.")
            creator = self.bot.get_member(event.user_id)
            if creator is not None:
                await creator.send(f"Your event **{event.name}** was renamed to **{new_name}** by "
                                   f"{ctx.author.mention}")
        await self.notify_subscribers(event, f"The event **{event.name}** was renamed to **{new_name}**.")

    @commands.guild_only()
    @event_edit.command(name="slots", aliases=["size"], usage="<id> [new slots]")
    async def event_edit_slots(self, ctx: NabCtx, event_id: int, slots: int = None):
        """Edits an event's number of slots

        Slots is the number of characters an event can have. By default this is 0, which means no limit."""
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)

        if slots is None:
            msg = await ctx.send(f"What would you like to be the new number of slots for  **{event.name}**? "
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
                await ctx.error(f"You can't have negative slots!")
                return
        except ValueError:
            await ctx.error("That's not a number...")
            return
        message = await ctx.send(f"Do you want the number of slots of **{event.name}** to **{slots}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, slots remain unchanged.")
            return

        await event.edit_slots(ctx.pool, slots)

        if event.user_id == ctx.author.id:
            await ctx.success(f"Your event slots were changed to **{slots}**.")
        else:
            await ctx.success(f"Event slots changed to **{slots}**.")
            creator = self.bot.get_member(event.user_id)
            if creator is not None:
                await creator.send(f"Your event **{event.name}** slots were changed to **{slots}** by "
                                   f"{ctx.author.mention}")

    @commands.guild_only()
    @checks.can_embed()
    @event_edit.command(name="time", aliases=["start"], usage="<id> [new start time]")
    async def event_edit_time(self, ctx: NabCtx, event_id: int, starts_in: TimeString = None):
        """Edit's an event's start time.

        If no new time is provided initially, the bot will ask for one."""
        now = dt.datetime.now(dt.timezone.utc)
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)

        if starts_in is None:
            msg = await ctx.send(f"When would you like the new start time of **{event.name}** be?"
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
        embed = discord.Embed(title=event.name, timestamp=new_time)
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

        await event.edit_start(ctx.pool, new_time)

        if event.user_id == ctx.author.id:
            await ctx.success(f"Your event's start time was changed successfully to **{starts_in.original}**.")
        else:
            await ctx.success("Event's time changed successfully.")
            creator = self.bot.get_member(event.user_id)
            if creator is not None:
                await creator.send(f"The start time of your event **{event.name}** was changed to "
                                   f"**{starts_in.original}** by {ctx.author.mention}.")
        await self.notify_subscribers(event, f"The start time of **{event.name}** was changed:", embed=embed)
        self.event_time_changed(event)

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="info", aliases=["show"])
    async def event_info(self, ctx: NabCtx, event_id: int):
        """Displays an event's info.

        The start time shown in the footer is always displayed in your device's timezone."""
        event = await Event.get_by_id(ctx.pool, event_id)
        if not event or event.server_id != ctx.guild.id:
            await ctx.error("There's no event with that id.")
            return
        author = ctx.guild.get_member(event.user_id)
        embed = discord.Embed(title=event.name, description=event.description, timestamp=event.start)
        if author:
            embed.set_author(name=author.display_name, icon_url=get_user_avatar(author))
        embed.set_footer(text="Start time")
        if event.participants and event.joinable:
            slots = ""
            if event.slots:
                slots = f"/{event.slots}"
            embed.add_field(name="Participants", value=f"{len(event.participants)}{slots}")
        await ctx.send(embed=embed)

    @commands.guild_only()
    @events.command(name="join")
    async def event_join(self, ctx: NabCtx, event_id: int, *, character: str):
        """Join an event with a specific character

        You can only join an event with a character at a time.
        Some events may not be joinable and require the creator to add characters themselves."""
        event = await Event.get_by_id(ctx.pool, event_id, True)
        if event is None or event.server_id != ctx.guild.id:
            return await ctx.error("There's no active event with that id.")
        char = await DbChar.get_by_name(ctx.pool, character)
        if char is None:
            return await ctx.error("That character is not registered.")
        if not event.joinable:
            await ctx.error(f"You can't join this event."
                            f"Maybe you meant to subscribe? Try `/event sub {event_id}`.")
            return
        if event.slots != 0 and len(event.participants) >= event.slots:
            return await ctx.error(f"All the slots for this event has been filled.")

        if char.user_id != ctx.author.id:
            return await ctx.error("You can only join with characters registered to you.")
        if ctx.world != char.world:
            return await ctx.error("You can't join with a character from another world.")
        if ctx.author.id in event.participant_users:
            return await ctx.error(f"A character of yours is already in this event.")

        message = await ctx.send(f"Do you want to join the event '**{event.name}**' as **{char.name}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            return await ctx.send("You took too long!")
        if not confirm:
            return await ctx.send("Nevermind then.")

        await event.add_participant(ctx.pool, char)
        await ctx.success(f"You successfully joined this event.")

    @commands.guild_only()
    @events.command(name="leave")
    async def event_leave(self, ctx: NabCtx, event_id: int):
        """Leave an event you were participating in."""
        event = await Event.get_by_id(ctx.pool, event_id, True)
        if event is None or event.server_id != ctx.guild.id:
            return await ctx.error("There's no active event with that id.")
        joined_char = next((participant for participant in event.participants
                            if ctx.author.id == participant.user_id), None)
        if joined_char is None:
            await ctx.error(f"You haven't joined this event.")
            return

        message = await ctx.send(f"Do you want to leave **{event.name}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        await event.remove_participant(ctx.pool, joined_char)
        await ctx.success("You successfully left this event.")

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="make", aliases=["creator", "maker"])
    async def event_make(self, ctx: NabCtx):
        """Creates an event guiding you step by step

        Instead of using confusing parameters, commas and spaces, this commands has the bot ask you step by step."""

        event_count = await ctx.pool.fetchval("""SELECT count(*) FROM event
                                                 WHERE user_id = $1 AND start > now() AND active""", ctx.author.id)
        if event_count >= MAX_EVENTS and not await checks.check_guild_permissions(ctx, {'manage_guild': True}):
            await ctx.error(f"You can only have {MAX_EVENTS} active events simultaneously."
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
        starts_in = None
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

        event = await Event.insert(ctx.pool, ctx.author.id, ctx.guild.id, start_time, name, description)
        await ctx.success(f"Event registered successfully.\n\t**{name}** in *{starts_in.original}*.\n"
                          f"*To edit this event use ID {event.id}*")
        self.event_time_changed(event)

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="participants")
    async def event_participants(self, ctx: NabCtx, event_id: int):
        """Shows the list of characters participating in this event."""
        event = await Event.get_by_id(ctx.pool, event_id)
        if event is None:
            return await ctx.error("There's no active event with that id.")
        if not event.participants:
            join_prompt = ""
            if event.joinable:
                join_prompt = f" To join, use `/event join {event_id} characterName`."
            return await ctx.error(f"There are no participants in this event.{join_prompt}")
        entries = []
        vocations = []
        for char in event.participants:
            level = abs(char.level)
            emoji = get_voc_emoji(char.vocation)
            vocations.append(char.vocation)
            vocation = get_voc_abb(char.vocation)
            owner = ctx.guild.get_member(char.user_id)
            user = "unknown" if owner is None else owner.display_name
            entries.append(f"**{char.name}** - {level} {vocation}{emoji} - **@{user}**")
        author = ctx.guild.get_member(event.user_id)
        author_name = None
        author_icon = None
        if author is not None:
            author_name = author.display_name
            author_icon = author.avatar_url if author.avatar_url else author.default_avatar_url
        pages = VocationPages(ctx, entries=entries, per_page=15, vocations=vocations)
        pages.embed.title = event.name
        pages.embed.set_author(name=author_name, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @events.command(name="remove", aliases=["delete", "cancel"])
    async def event_remove(self, ctx: NabCtx, event_id: int):
        """Deletes or cancels an event."""
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)

        message = await ctx.send(f"Do you want to delete the event **{event.name}**?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, event remains active.")
            return

        await event.edit_active(ctx.pool, False)
        if event.user_id == ctx.author.id:
            await ctx.success(f"Your event was deleted successfully.")
        else:
            await ctx.success(f"Event deleted successfully.")
            creator = ctx.guild.get_member(event.user_id)
            if creator is not None:
                try:
                    await creator.send(f"Your event **{event.name}** was deleted by {ctx.author.mention}.")
                except discord.HTTPException:
                    pass
        await self.notify_subscribers(event, f"The event **{event.name}** was deleted by {ctx.author.mention}.")

    @commands.guild_only()
    @events.command(name="removeplayer", aliases=["removechar"])
    async def event_removeplayer(self, ctx: NabCtx, event_id: int, *, character):
        """Removes a player from an event.

        Only the event's creator can remove players through this command.
        Players can remove themselves using `event leave`"""
        try:
            event = await self.get_editable_event(ctx, event_id)
        except errors.NabError as e:
            return await ctx.error(e)
        char = await DbChar.get_by_name(ctx.pool, character)
        if char is None:
            return await ctx.error("This character doesn't exist.")
        if char not in event.participants:
            return await ctx.error("This character is not in this event.")
        owner = ctx.guild.get_member(char.user_id)
        owner_name = "unknown" if owner is None else owner.display_name
        message = await ctx.send(f"Do you want to remove **{char.name}** (@**{owner_name}**) "
                                 f"from **{event.name}**?")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        await event.remove_participant(ctx.pool, char)
        await ctx.success("Character removed from event.")

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="subscribe", aliases=["sub"])
    async def event_subscribe(self, ctx, event_id: int):
        """Subscribe to receive a PM when an event is happening."""
        event = await Event.get_by_id(ctx.pool, event_id, True)
        if event is None:
            return await ctx.error(f"There's no active event with that id.")
        if ctx.author.id in event.subscribers or ctx.author.id == event.user_id:
            return await ctx.error(f"You're already subscribed to this event.")
        message = await ctx.send(f"Do you want to subscribe to **{event.name}**")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Ok then.")
            return

        await event.add_subscriber(ctx.pool, ctx.author)
        await ctx.success("You have subscribed successfully to this event. "
                          "I'll let you know when it's happening.")

    @commands.guild_only()
    @events.command(name="unsubscribe", aliases=["unsub"])
    async def event_unsubscribe(self, ctx, event_id: int):
        """Unsubscribe to an event."""
        event = await Event.get_by_id(ctx.pool, event_id, True)
        if event is None:
            return await ctx.error("There's no active event with that id.")
        if ctx.author.id == event.user_id:
            return await ctx.error("You can't unsubscribe from your own event.")
        if ctx.author.id not in event.subscribers:
            return await ctx.error("You are not subscribed to this event.")
        message = await ctx.send(f"Do you want to unsubscribe to **{event.name}**")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            return await ctx.send("You took too long!")
        if not confirm:
            return await ctx.send("Ok then.")

        await event.remove_subscriber(ctx.pool, ctx.author)
        await ctx.success(f"You have unsubscribed from this event.")

    @commands.command()
    async def remindme(self, ctx: NabCtx, when: TimeString, *, what: clean_content):
        """Creates a personal reminder.

        You will be notified in the same channel when the time is over."""
        now = dt.datetime.now(tz=dt.timezone.utc)
        expires = now+dt.timedelta(seconds=when.seconds)
        await self.create_timer(now, expires, what, ReminderType.CUSTOM, ctx.author.id, {"message": ctx.message.id,
                                                                                         "channel": ctx.channel.id})
        await ctx.success(f"Ok, I will remind you in {when.original} about: {what}")

    # endregion

    # Auxiliary functions

    async def await_next_timer(self, connection=None, days=7) -> Timer:
        """Finds the next upcoming timer

        If there's no upcoming timer in the specified days, it will keep waiting until there's one.
        It returns the timer when found."""
        timer = await self.get_next_timer(connection=connection, days=days)
        if timer is not None:
            self._timer_available.set()
            return timer

        self._timer_available.clear()
        self._next_timer = None
        await self._timer_available.wait()
        return await self.get_next_timer(connection=connection, days=days)

    async def await_next_event(self, connection=None, days=7) -> Event:
        """Finds the next upcoming event notification

        If there's no upcoming notification in the specified days, it will keep waiting until there's one.
        It returns the event when found."""
        event = await self.get_next_event_notification(connection=connection, days=days)
        if event is not None:
            self._event_available.set()
            return event

        self._event_available.clear()
        self._next_event = None
        await self._event_available.wait()
        return await self.get_next_event_notification(connection=connection, days=days)

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

        timer_id = await conn.fetchval(query, name, type.value, extra, expires, created, user_id)
        timer.id = timer_id
        log.debug(f"{self.tag} Timer created {timer}")
        if delta <= (86400 * 40):  # 40 days
            self._timer_available.set()

        if self._next_timer and expires < self._next_timer.expires:
            log.debug(f"{self.tag} Timer is newer than next timer, restarting task")
            self.timers_task.cancel()
            self.timers_task = self.bot.loop.create_task(self.check_timers())
        return timer

    def event_time_changed(self, event: Event):
        """When an event's time changes, it checks if the tasks should be restarted or not."""
        if (event.start-dt.datetime.now(event.start.tzinfo)) <= dt.timedelta(days=40):  # 40 days
            self._event_available.set()

        if self._next_event and event.start - FIRST_NOTIFICATION < self._next_event.notification:
            log.debug(f"{self.tag} New event's newer than current one, restarting task.")
            self.events_announce_task.cancel()
            self.events_announce_task = self.bot.loop.create_task(self.check_events())

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
        timer = Timer(**record)
        return timer

    async def get_next_event_notification(self, connection=None, days=7) -> Optional[Event]:
        """Gets the first upcoming event, if any."""
        query = """SELECT *, 
                       CASE
                           WHEN reminder = 0 THEN start-$1::interval
                           WHEN reminder = 1 THEN start-$2::interval
                           WHEN reminder = 2 THEN start-$3::interval
                           WHEN reminder = 3 THEN start
                       END as notification 
                   FROM "event"
                   WHERE start >= (now() + $4) AND active AND reminder <= 3
                   ORDER BY notification ASC LIMIT 1"""
        conn = connection or self.bot.pool
        row = await conn.fetchrow(query, FIRST_NOTIFICATION, SECOND_NOTIFICATION, THIRD_NOTIFICATION, TIME_MARGIN)
        if row is None:
            return None

        event = Event(**row)
        if event.notification-dt.datetime.now(dt.timezone.utc) < dt.timedelta(days=days):
            return event
        return None

    @classmethod
    async def get_editable_event(cls, ctx: NabCtx, event_id) -> Event:
        """Gets an events by its ID and checks if the event can be edited by the author."""
        event = await Event.get_by_id(ctx.pool, event_id, True)
        if event is None:
            raise errors.NabError("There's no active event with that id.")
        if event.user_id != ctx.author.id and not checks.is_owner(ctx):
            raise errors.NabError("You can only edit your own events.")
        if event.server_id != ctx.guild.id:
            raise errors.NabError("That event is not from this server.")
        return event

    async def notify_subscribers(self, event: Event, content, *, embed: discord.Embed = None, include_owner=False):
        """Sends a message to all users subscribed to an event"""
        subscribers = event.subscribers[:]
        if include_owner:
            subscribers.append(event.user_id)
        for subscriber in subscribers:
            member = self.bot.get_user(subscriber)
            if member is None:
                continue
            try:
                await member.send(content, embed=embed)
                log.debug(f"{self.tag} Event notification sent | Event: {event.id} | User: {member.id}")
            except discord.HTTPException:
                log.debug(f"{self.tag} Could not send event notification | Event: {event.id} | User: {member.id}")

    async def run_event(self, event: Event):
        """Runs an event notification.

        The announcing of the event is dispatched to make this as quick as possible and avoid delaying the task"""
        log.debug(f"{self.tag} Running event notification: {event}")
        reminder = event.reminder
        await event.edit_reminder(self.bot.pool, event.reminder + 1)
        self.bot.dispatch("event_notification", event, reminder)

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
        """For short timers, waits for the timer to be ready."""
        await asyncio.sleep(seconds)
        await self.run_timer(timer, True)

    # endregion

    def __unload(self):
        log.info(f"{self.tag} Unloading cog")
        self.timers_task.cancel()
        self.events_announce_task.cancel()


def setup(bot):
    bot.add_cog(Timers(bot))
