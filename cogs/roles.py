import asyncio
from typing import List

import discord
from discord.ext import commands

from cogs.utils.database import get_affected_count
from nabbot import NabBot
from .utils import checks
from .utils.context import NabCtx
from .utils.converter import InsensitiveRole
from .utils import log, get_user_avatar
from .utils.pages import CannotPaginate, Pages
from .utils.tibia import get_guild, NetworkError


class Roles:
    """Commands related to role management."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def __error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)
        if isinstance(error, commands.CommandOnCooldown):

            await ctx.send(f"You're using this too much! Try again in {error.retry_after:.0f} seconds.")

    async def on_guild_role_delete(self, role: discord.Role):
        """Called when a role is deleted.

        Removes joinable groups from the database when the role is deleted.
        """
        async with self.bot.pool.acquire() as conn:
            joinable_result = await conn.execute("DELETE FROM role_joinable WHERE role_id = $1", role.id)
            auto_result = await conn.execute("DELETE FROM role_auto WHERE role_id = $1", role.id)
            deleted_joinable = get_affected_count(joinable_result)
            deleted_auto = get_affected_count(auto_result)
            if deleted_auto:
                self.bot.dispatch("role_auto_deleted", role)
            if deleted_joinable:
                self.bot.dispatch("role_joinable_deleted", role)

    # Todo: Requires optimization
    async def on_character_change(self, user_id: int):
        """Event occurs everytime a character changes guild or owner.

        Updates automatic roles accordingly."""
        try:
            async with self.bot.pool.acquire() as conn:
                guilds_raw = await conn.fetch('SELECT guild, world FROM "character" WHERE user_id = $1', user_id)
                rules_raw = await conn.fetch("SELECT server_id, role_id, rule FROM role_auto ORDER BY server_id")
            # Flatten list of guilds
            guilds = set(g['guild'] for g in guilds_raw)
            worlds = set(g['world'] for g in guilds_raw)

            # Flatten rules
            rules = {}
            for rule in rules_raw:
                server_id = rule["server_id"]
                if server_id not in rules:
                    rules[rule["server_id"]] = []
                rules[server_id].append((rule["role_id"], rule["rule"]))

            for server_id, rules in rules.items():
                server: discord.Guild = self.bot.get_guild(server_id)
                if server is None:
                    continue
                member: discord.Member = server.get_member(user_id)
                if member is None:
                    continue

                all_roles = set()
                to_add = set()
                for role_id, char_guild in rules:
                    role: discord.Role = server.get_role(role_id)
                    if role is None:
                        continue
                    all_roles.add(role)
                    if (char_guild == "*" and self.bot.tracked_worlds.get(server_id) in worlds) or char_guild in guilds:
                        to_add.add(role)
                to_remove = all_roles-to_add
                try:
                    before_roles = set(member.roles)
                    await member.remove_roles(*to_remove, reason="Automatic roles")
                    await member.add_roles(*to_add, reason="Automatic roles")
                    # A small delay is needed so member.roles is updated with the added possible added roles.
                    await asyncio.sleep(0.15)
                    after_roles = set(member.roles)

                    new_roles = after_roles-before_roles
                    removed_roles = before_roles-after_roles
                    if new_roles or removed_roles:
                        embed = discord.Embed(colour=discord.Colour.dark_blue(), title="Autorole changes")
                        embed.set_author(name="{0.name}#{0.discriminator} (ID: {0.id})".format(member),
                                         icon_url=get_user_avatar(member))
                        if new_roles:
                            embed.add_field(name="Added roles", value=", ".join(r.mention for r in new_roles))
                        if removed_roles:
                            embed.add_field(name="Removed roles", value=", ".join(r.mention for r in removed_roles))
                        await self.bot.send_log_message(server, embed=embed)
                except discord.HTTPException:
                    pass
        except Exception:
            log.exception("Event: character_change")

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @commands.group(case_insensitive=True)
    async def autorole(self, ctx):
        """Autorole commands.

        All the subcommands require having `Manage Roles` permission."""
        pass

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @autorole.command(name="add", usage="<role> <guild>")
    async def autorole_add(self, ctx: NabCtx, _role: InsensitiveRole, *, guild: str):
        """Creates a new autorole rule.

        Rules consist of a role and a guild name.
        When a user has a registered character in said guild, they receive the role.
        If they stop having a character in the guild, the role is removed.

        If `*` is used as a guild. It means that the role will be given for having any assigned character.

        Role names, role mentions or role ids are allowed. Role names with multiple words must be quoted.
        Note that current members will be updated until their characters or guilds change."""
        role: discord.Role = _role
        name = guild.replace("\"", "")
        if guild != "*":
            try:
                guild = await get_guild(name)
                if guild is None:
                    await ctx.send(f"There's no guild named `{name}`")
                    return
                name = guild.name
            except NetworkError:
                await ctx.send("I'm having network issues, try again later.")
                return
        result = await ctx.pool.fetchrow("SELECT true FROM role_auto WHERE role_id = $1 and rule = $2", role.id, name)
        if result:
            await ctx.send(f"{ctx.tick(False)} Autorole rule already exists.")
            return

        # Can't make autorole rule for role higher than the owner's top role
        top_role: discord.Role = ctx.author.top_role
        if role >= top_role:
            await ctx.send(f"{ctx.tick(False)} You can't create an automatic role with a role higher or equals "
                           f"than your highest.")
            return

        if name != "*":
            msg = await ctx.send(f"Members of guild `{name}` will automatically receive the `{role.name}` role. "
                                 f"Is this correct?")
        else:
            msg = await ctx.send(f"All users with registered characters will automatically receive the `{role.name}` "
                                 f"role. Is this correct?")
        confirm = await ctx.react_confirm(msg, delete_after=True, timeout=60)
        if not confirm:
            return

        await ctx.pool.execute("INSERT INTO role_auto(server_id, role_id, rule) VALUES($1, $2, $3)",
                               ctx.guild.id, role.id, name)
        await ctx.send(f"{ctx.tick()} Autorole rule created.")

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @autorole.command(name="list", aliases=["rules"])
    async def autorole_list(self, ctx: NabCtx):
        """Shows a list of autorole rules."""
        rules = await ctx.pool.fetch("SELECT role_id, rule FROM role_auto WHERE server_id = $1", ctx.guild.id)
        if not rules:
            await ctx.send(f"{ctx.tick(False)} This server has no autorole rules.")
            return

        entries = []
        for role_id, guild in rules:
            role: discord.Role = discord.utils.get(ctx.guild.roles, id=role_id)
            if role is None:
                continue
            entries.append(f"{role.mention} — `{guild}`")

        if not entries:
            await ctx.send(f"{ctx.tick(False)} This server has no autorole rules.")
            return

        per_page = 20 if await ctx.is_long() else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = "Autorole rules"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @commands.cooldown(1, 3600, commands.BucketType.guild)
    @autorole.command(name="refresh")
    async def autorole_refresh(self, ctx: NabCtx):
        """Triggers a refresh on all members.

        This will apply existing rules to all members.
        Note that guild changes from members that haven't been online won't be detected.
        Deleted rules won't have any effect.

        This command can only be used once per server every hour.
        """
        msg = await ctx.send("This will make me check the guilds of all registered characters to apply existing rules."
                             "\nNote that character with outdated information won't be updated until they are online "
                             "again or checked using `whois`\nAre you sure you want this?.")
        confirm = await ctx.react_confirm(msg, timeout=60, delete_after=True)
        if not confirm:
            ctx.command.reset_cooldown(ctx)
            return
        msg: discord.Message = await ctx.send("Dispatching events...")
        for member in ctx.guild.members:
            self.bot.dispatch("character_change", member.id)
        try:
            await msg.edit(content=f"{ctx.tick()} Refresh done, roles will be updated shortly.")
        except discord.HTTPException:
            await ctx.send(f"{ctx.tick()} Refresh done, roles will be updated shortly.")

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @autorole.command(name="remove", aliases=["delete"])
    async def autorole_remove(self, ctx: NabCtx, role: InsensitiveRole, *, guild: str):
        """Removes an autorole rule.

        Role names, mentions and ids are accepted. Role names with multiple words need to be quoted.

        Note that members that currently have the role won't be affected."""
        group: discord.Role = role
        guild = guild.replace("\"", "")
        exists = await ctx.pool.fetchval("SELECT true FROM role_auto WHERE role_id = $1 AND lower(rule) = $2",
                                         group.id, guild.lower())
        if not exists:
            await ctx.send(f"{ctx.tick(False)} That rule doesn't exist.")
            return

        # Can't modify role higher than the owner's top role
        top_role: discord.Role = ctx.author.top_role
        if group >= top_role:
            await ctx.send(f"{ctx.tick(False)} You can't delete a role rule for a role higher than yours.")
            return

        await ctx.send(f"{ctx.tick()} Auto role rule removed. "
                       f"Note that the role won't be removed from current members.")
        await ctx.pool.execute("DELETE FROM role_auto WHERE role_id = $1 AND lower(rule) = $2", group.id, guild.lower())

    @commands.guild_only()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def group(self, ctx: NabCtx, *, _group: InsensitiveRole):
        """Joins or leaves a group (role).

        If you're not in the group, you will be added.
        If you're already in the group, you will be removed.

        To see a list of joinable groups, use `group list`"""
        group: discord.Role = _group
        exists = await ctx.pool.fetchval("SELECT true FROM role_joinable WHERE role_id = $1", group.id)
        if not exists:
            await ctx.send(f"{ctx.tick(False)} Group `{group.name}` doesn't exists.")
            return

        # Check if user already has the role
        member_role = discord.utils.get(ctx.author.roles, id=group.id)

        try:
            if member_role is None:
                await ctx.author.add_roles(group, reason="Joined group")
            else:
                await ctx.author.remove_roles(member_role, reason="Left group")
        except discord.Forbidden:
            await ctx.send(f"{ctx.tick(False)} I need `Manage Roles` to manage groups.")
        except discord.HTTPException:
            await ctx.send(f"{ctx.tick(False)} Something went wrong. Try again later.")
        else:
            if member_role is None:
                await ctx.send(f"{ctx.tick(True)} Joined `{group.name}`.")
            else:
                await ctx.send(f"{ctx.tick(True)} You left `{group.name}`.")

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @group.command(name="add")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def group_add(self, ctx: NabCtx, *, name: str):
        """Creates a new group for members to join.

        The group can be a new role that will be created with this command.
        If the name matches an existent role, that role will become joinable.

        You need `Manage Roles` permissions to use this command."""
        name = name.replace("\"", "")
        forbidden = ["add", "remove", "delete", "list"]
        converter = InsensitiveRole()
        try:
            role = await converter.convert(ctx, name)
        except commands.BadArgument:
            try:
                if name.lower() in forbidden:
                    raise discord.InvalidArgument()
                role = await ctx.guild.create_role(name=name, reason="Created joinable role")
            except discord.Forbidden:
                await ctx.send(f"{ctx.tick(False)} I need `Manage Roles` permission to create a group.")
                return
            except discord.InvalidArgument:
                await ctx.send(f"{ctx.tick(False)} Invalid group name.")
                return

        exists = await ctx.pool.fetchval("SELECT true FROM role_joinable WHERE role_id = $1", role.id)
        if exists:
            await ctx.send(f"{ctx.tick(False)} Group `{role.name}` already exists.")
            return

        # Can't make joinable group a role higher than the owner's top role
        top_role: discord.Role = ctx.author.top_role
        if role >= top_role:
            await ctx.send(f"{ctx.tick(False)} You can't make a group with a role higher or equals than your highest.")
            return

        await ctx.pool.execute("INSERT INTO role_joinable(server_id, role_id) VALUES($1, $2)", ctx.guild.id, role.id)
        await ctx.send(f"{ctx.tick()} Group `{role.name}` created successfully.")

    @commands.guild_only()
    @group.command(name="list")
    async def group_list(self, ctx: NabCtx):
        """Shows a list of available groups."""
        groups = await ctx.pool.fetch("SELECT role_id FROM role_joinable WHERE server_id = $1", ctx.guild.id)
        if not groups:
            await ctx.send(f"{ctx.tick(False)} This server has no joinable groups.")
            return

        flat_groups = [g['role_id'] for g in groups]
        entries = []
        roles = reversed(ctx.guild.roles)
        for role in roles:
            if role.id in flat_groups:
                entries.append(f"{role.mention} (`{len(role.members)} members`)")

        per_page = 20 if await ctx.is_long() else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = "Joinable groups"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @group.command(name="remove", aliases=["delete"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def group_remove(self, ctx: NabCtx, *, _group: InsensitiveRole):
        """Removes a group.

        Removes a group, making members unable to join.
        When removing a group, you can optionally delete the role too."""
        group: discord.Role = _group
        exists = await ctx.pool.fetchval("SELECT true FROM role_joinable WHERE role_id = $1", group.id)
        if not exists:
            await ctx.send(f"{ctx.tick(False)} `{group.name}` is not a group.")
            return

        # Can't modify role higher than the owner's top role
        top_role: discord.Role = ctx.author.top_role
        if group >= top_role:
            await ctx.send(
                f"{ctx.tick(False)} You can't delete a group of a role higher than yours.")
            return

        msg = await ctx.send(f"Group `{group.name}` will be removed."
                             f"Do you want to remove the role too?")
        confirm = await ctx.react_confirm(msg, timeout=60, delete_after=True)
        if confirm is True:
            try:
                await group.delete(reason=f"Group removed by {ctx.author}")
                await ctx.send(f"{ctx.tick()} Group `{group.name}`  was removed and the role was deleted.")
            except discord.Forbidden:
                await ctx.send(f"{ctx.tick(False)} I need `Manage Roles` permission to delete the role.\n"
                               f"{ctx.tick()} Group `{group.name}` removed.")
        else:
            await ctx.send(f"{ctx.tick()} Group `{group.name}` was removed.")
        await ctx.pool.execute("DELETE FROM role_joinable WHERE role_id = $1", group.id)

    @commands.guild_only()
    @commands.command(aliases=["norole"])
    async def noroles(self, ctx: NabCtx):
        """Shows a list of members with no roles."""
        entries = []

        for member in ctx.guild.members:
            # Member only has the @everyone role
            if len(member.roles) == 1:
                entries.append(member.mention)

        if not entries:
            await ctx.send("There are no members without roles.")
            return

        per_page = 20 if await ctx.is_long() else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = "Members with no roles"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @commands.command(name="roleinfo")
    async def role_info(self, ctx: NabCtx, *, role: InsensitiveRole):
        """Shows details about a role."""
        _role: discord.Role = role
        embed = discord.Embed(title=_role.name, colour=_role.colour, timestamp=_role.created_at,
                              description=f"**ID** {role.id}")
        embed.add_field(name="Members", value=f"{len(role.members):,}")
        embed.add_field(name="Mentionable", value=f"{role.mentionable}")
        embed.add_field(name="Hoisted", value=f"{role.hoist}")
        embed.add_field(name="Position", value=f"{role.position}")
        embed.add_field(name="Color", value=f"{role.colour}")
        embed.add_field(name="Mention", value=f"`{role.mention}`")
        embed.set_footer(text="Created on")
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(name="rolemembers")
    async def role_members(self, ctx: NabCtx, *, role: InsensitiveRole):
        """Shows a list of members with that role."""
        _role: discord.Role = role
        if _role is None:
            await ctx.send("There's no role with that name in here.")
            return

        role_members = [m.mention for m in _role.members]
        if not role_members:
            await ctx.send("Seems like there are no members with that role.")
            return

        title = "Members with the role '{0.name}'".format(_role)
        per_page = 20 if await ctx.is_long() else 5
        pages = Pages(ctx, entries=role_members, per_page=per_page)
        pages.embed.title = title
        pages.embed.colour = _role.colour
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @commands.command()
    async def roles(self, ctx: NabCtx, *, user: str=None):
        """Shows a user's roles or a list of server roles.

        If a user is specified, it will list their roles.
        If user is blank, I will list all the server's roles."""
        if user is None:
            title = "Roles in this server"
            roles: List[discord.Role] = ctx.guild.roles[:]
            if len(roles) <= 1:
                await ctx.send("There are no roles in this server.")
                return
        else:
            member = self.bot.get_member(user, ctx.guild)
            if member is None:
                await ctx.send(f"I don't see any user named **{user}**.")
                return
            title = f"Roles for @{member.display_name}"
            roles: List[discord.Role] = member.roles[:]
            if len(roles) <= 1:
                await ctx.send(f"@**{member.display_name}** has no roles.")
                return
        # Remove @everyone
        roles.remove(ctx.guild.default_role)
        # Sorting roles by their position
        roles = sorted(roles, key=lambda r: r.position, reverse=True)
        entries = [f"{r.mention} ({len(r.members):,} member{'s' if len(r.members) > 1 else ''})" for r in roles]

        per_page = 20 if await ctx.is_long() else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)
        return


def setup(bot):
    bot.add_cog(Roles(bot))
