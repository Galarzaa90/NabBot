import asyncio
import re

import discord
from datetime import timedelta, datetime
from discord.ext import commands
import psutil
import random
import time

from config import ask_channel_name, owner_ids, mod_ids
from nabbot import NabBot
from utils import checks
from utils.database import userDatabase
from utils.discord import is_lite_mode, get_region_string, get_role_list, get_role, is_private, clean_string
from utils.general import get_uptime, TimeString, single_line, is_numeric
from utils.messages import EMOJI
from utils.paginator import Paginator, CannotPaginate


class General:
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.bot.loop.create_task(self.events_announce())

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
                    time_diff = timedelta(seconds=event["start"] - date)
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
                    await guild.default_channel.send(message)
                    # Fetch list of subscribers
                    c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (event["id"],))
                    subscribers = c.fetchall()
                    if not subscribers:
                        continue
                    for subscriber in subscribers:
                        member = self.bot.get_member(subscriber["user_id"])
                        if member is None:
                            continue
                        await member.send(message)
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
        destination = ctx.message.channel if is_private(
            ctx.message.channel) or ctx.message.channel.name == ask_channel_name else ctx.message.author

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
                if command is None:
                    await destination.send(bot.command_not_found.format(name))
                    return

            pages = await bot.formatter.format_help_for(ctx, command)
        else:
            name = _mention_pattern.sub(repl, commands[0])
            command = bot.all_commands.get(name)
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
        user = ctx.message.author
        await ctx.send('Alright, **@{0}**, I choose: "{1}"'.format(user.display_name, random.choice(choices)))

    @commands.command()
    async def uptime(self, ctx):
        """Shows how long the bot has been running"""
        await ctx.send("I have been running for {0}.".format(get_uptime(True)))

    @commands.guild_only()
    @commands.command(name="server", aliases=["serverinfo", "server_info"])
    async def info_server(self, ctx):
        """Shows the server's information."""
        permissions = ctx.message.channel.permissions_for(self.bot.get_member(self.bot.user.id, ctx.message.guild))
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        embed = discord.Embed()
        guild = ctx.message.guild  # type: discord.Guild
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
        """Shows a list of roles or an user's roles

        If no user_name is specified, it shows a list of the server's role.
        If user_name is specified, it shows a list of that user's roles."""

        if user_name is None:
            title = "Roles in this server"
            entries = [r.mention for r in get_role_list(ctx.message.guild)]
        else:
            member = self.bot.get_member_by_name(user_name, ctx.message.guild)
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

        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
        if is_private(ctx.message.channel) or ctx.message.channel == ask_channel:
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
        role = get_role(ctx.message.guild, role_name=name)
        if role is None:
            await ctx.send("There's no role with that name in here.")
            return

        role_members = []
        # Iterate through each member, adding the ones that contain the role to a list
        for member in ctx.message.guild.members:
            for r in member.roles:
                if r == role:
                    role_members.append(member.mention)
                    break
        if not role_members:
            await ctx.send("Seems like there are no members with that role.")
            return

        title = "Members with the role '{0.name}'".format(role)
        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
        if is_private(ctx.message.channel) or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        pages = Paginator(self.bot, message=ctx.message, entries=role_members, per_page=per_page, title=title,
                          color=role.colour)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command()
    async def about(self, ctx):
        """Shows information about the bot"""
        permissions = ctx.message.channel.permissions_for(self.bot.get_member(self.bot.user.id, ctx.message.guild))
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        lite_mode = is_lite_mode(ctx)
        user_count = 0
        char_count = 0
        deaths_count = 0
        levels_count = 0
        if not lite_mode:
            c = userDatabase.cursor()
            try:
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
            finally:
                c.close()

        embed = discord.Embed(description="*Beep boop beep boop*. I'm just a bot!")
        embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                         icon_url="https://assets-cdn.github.com/favicon.ico")
        embed.add_field(name="Authors", value="@Galarzaa#8515, @Nezune#2269")
        embed.add_field(name="Platform", value="Python " + EMOJI[":snake:"])
        embed.add_field(name="Created", value="March 30th 2016")
        embed.add_field(name="Servers", value="{0:,}".format(len(self.bot.guilds)))
        embed.add_field(name="Members", value="{0:,}".format(len(set(self.bot.get_all_members()))))
        if not lite_mode:
            embed.add_field(name="Tracked users", value="{0:,}".format(user_count))
            embed.add_field(name="Tracked chars", value="{0:,}".format(char_count))
            embed.add_field(name="Tracked deaths", value="{0:,}".format(deaths_count))
            embed.add_field(name="Tracked level ups", value="{0:,}".format(levels_count))

        embed.add_field(name="Uptime", value=get_uptime())
        memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
        embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
        await ctx.send(embed=embed)

    @commands.group(aliases=["event"], invoke_without_command=True)
    @checks.is_not_lite()
    async def events(self, ctx):
        """Shows a list of current active events"""
        permissions = ctx.message.channel.permissions_for(self.bot.get_member(self.bot.user.id, ctx.message.guild))
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        time_threshold = 60 * 30
        now = time.time()
        c = userDatabase.cursor()
        server = ctx.message.guild
        try:
            # If this is used on a PM, show events for all shared servers
            if is_private(ctx.message.channel):
                guilds = self.bot.get_user_guilds(ctx.message.author.id)
            else:
                guilds = [ctx.message.guild]
            servers_ids = [g.id for g in guilds]
            placeholders = ", ".join("?" for g in guilds)
            embed = discord.Embed(description="For more info about an event, use `/event info (id)`"
                                              "\nTo receive notifications for an event, use `/event sub (id)`")
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
                    time_diff = timedelta(seconds=now - event["start"])
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
                    time_diff = timedelta(seconds=event["start"] - now)
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
        finally:
            c.close()

    @checks.is_not_lite()
    @events.command(name="info", aliases=["show", "details"])
    async def event_info(self, ctx, event_id: int):
        """Displays an event's info"""
        permissions = ctx.message.channel.permissions_for(self.bot.get_member(self.bot.user.id, ctx.message.guild))
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        c = userDatabase.cursor()
        guild = ctx.message.guild
        try:
            # If this is used on a PM, show events for all shared servers
            if is_private(ctx.message.channel):
                guilds = self.bot.get_user_guilds(ctx.message.author.id)
            else:
                guilds = [ctx.message.guild]
            servers_ids = [g.id for g in guilds]
            placeholders = ", ".join("?" for g in guilds)

            c.execute("SELECT * FROM events "
                      "WHERE id = {0} AND active = 1 and server IN ({1})".format(event_id, placeholders),
                      tuple(servers_ids))
            event = c.fetchone()
            if not event:
                await ctx.send("There's no event with that id.")
                return
            start = datetime.fromtimestamp(event["start"])
            embed = discord.Embed(title=event["name"], description=event["description"], timestamp=start)
            author = self.bot.get_member(event["creator"], guild)
            footer = "Start time"
            footer_icon = ""
            if author is not None:
                if guild is None:
                    author_name = author.name
                else:
                    author_name = author.display_name
                footer = "Created by " + author_name + " | Start time"
                footer_icon = author.avatar_url if author.avatar_url else author.default_avatar_url
            embed.set_footer(text=footer, icon_url=footer_icon)
            await ctx.send(embed=embed)
        finally:
            c.close()

    @checks.is_not_lite()
    @events.command(name="add")
    async def event_add(self, ctx, starts_in: TimeString, *, params):
        """Adds an event

        The syntax is:
        /event starts_in name
        /event starts_in name,description

        starts_in means in how much time the event will start since the moment of creation
        The time can be set using units such as 'd' for days, 'h' for hours, 'm' for minutes and 'd' for seconds.
        Examples: 1d20h5m, 1d30m, 1h40m, 40m
        """
        now = time.time()
        creator = ctx.message.author.id
        start = now + starts_in.seconds
        params = params.split(",", 1)
        name = single_line(clean_string(ctx, params[0]))
        event_description = ""
        if len(params) > 1:
            event_description = clean_string(ctx, params[1])

        c = userDatabase.cursor()
        try:
            c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
            result = c.fetchall()
            if len(result) > 1 and creator not in owner_ids + mod_ids:
                await ctx.send("You can only have two running events simultaneously. Delete or edit an active event")
                return

            guilds = self.bot.get_user_guilds(creator)
            # If message is via PM, but user only shares one server, we just consider that server
            if is_private(ctx.message.channel) and len(guilds) == 1:
                guild = guilds[0]
            # Not a private message, so we just take current guild
            elif not is_private(ctx.message.channel):
                guild = ctx.message.guild
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

            c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                      (creator, guild.id, start, name, event_description))
            event_id = c.lastrowid
            reply = "Event registered successfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*"
            await ctx.send(reply.format(name, starts_in.original, event_id))
        finally:
            userDatabase.commit()
            c.close()

    @event_add.error
    @checks.is_not_lite()
    async def event_add_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error))

    @events.command(name="editname")
    @checks.is_not_lite()
    async def event_edit_name(self, ctx, event_id: int, *, new_name):
        """Changes an event's name

        Only the creator of the event or mods can edit an event's name
        Only upcoming events can be edited"""
        c = userDatabase.cursor()
        now = time.time()
        new_name = single_line(clean_string(ctx, new_name))
        try:
            c.execute("SELECT creator, name FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
            event = c.fetchone()
            if not event:
                await ctx.send("There are no active events with that ID.")
                return
            if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids + owner_ids:
                await ctx.send("You can only edit your own events.")
                return
            await ctx.send("Do you want to change the name of **{0}**? `(yes/no)`".format(event["name"]))

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                answer = await self.bot.wait_for("message", timeout=30.0, check=check)
                if answer.content.lower() in ["yes", "y"]:
                    c.execute("UPDATE events SET name = ? WHERE id = ?", (new_name, event_id,))
                    await ctx.send("Your event was renamed successfully to **{0}**.".format(new_name))
                else:
                    await ctx.send("Ok, nevermind.")
            except asyncio.TimeoutError:
                await ctx.send("I will take your silence as a no...")
        finally:
            userDatabase.commit()
            c.close()

    @checks.is_not_lite()
    @events.command(name="editdesc", aliases=["editdescription"])
    async def event_edit_description(self, ctx, event_id: int, *, new_description):
        """Changes an event's description

        Only the creator of the event or mods can edit an event's description
        Only upcoming events can be edited"""
        c = userDatabase.cursor()
        now = time.time()
        new_description = clean_string(ctx, new_description)
        try:
            c.execute("SELECT creator FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
            event = c.fetchone()
            if not event:
                await ctx.send("There are no active events with that ID.")
                return
            if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids + owner_ids:
                await ctx.send("You can only edit your own events.")
                return
            await ctx.send("Do you want to change the description of **{0}**? `(yes/no)`")

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                answer = await self.bot.wait_for("message", timeout=60.0, check=check)
                if answer.content.lower() in ["yes", "y"]:
                    c.execute("UPDATE events SET description = ? WHERE id = ?", (new_description, event_id,))
                    await ctx.send(
                        "Your event's description was changed successfully to **{0}**.".format(new_description))
                else:
                    await ctx.send("Ok, nevermind.")
            except asyncio.TimeoutError:
                await ctx.send("I will take your silence as a no...")

        finally:
            userDatabase.commit()
            c.close()

    @checks.is_not_lite()
    @events.command(name="edittime", aliases=["editstart"])
    async def event_edit_time(self, ctx, event_id: int, starts_in: TimeString):
        """Changes an event's time

        Only the creator of the event or mods can edit an event's time
        Only upcoming events can be edited"""
        c = userDatabase.cursor()
        now = time.time()
        try:
            c.execute("SELECT creator, name FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
            event = c.fetchone()
            if not event:
                await ctx.send("There are no active events with that ID.")
                return
            if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids + owner_ids:
                await ctx.send("You can only edit your own events.")
                return
            await ctx.send("Do you want to change the start time of '**{0}**'? `(yes/no)`".format(event["name"]))

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                answer = await self.bot.wait_for("message", timeout=30.0, check=check)
                if answer.content.lower() in ["yes", "y"]:
                    c.execute("UPDATE events SET start = ? WHERE id = ?", (now + starts_in.seconds, event_id,))
                    await ctx.send(
                        "Your event's start time was changed successfully to **{0}**.".format(starts_in.original))
                else:
                    await ctx.send("Ok, nevermind.")
            except asyncio.TimeoutError:
                await ctx.send("I will take your silence as a no...")
        finally:
            userDatabase.commit()
            c.close()

    @checks.is_not_lite()
    @events.command(name="delete", aliases=["remove"])
    async def event_remove(self, ctx, event_id: int):
        """Deletes an event

        Only the creator of the event or mods can delete an event
        Only upcoming events can be edited"""
        c = userDatabase.cursor()
        now = time.time()
        try:
            c.execute("SELECT creator,name FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
            event = c.fetchone()
            if not event:
                await ctx.send("There are no active events with that ID.")
                return
            if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids + owner_ids:
                await ctx.send("You can only delete your own events.")
                return
            await ctx.send("Do you want to delete the event '**{0}**'? `(yes/no)`".format(event["name"]))

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                answer = await self.bot.wait_for("message", timeout=60.0, check=check)
                if answer.content.lower() in ["yes", "y"]:
                    c.execute("UPDATE events SET active = 0 WHERE id = ?", (event_id,))
                    await ctx.send("Your event was deleted successfully.")
                else:
                    await ctx.send("Ok, nevermind.")
            except asyncio.TimeoutError:
                await ctx.send("I will take your silence as a no...")
        finally:
            userDatabase.commit()
            c.close()

    @checks.is_not_lite()
    @events.command(name="make", aliases=["creator", "maker"])
    async def event_make(self, ctx):
        """Creates an event guiding you step by step

        Instead of using confusing parameters, commas and spaces, this commands has the self.bot ask you step by step."""

        def check(m):
            return m.channel == ctx.channel and m.author == ctx.author

        author = ctx.message.author
        creator = author.id
        now = time.time()
        c = userDatabase.cursor()
        try:
            c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
            event = c.fetchall()
            if len(event) > 1 and creator not in owner_ids + mod_ids:
                return
            await ctx.send("Let's create an event. What would you like the name to be?")

            try:
                name = await self.bot.wait_for("message", timeout=50.0, check=check)
                name = single_line(name.clean_content)
            except asyncio.TimeoutError:
                await ctx.send("...You took to long. Try the command again.")
                return

            await ctx.send("Alright, what description would you like the event to have? `(no/none = no description)`")

            try:
                event_description = await self.bot.wait_for("message", timeout=50.0, check=check)
                if event_description.content.lower().strip() in ["no", "none"]:
                    await ctx.send("No description then? Alright, now tell me the start time of the event from now. "
                                   "`e.g. 2d1h20m, 2d3h`")
                    event_description = ""
                else:
                    event_description = event_description.clean_content
                    await ctx.send("Alright, now tell me the start time of the event from now. `e.g. 2d1h20m, 2d3h`")
            except asyncio.TimeoutError:
                await ctx.send("...You took too long. Try the command again.")
                return

            starts_in = await self.bot.wait_for("message", timeout=50.0, check=check)
            if starts_in is None:
                await ctx.send("...You took too long. Try the command again.")
                return
            try:
                starts_in = TimeString(starts_in.content)
            except commands.BadArgument:
                await ctx.send("Invalid time. Try  the command again. `Time examples: 1h2m, 2d30m, 40m, 5h`")
                return

            guilds = self.bot.get_user_guilds(creator)
            # If message is via PM, but user only shares one server, we just consider that server
            if is_private(ctx.message.channel) and len(guilds) == 1:
                guild = guilds[0]
            # Not a private message, so we just take current server
            elif not is_private(ctx.message.channel):
                guild = ctx.message.guild
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

            now = time.time()
            c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                      (creator, guild.id, now + starts_in.seconds, name, event_description))
            event_id = c.lastrowid
            reply = "Event registered successfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*"
            await ctx.send(reply.format(name, starts_in.original, event_id))
        finally:
            userDatabase.commit()
            c.close()

    @checks.is_not_lite()
    @events.command(name="subscribe", aliases=["sub"])
    async def event_subscribe(self, ctx, event_id: int):
        """Subscribe to receive a PM when an event is happening."""
        c = userDatabase.cursor()
        author = ctx.message.author
        now = time.time()
        try:
            # If this is used on a PM, show events for all shared servers
            if is_private(ctx.message.channel):
                guilds = self.bot.get_user_guilds(ctx.message.author.id)
            else:
                guilds = [ctx.message.guild]
            guild_ids = [s.id for s in guilds]
            placeholders = ", ".join("?" for s in guilds)
            c.execute("SELECT * FROM events "
                      "WHERE id = {0} AND active = 1 AND start > {1} AND server IN ({2})".format(event_id, now,
                                                                                                 placeholders)
                      , tuple(guild_ids))
            event = c.fetchone()
            if event is None:
                await ctx.send("There are no active events with that id.")
                return

            c.execute("SELECT * FROM event_subscribers WHERE event_id = ? AND user_id = ?", (event_id, author.id))
            subscription = c.fetchone()
            if subscription is not None:
                await ctx.send("You're already subscribed to this event.")
                return
            await ctx.send("Do you want to subscribe to **{0}**? `(yes/no)`".format(event["name"]))

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                reply = await self.bot.wait_for("message", timeout=30.0, check=check)
                if reply.content.lower() in ["yes", "y"]:
                    c.execute("INSERT INTO event_subscribers (event_id, user_id) VALUES(?,?)", (event_id, author.id))
                    await ctx.send(
                        "You have subscribed successfully to this event. I'll let you know when it's happening.")
                else:
                    await ctx.send("No? Alright then...")
            except asyncio.TimeoutError:
                await ctx.send("No answer? Nevermind then.")
        finally:
            c.close()
            userDatabase.commit()

    @event_edit_name.error
    @event_edit_description.error
    @event_edit_time.error
    @event_remove.error
    @event_subscribe.error
    async def event_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("Invalid arguments used. `Type /help {0}`".format(ctx.invoked_subcommand))
        elif isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send("You're missing a required argument. `Type /help {0}`".format(ctx.invoked_subcommand))


def setup(bot):
    bot.add_cog(General(bot))
