from discord.ext import commands

from nabbot import NabBot
from utils import context
from utils.config import config
from utils.discord import get_role_list, is_private, get_role
from utils.paginator import CannotPaginate, Pages


class Roles:
    """Commands related to role management."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.guild_only()
    @commands.command()
    async def roles(self, ctx: context.Context, *, user: str = None):
        """Shows a user's roles or a list of server roles.

        If a user is specified, it will list their roles.
        If user is blank, I will list all the server's roles."""

        if user is None:
            title = "Roles in this server"
            entries = [r.mention for r in get_role_list(ctx.guild)]
        else:
            member = self.bot.get_member(user, ctx.guild)
            if member is None:
                await ctx.send("I don't see any user named **" + user + "**.")
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
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)
        return

    @commands.guild_only()
    @commands.command()
    async def role(self, ctx, *, name: str):
        """Shows a list of members with that role."""
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
        pages = Pages(ctx, entries=role_members, per_page=per_page)
        pages.embed.title = title
        pages.embed.colour = role.colour
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @commands.command(aliases=["norole"])
    async def noroles(self, ctx):
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
        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        pages = Pages(ctx, entries=entries, per_page=per_page, title=title)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)


def setup(bot):
    bot.add_cog(Roles(bot))
