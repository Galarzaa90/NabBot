import asyncio
from typing import List, Dict

import discord
from discord.ext import commands

from nabbot import NabBot
from .utils import checks, config
from .utils.context import NabCtx
from .utils.database import get_server_property
from .utils.pages import Pages, CannotPaginate


class Mod:
    """Commands server moderators."""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.ignored = {}
        self.bot.loop.run_until_complete(self.reload_ignored())

    def __global_check(self, ctx: NabCtx):
        return ctx.is_private or ctx.channel.id not in self.ignored.get(ctx.guild.id, []) or checks.is_owner_check(ctx) \
               or checks.check_guild_permissions(ctx, {'manage_channels': True})

    # Commands
    @commands.guild_only()
    @checks.is_channel_mod()
    @commands.command()
    async def cleanup(self, ctx: NabCtx, limit: int=50):
        """Cleans the channel from bot commands.

        If the bot has `Manage Messages` permission, it will also delete command invocation messages."""
        count = 0
        prefixes = await get_server_property(ctx.pool, ctx.guild.id, "prefixes", default=config.command_prefix)
        # Also skip death and levelup messages from cleanup
        announce_prefix = (config.levelup_emoji, config.death_emoji, config.pvpdeath_emoji)
        if ctx.bot_permissions.manage_messages:
            def check(m: discord.Message):
                return (m.author == ctx.me and not m.content.startswith(announce_prefix)) or \
                       m.content.startswith(tuple(prefixes))

            deleted = await ctx.channel.purge(limit=limit, check=check)
            count = len(deleted)
        else:
            with ctx.typing():
                async for msg in ctx.channel.history(limit=limit):
                    if msg.author == ctx.me:
                        await msg.delete()
                        count += 1
        if not count:
            return await ctx.send("There are no messages to clean.", delete_after=10)

        await ctx.send(f"{ctx.tick()} Deleted {count:,} messages.", delete_after=20)

    @commands.guild_only()
    @checks.is_channel_mod()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def ignore(self, ctx: NabCtx, *, channel: discord.TextChannel = None):
        """Makes the bot ignore a channel.

        Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

        If the command   is used with no parameters, it ignores the current channel.

        Note that server administrators can bypass this."""
        if channel is None:
            channel = ctx.channel

        if channel.id in self.ignored.get(ctx.guild.id, []):
            await ctx.send(f"{channel.mention} is already ignored.")
            return

        await ctx.pool.execute("INSERT INTO channel_ignored(server_id, channel_id) VALUES($1, $2)",
                               ctx.guild.id, channel.id)
        await ctx.send(f"{channel.mention} is now ignored.")
        await self.reload_ignored()

    @commands.guild_only()
    @checks.is_channel_mod()
    @ignore.command(name="list")
    async def ignore_list(self, ctx: NabCtx):
        """Shows a list of ignored channels."""
        entries = [ctx.guild.get_channel(c).name for c in self.ignored.get(ctx.guild.id, []) if ctx.guild.get_channel(c) is not None]
        if not entries:
            await ctx.send("There are no ignored channels in this server.")
            return
        pages = Pages(ctx, entries=entries)
        pages.embed.title = "Ignored channels"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command()
    @checks.is_channel_mod_somewhere()
    async def makesay(self, ctx: NabCtx, *, message: str):
        """Makes the bot say a message.

        If it's used directly on a text channel, the bot will delete the command's message and repeat it itself.
        Note that deleting the message requires `Manage Messages` permissions in the channel.

        If it's used on a private message, the bot will ask on which channel he should say the message.
        Each channel in the list is numerated, by choosing a number, the message will be sent in the chosen channel.
        You can only send messages on channels where you have `Manage Channel` permissions.
        """
        if ctx.is_private:
            description_list = []
            channel_list = []
            prev_server = None
            num = 1
            for server in self.bot.guilds:
                author = server.get_member(ctx.author.id)
                bot_member = self.bot.get_member(self.bot.user.id, server)
                # Skip servers where the command user is not in
                if author is None:
                    continue
                # Check for every channel
                for channel in server.text_channels:
                    author_permissions = author.permissions_in(channel)
                    bot_permissions = bot_member.permissions_in(channel)
                    # Check if both the author and the bot have permissions to send messages and add channel to list
                    if author_permissions.send_messages and bot_permissions.send_messages \
                            and author_permissions.manage_channels:
                        separator = ""
                        if prev_server is not server:
                            separator = "---------------\n\t"
                        description_list.append("{2}{3}: **#{0}** in **{1}**".format(channel.name, server.name,
                                                                                     separator, num))
                        channel_list.append(channel)
                        prev_server = server
                        num += 1
            if len(description_list) < 1:
                await ctx.send("We don't have any channels where we both can send messages and that you manage.")
                return
            await ctx.send("Choose a channel for me to send your message (number only): \n\t0: *Cancel*\n\t" +
                           "\n\t".join(["{0}".format(i) for i in description_list]))

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            try:
                answer = await self.bot.wait_for("message", timeout=60.0, check=check)
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
            if not ctx.bot_permissions.manage_messages:
                return await ctx.send(f"{ctx.tick(False)} I need `Manage Messages` permission to use this command.")
            if not ctx.author_permissions.manage_channels:
                return await ctx.send(f"{ctx.tick(False)} You need `Manage Channel` permission to use this command.")
            await ctx.message.delete()
            await ctx.channel.send(message)

    @commands.guild_only()
    @checks.is_channel_mod()
    @commands.command()
    async def unignore(self, ctx: NabCtx, *, channel: discord.TextChannel = None):
        """Unignores a channel.

        If no channel is provided, the current channel will be unignored.

        Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

        If the command is used with no parameters, it unignores the current channel."""
        if channel is None:
            channel = ctx.channel

        if channel.id not in self.ignored.get(ctx.guild.id, []):
            await ctx.send(f"{channel.mention} is not ignored.")
            return

        await ctx.pool.execute("DELETE FROM channel_ignored WHERE channel_id = $1", channel.id)
        await ctx.send(f"{channel.mention} is not ignored anymore.")
        await self.reload_ignored()

    @checks.is_channel_mod()
    @checks.is_tracking_world()
    @commands.command()
    async def unregistered(self, ctx: NabCtx):
        """Shows a list of users with no registered characters."""
        entries = []
        if ctx.world is None:
            await ctx.send("This server is not tracking any worlds.")
            return

        results = await ctx.pool.fetch('SELECT user_id FROM "character" WHERE world = $1 GROUP BY user_id', ctx.world)
        if len(results) <= 0:
            await ctx.send("There are no unregistered users.")
            return
        users = [i["user_id"] for i in results]
        for member in ctx.guild.members:  # type: discord.Member
            # Skip bots
            if member.bot:
                continue
            if member.id not in users:
                entries.append(f"@**{member.display_name}** \u2014 Joined: **{member.joined_at.date()}**")
        if len(entries) == 0:
            await ctx.send("There are no unregistered users.")
            return

        pages = Pages(ctx, entries=entries, per_page=10)
        pages.embed.title = "Unregistered members"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    async def reload_ignored(self):
        """Refresh the world list from the database

        This is used to avoid reading the database every time the world list is needed.
        A global variable holding the world list is loaded on startup and refreshed only when worlds are modified"""
        ignored_dict_temp: Dict[int, List[int]] = {}
        result = await self.bot.pool.fetch("SELECT server_id, channel_id FROM channel_ignored")
        if len(result) > 0:
            for row in result:
                if not ignored_dict_temp.get(row["server_id"]):
                    ignored_dict_temp[row["server_id"]] = []
                ignored_dict_temp[row["server_id"]].append(row["channel_id"])

        self.ignored.clear()
        self.ignored.update(ignored_dict_temp)


def setup(bot):
    bot.add_cog(Mod(bot))
