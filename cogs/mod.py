#  Copyright 2019 Allan Galarza
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import logging
from typing import Union

import discord
from discord.ext import commands

from cogs import utils
from cogs.utils import converter
from cogs.utils.tibia import get_guild, get_voc_emoji, get_voc_abb
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


class Mod(commands.Cog, utils.CogUtils):
    """Moderating related commands."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    def cog_unload(self):
        log.info(f"{self.tag} Unloading cog")

    async def bot_check_once(self, ctx: NabCtx):
        """Checks if the current channel or user is ignored.

        Bot owners and guild managers can bypass this.
        """
        if ctx.guild is None:
            return True
        if await checks.is_owner(ctx):
            return True
        if ctx.author_permissions.manage_guild:
            return True

        return not await self.is_ignored(ctx.pool, ctx)

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
    @commands.guild_only()
    @checks.has_permissions(**{"manage_messages": True})
    async def makesay(self, ctx: NabCtx, *, message: str):
        """Makes the bot say a message.

        If the user using the command doesn't have mention everyone permissions, the message will be cleaned of
        mass mentions.
        """
        if not ctx.bot_permissions.manage_messages:
            return await ctx.error("I need `Manage Messages` permissions here to use the command.")
        # If bot or user don't have mention everyone permissions, clean @everyone and @here
        if not ctx.bot_permissions.mention_everyone or not ctx.author_permissions.mention_everyone:
            message = message.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

        await safe_delete_message(ctx.message)
        await ctx.send(message)

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
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def unregistered(self, ctx: NabCtx):
        """Shows a list of users with no registered characters."""
        entries = []
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

    @checks.channel_mod_only()
    @checks.tracking_world_only()
    @unregistered.command(name="guild")
    async def unregistered_guild(self, ctx: NabCtx, *, name: str):
        """Shows a list of unregistered guild members.

        Unregistered guild members can be either characters not registered to NabBot or
        registered to users not in the server."""
        guild = await get_guild(name)
        if guild is None:
            return await ctx.error("There's no guild with that name.")
        if guild.world != ctx.world:
            return await ctx.error(f"**{guild.name}** is not in **{ctx.world}**")

        names = [m.name for m in guild.members]
        registered = await ctx.pool.fetch("""SELECT name FROM "character" T0
                                             INNER JOIN user_server T1 ON T0.user_id = T1.user_id
                                             WHERE name = any($1) AND server_id = $2""", names, ctx.guild.id)
        registered_names = [m['name'] for m in registered]

        entries = []
        for member in guild.members:
            if member.name in registered_names:
                continue
            emoji = get_voc_emoji(member.vocation.value)
            voc_abb = get_voc_abb(member.vocation.value)
            entries.append(f'{member.rank} — **{member.name}** (Lvl {member.level} {voc_abb} {emoji})')
        if len(entries) == 0:
            await ctx.send("There are no unregistered users.")
            return

        pages = Pages(ctx, entries=entries, per_page=10)
        pages.embed.set_author(name=f"Unregistered members from {guild.name}", icon_url=guild.logo_url)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    # endregion

    @classmethod
    async def is_ignored(cls, conn, ctx: NabCtx):
        """Checks if the current context is ignored.

        A context could be ignored because either the channel or the user are in the ignored list."""
        query = "SELECT True FROM ignored_entry WHERE server_id=$1 AND (entry_id=$2 OR entry_id=$3);"
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
