import discord
from discord.ext import commands
import psutil
import random

from config import ask_channel_name
from utils.database import userDatabase
from utils.discord import get_member, is_lite_mode, get_region_string, get_role_list, get_member_by_name, get_role, \
    get_channel_by_name, is_private
from utils.general import get_uptime
from utils.messages import EMOJI
from utils.paginator import Paginator, CannotPaginate


class General:
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        print(get_member(self.bot, self.bot.user.id))
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.guild))
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
    async def roles(self, ctx, *, user_name: str = None):
        """Shows a list of roles or an user's roles

        If no user_name is specified, it shows a list of the server's role.
        If user_name is specified, it shows a list of that user's roles."""
        msg = "These are the active roles for "

        if user_name is None:
            msg += "this server:\n"

            for role in get_role_list(ctx.message.guild):
                msg += role.name + "\n"
        else:
            member = get_member_by_name(self.bot, user_name, ctx.message.guild)
            if member is None:
                await ctx.send("I don't see any user named **" + user_name + "**.")
            else:
                msg += "**" + member.display_name + "**:\n"
                roles = []

                # Ignoring "default" roles
                for role in member.roles:
                    if role.name not in ["@everyone", "Nab Bot"]:
                        roles.append(role.name)

                # There shouldn't be anyone without active roles, but since people can check for NabBot,
                # might as well show a specific message.
                if roles:
                    for roleName in roles:
                        msg += roleName + "\r\n"
                else:
                    msg = "There are no active roles for **" + member.display_name + "**."
        await ctx.send(msg)
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
                    role_members.append(member.display_name)
                    break
        if not role_members:
            await ctx.send("Seems like there are no members with that role.")
            return

        title = "Members with the role '{0.name}'".format(role)
        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.guild)
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
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.guild))
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


def setup(bot):
    bot.add_cog(General(bot))
