import asyncio
import datetime as dt
import platform
import random
import re
import time
from collections import Counter
from contextlib import closing
from typing import Union, Dict, Optional, List

import discord
import psutil
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.context import NabCtx
from utils.database import userDatabase, get_server_property
from utils.general import parse_uptime, TimeString, single_line, log, BadTime, get_user_avatar, get_region_string, \
    clean_string, is_numeric
from utils.pages import CannotPaginate, VocationPages, HelpPaginator
from utils.tibia import get_voc_abb, get_voc_emoji, tibia_worlds

EVENT_NAME_LIMIT = 50
EVENT_DESCRIPTION_LIMIT = 400
MAX_EVENTS = 3


class General:
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.events_announce_task = self.bot.loop.create_task(self.events_announce())
        self.game_update_task = self.bot.loop.create_task(self.game_update())

    async def __error(self, ctx: NabCtx, error):
        if isinstance(error, BadTime):
            await ctx.send(error)
            return
        if isinstance(error, commands.UserInputError):
            await ctx.send(f"{ctx.tick(False)} The correct syntax is: "
                           f"`{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.usage}`.\n"
                           f"Try `{ctx.clean_prefix}help {ctx.command.qualified_name}` for more info.")

    async def game_update(self):
        """Updates the bot's status.

        A random status is selected every 20 minutes.
        """
        game_list = ["Half-Life 3", "Tibia on Steam", "DOTA 3", "Human Simulator 2018", "Russian roulette",
                     "with my toy humans", "with fire🔥", "God", "innocent", "the part", "hard to get",
                     "with my human minions", "Singularity", "Portal 3", "Dank Souls", "you", "01101110", "dumb",
                     "with GLaDOS 💙", "with myself", "with your heart", "Generic MOBA", "Generic Battle Royale",
                     "League of Dota", "my cards right", "out your death in my head"]
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            if random.randint(0, 9) >= 7:
                await self.bot.change_presence(activity=discord.Game(name=f"in {len(self.bot.guilds)} servers"))
            else:
                await self.bot.change_presence(activity=discord.Game(name=random.choice(game_list)))
            await asyncio.sleep(60*20)  # Change game every 20 minutes

    async def events_announce(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            """Announces when an event is close to starting."""
            first_announce = 60 * 30
            second_announce = 60 * 15
            third_announce = 60 * 5
            c = userDatabase.cursor()
            try:
                # Current time
                date = time.time()
                c.execute("SELECT creator, start, name, id, server, status "
                          "FROM events "
                          "WHERE start >= ? AND active = 1 AND status != 0 "
                          "ORDER by start ASC", (date,))
                events = c.fetchall()
                if not events:
                    await asyncio.sleep(20)
                    continue
                for event in events:
                    await asyncio.sleep(0.1)
                    if date + first_announce + 60 > event["start"] > date + first_announce and event["status"] > 3:
                        new_status = 3
                    elif date + second_announce + 60 > event["start"] > date + second_announce and event["status"] > 2:
                        new_status = 2
                    elif date + third_announce + 60 > event["start"] > date + third_announce and event["status"] > 1:
                        new_status = 1
                    elif date + 60 > event["start"] > date and event["status"] > 0:
                        new_status = 0
                    else:
                        continue
                    guild = self.bot.get_guild(event["server"])
                    if guild is None:
                        continue
                    author = self.bot.get_member(event["creator"], guild)
                    if author is None:
                        continue
                    event["author"] = author.display_name
                    time_diff = dt.timedelta(seconds=event["start"] - date)
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
                    c.execute("UPDATE events SET status = ? WHERE id = ?", (new_status, event["id"],))
                    announce_channel_id = get_server_property(guild.id, "events_channel", is_int=True, default=0)
                    if announce_channel_id == 0:
                        continue
                    announce_channel = self.bot.get_channel_or_top(guild, announce_channel_id)
                    if announce_channel is not None:
                        await announce_channel.send(message)
                    await self.notify_subscribers(event["id"], message)
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Task: events_announce")
                continue
            finally:
                userDatabase.commit()
                c.close()
            await asyncio.sleep(20)

    # Commands
    @checks.can_embed()
    @commands.command()
    async def about(self, ctx: NabCtx):
        """Shows basic information about the bot."""
        embed = discord.Embed(description=ctx.bot.description, colour=discord.Colour.blurple())
        embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                         icon_url="https://github.com/fluidicon.png")
        prefixes = list(config.command_prefix)
        if ctx.guild:
            prefixes = get_server_property(ctx.guild.id, "prefixes", deserialize=True, default=prefixes)
        prefixes_str = "\n".join(f"- `{p}`" for p in prefixes)
        embed.add_field(name="Prefixes", value=prefixes_str, inline=False)
        embed.add_field(name="Authors", value="\u2023 [Galarzaa90](https://github.com/Galarzaa90)\n"
                                              "\u2023 [Nezune](https://github.com/Nezune)")
        embed.add_field(name="Created", value="March 30th 2016")
        embed.add_field(name="Version", value=f"v{self.bot.__version__}")
        embed.add_field(name="Platform", value="Python "
                                               "([discord.py](https://github.com/Rapptz/discord.py/tree/rewrite))")
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}")
        embed.add_field(name="Users", value=f"{len(self.bot.users):,}")
        embed.add_field(name="Links", inline=False,
                        value=f"[Add to your server](https://discordbots.org/bot/178966653982212096)  |  "
                              f"[Support Server](https://discord.me/nabbot)  |  "
                              f"[Docs](https://galarzaa90.github.io/NabBot)  |  "
                              f"[Donate](https://www.paypal.com/cgi-bin/webscr?"
                              f"cmd=_s-xclick&hosted_button_id=B33DCPZ9D3GMJ)")
        embed.set_footer(text=f"Uptime | {parse_uptime(self.bot.start_time, True)}")
        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command(name="botinfo")
    async def bot_info(self, ctx: NabCtx):
        """Shows advanced information about the bot."""
        char_count = 0
        deaths_count = 0
        levels_count = 0
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT COUNT(*) as count FROM chars")
            result = c.fetchone()
            if result is not None:
                char_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_deaths")
            result = c.fetchone()
            if result is not None:
                deaths_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_levelups")
            result = c.fetchone()
            if result is not None:
                levels_count = result["count"]

        used_ram = psutil.Process().memory_full_info().uss / 1024 ** 2
        total_ram = psutil.virtual_memory().total / 1024 ** 2
        percentage_ram = psutil.Process().memory_percent()

        def ram(value):
            if value >= 1024:
                return f"{value/1024:.2f}GB"
            else:
                return f"{value:.2f}MB"
        
        # Calculate ping
        t1 = time.perf_counter()
        await ctx.trigger_typing()
        t2 = time.perf_counter()
        ping = round((t2 - t1) * 1000)

        embed = discord.Embed()
        embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                         icon_url="https://github.com/fluidicon.png")
        embed.description = f"🔰 Version: **{self.bot.__version__}**\n" \
                            f"⏱ ️Uptime **{parse_uptime(self.bot.start_time)}**\n" \
                            f"🖥️ OS: **{platform.system()} {platform.release()}**\n" \
                            f"📉 RAM: **{ram(used_ram)}/{ram(total_ram)} ({percentage_ram:.2f}%)**\n"
        try:
            embed.description += f"⚙️ CPU: **{psutil.cpu_count()} @ {psutil.cpu_freq().max} MHz**\n"
        except AttributeError:
            pass
        embed.description += f"🏓 Ping: **{ping} ms**\n" \
                             f"👾 Servers: **{len(self.bot.guilds):,}**\n" \
                             f"💬 Channels: **{len(list(self.bot.get_all_channels())):,}**\n"\
                             f"👨 Users: **{len(self.bot.users):,}** \n" \
                             f"👤 Characters: **{char_count:,}**\n" \
                             f"🌐 Tracked worlds: **{len(self.bot.tracked_worlds_list)}/{len(tibia_worlds)}**\n" \
                             f"{config.levelup_emoji} Level ups: **{levels_count:,}**\n" \
                             f"{config.death_emoji} Deaths: **{deaths_count:,}**"
        await ctx.send(embed=embed)

    @commands.command(usage="<choices...>")
    async def choose(self, ctx, *choices: str):
        """Chooses between multiple choices.

        Each choice is separated by spaces. For choices that contain spaces surround it with quotes.
        e.g. "Choice A" ChoiceB "Choice C"
        """
        if not choices:
            await ctx.send(f"{ctx.tick(False)} I can't tell you what to choose if you don't give me choices")
            return
        user = ctx.author
        await ctx.send('Alright, **@{0}**, I choose: "{1}"'.format(user.display_name, random.choice(choices)))

    @checks.can_embed()
    @commands.command(name='help', aliases=["commands"])
    async def _help(self, ctx, *, command: str = None):
        """Shows help about a command or the bot.

        - If no command is specified, it will list all available commands
        - If a command is specified, it will show further info, and its subcommands if applicable.
        - If a category is specified, it will show only commands in that category.

        Various symbols are used to represent a command's signature and/or show further info.
        **<argument>**
        This means the argument is __**required**__.

        **[argument]**
        This means the argument is __**optional**__.

        **[A|B]**
        This means the it can be __**either A or B**__.

        **[argument...]**
        This means you can have __**multiple arguments**__.

        🔸
        This means the command has subcommands.
        Check the command's help to see them."""
        try:
            if command is None:
                p = await HelpPaginator.from_bot(ctx)
            else:
                entity = self.bot.get_cog(command) or self.bot.get_command(command)

                if entity is None:
                    clean = command.replace('@', '@\u200b')
                    return await ctx.send(f'Command or category "{clean}" not found.')
                elif isinstance(entity, commands.Command):
                    p = await HelpPaginator.from_command(ctx, entity)
                else:
                    p = await HelpPaginator.from_cog(ctx, entity)
            await p.paginate()
        except Exception as e:
            await ctx.send(e)

    @commands.command(name="oldhelp", hidden=True)
    async def oldhelp(self, ctx, *commands: str):
        """Shows this message."""
        _mentions_transforms = {
            '@everyone': '@\u200beveryone',
            '@here': '@\u200bhere'
        }
        _mention_pattern = re.compile('|'.join(_mentions_transforms.keys()))

        bot = ctx.bot
        destination = ctx.channel if ctx.long else ctx.author

        def repl(obj):
            return _mentions_transforms.get(obj.group(0), '')

        # help by itself just lists our own commands.
        if len(commands) == 0:
            pages = await bot.formatter.format_help_for(ctx, bot)
        elif len(commands) == 1:
            # try to see if it is a cog name
            name = _mention_pattern.sub(repl, commands[0])
            command = None
            if name in bot.cogs:
                command = bot.cogs[name]
            else:
                command = bot.all_commands.get(name)
                destination = ctx.channel
                if command is None:
                    await destination.send(bot.command_not_found.format(name))
                    return

            pages = await bot.formatter.format_help_for(ctx, command)
        else:
            name = _mention_pattern.sub(repl, commands[0])
            command = bot.all_commands.get(name)
            destination = ctx.channel
            if command is None:
                await destination.send(bot.command_not_found.format(name))
                return

            for key in commands[1:]:
                try:
                    key = _mention_pattern.sub(repl, key)
                    command = command.all_commands.get(key)
                    if command is None:
                        await destination.send(bot.command_not_found.format(key))
                        return
                except AttributeError:
                    await destination.send(bot.command_has_no_subcommands.format(command, key))
                    return

            pages = await bot.formatter.format_help_for(ctx, command)

        for page in pages:
            await destination.send(page)

    @commands.guild_only()
    @checks.can_embed()
    @commands.group(aliases=["event"], invoke_without_command=True, case_insensitive=True, usage="[event id]")
    async def events(self, ctx: NabCtx, event_id: int=None):
        """Shows a list of upcoming and recent events.

        If a number is specified, it will show details for that event. Same as using `events info`"""
        if event_id is not None:
            await ctx.invoke(self.bot.all_commands.get('events').get_command("info"), event_id)
            return
        # Time in seconds the bot will show past events
        time_threshold = 60 * 30
        now = time.time()
        embed = discord.Embed(description="For more info about an event, use `/event info (id)`"
                                          "\nTo receive notifications for an event, use `/event sub (id)`")
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT creator, start, name, id, server FROM events "
                      "WHERE start < ? AND start > ? AND active = 1 AND server == ? "
                      "ORDER by start ASC", (now, now - time_threshold, ctx.guild.id))
            recent_events = c.fetchall()
            c.execute("SELECT creator, start, name, id, server FROM events "
                      "WHERE start > ? AND active = 1 AND server == ?"
                      "ORDER BY start ASC", (now, ctx.guild.id))
            upcoming_events = c.fetchall()
        if len(recent_events) + len(upcoming_events) == 0:
            await ctx.send("There are no upcoming events.")
            return
        # Recent events
        if recent_events:
            name = "Recent events"
            value = ""
            for event in recent_events:
                author = ctx.guild.get_member(event["creator"])
                event["author"] = "unknown" if author is None else author.display_name
                time_diff = dt.timedelta(seconds=now - event["start"])
                minutes = round((time_diff.seconds / 60) % 60)
                event["start_str"] = "Started {0} minutes ago".format(minutes)
                value += "\n**{name}** (*ID: {id}*) - by **@{author}** - {start_str}".format(**event)
            embed.add_field(name=name, value=value, inline=False)
        # Upcoming events
        if upcoming_events:
            name = "Upcoming events"
            value = ""
            for event in upcoming_events:
                author = ctx.guild.get_member(event["creator"])
                event["author"] = "unknown" if author is None else author.display_name
                time_diff = dt.timedelta(seconds=event["start"] - now)
                days, hours, minutes = time_diff.days, time_diff.seconds // 3600, (time_diff.seconds // 60) % 60
                if days:
                    event["start_str"] = 'In {0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                elif hours:
                    event["start_str"] = 'In {0} hours and {1} minutes'.format(hours, minutes)
                elif minutes > 0:
                    event["start_str"] = 'In {0} minutes'.format(minutes)
                else:
                    event["start_str"] = 'Starting now!'
                value += "\n**{name}** (*ID:{id}*) -  by **@{author}** - {start_str}".format(**event)
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="add", usage="<starts in> <name>[,description]")
    async def event_add(self, ctx, starts_in: TimeString, *, params):
        """Creates a new event.

        `starts in` is in how much time the event will start from the moment of creation.
        This is done to avoid dealing with different timezones.
        Just say in how many days/hours/minutes the event is starting.

        The time can be set using units such as 'd' for days, 'h' for hours, 'm' for minutes and 'd' for seconds.
        Examples: 1d20h5m, 1d30m, 1h40m, 40m

        The event description is optional, you can also use links like: `[link title](link url)`.

        Once the event is created, the id of the event will be returned. This is used for further edits.
        """
        now = time.time()
        creator = ctx.author.id
        start = now + starts_in.seconds
        params = params.split(",", 1)
        name = single_line(clean_string(ctx, params[0]))
        if len(name) > EVENT_NAME_LIMIT:
            await ctx.send(f"{ctx.tick(False)} The event's name can't be longer than {EVENT_NAME_LIMIT} characters.")
            return

        event_description = ""
        if len(params) > 1:
            event_description = clean_string(ctx, params[1])

        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
            result = c.fetchall()

        if len(result) >= MAX_EVENTS and creator not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only have {MAX_EVENTS} active events simultaneously."
                           f"Delete or edit an active event.")
            return

        embed = discord.Embed(title=name, description=event_description, timestamp=dt.datetime.utcfromtimestamp(start))
        embed.set_footer(text="Start time")

        message = await ctx.send("Is this correct?", embed=embed)
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, no event for you.")
            return
        with closing(userDatabase.cursor()) as c:
            c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                      (creator, ctx.guild.id, start, name, event_description))
            event_id = c.lastrowid
            userDatabase.commit()

        await ctx.send(f"{ctx.tick()} Event created successfully.\n\t**{name}** in *{starts_in.original}*.\n"
                       f"*To edit this event use ID {event_id}*")

    @commands.guild_only()
    @events.command(name="addplayer", aliases=["addchar"])
    async def event_addplayer(self, ctx, event_id: int, *, character):
        """Adds a character to an event.

        Only the creator can add characters to an event.
        If the event is joinable, anyone can join an event using `event join`"""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only add people to your own events.")
            return
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT * FROM chars WHERE name LIKE ? AND user_id != 0", (character,))
            char = c.fetchone()
        if event["slots"] != 0 and len(event["participants"]) >= event["slots"]:
            await ctx.send(f"{ctx.tick(False)} All the slots for this event has been filled. "
                           f"You can change them by using `/event edit slots {event_id} newSlots`.")
            return

        if char is None:
            await ctx.send(f"{ctx.tick(False)} That character is not registered.")
            return
        owner = self.bot.get_member(char["user_id"], ctx.guild)
        if owner is None:
            await ctx.send(f"{ctx.tick(False)} That character is not registered.")
            return
        world = self.bot.tracked_worlds.get(event["server"])
        if world != char["world"]:
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

        with userDatabase as con:
            con.execute("INSERT INTO event_participants(event_id, char_id) VALUES(?,?)", (event_id, char["id"]))
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
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
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

        embed = discord.Embed(title=event["name"], description=new_description,
                              timestamp=dt.datetime.utcfromtimestamp(event["start"]))
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

        with userDatabase as conn:
            conn.execute("UPDATE events SET description = ? WHERE id = ?", (new_description, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event's description was changed successfully.")
        else:
            await ctx.send(f"{ctx.tick()} Event's description changed successfully.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** had its description changed by {ctx.author.mention}",
                                   embed=embed)
        await self.notify_subscribers(event_id, f"The description of event **{event['name']}** was changed.",
                                      embed=embed, skip_creator=True)

    @commands.guild_only()
    @event_edit.command(name="joinable", aliases=["open"], usage="<id> [yes/no]")
    async def event_edit_joinable(self, ctx: NabCtx, event_id: int, *, yes_no: str=None):
        """Changes whether anyone can join an event or only the owner may add people.

        If an event is joinable, anyone can join using `event join id`  .
        Otherwise, the event creator has to add people with `event addplayer id`.
        """
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
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

        with userDatabase as conn:
            conn.execute("UPDATE events SET joinable = ? WHERE id = ?", (joinable, event_id))

        if event["creator"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()}Your event's was changed succesfully to **{joinable_string}**.")
        else:
            await ctx.send(f"{ctx.tick} Event is now **{joinable_string}**.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was changed to **{joinable_string}** "
                                   f"by {ctx.author.mention}.")

    @commands.guild_only()
    @event_edit.command(name="name", aliases=["title"], usage="<id> [new name]")
    async def event_edit_name(self, ctx: NabCtx, event_id: int, *, new_name=None):
        """Edits an event's name.

        If no new name is provided initially, the bot will ask for one."""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
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

        with userDatabase as conn:
            conn.execute("UPDATE events SET name = ? WHERE id = ?", (new_name, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event was renamed successfully to **{new_name}**.")
        else:
            await ctx.send(f"{ctx.tick()} Event renamed successfully to **{new_name}**.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was renamed to **{new_name}** by "
                                   f"{ctx.author.mention}")
        await self.notify_subscribers(event_id, f"The event **{event['name']}** was renamed to **{new_name}**.",
                                      skip_creator=True)

    @commands.guild_only()
    @event_edit.command(name="slots", aliases=["size"], usage="<id> [new slots]")
    async def event_edit_slots(self, ctx: NabCtx, event_id: int, slots: int=None):
        """Edits an event's number of slots

        Slots is the number of characters an event can have. By default this is 0, which means no limit."""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
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

        with userDatabase as conn:
            conn.execute("UPDATE events SET slots = ? WHERE id = ?", (slots, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event slots were changed to **{slots}**.")
        else:
            await ctx.send(f"{ctx.tick()} Event slots changed to **{slots}**.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** slots were changed to **{slots}** by "
                                   f"{ctx.author.mention}")

    @commands.guild_only()
    @checks.can_embed()
    @event_edit.command(name="time", aliases=["start"], usage="<id> [new start time]")
    async def event_edit_time(self, ctx: NabCtx, event_id: int, starts_in: TimeString=None):
        """Edit's an event's start time.

        If no new time is provided initially, the bot will ask for one."""
        now = time.time()
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
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
        embed = discord.Embed(title=event["name"], timestamp=dt.datetime.utcfromtimestamp(now+starts_in.seconds))
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

        with userDatabase as conn:
            conn.execute("UPDATE events SET start = ? WHERE id = ?", (now + starts_in.seconds, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()}Your event's start time was changed successfully to **{starts_in.original}**.")
        else:
            await ctx.send(f"{ctx.tick()}Event's time changed successfully.")
            creator = self.bot.get_member(event["creator"])
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
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        event = self.get_event(ctx, event_id)
        if not event:
            await ctx.send(f"{ctx.tick(False)} There's no event with that id.")
            return
        guild = self.bot.get_guild(event["server"])
        start = dt.datetime.utcfromtimestamp(event["start"])
        author = self.bot.get_member(event["creator"], guild)
        embed = discord.Embed(title=event["name"], description=event["description"], timestamp=start)
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
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT * FROM chars WHERE name LIKE ?", (character,))
            char = c.fetchone()
            c.execute("SELECT char_id, user_id FROM event_participants, chars WHERE event_id = ? AND chars.id = char_id"
                      , (event_id,))
            participants = c.fetchall()
            if participants is None:
                participants = []
        if event["joinable"] != 1:
            await ctx.send(f"{ctx.tick(False)} You can't join this event."
                           f"Maybe you meant to subscribe? Try `/event sub {event_id}`.")
            return
        if event["slots"] != 0 and len(participants) >= event["slots"]:
            await ctx.send(f"{ctx.tick(False)} All the slots for this event has been filled.")
            return
        if char is None:
            await ctx.send(f"{ctx.tick(False)} That character is not registered.")
            return
        if char["user_id"] != ctx.author.id:
            await ctx.send(f"{ctx.tick(False)} You can only join with characters registered to you.")
            return
        world = self.bot.tracked_worlds.get(event["server"])
        if world != char["world"]:
            await ctx.send(f"{ctx.tick(False)} You can't join with a character from another world.")
            return
        if any(ctx.author.id == participant["user_id"] for participant in participants):
            await ctx.send(f"{ctx.tick(False)} A character of yours is already in this event.")
            return

        message = await ctx.send(f"Do you want to join the event \'**{event['name']}**\' as **{char['name']}**?")
        confirm = await ctx.react_confirm(message, delete_after=True)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        with userDatabase as con:
            con.execute("INSERT INTO event_participants(event_id, char_id) VALUES(?,?)", (event_id, char["id"]))
            await ctx.send(f"{ctx.tick()} You successfully joined this event.")
            return

    @commands.guild_only()
    @events.command(name="leave")
    async def event_leave(self, ctx, event_id: int):
        """Leave an event you were participating in."""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        joined_char = next((participant["char_id"] for participant in event["participants"]
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

        with userDatabase as con:
            con.execute("DELETE FROM event_participants WHERE event_id = ? AND char_id = ?", (event_id, joined_char))
            await ctx.send(f"{ctx.tick()} You successfully left this event.")
            return

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="make", aliases=["creator", "maker"])
    async def event_make(self, ctx: NabCtx):
        """Creates an event guiding you step by step

        Instead of using confusing parameters, commas and spaces, this commands has the bot ask you step by step."""
        now = time.time()

        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (ctx.author.id, now))
            event = c.fetchall()
        if len(event) >= MAX_EVENTS and ctx.author.id not in config.owner_ids:
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
        now = time.time()
        start_time = now
        while True:
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
                start_time = now+starts_in.seconds
            except commands.BadArgument as e:
                await msg.delete()
                msg = await ctx.send(f'{e}\nAgain, tell me the start time of the event from now.\n'
                                     f'You can `cancel` if you want.')
                continue
            await msg.delete()
            msg = await ctx.send("Is this correct in your local timezone?",
                                 embed=discord.Embed(timestamp=dt.datetime.utcfromtimestamp(start_time)))
            confirm = await ctx.react_confirm(msg, timeout=60, )
            if confirm is None:
                await ctx.send(f"Where did you go {ctx.author.mention}? Ok, event making cancelled.")
                cancel = True
                break
            if confirm is False:
                await msg.delete()
                msg = await ctx.send(f"Ok, again, tell me when will the event start.\nRemember you "
                                     f"can `cancel` the process.")
            else:
                break

        await msg.delete()
        if cancel:
            return

        embed.timestamp = dt.datetime.utcfromtimestamp(start_time)
        msg = await ctx.send("This will be your event, confirm that everything is correct and we will be done.",
                             embed=embed)
        confirm = await ctx.react_confirm(msg, timeout=120, delete_after=True)
        if not confirm:
            await ctx.send("Alright, guess all this was for nothing. Goodbye!")
            return

        with closing(userDatabase.cursor()) as c:
            c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                      (ctx.author.id, ctx.guild.id, start_time, name, description))
            event_id = c.lastrowid
            userDatabase.commit()
        await ctx.send(f"{ctx.tick()} Event registered successfully.\n\t**{name}** in *{starts_in.original}*.\n"
                       f"*To edit this event use ID {event_id}*")

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="participants")
    async def event_participants(self, ctx, event_id: int):
        """Shows the list of characters participating in this event."""
        event = self.get_event(ctx, event_id)
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
        event_server: discord.Guild = self.bot.get_guild(event["server"])
        for char in event["participants"]:
            char["level"] = abs(char["level"])
            char["emoji"] = get_voc_emoji(char["vocation"])
            vocations.append(char["vocation"])
            char["vocation"] = get_voc_abb(char["vocation"])
            owner = self.bot.get_member(char["user_id"], self.bot.get_guild(event_server))
            char["owner"] = "unknown" if owner is None else owner.display_name
            entries.append("**{name}** - {level} {vocation}{emoji} - **@{owner}**".format(**char))
        author = self.bot.get_member(event["creator"], event_server)
        author_name = None
        author_icon = None
        if author is not None:
            if event_server is None:
                author_name = author.name
            else:
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
    async def event_remove(self, ctx, event_id: int):
        """Deletes or cancels an event."""
        c = userDatabase.cursor()
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
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

        with userDatabase as conn:
            conn.execute("UPDATE events SET active = 0 WHERE id = ?", (event_id,))
        if event["creator"] == ctx.author.id:
            await ctx.send(f"{ctx.tick()} Your event was deleted successfully.")
        else:
            await ctx.send(f"{ctx.tick()} Event deleted successfully.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was deleted by {ctx.author.mention}.")
        await self.notify_subscribers(event_id, f"The event **{event['name']}** was deleted by {ctx.author.mention}.",
                                      skip_creator=True)

    @commands.guild_only()
    @events.command(name="removeplayer", aliases=["removechar"])
    async def event_removeplayer(self, ctx, event_id: int, *, character):
        """Removes a player from an event.

        Players can remove themselves using `event leave`"""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send(f"{ctx.tick(False)} You can only add people to your own events.")
            return
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT * FROM chars WHERE name LIKE ?", (character,))
            char = c.fetchone()
        joined_char = next((participant["char_id"] for participant in event["participants"]
                            if char["id"] == participant["char_id"]), None)
        if joined_char is None:
            await ctx.send(f"{ctx.tick(False)} This character is not in this event.")
            return
        event_server = self.bot.get_guild(event["server"])
        owner = self.bot.get_member(char["user_id"], self.bot.get_guild(event_server))
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

        with userDatabase as con:
            con.execute("DELETE FROM event_participants WHERE event_id = ? AND char_id = ?", (event_id, joined_char))
            await ctx.send(f"{ctx.tick()} You successfully left this event.")
            return

    @commands.guild_only()
    @checks.can_embed()
    @events.command(name="subscribe", aliases=["sub"])
    async def event_subscribe(self, ctx, event_id: int):
        """Subscribe to receive a PM when an event is happening."""
        c = userDatabase.cursor()
        author = ctx.author
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        try:
            message = await ctx.send(f"Do you want to subscribe to **{event['name']}**")
            confirm = await ctx.react_confirm(message)
            if confirm is None:
                await ctx.send("You took too long!")
                return
            if not confirm:
                await ctx.send("Ok then.")
                return

            c.execute("INSERT INTO event_subscribers (event_id, user_id) VALUES(?,?)", (event_id, author.id))
            await ctx.send(f"{ctx.tick()} You have subscribed successfully to this event. "
                           f"I'll let you know when it's happening.")

        finally:
            c.close()
            userDatabase.commit()

    @commands.guild_only()
    @events.command(name="unsubscribe", aliases=["unsub"])
    async def event_unsubscribe(self, ctx, event_id: int):
        """Unsubscribe to an event."""
        c = userDatabase.cursor()
        author = ctx.author
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send(f"{ctx.tick(False)} There's no active event with that id.")
            return
        try:
            c.execute("SELECT * FROM event_subscribers WHERE event_id = ? AND user_id = ?", (event_id, author.id))
            subscription = c.fetchone()
            if subscription is None:
                await ctx.send(f"{ctx.tick(False)} You are not subscribed to this event.")
                return

            message = await ctx.send(f"Do you want to unsubscribe to **{event['name']}**")
            confirm = await ctx.react_confirm(message)
            if confirm is None:
                await ctx.send("You took too long!")
                return
            if not confirm:
                await ctx.send("Ok then.")
                return

            c.execute("DELETE FROM event_subscribers WHERE event_id = ? AND user_id = ?", (event_id, author.id))
            await ctx.send(f"{ctx.tick()} You have subscribed successfully to this event. "
                           f"I'll let you know when it's happening.")

        finally:
            c.close()
            userDatabase.commit()

    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @checks.can_embed()
    @commands.command(nam="permissions", aliases=["perms"])
    async def permissions(self, ctx: NabCtx, member: discord.Member=None, channel: discord.TextChannel=None):
        """Shows a member's permissions in the current channel.

        If no member is provided, it will show your permissions.
        Optionally, a channel can be provided as the second parameter, to check permissions in said channel."""
        member = member or ctx.author
        channel = channel or ctx.channel
        guild_permissions = channel.permissions_for(member)
        embed = discord.Embed(title=f"Permissions in #{channel.name}", colour=member.colour)
        embed.set_author(name=member.display_name, icon_url=get_user_avatar(member))
        allowed = []
        denied = []
        for name, value in guild_permissions:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)
        if allowed:
            embed.add_field(name=f"{ctx.tick()}Allowed", value="\n".join(allowed))
        if denied:
            embed.add_field(name=f"{ctx.tick(False)}Denied", value="\n".join(denied))
        await ctx.send(embed=embed)

    @commands.guild_only()
    @checks.can_embed()
    @commands.command()
    async def quote(self, ctx: NabCtx, message_id: int):
        """Shows a messages by its ID.

        In order to get a message's id, you need to enable Developer Mode.
        Developer mode is found in `User Settings > Appearance`.
        Once enabled, you can right click a message and select **Copy ID**.

        Note that the bot won't attempt to search in channels you can't read."""
        channels: List[discord.TextChannel] = ctx.guild.text_channels
        message: discord.Message = None
        with ctx.typing():
            for channel in channels:
                bot_perm = ctx.bot_permissions
                auth_perm = ctx.author_permissions
                if not(bot_perm.read_message_history and bot_perm.read_messages and
                       auth_perm.read_message_history and auth_perm.read_messages):
                    continue
                try:
                    message = await channel.get_message(message_id)
                except discord.HTTPException:
                    continue
                if message is not None:
                    break
        if message is None:
            await ctx.send("I can't find that message, or it is in a channel you can't access.")
            return
        if not message.content:
            await ctx.send("I can't quote embed messages.")
            return
        embed = discord.Embed(description=message.content, timestamp=message.created_at)
        try:
            embed.colour = message.author.colour
        except AttributeError:
            pass
        embed.set_author(name=message.author.display_name, icon_url=get_user_avatar(message.author),
                         url=message.jump_url)
        embed.set_footer(text=f"In #{message.channel.name}")
        if len(message.attachments) >= 1:
            attachment: discord.Attachment = message.attachments[0]
            if attachment.height is not None:
                embed.set_image(url=message.attachments[0].url)
            else:
                embed.add_field(name="Attached file",
                                value=f"[{attachment.filename}]({attachment.url}) ({attachment.size:,} bytes)")
        await ctx.send(embed=embed)

    @commands.command(aliases=["dice"], usage="[times][d[sides]]")
    async def roll(self, ctx: NabCtx, params=None):
        """Rolls a die.

        By default, it rolls a 6-sided die once.
        You can specify how many times you want the die to be rolled.

        You can also specify the number of sides of the die, using the format `TdS` where T is times and S is sides."""
        sides = 6
        if params is None:
            times = 1
        elif is_numeric(params):
            times = int(params)
        else:
            try:
                times, sides = map(int, params.split('d'))
            except ValueError:
                await ctx.send(f"{ctx.tick(False)} Invalid parameter! I'm expecting `<times>d<rolls>`.")
                return
        if times == 0:
            await ctx.send("You want me to roll the die zero times? Ok... There, done.")
            return
        if times < 0:
            await ctx.send(f"{ctx.tick(False)} It's impossible to roll negative times!")
            return
        if sides <= 0:
            await ctx.send(f"{ctx.tick(False)} There's no dice with zero or less sides!")
            return
        if times > 20:
            await ctx.send(f"{ctx.tick(False)} I can't roll the die that many times. Only up to 20.")
            return
        if sides > 100:
            await ctx.send(f"{ctx.tick(False)} I don't have dice with more than 100 sides.")
            return
        time_plural = "times" if times > 1 else "time"
        results = [str(random.randint(1, sides)) for r in range(times)]
        result = f"You rolled a **{sides}**-sided die **{times}** {time_plural} and got:\n\t{', '.join(results)}"
        if sides == 1:
            result += "\nWho would have thought? 🙄"
        await ctx.send(result)

    @commands.guild_only()
    @commands.command()
    @checks.can_embed()
    async def serverinfo(self, ctx: NabCtx, server=None):
        """Shows the server's information.

        The bot owner can additionally check the information of a specific server where the bot is.
        """
        if await checks.is_owner_check(ctx) and server is not None:
            try:
                guild = self.bot.get_guild(int(server))
                if guild is None:
                    return await ctx.send(f"{ctx.tick(False)} I'm not in any server with ID {server}.")
            except ValueError:
                return await ctx.send(f"{ctx.tick(False)} That is not a valid id.")
        else:
            guild = ctx.guild
        embed = discord.Embed(title=guild.name, timestamp=guild.created_at, color=discord.Color.blurple())
        embed.set_footer(text="Created on")
        embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="ID", value=str(guild.id), inline=False)
        if ctx.guild != guild:
            embed.add_field(name="Owner", value=str(guild.owner))
        else:
            embed.add_field(name="Owner", value=guild.owner.mention)
        embed.add_field(name="Voice Region", value=get_region_string(guild.region))
        embed.add_field(name=f"Channels ({len(guild.text_channels)+len(guild.voice_channels):,})",
                        value=f"📄 Text: **{len(guild.text_channels):,}**\n"
                              f"🎙 Voice: **{len(guild.voice_channels):,}**\n"
                              f"🗂 Categories: **{len(guild.categories):,}**")
        status_count = Counter(str(m.status) for m in guild.members)
        bot_count = len(list(filter(lambda m: m.bot, guild.members)))
        if config.use_status_emojis:
            embed.add_field(name=f"Members ({len(guild.members):,})",
                            value=f"**{status_count['online']:,}**{config.status_emojis['online']} "
                                  f"**{status_count['idle']:,}**{config.status_emojis['idle']} "
                                  f"**{status_count['dnd']:,}**{config.status_emojis['dnd']} "
                                  f"**{status_count['offline']:,}**{config.status_emojis['offline']}\n"
                                  f"👨 Humans: **{len(guild.members)-bot_count:,}**\n"
                                  f"🤖 Bots: **{bot_count:,}**"
                            )
        else:
            embed.add_field(name=f"Members ({len(guild.members):,})",
                            value=f"Online: **{status_count['online']:,}**\n"
                                  f"Idle: **{status_count['idle']:,}**\n"
                                  f"Busy: **{status_count['dnd']:,}**\n"
                                  f"Offline: **{status_count['offline']:,}**\n"
                                  f"Humans: **{len(guild.members)-bot_count:,}**\n"
                                  f"Bots: **{bot_count:,}**"
                            )
        embed.add_field(name="Roles", value=f"{len(guild.roles):,}")
        embed.add_field(name="Emojis", value=f"{len(guild.emojis):,}")
        if self.bot.tracked_worlds.get(guild.id):
            embed.add_field(name="Tracked world", value=self.bot.tracked_worlds.get(guild.id))
        if guild.splash_url:
            embed.add_field(name="Splash screen", value="\u200F", inline=True)
            embed.set_image(url=guild.splash_url)
        await ctx.send(embed=embed)

    @commands.command()
    async def uptime(self, ctx):
        """Shows how long the bot has been running."""
        await ctx.send("I have been running for {0}.".format(parse_uptime(self.bot.start_time, True)))

    @commands.guild_only()
    @checks.can_embed()
    @commands.command(aliases=["memberinfo"])
    async def userinfo(self, ctx, *, user: str=None):
        """Shows a user's information.

        About user statutes:
        - Server Owner: Owner of the server
        - Server Admin: User with Administrator permission
        - Server Moderator: User with `Manage Server` permissions.
        - Channel Moderator: User with `Manage Channels` permissions in at least one channel."""
        if user is None:
            user = ctx.author
        else:
            _user = self.bot.get_member(user, ctx.guild)
            if _user is None:
                await ctx.send(f"Could not find user `{user}`")
                return
            user = _user
        embed = discord.Embed(title=f"{user.name}#{user.discriminator}", timestamp=user.joined_at, colour=user.colour)
        if config.use_status_emojis:
            embed.title += config.status_emojis[str(user.status)]
        embed.set_thumbnail(url=get_user_avatar(user))
        embed.set_footer(text="Member since")
        embed.add_field(name="ID", value=user.id)
        embed.add_field(name="Created", value=user.created_at)
        status = []
        if ctx.guild.owner == user:
            status.append("Server Owner")
        if user.guild_permissions.administrator:
            status.append("Server Admin")
        if user.guild_permissions.manage_guild:
            status.append("Server Moderator")
        if any(c.permissions_for(user).manage_channels for c in ctx.guild.text_channels):
            status.append("Channel Moderator")
        if user.bot:
            status.append("Bot")
        if not status:
            status.append("Regular User")
        embed.add_field(name="User Status", value=", ".join(status), inline=False)

        embed.add_field(name="Servers", value=f"{len(self.bot.get_user_guilds(user.id))} shared")
        embed.add_field(name="Roles", value=f"{len(user.roles):,}")
        embed.add_field(name="Highest role", value=f"{user.top_role.mention}")

        await ctx.send(embed=embed)

    async def notify_subscribers(self, event_id: int, content, *, embed: discord.Embed=None, skip_creator=False):
        """Sends a message to all users subscribed to an event"""
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            creator = c.fetchone()["creator"]
            c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (event_id,))
            subscribers = c.fetchall()
        if not subscribers:
            return
        for subscriber in subscribers:
            if subscriber == creator and skip_creator:
                continue
            member = self.bot.get_member(subscriber["user_id"])
            if member is None:
                continue
            await member.send(content, embed=embed)

    def get_event(self, ctx: NabCtx, event_id: int) -> Optional[Dict[str, Union[int, str]]]:
        # If this is used on a PM, show events for all shared servers
        if ctx.is_private:
            guilds = self.bot.get_user_guilds(ctx.author.id)
        else:
            guilds = [ctx.guild]
        guild_ids = [s.id for s in guilds]
        placeholders = ", ".join("?" for s in guilds)
        c = userDatabase.cursor()
        now = time.time()
        c.execute("SELECT * FROM events "
                  "WHERE id = {0} AND active = 1 AND start > {1} AND server IN ({2})".format(event_id, now,
                                                                                             placeholders)
                  , tuple(guild_ids))

        event = c.fetchone()
        if event is None:
            return None
        c.execute("SELECT user_id, id as char_id, name, ABS(level) as level, vocation, world  "
                  "FROM chars WHERE id IN (SELECT char_id FROM event_participants WHERE event_id = ?)",
                  (event_id,))
        event["participants"] = c.fetchall()
        return event

    def __unload(self):
        self.events_announce_task.cancel()
        self.game_update_task.cancel()


def setup(bot):
    bot.add_cog(General(bot))
