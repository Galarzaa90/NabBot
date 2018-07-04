from typing import List

import discord
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.context import NabCtx
from utils.converter import InsensitiveRole
from utils.database import userDatabase
from utils.pages import CannotPaginate, Pages


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
        result = userDatabase.execute("SELECT * FROM joinable_roles WHERE role_id = ?", (role.id,))
        exists = list(result)
        if exists:
            userDatabase.execute("DELETE FROM joinable_roles WHERE role_id = ?", (role.id,))

    @commands.guild_only()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def group(self, ctx: NabCtx, group: InsensitiveRole):
        """Joins or leaves a group (role).

        If you're not in the group, you will be added.
        If you're already in the group, you will be removed.

        To see a list of joinable groups, use `group list`"""
        group: discord.Role = group
        result = userDatabase.execute("SELECT * FROM joinable_roles WHERE role_id = ?", (group.id,))
        exists = list(result)
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
        result = userDatabase.execute("SELECT * FROM joinable_roles WHERE role_id = ?", (role.id, ))
        group = list(result)
        if group:
            await ctx.send(f"{ctx.tick(False)} Group `{role.name}` already exists.")
            return

        # Can't make joinable group a role higher than the owner's top role
        top_role: discord.Role = ctx.author.top_role
        if role >= top_role:
            await ctx.send(f"{ctx.tick(False)} You can't make a group with a role higher or equals than your highest.")
            return

        userDatabase.execute("INSERT INTO joinable_roles(server_id, role_id) VALUES(?,?)", (ctx.guild.id, role.id))
        await ctx.send(f"{ctx.tick()} Group `{role.name}` created successfully.")

    @checks.has_guild_permissions(manage_roles=True)
    @commands.guild_only()
    @group.command(name="remove", aliases=["delete"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def group_remove(self, ctx: NabCtx, *, group: InsensitiveRole):
        """Removes a group.

        Removes a group, making members unable to join.
        When removing a group, you can optionally delete the role too."""
        group: discord.Role = group
        result = userDatabase.execute("SELECT * FROM joinable_roles WHERE role_id = ?", (group.id,))
        exists = list(result)
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
        userDatabase.execute("DELETE FROM joinable_roles WHERE role_id = ?", (group.id,))

    @commands.guild_only()
    @group.command(name="list")
    async def group_list(self, ctx: NabCtx):
        """Shows a list of available groups."""
        result = userDatabase.execute("SELECT role_id FROM joinable_roles WHERE server_id = ?", (ctx.guild.id, ))
        groups = list(result)
        if not groups:
            await ctx.send(f"{ctx.tick(False)} This server has no joinable groups.")
            return

        flat_groups = [g['role_id'] for g in groups]

        entries = []
        roles = ctx.guild.role_hierarchy
        for role in roles:
            if role.id in flat_groups:
                entries.append(f"{role.mention} (`{len(role.members)} members`)")

        per_page = 20 if ctx.long else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = "Joinable groups"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

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

        per_page = 20 if ctx.long else 5
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
        role: discord.Role = role
        embed = discord.Embed(title=role.name, colour=role.colour, timestamp=role.created_at,
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
        role: discord.Role = role
        if role is None:
            await ctx.send("There's no role with that name in here.")
            return

        role_members = [m.mention for m in role.members]
        if not role_members:
            await ctx.send("Seems like there are no members with that role.")
            return

        title = "Members with the role '{0.name}'".format(role)
        per_page = 20 if ctx.long else 5
        pages = Pages(ctx, entries=role_members, per_page=per_page)
        pages.embed.title = title
        pages.embed.colour = role.colour
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

        per_page = 20 if ctx.long else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)
        return


def setup(bot):
    bot.add_cog(Roles(bot))
