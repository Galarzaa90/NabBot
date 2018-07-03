from typing import List

import discord
from discord.ext import commands

from nabbot import NabBot
from utils.context import NabCtx
from utils.converter import InsensitiveRole
from utils.pages import CannotPaginate, Pages


class Roles:
    """Commands related to role management."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def __error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)

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

        title = "Members with no roles"
        per_page = 20 if ctx.long else 5
        pages = Pages(ctx, entries=entries, per_page=per_page, title=title)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @commands.command()
    async def roleinfo(self, ctx: NabCtx, *, role: InsensitiveRole):
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
    @commands.command()
    async def rolemembers(self, ctx: NabCtx, *, role: InsensitiveRole):
        """Shows a list of members with that role."""
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
