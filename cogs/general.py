import asyncio
import datetime as dt
import random
import re
import time
from contextlib import closing
from typing import Union, Dict, Optional

import discord
import psutil
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.database import userDatabase, tibiaDatabase, get_server_property
from utils.discord import is_lite_mode, get_region_string, get_role_list, get_role, is_private, clean_string
from utils.general import parse_uptime, TimeString, single_line, is_numeric, log
from utils.emoji import EMOJI
from utils.paginator import Paginator, CannotPaginate, VocationPaginator
from utils.tibia import get_voc_abb, get_voc_emoji

EVENT_NAME_LIMIT = 50


class General:
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.events_announce_task = self.bot.loop.create_task(self.events_announce())
        self.game_update_task = self.bot.loop.create_task(self.game_update())

    async def game_update(self):
        """Updates the bot's status.

        A random status is selected every 20 minutes.
        """
        game_list = ["Half-Life 3", "Tibia on Steam", "DOTA 3", "Human Simulator 2018", "Russian roulette",
                     "with my toy humans", "with fire"+EMOJI[":fire:"], "God", "innocent", "the part", "hard to get",
                     "with my human minions", "Singularity", "Portal 3", "Dank Souls", "you", "01101110", "dumb",
                     "with GLaDOS " + EMOJI[":blue_heart:"], "with myself", "with your heart", "Generic MOBA",
                     "Generic Battle Royale", "League of Dota", "my cards right", "out your death in my head"]
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
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
                    announce_channel = \
                        self.bot.get_channel_or_top(guild, get_server_property("events_channel", guild.id, is_int=True))
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

    # Bot commands
    @commands.command(aliases=["commands"], hidden=True)
    async def help(self, ctx, *commands: str):
        """Shows this message."""
        _mentions_transforms = {
            '@everyone': '@\u200beveryone',
            '@here': '@\u200bhere'
        }
        _mention_pattern = re.compile('|'.join(_mentions_transforms.keys()))

        bot = ctx.bot
        destination = ctx.channel if is_private(
            ctx.channel) or ctx.channel.name == config.ask_channel_name else ctx.author

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

    @commands.command()
    async def choose(self, ctx, *choices: str):
        """Chooses between multiple choices."""
        if choices is None:
            return
        user = ctx.author
        await ctx.send('Alright, **@{0}**, I choose: "{1}"'.format(user.display_name, random.choice(choices)))

    @commands.command()
    async def uptime(self, ctx):
        """Shows how long the bot has been running"""
        await ctx.send("I have been running for {0}.".format(parse_uptime(self.bot.start_time, True)))

    @commands.guild_only()
    @commands.command(name="server", aliases=["serverinfo", "server_info"])
    async def info_server(self, ctx):
        """Shows the server's information."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        embed = discord.Embed()
        guild = ctx.guild  # type: discord.Guild
        embed.set_thumbnail(url=guild.icon_url)
        embed.description = guild.name
        # Check if owner has a nickname
        if guild.owner.name == guild.owner.display_name:
            owner = "{0.name}#{0.discriminator}".format(guild.owner)
        else:
            owner = "{0.display_name}\n({0.name}#{0.discriminator})".format(guild.owner)
        embed.add_field(name="Owner", value=owner)
        embed.add_field(name="Created", value=guild.created_at.strftime("%d/%m/%y"))
        embed.add_field(name="Server Region", value=get_region_string(guild.region))
        embed.add_field(name="Text channels", value=len(guild.text_channels))
        embed.add_field(name="Voice channels", value=len(guild.voice_channels))
        embed.add_field(name="Members", value=guild.member_count)
        embed.add_field(name="Roles", value=len(guild.roles))
        embed.add_field(name="Emojis", value=len(guild.emojis))
        embed.add_field(name="Bot joined", value=guild.me.joined_at.strftime("%d/%m/%y"))
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command()
    async def roles(self, ctx: commands.Context, *, user_name: str = None):
        """Shows a list of roles or a user's roles

        If no user_name is specified, it shows a list of the server's role.
        If user_name is specified, it shows a list of that user's roles."""

        if user_name is None:
            title = "Roles in this server"
            entries = [r.mention for r in get_role_list(ctx.guild)]
        else:
            member = self.bot.get_member(user_name, ctx.guild)
            if member is None:
                await ctx.send("I don't see any user named **" + user_name + "**.")
                return
            title = f"Roles for @{member.display_name}"
            entries = []
            # Ignoring "default" roles
            for role in member.roles:
                if role.name not in ["@everyone", "Nab Bot"]:
                    entries.append(role.mention)

            # There shouldn't be anyone without active roles, but since people can check for NabBot,
            # might as well show a specific message.
            if not entries:
                await ctx.send(f"There are no active roles for **{member.display_name}**.")
                return

        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)
        return

    @commands.guild_only()
    @commands.command()
    async def role(self, ctx, *, name: str = None):
        """Shows a list of members with that role"""
        if name is None:
            await ctx.send("You must tell me the name of a role.")
            return
        role = get_role(ctx.guild, role_name=name)
        if role is None:
            await ctx.send("There's no role with that name in here.")
            return

        role_members = [m.mention for m in role.members]
        if not role_members:
            await ctx.send("Seems like there are no members with that role.")
            return

        title = "Members with the role '{0.name}'".format(role)
        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        pages = Paginator(self.bot, message=ctx.message, entries=role_members, per_page=per_page, title=title,
                          color=role.colour)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @commands.command(aliases=["norole"])
    async def noroles(self, ctx):
        """Shows a list of members with no roles"""

        entries = []

        for member in ctx.guild.members:
            # Member only has the @everyone role
            if len(member.roles) == 1:
                entries.append(member.mention)

        if not entries:
            await ctx.send("There are no members without roles.")
            return

        title = "Members with no roles"
        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command()
    async def about(self, ctx):
        """Shows information about the bot"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        lite_mode = is_lite_mode(ctx)
        user_count = 0
        char_count = 0
        deaths_count = 0
        levels_count = 0
        if not lite_mode:
            with closing(userDatabase.cursor()) as c:
                c.execute("SELECT COUNT(*) as count FROM users")
                result = c.fetchone()
                if result is not None:
                    user_count = result["count"]
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

        embed = discord.Embed(description="*Beep bop beep bop*. I'm just a bot!")
        embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                         icon_url="https://github.com/fluidicon.png")
        embed.add_field(name="Version", value=self.bot.__version__)
        embed.add_field(name="Authors", value="\u2023 [Galarzaa90](https://github.com/Galarzaa90)\n"
                                              "\u2023 [Nezune](https://github.com/Nezune)")
        embed.add_field(name="Platform", value="Python " + EMOJI[":snake:"])
        embed.add_field(name="Created", value="March 30th 2016")
        embed.add_field(name="Servers", value="{0:,}".format(len(self.bot.guilds)))
        embed.add_field(name="Members", value="{0:,}".format(len(set(self.bot.get_all_members()))))
        if not lite_mode:
            embed.add_field(name="Tracked users", value="{0:,}".format(user_count))
            embed.add_field(name="Tracked chars", value="{0:,}".format(char_count))
            embed.add_field(name="Tracked deaths", value="{0:,}".format(deaths_count))
            embed.add_field(name="Tracked level ups", value="{0:,}".format(levels_count))

        embed.add_field(name="Uptime", value=parse_uptime(self.bot.start_time))
        memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
        embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
        with closing(tibiaDatabase.cursor()) as c:
            try:
                c.execute("SELECT * FROM database_info WHERE key = ?", ("version",))
                result = c.fetchone()
                if result:
                    version = result["value"]
                c.execute("SELECT * FROM database_info WHERE key = ?", ("generated_date",))
                result = c.fetchone()
                if result:
                    timestamp = float(result["value"])
                    db_date = dt.datetime.utcfromtimestamp(timestamp)
                embed.add_field(name="TibiaWiki Database", value=f"{version}, fetched on "
                                                                 f"{db_date.strftime('%b %d %Y, %H:%M:%S UTC')}")
            except KeyError:
                pass
        await ctx.send(embed=embed)

    @commands.group(aliases=["event"], invoke_without_command=True, case_insensitive=True)
    @checks.is_not_lite()
    async def events(self, ctx, event_id: int=0):
        """Shows a list of current active events

        If a number is specified, it will show details for that event. Same as using /events info"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links and not is_private(ctx.channel):
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        if event_id != 0:
            await ctx.invoke(self.bot.all_commands.get('events').get_command("info"), event_id)
            return
        # Time in seconds the bot will show past events
        time_threshold = 60 * 30
        now = time.time()
        server = ctx.guild
        # If this is used on a PM, show events for all shared servers
        if is_private(ctx.channel):
            guilds = self.bot.get_user_guilds(ctx.author.id)
        else:
            guilds = [ctx.guild]
        servers_ids = [g.id for g in guilds]
        placeholders = ", ".join("?" for g in guilds)
        embed = discord.Embed(description="For more info about an event, use `/event info (id)`"
                                          "\nTo receive notifications for an event, use `/event sub (id)`")
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT creator, start, name, id, server FROM events "
                      "WHERE start < {0} AND start > {1} AND active = 1 AND server IN ({2}) "
                      "ORDER by start ASC".format(now, now - time_threshold, placeholders), tuple(servers_ids))
            recent_events = c.fetchall()
            c.execute("SELECT creator, start, name, id, server FROM events "
                      "WHERE start > {0} AND active = 1 AND server IN ({1})"
                      "ORDER BY start ASC".format(now, placeholders), tuple(servers_ids))
            upcoming_events = c.fetchall()
        if len(recent_events) + len(upcoming_events) == 0:
            await ctx.send("There are no upcoming events.")
            return
        # Recent events
        if recent_events:
            name = "Recent events"
            value = ""
            for event in recent_events:
                author = self.bot.get_member(event["creator"], server)
                event["author"] = "unknown" if author is None else (author.display_name if server else author.name)
                time_diff = dt.timedelta(seconds=now - event["start"])
                minutes = round((time_diff.seconds / 60) % 60)
                event["start_str"] = "Started {0} minutes ago".format(minutes)
                value += "\n**{name}** (by **@{author}**,*ID:{id}*) - {start_str}".format(**event)
            embed.add_field(name=name, value=value, inline=False)
        # Upcoming events
        if upcoming_events:
            name = "Upcoming events"
            value = ""
            for event in upcoming_events:
                author = self.bot.get_member(event["creator"], server)
                event["author"] = "unknown" if author is None else (author.display_name if server else author.name)
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
                value += "\n**{name}** (by **@{author}**,*ID:{id}*) - {start_str}".format(**event)
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @checks.is_not_lite()
    @events.command(name="info", aliases=["show", "details"])
    async def event_info(self, ctx, event_id: int):
        """Displays an event's info

        The start time shown in the footer is always displayed in your device's timezone."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        event = self.get_event(ctx, event_id)
        if not event:
            await ctx.send("There's no event with that id.")
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

    @checks.is_not_lite()
    @events.command(name="add")
    async def event_add(self, ctx, starts_in: TimeString, *, params):
        """Adds an event

        The syntax is:
        /event add starts_in name
        /event add starts_in name,description

        starts_in means in how much time the event will start since the moment of creation
        The time can be set using units such as 'd' for days, 'h' for hours, 'm' for minutes and 'd' for seconds.
        You can embed links using this syntax: [link title](link url)
        Examples: 1d20h5m, 1d30m, 1h40m, 40m
        """
        now = time.time()
        creator = ctx.author.id
        start = now + starts_in.seconds
        params = params.split(",", 1)
        name = single_line(clean_string(ctx, params[0]))
        if len(name) > EVENT_NAME_LIMIT:
            await ctx.send(f"The event's name can't be longer than {EVENT_NAME_LIMIT} characters.")
            return
        event_description = ""
        if len(params) > 1:
            event_description = clean_string(ctx, params[1])

        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
            result = c.fetchall()
        if len(result) > 1 and creator not in config.owner_ids:
            await ctx.send("You can only have two running events simultaneously. Delete or edit an active event")
            return

        guilds = self.bot.get_user_guilds(creator)
        # If message is via PM, but user only shares one server, we just consider that server
        if is_private(ctx.channel) and len(guilds) == 1:
            guild = guilds[0]
        # Not a private message, so we just take current guild
        elif not is_private(ctx.channel):
            guild = ctx.guild
        # PM and user shares multiple servers, we must ask him for which server is the event
        else:
            await ctx.send("For which server is this event? Choose one (number only)" +
                           "\n\t0: *Cancel*\n\t" +
                           "\n\t".join(["{0}: **{1.name}**".format(i + 1, j) for i, j in enumerate(guilds)]))

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                answer = int(reply.content)
                if answer == 0:
                    await ctx.send("Changed your mind? Typical human.")
                    return
                guild = guilds[answer - 1]
            except IndexError:
                await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
                return
            except ValueError:
                await ctx.send("That's not a valid answer, try the command again.")
                return
            except asyncio.TimeoutError:
                await ctx.send("Nothing? Forget it then.")
                return

        embed = discord.Embed(title=name, description=event_description, timestamp=dt.datetime.utcfromtimestamp(start))
        embed.set_footer(text="Start time")

        message = await ctx.send("Is this correct?", embed=embed)
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, no event for you.")
            return
        with closing(userDatabase.cursor()) as c:
            c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                      (creator, guild.id, start, name, event_description))
            event_id = c.lastrowid
            userDatabase.commit()

        reply = "Event created successfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*"
        await ctx.send(reply.format(name, starts_in.original, event_id))

    @event_add.error
    @checks.is_not_lite()
    async def event_add_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error))

    @events.group(name="edit", invoke_without_command=True, case_insensitive=True)
    async def event_edit(self, ctx):
        """Edits an event's name, description or time
        
        This command by itself does nothing, you must use one of its subcommands."""
        await ctx.send("To edit an event try:\n```"
                       "/event edit name <id> [new_name]\n"
                       "/event edit description <id> [new_description]\n"
                       "/event edit time <id> [new_time]\n"
                       "/event edit joinable <id> [yes_no]\n"
                       "/event edit slots <id> [new_slots]"
                       "```")

    @event_edit.command(name="name", aliases=["title"])
    @checks.is_not_lite()
    async def event_edit_name(self, ctx, event_id: int = None, *, new_name=None):
        """Edits an event's name

        Only the creator of the event or mods can edit an event's name
        Only upcoming events can be edited"""
        if event_id is None:
            await ctx.send(f"You need to tell me the id of the event you want to edit."
                           f"\nLike this: `{ctx.message.content} 50` or `{ctx.message.content} 50 new_name`")
            return
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only edit your own events.")
            return

        def check(m):
            return ctx.channel == m.channel and ctx.author == m.author

        if new_name is None:
            await ctx.send(f"What would you like to be the new name of **{event['name']}**? You can `cancel` this.")
            try:
                reply = await self.bot.wait_for("message", check=check, timeout=120)
                new_name = reply.content
                if new_name.strip().lower() == "cancel":
                    await ctx.send("Alright, operation cancelled.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("Guess you don't want to change the name...")
                return

        new_name = single_line(clean_string(ctx, new_name))
        if len(new_name) > EVENT_NAME_LIMIT:
            await ctx.send(f"The name can't be longer than {EVENT_NAME_LIMIT} characters.")
            return
        message = await ctx.send(f"Do you want to change the name of **{event['name']}** to **{new_name}**?")
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, name remains the same.")
            return

        with userDatabase as conn:
            conn.execute("UPDATE events SET name = ? WHERE id = ?", (new_name, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send(f"Your event was renamed successfully to **{new_name}**.")
        else:
            await ctx.send(f"Event renamed successfully to **{new_name}**.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was renamed to **{new_name}** by "
                                   f"{ctx.author.mention}")
        await self.notify_subscribers(event_id, f"The event **{event['name']}** was renamed to **{new_name}**.",
                                      skip_creator=True)

    @event_edit.command(name="description", aliases=["desc", "details"])
    @checks.is_not_lite()
    async def event_edit_description(self, ctx, event_id: int=None, *, new_description=None):
        """Edits an event's description

        Only the creator of the event or mods can edit an event's description
        Only upcoming events can be edited"""
        if event_id is None:
            await ctx.send(f"You need to tell me the id of the event you want to edit."
                           f"\nLike this: `{ctx.message.content} 50` or `{ctx.message.content} 50 new_description`")
            return
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only edit your own events.")
            return

        def check(m):
            return ctx.channel == m.channel and ctx.author == m.author

        if new_description is None:
            await ctx.send(f"What would you like to be the new description of **{event['name']}**?"
                           f"You can `cancel` this or set a `blank` description.")
            try:
                reply = await self.bot.wait_for("message", check=check, timeout=120)
                new_description = reply.content
                if new_description.strip().lower() == "cancel":
                    await ctx.send("Alright, operation cancelled.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("Guess you don't want to change the description...")
                return

        if new_description.strip().lower() == "blank":
            new_description = ""
        new_description = clean_string(ctx, new_description)

        embed = discord.Embed(title=event["name"], description=new_description,
                              timestamp=dt.datetime.utcfromtimestamp(event["start"]))
        embed.set_footer(text="Start time")
        message = await ctx.send("Do you want this to be the new description?", embed=embed)
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, no changes will be done.")
            return

        with userDatabase as conn:
            conn.execute("UPDATE events SET description = ? WHERE id = ?", (new_description, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send("Your event's description was changed successfully.")
        else:
            await ctx.send("Event's description changed successfully.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** had its description changed by {ctx.author.mention}",
                                   embed=embed)
        await self.notify_subscribers(event_id, f"The description of event **{event['name']}** was changed.",
                                      embed=embed, skip_creator=True)

    @event_edit.command(name="time", aliases=["date", "start"])
    @checks.is_not_lite()
    async def event_edit_time(self, ctx, event_id: int, starts_in: TimeString=None):
        """Changes an event's time

        Only the creator of the event or mods can edit an event's time
        Only upcoming events can be edited"""
        if event_id is None:
            await ctx.send(f"You need to tell me the id of the event you want to edit."
                           f"\nLike this: `{ctx.message.content} 50` or `{ctx.message.content} 50 new_time`")
            return
        now = time.time()
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only edit your own events.")
            return

        def check(m):
            return ctx.channel == m.channel and ctx.author == m.author

        if starts_in is None:
            await ctx.send(f"When would you like the new start time of **{event['name']}** be?"
                           f"You can `cancel` this.\n Examples: `1h20m`, `2d10m`")
            try:
                reply = await self.bot.wait_for("message", check=check, timeout=120)
                new_time = reply.content
                if new_time.strip().lower() == "cancel":
                    await ctx.send("Alright, operation cancelled.")
                    return
                starts_in = TimeString(new_time)
            except commands.BadArgument as e:
                await ctx.send(str(e))
                return
            except asyncio.TimeoutError:
                await ctx.send("Guess you don't want to change the time...")
                return
        embed = discord.Embed(title=event["name"], timestamp=dt.datetime.utcfromtimestamp(now+starts_in.seconds))
        embed.set_footer(text="Start time")
        message = await ctx.send(f"This will be the time of your new event in your local time. Is this correct?",
                                 embed=embed)
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, event remains the same.")
            return

        with userDatabase as conn:
            conn.execute("UPDATE events SET start = ? WHERE id = ?", (now + starts_in.seconds, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send("Your event's start time was changed successfully to **{0}**.".format(starts_in.original))
        else:
            await ctx.send("Event's time changed successfully.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"The start time of your event **{event['name']}** was changed to "
                                   f"**{starts_in.original}** by {ctx.author.mention}.")
        await self.notify_subscribers(event_id, f"The start time of **{event['name']}** was changed:", embed=embed,
                                      skip_creator=True)

    @event_edit.command(name="slots", aliases=["spaces", "slot", "size"])
    @checks.is_not_lite()
    async def event_edit_slots(self, ctx, event_id: int = None, *, slots=None):
        """Edits an event's number of slots

        Only the creator of the event or mods can edit an event's slots
        Only upcoming events can be edited"""
        if event_id is None:
            await ctx.send(f"You need to tell me the id of the event you want to edit."
                           f"\nLike this: `{ctx.message.content} 50` or `{ctx.message.content} 50 new_name`")
            return
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only edit your own events.")
            return

        def check(m):
            return ctx.channel == m.channel and ctx.author == m.author

        if slots is None:
            await ctx.send(f"What would you like to be the new number of slots for  **{event['name']}**? "
                           f"You can `cancel` this.\n Note that `0` means no slot limit.")
            try:
                reply = await self.bot.wait_for("message", check=check, timeout=120)
                slots = reply.content
                if slots.strip().lower() == "cancel":
                    await ctx.send("Alright, operation cancelled.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("Guess you don't want to change the name...")
                return
        try:
            slots = int(slots)
            if slots < 0:
                await ctx.send("You can't have negative slots!")
                return
        except ValueError:
            await ctx.send("That's not a number...")
            return
        message = await ctx.send(f"Do you want the number of slots of **{event['name']}** to **{slots}**?")
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, slots remain unchanged.")
            return

        with userDatabase as conn:
            conn.execute("UPDATE events SET slots = ? WHERE id = ?", (slots, event_id,))

        if event["creator"] == ctx.author.id:
            await ctx.send(f"Your event slots were changed to **{slots}**.")
        else:
            await ctx.send(f"Event slots changed to **{slots}**.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** slots were changed to **{slots}** by "
                                   f"{ctx.author.mention}")

    @event_edit.command(name="joinable", aliases=["open"])
    @checks.is_not_lite()
    async def event_edit_joinable(self, ctx, event_id: int, *, yes_no: str=None):
        """Changes whether anyone can join an event or only the owner may add people

        If an event is joinable, anyone can join using /event join id
        Otherwise, the event creator has to add people with /event addplayer id
        Only the creator of the event or mods can edit this
        Only upcoming events can be edited"""
        if event_id is None:
            await ctx.send(f"You need to tell me the id of the event you want to edit."
                           f"\nLike this: `{ctx.message.content} 50` or `{ctx.message.content} 50 new_time`")
            return
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only edit your own events.")
            return

        def check(m):
            return ctx.channel == m.channel and ctx.author == m.author

        if yes_no is None:
            await ctx.send(f"Do you want **{event['name']}** to be joinable? `yes/no/cancel`")
            try:
                reply = await self.bot.wait_for("message", check=check, timeout=120)
                new_joinable = reply.content
                if new_joinable.strip().lower() == "cancel":
                    await ctx.send("Alright, operation cancelled.")
                    return
                joinable = new_joinable.lower() in ["yes", "yeah"]
            except asyncio.TimeoutError:
                await ctx.send("Guess you don't want to change the time...")
                return
        else:
            joinable = yes_no.lower() in ["yes", "yeah"]
        joinable_string = "joinable" if joinable else "not joinable"

        with userDatabase as conn:
            conn.execute("UPDATE events SET joinable = ? WHERE id = ?", (joinable, event_id))

        if event["creator"] == ctx.author.id:
            await ctx.send("Your event's was changed succesfully to **{0}**.".format(joinable_string))
        else:
            await ctx.send("Event's time changed successfully.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was changed to **{joinable_string}** "
                                   f"by {ctx.author.mention}.")

    @checks.is_not_lite()
    @events.command(name="delete", aliases=["remove", "cancel"])
    async def event_remove(self, ctx, event_id: int):
        """Deletes an event

        Only the creator of the event or mods can delete an event
        Only upcoming events can be edited"""
        c = userDatabase.cursor()
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only delete your own events.")
            return

        message = await ctx.send("Do you want to delete the event **{0}**?".format(event["name"]))
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, event remains active.")
            return

        with userDatabase as conn:
            conn.execute("UPDATE events SET active = 0 WHERE id = ?", (event_id,))
        if event["creator"] == ctx.author.id:
            await ctx.send("Your event was deleted successfully.")
        else:
            await ctx.send("Event deleted successfully.")
            creator = self.bot.get_member(event["creator"])
            if creator is not None:
                await creator.send(f"Your event **{event['name']}** was deleted by {ctx.author.mention}.")
        await self.notify_subscribers(event_id, f"The event **{event['name']}** was deleted by {ctx.author.mention}.",
                                      skip_creator=True)

    # TODO: Do not cancel the whole process if a parameter is invalid, retry at that point
    @checks.is_not_lite()
    @events.command(name="make", aliases=["creator", "maker"])
    async def event_make(self, ctx):
        """Creates an event guiding you step by step

        Instead of using confusing parameters, commas and spaces, this commands has the self.bot ask you step by step."""

        def check(m):
            return m.channel == ctx.channel and m.author == ctx.author

        author = ctx.author
        creator = author.id
        now = time.time()
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
            event = c.fetchall()
        if len(event) > 1 and creator not in config.owner_ids:
            return
        await ctx.send("Let's create an event. What would you like the name to be? You can `cancel` at any time.")

        try:
            name = await self.bot.wait_for("message", timeout=120.0, check=check)
            name = single_line(name.clean_content)
            if len(name) > EVENT_NAME_LIMIT:
                await ctx.send(f"The name can't be longer than {EVENT_NAME_LIMIT} characters.")
                return
            if name.strip().lower() == "cancel":
                await ctx.send("Event making cancelled.")
                return
        except asyncio.TimeoutError:
            await ctx.send("...You took to long. Event making cancelled.")
            return

        await ctx.send("Alright, what description would you like the event to have? "
                       "`no/none/blank` to leave it empty.")

        try:
            event_description = await self.bot.wait_for("message", timeout=120.0, check=check)
            if event_description.content.strip().lower() == "cancel":
                await ctx.send("Event making cancelled.")
                return
            if event_description.content.lower().strip() in ["no", "none","blank"]:
                await ctx.send("No description then? Alright, now tell me the start time of the event from now. "
                               "`e.g. 2d1h20m, 2d3h`")
                event_description = ""
            else:
                event_description = event_description.clean_content
                await ctx.send("Alright, now tell me the start time of the event from now. `e.g. 2d1h20m, 2d3h`")
        except asyncio.TimeoutError:
            await ctx.send("...You took too long. Event making cancelled.")
            return

        while True:
            try:
                starts_in = await self.bot.wait_for("message", timeout=120.0, check=check)
                if starts_in.content.strip().lower() == "cancel":
                    await ctx.send("Event making cancelled.")
                    return
                starts_in = TimeString(starts_in.content)
                break
            except commands.BadArgument as e:
                await ctx.send(f'{e}\nAgain, tell me the start time of the event from now')
            except asyncio.TimeoutError:
                await ctx.send("...You took too long. Event making cancelled.")
                return

        guilds = self.bot.get_user_guilds(creator)
        # If message is via PM, but user only shares one server, we just consider that server
        if is_private(ctx.channel) and len(guilds) == 1:
            guild = guilds[0]
        # Not a private message, so we just take current server
        elif not is_private(ctx.channel):
            guild = ctx.guild
        # PM and user shares multiple servers, we must ask him for which server is the event
        else:
            await ctx.send("One more question...for which server is this event? Choose one (number only)" +
                           "\n\t0: *Cancel*\n\t" +
                           "\n\t".join(["{0}: **{1.name}**".format(i + 1, j) for i, j in enumerate(guilds)]))
            try:
                reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                if is_numeric(reply.content):
                    answer = int(reply.content)
                    if answer == 0:
                        await ctx.send("Changed your mind? Typical human.")
                        return
                    guild = guilds[answer - 1]
                else:
                    await ctx.send("That's not a valid answer, try the command again.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("Nothing? Forget it then.")
                return
            except ValueError:
                await ctx.send("That isn't even a number!")
                return
            except IndexError:
                await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
                return

        embed = discord.Embed(title=name, description=event_description,
                              timestamp=dt.datetime.utcfromtimestamp(now+starts_in.seconds))
        embed.set_footer(text="Start time")
        message = await ctx.send("Ok, so this will be your new event. Is this correct?", embed=embed)
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Alright, no event will be made.")
            return

        now = time.time()
        with closing(userDatabase.cursor()) as c:
            c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                      (creator, guild.id, now + starts_in.seconds, name, event_description))
            event_id = c.lastrowid
            userDatabase.commit()
        reply = "Event registered successfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*"
        await ctx.send(reply.format(name, starts_in.original, event_id))

    @checks.is_not_lite()
    @events.command(name="subscribe", aliases=["sub"])
    async def event_subscribe(self, ctx, event_id: int):
        """Subscribe to receive a PM when an event is happening."""
        c = userDatabase.cursor()
        author = ctx.author
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        try:
            message = await ctx.send(f"Do you want to subscribe to **{event['name']}**")
            confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
            if confirm is None:
                await ctx.send("You took too long!")
                return
            if not confirm:
                await ctx.send("Ok then.")
                return

            c.execute("INSERT INTO event_subscribers (event_id, user_id) VALUES(?,?)", (event_id, author.id))
            await ctx.send("You have subscribed successfully to this event. I'll let you know when it's happening.")

        finally:
            c.close()
            userDatabase.commit()

    @checks.is_not_lite()
    @events.command(name="unsubscribe", aliases=["unsub"])
    async def event_unsubscribe(self, ctx, event_id: int):
        """Unsubscribe to an event."""
        c = userDatabase.cursor()
        author = ctx.author
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        try:
            c.execute("SELECT * FROM event_subscribers WHERE event_id = ? AND user_id = ?", (event_id, author.id))
            subscription = c.fetchone()
            if subscription is None:
                await ctx.send("You are not subscribed to this event.")
                return

            message = await ctx.send(f"Do you want to unsubscribe to **{event['name']}**")
            confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
            if confirm is None:
                await ctx.send("You took too long!")
                return
            if not confirm:
                await ctx.send("Ok then.")
                return

            c.execute("DELETE FROM event_subscribers WHERE event_id = ? AND user_id = ?", (event_id, author.id))
            await ctx.send("You have subscribed successfully to this event. I'll let you know when it's happening.")

        finally:
            c.close()
            userDatabase.commit()

    @checks.is_not_lite()
    @events.command(name="participants")
    async def event_participants(self, ctx, event_id: int):
        """Shows the list of characters participating in this event."""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if len(event["participants"]) == 0:
            join_prompt = ""
            if event["joinable"] != 0:
                join_prompt = f" To join, use `/event join {event_id} characterName`."
            await ctx.send(f"There are no participants in this event.{join_prompt}")
            return
        entries = []
        vocations = []
        event_server = self.bot.get_guild(event["server"])  # type: discord.Guild
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
        pages = VocationPaginator(self.bot, message=ctx.message, entries=entries, per_page=15, title=event["name"],
                                  author=author_name, author_icon=author_icon, vocations=vocations)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.is_not_lite()
    @events.command(name="join")
    async def event_join(self, ctx, event_id: int, *, character: str):
        """Join an event with a specific character

        You can only join an event with a character at a time.
        Some events may not be joinable and require the creator to add characters themselves."""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
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
            await ctx.send(f"You can't join this event. Maybe you meant to subscribe? Try `/event sub {event_id}`.")
            return
        if event["slots"] != 0 and len(participants) >= event["slots"]:
            await ctx.send("All the slots for this event has been filled.")
            return
        if char is None:
            await ctx.send("That character is not registered.")
            return
        if char["user_id"] != ctx.author.id:
            await ctx.send("You can only join with characters registered to you.")
            return
        world = self.bot.tracked_worlds.get(event["server"])
        if world != char["world"]:
            await ctx.send("You can't join with a character from another world.")
            return
        if any(ctx.author.id == participant["user_id"] for participant in participants):
            await ctx.send("A character of yours is already in this event.")
            return

        message = await ctx.send(f"Do you want to join the event \'**{event['name']}**\' as **{char['name']}**?")
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        with userDatabase as con:
            con.execute("INSERT INTO event_participants(event_id, char_id) VALUES(?,?)", (event_id, char["id"]))
            await ctx.send("You successfully joined this event.")
            return

    @checks.is_not_lite()
    @events.command(name="leave")
    async def event_leave(self, ctx, event_id: int):
        """Leave an event you were participating in"""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        joined_char = next((participant["char_id"] for participant in event["participants"]
                           if ctx.author.id == participant["user_id"]), None)
        if joined_char is None:
            await ctx.send("You haven't joined this event.")
            return

        message = await ctx.send(f"Do you want to leave **{event['name']}**?")
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        with userDatabase as con:
            con.execute("DELETE FROM event_participants WHERE event_id = ? AND char_id = ?", (event_id, joined_char))
            await ctx.send("You successfully left this event.")
            return

    @checks.is_not_lite()
    @events.command(name="addplayer", aliases=["addchar"])
    async def event_addplayer(self, ctx, event_id: int, *, character):
        """Adds a character to an event

        Only the creator can add characters to an event.
        If the event is joinable, anyone can join an event using /event join"""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only add people to your own events.")
            return
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT * FROM chars WHERE name LIKE ?", (character,))
            char = c.fetchone()
        if event["slots"] != 0 and len(event["participants"]) >= event["slots"]:
            await ctx.send(f"All the slots for this event has been filled. "
                           f"You can change them by using `/event edit slots {event_id} newSlots`.")
            return
        owner = self.bot.get_member(char["user_id"], ctx.guild)
        if char is None or owner is None:
            await ctx.send("That character is not registered.")
            return

        world = self.bot.tracked_worlds.get(event["server"])
        if world != char["world"]:
            await ctx.send("You can't add a character from another world.")
            return
        if any(owner.id == participant["user_id"] for participant in event["participants"]):
            await ctx.send(f"A character of @{owner.display_name} is already participating.")
            return

        message = await ctx.send(f"Do you want to add **{char['name']}** (@{owner.display_name}) "
                                 f"to **{event['name']}**?")
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        with userDatabase as con:
            con.execute("INSERT INTO event_participants(event_id, char_id) VALUES(?,?)", (event_id, char["id"]))
            await ctx.send(f"You successfully added **{char['name']}** to this event.")
            return

    @checks.is_not_lite()
    @events.command(name="removeplayer", aliases=["removechar"])
    async def event_removeplayer(self, ctx, event_id: int, *, character):
        """Removes a player from an event

        Only the creator can remove players from an event.
        Players can remove themselves using /event leave"""
        event = self.get_event(ctx, event_id)
        if event is None:
            await ctx.send("There's no active event with that id.")
            return
        if event["creator"] != int(ctx.author.id) and ctx.author.id not in config.owner_ids:
            await ctx.send("You can only add people to your own events.")
            return
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT * FROM chars WHERE name LIKE ?", (character,))
            char = c.fetchone()
        joined_char = next((participant["char_id"] for participant in event["participants"]
                            if char["id"] == participant["char_id"]), None)
        if joined_char is None:
            await ctx.send("This character is not in this event.")
            return
        event_server = self.bot.get_guild(event["server"])
        owner = self.bot.get_member(char["user_id"], self.bot.get_guild(event_server))
        owner_name = "unknown" if owner is None else owner.display_name
        message = await ctx.send(f"Do you want to remove **{char['name']}** (@**{owner_name}**) from **{event['name']}**?")
        confirm = await self.bot.wait_for_confirmation_reaction(ctx, message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Nevermind then.")
            return

        with userDatabase as con:
            con.execute("DELETE FROM event_participants WHERE event_id = ? AND char_id = ?", (event_id, joined_char))
            await ctx.send("You successfully left this event.")
            return

    @event_edit_name.error
    @event_edit_description.error
    @event_edit_time.error
    @event_edit_joinable.error
    @event_edit_slots.error
    @event_participants.error
    @event_remove.error
    @event_subscribe.error
    @event_join.error
    @event_leave.error
    @event_addplayer.error
    @event_removeplayer.error
    async def event_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("Invalid arguments used. `Type /help {0}`".format(ctx.invoked_subcommand))
        elif isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send("You're missing a required argument. `Type /help {0}`".format(ctx.invoked_subcommand))

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

    def get_event(self, ctx: commands.Context, event_id: int) -> Optional[Dict[str, Union[int, str]]]:
        # If this is used on a PM, show events for all shared servers
        if is_private(ctx.channel):
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
