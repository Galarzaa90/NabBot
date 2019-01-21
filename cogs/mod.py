import asyncio
import logging
from typing import Union

import discord
from discord.ext import commands

from cogs.utils import converter
from nabbot import NabBot
from .utils import checks, config, safe_delete_message
from .utils.context import NabCtx
from .utils.database import get_server_property
from .utils.errors import CannotPaginate
from .utils.pages import Pages

log = logging.getLogger("nabbot")


class LazyEntry:
    __slots__ = ('entity_id', 'guild', '_cache')

    def __init__(self, guild, entity_id):
        self.entity_id = entity_id
        self.guild = guild
        self._cache = None

    def __str__(self):
        if self._cache:
            return self._cache

        e = self.entity_id
        g = self.guild
        resolved = g.get_channel(e) or g.get_member(e)
        if resolved is None:
            self._cache = f'<Not Found: {e}>'
        else:
            self._cache = resolved.mention
        return self._cache


class Mod:
    """Moderating related commands."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def __global_check_once(self, ctx: NabCtx):
        if ctx.guild is None:
            return True
        if await checks.is_owner(ctx):
            return True

        return await self.is_ignored(ctx.pool, ctx)

    # region Commands
    @commands.guild_only()
    @checks.channel_mod_only()
    @commands.command()
    async def cleanup(self, ctx: NabCtx, limit: int = 50):
        """Cleans the channel from bot commands.

        If the bot has `Manage Messages` permission, it will also delete command invocation messages."""
        count = 0
        prefixes = await get_server_property(ctx.pool, ctx.guild.id, "prefixes", default=config.command_prefix)
        # Also skip death and level up messages from cleanup
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

        await ctx.success(f"Deleted {count:,} messages.", delete_after=20)

    @checks.server_mod_only()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def ignore(self, ctx: NabCtx, *entries: converter.ChannelOrMember):
        """Makes the bot ignore a channel or user.

        Commands cannot be used in ignored channels or by ignored users.

        The command accepts a list of names, ids or mentions of users or channels.
        If the command is used with no parameters, it ignores the current channel.

        Ignores are bypassed by users with the `Manage Server` permission."""
        if len(entries) == 0:
            entries = [ctx.channel]
        if len(entries) == 1:
            entry: Union[discord.Member, discord.TextChannel] = entries[0]
            query = "INSERT INTO ignored_entry(server_id, entry_id) VALUES($1, $2) ON CONFLICT DO NOTHING RETURNING 1"
            ret = await ctx.pool.fetchval(query, ctx.guild.id, entry.id)
            rep = entry.mention if isinstance(entry, discord.TextChannel) else entry.display_name
            if ret:
                return await ctx.success(f"I'm now ignoring **{rep}**")
            return await ctx.error(f"{rep} is already ignored.")

        inserted = await self.bulk_ignore(ctx, entries)
        if inserted:
            if inserted != len(entries):
                await ctx.success(f"{inserted} entries are now ignored. The rest was already ignored.")
            else:
                await ctx.success(f"All {inserted} entries are now ignored.")
        else:
            await ctx.error("No entries were ignored. They were all already ignored.")

    @checks.server_mod_only()
    @ignore.command(name="list")
    async def ignore_list(self, ctx: NabCtx):
        """Shows a list of ignored channels and users."""
        query = "SELECT entry_id FROM ignored_entry WHERE server_id = $1"
        rows = await ctx.pool.fetch(query, ctx.guild.id)

        entries = [LazyEntry(ctx.guild, e[0]) for e in rows]
        if not entries:
            await ctx.send("There are no ignored entries in this server.")
            return
        pages = Pages(ctx, entries=entries)
        pages.embed.title = "Ignored entries"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command()
    @checks.channel_mod_somewhere()
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
            await safe_delete_message(ctx.message)
            await ctx.message.delete()
            await ctx.channel.send(message)

    @commands.guild_only()
    @checks.channel_mod_only()
    @commands.command()
    async def unignore(self, ctx: NabCtx, *entries: converter.ChannelOrMember):
        """Removes a channel or user from the ignored list.

        If no parameter is provided, the current channel will be unignored.

        If the command is used with no parameters, it unignores the current channel."""
        if len(entries) == 0:
            query = "DELETE FROM ignored_entry WHERE server_id=$1 AND entry_id=$2 RETURNING true"
            res = await ctx.pool.fetchval(query, ctx.guild.id, ctx.channel.id)
            if res:
                return await ctx.success(f"{ctx.channel.mention} is no longer ignored.")
            return await ctx.error(f"{ctx.channel.mention} wasn't ignored.")
        query = "DELETE FROM ignored_entry WHERE server_id=$1 AND entry_id = ANY($2::bigint[]) RETURNING entry_id"
        # noinspection PyUnresolvedReferences
        entries = [c.id for c in entries]
        rows = await ctx.pool.fetch(query, ctx.guild.id, entries)
        if rows:
            return await ctx.success(f"{len(rows)} are now unignored.")
        await ctx.error("No entries were unignored.")

    @checks.channel_mod_only()
    @checks.tracking_world_only()
    @commands.command()
    async def unregistered(self, ctx: NabCtx):
        """Shows a list of users with no registered characters."""
        entries = []
        if ctx.world is None:
            await ctx.send("This server is not tracking any worlds.")
            return

        results = await ctx.pool.fetch('SELECT user_id FROM "character" WHERE world = $1 GROUP BY user_id', ctx.world)
        # Flatten list
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
    # endregion

    @classmethod
    async def is_ignored(cls, conn, ctx: NabCtx):
        """Checks if the current context is ignored.

        A context could be ignored because either the channel or the user are in the ignored list."""
        query = "SELECT True FROM ingored_entry WHERE guild_id=$1 AND (entry_id=$2 OR entry_id=$3);"
        return await conn.fetchrow(query, ctx.guild.id, ctx.channel.id, ctx.author.id)

    @classmethod
    async def bulk_ignore(cls, ctx: NabCtx, entries):
        async with ctx.pool.acquire() as conn:
            async with conn.transaction():
                query = "SELECT entry_id FROM ignored_entry WHERE server_id=$1;"
                records = await conn.fetch(query, ctx.guild.id)

                # Removing duplicates
                current_entries = {r[0] for r in records}
                records = [(ctx.guild.id, e.id) for e in entries if e.id not in current_entries]

                # do a bulk COPY
                await conn.copy_records_to_table('ignored_entry', columns=['server_id', 'entry_id'], records=records)
                return len(records)


def setup(bot):
    bot.add_cog(Mod(bot))
