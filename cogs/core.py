import datetime as dt

import discord
from discord.ext import commands

from nabbot import NabBot
from .utils.checks import CannotEmbed
from .utils import context
from .utils import log
from .utils import config


class Core:
    """Cog with NabBot's main functions."""

    def __init__(self, bot: NabBot):
        self.bot = bot

    async def on_command_error(self, ctx: context.NabCtx, error):
        """Handles command errors"""
        if isinstance(error, commands.errors.CommandNotFound):
            return
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(error)
        elif isinstance(error, CannotEmbed):
            await ctx.send(f"{ctx.tick(False)} Sorry, `Embed Links` permission is required for this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{ctx.tick(False)} The correct syntax is: "
                           f"`{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.usage}`.\n"
                           f"Try `{ctx.clean_prefix}help {ctx.command.qualified_name}` for more info.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"{ctx.tick(False)} {error}\n"
                           f"Try `{ctx.clean_prefix}help {ctx.command.qualified_name}` for more info.")
        elif isinstance(error, commands.CommandInvokeError):
            log.error(f"Exception in command: {ctx.message.clean_content}", exc_info=error.original)
            if isinstance(error.original, discord.HTTPException):
                await ctx.send("Sorry, the message was too long to send.")
            else:
                if ctx.bot_permissions.embed_links:
                    embed = discord.Embed(colour=discord.Colour(0xff1414))
                    embed.set_author(name="Support Server", url="https://discord.gg/NmDvhpY",
                                     icon_url=self.bot.user.avatar_url)
                    embed.set_footer(text="Please report this bug in the support server.")
                    embed.add_field(name=f"{ctx.tick(False)}Command Error",
                                    value=f"```py\n{error.original.__class__.__name__}: {error.original}```",
                                    inline=False)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f'{ctx.tick(False)} Command error:\n```py\n{error.original.__class__.__name__}:'
                                   f'{error.original}```')

    async def on_command(self, ctx):
        command = ctx.command.qualified_name
        guild_id = ctx.guild.id if ctx.guild is not None else None
        query = """INSERT INTO command(server_id, channel_id, user_id, date, prefix, command)
                   VALUES ($1, $2, $3, $4, $5, $6)
                """
        await self.bot.pool.execute(query, guild_id, ctx.channel.id, ctx.author.id,
                                    ctx.message.created_at.replace(tzinfo=dt.timezone.utc), ctx.prefix, command)

    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a guild (server)."""
        log.info("Nab Bot added to server: {0.name} (ID: {0.id})".format(guild))
        message = f"**I've been added to this server.**\n" \
                  f"Some things you should know:\n" \
                  f"‣ My command prefix is: `{config.command_prefix[0]}` (it is customizable)\n" \
                  f"‣ You can see all my commands with: `{config.command_prefix[0]}help` or " \
                  f"`{config.command_prefix[0]}commands`\n" \
                  f"‣ You can configure me using: `{config.command_prefix[0]}settings`\n" \
                  f"‣ You can set a world for me to track by using `{config.command_prefix[0]}settings world`\n" \
                  f"‣ If you want a logging channel, create a channel named `{config.log_channel_name}`\n" \
                  f"‣ If you need help, join my support server: **<https://discord.me/NabBot>**\n" \
                  f"‣ For more information and links in: `{config.command_prefix[0]}about`"
        for member in guild.members:
            if member.id in self.bot.members:
                self.bot.members[member.id].append(guild.id)
            else:
                self.bot.members[member.id] = [guild.id]
        try:
            channel = self.bot.get_top_channel(guild)
            if channel is None:
                log.warning(f"Could not send join message on server: {guild.name}. No allowed channel found.")
                return
            await channel.send(message)
        except discord.HTTPException as e:
            log.error(f"Could not send join message on server: {guild.name}.", exc_info=e)

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot leaves a guild (server)."""
        log.info("Nab Bot left server: {0.name} (ID: {0.id})".format(guild))
        for member in guild.members:
            if member.id in self.bot.members:
                self.bot.members[member.id].remove(guild.id)

    async def on_member_join(self, member: discord.Member):
        """ Called when a member joins a guild (server) the bot is in."""
        # Updating member list
        if member.id in self.bot.members:
            self.bot.members[member.id].append(member.guild.id)
        else:
            self.bot.members[member.id] = [member.guild.id]

    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves or is kicked from a guild."""
        self.bot.members[member.id].remove(member.guild.id)


def setup(bot):
    bot.add_cog(Core(bot))
