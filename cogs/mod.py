import asyncio
from contextlib import closing
from typing import List, Dict

import discord
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.database import userDatabase, tracked_worlds
from utils.discord import is_private
from utils.paginator import Paginator, CannotPaginate


class Mod:
    """Commands for bot/server moderators."""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.ignored = {}
        self.reload_ignored()

    def __global_check(self, ctx):
        return is_private(ctx.channel) or \
               ctx.channel.id not in self.ignored.get(ctx.guild.id, []) or checks.is_owner_check(ctx) \
               or checks.check_guild_permissions(ctx, {'manage_channels': True})

    # Admin only commands #
    @commands.command()
    @checks.is_mod()
    async def makesay(self, ctx: discord.ext.commands.Context, *, message: str):
        """Makes the bot say a message
        If it's used directly on a text channel, the bot will delete the command's message and repeat it itself

        If it's used on a private message, the bot will ask on which channel he should say the message."""
        if is_private(ctx.message.channel):
            description_list = []
            channel_list = []
            prev_server = None
            num = 1
            for server in self.bot.guilds:
                author = self.bot.get_member(ctx.message.author.id, server)
                bot_member = self.bot.get_member(self.bot.user.id, server)
                # Skip servers where the command user is not in
                if author is None:
                    continue
                # Check for every channel
                for channel in server.text_channels:
                    author_permissions = author.permissions_in(channel)  # type: discord.Permissions
                    bot_permissions = bot_member.permissions_in(channel)  # type: discord.Permissions
                    # Check if both the author and the bot have permissions to send messages and add channel to list
                    if (author_permissions.send_messages and bot_permissions.send_messages) and \
                            (ctx.message.author.id in config.owner_ids or author_permissions.administrator):
                        separator = ""
                        if prev_server is not server:
                            separator = "---------------\n\t"
                        description_list.append("{2}{3}: **#{0}** in **{1}**".format(channel.name, server.name,
                                                                                     separator, num))
                        channel_list.append(channel)
                        prev_server = server
                        num += 1
            if len(description_list) < 1:
                await ctx.send("We don't have channels in common with permissions.")
                return
            await ctx.send("Choose a channel for me to send your message (number only): \n\t0: *Cancel*\n\t" +
                                "\n\t".join(["{0}".format(i) for i in description_list]))

            def check(m):
                return m.author == ctx.message.author and m.channel == ctx.message.channel
            try:
                answer = await self.bot.wait_for("message",timeout=60.0, check=check)
                answer = int(answer.content)
                if answer == 0:
                    await ctx.send("Changed your mind? Typical human.")
                    return
                await channel_list[answer-1].send(message)
                await ctx.send("Message sent on {0} ({1})".format(channel_list[answer-1].mention,
                                                                       channel_list[answer-1].guild))
            except IndexError:
                await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
            except ValueError:
                await ctx.send("That's not a valid answer!")
            except asyncio.TimeoutError:
                await ctx.send("... are you there? Fine, nevermind!")
        else:
            await ctx.message.delete()
            await ctx.message.channel.send(message)

    @commands.command()
    @checks.is_mod()
    @commands.guild_only()
    async def unregistered(self, ctx):
        """Check which users are currently not registered."""

        world = tracked_worlds.get(ctx.guild.id, None)
        entries = []
        if world is None:
            await ctx.send("This server is not tracking any worlds.")
            return

        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT user_id FROM chars WHERE world LIKE ? GROUP BY user_id", (world,))
            result = c.fetchall()
            if len(result) <= 0:
                await ctx.send("There are no registered characters.")
                return
            users = [i["user_id"] for i in result]
        for member in ctx.guild.members:  # type: discord.Member
            if member.id == ctx.me.id:
                continue
            if member.id not in users:
                entries.append(f"@**{member.display_name}** \u2014 Joined on: **{member.joined_at.date()}**")
        if len(entries) == 0:
            await ctx.send("There are no unregistered users.")
            return

        pages = Paginator(self.bot, message=ctx.message, entries=entries, title="Unregistered members", per_page=10)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @checks.is_mod()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def ignore(self, ctx, *, channel: discord.TextChannel = None):
        """Makes the bot ignore a channel

        Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

        If the parameter is used with no parameters, it ignores the current channel.

        Note that server administrators can bypass this."""
        if channel is None:
            channel = ctx.channel

        if channel.id in self.ignored.get(ctx.guild.id, []):
            await ctx.send(f"{channel.mention} is already ignored.")
            return

        with userDatabase:
            userDatabase.execute("INSERT INTO ignored_channels(server_id, channel_id) VALUES(?, ?)",
                                 (ctx.guild.id, channel.id))
            await ctx.send(f"{channel.mention} is now ignored.")
            self.reload_ignored()

    @commands.guild_only()
    @checks.is_mod()
    @ignore.command(name="list")
    async def ignore_list(self, ctx):
        """Shows a list of ignored channels"""
        entries = [ctx.guild.get_channel(c).name for c in self.ignored.get(ctx.guild.id, []) if ctx.guild.get_channel(c) is not None]
        if not entries:
            await ctx.send("There are no ignored channels in this server.")
            return
        pages = Paginator(self.bot, message=ctx.message, entries=entries, title="Ignored channels")
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @checks.is_mod()
    @commands.command()
    async def unignore(self, ctx, *, channel: discord.TextChannel = None):
        """Makes the bot unignore a channel

        Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

        If the parameter is used with no parameters, it unignores the current channel."""
        if channel is None:
            channel = ctx.channel

        if channel.id not in self.ignored.get(ctx.guild.id, []):
            await ctx.send(f"{channel.mention} is not ignored.")
            return

        with userDatabase:
            userDatabase.execute("DELETE FROM ignored_channels WHERE channel_id = ?", (channel.id,))
            await ctx.send(f"{channel.mention} is not ignored anymore.")
            self.reload_ignored()

    @ignore.error
    @unignore.error
    async def ignore_error(self, ctx, error):
        if isinstance(error, commands.errors.BadArgument):
            await ctx.send(error)

    def reload_ignored(self):
        """Refresh the world list from the database

        This is used to avoid reading the database everytime the world list is needed.
        A global variable holding the world list is loaded on startup and refreshed only when worlds are modified"""
        c = userDatabase.cursor()
        ignored_dict_temp = {}  # type: Dict[int, List[int]]
        try:
            c.execute("SELECT server_id, channel_id FROM ignored_channels")
            result = c.fetchall()  # type: Dict
            if len(result) > 0:
                for row in result:
                    if not ignored_dict_temp.get(row["server_id"]):
                        ignored_dict_temp[row["server_id"]] = []

                    ignored_dict_temp[row["server_id"]].append(row["channel_id"])

            self.ignored.clear()
            self.ignored.update(ignored_dict_temp)
        finally:
            c.close()


def setup(bot):
    bot.add_cog(Mod(bot))
