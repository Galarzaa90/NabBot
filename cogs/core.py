import asyncio
import datetime as dt
import random

import discord
from discord.ext import commands

from cogs.utils.database import get_server_property
from nabbot import NabBot
from .utils.checks import CannotEmbed
from .utils import context, join_list
from .utils import log
from .utils import config


class Core:
    """Cog with NabBot's main functions."""

    def __init__(self, bot: NabBot):
        self.bot = bot
        self.game_update_task = self.bot.loop.create_task(self.game_update())

    async def game_update(self):
        """Updates the bot's status.

        A random status is selected every 20 minutes.
        """
        # Entries are prefixes with "Playing "
        # Entries starting with "w:" are prefixed with "Watching "
        # Entries starting with "l:" are prefixed with "Listening to "
        presence_list = [
            # Playing _____
            "Half-Life 3", "Tibia on Steam", "DOTA 3", "Human Simulator 2018", "Russian roulette",
            "with my toy humans", "with fire🔥", "God", "innocent", "the part", "hard to get",
            "with my human minions", "Singularity", "Portal 3", "Dank Souls", "you", "01101110", "dumb",
            "with GLaDOS 💙", "with myself", "with your heart", "League of Dota", "my cards right",
            "out your death in my head",
            # Watching ____
            "w:you", "w:the world", "w:my magic ball", "w:https://nabbot.xyz", "w:you from behind",
            # Listening to ____
            "l:the voices in my head", "l:your breath", "l:the screams", "complaints"
        ]
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                if random.randint(0, 9) >= 7:
                    await self.bot.change_presence(activity=discord.Activity(name=f"{len(self.bot.guilds)} servers",
                                                                             type=discord.ActivityType.watching))
                else:
                    choice = random.choice(presence_list)
                    activity_type = discord.ActivityType.playing
                    if choice.startswith("w:"):
                        choice = choice[2:]
                        activity_type = discord.ActivityType.watching
                    elif choice.startswith("l:"):
                        choice = choice[2:]
                        activity_type = discord.ActivityType.listening
                    await self.bot.change_presence(activity=discord.Activity(name=choice, type=activity_type))
            except asyncio.CancelledError:
                break
            except discord.DiscordException:
                log.exception("Task: game_update")
                continue
            await asyncio.sleep(60*20)  # Change game every 20 minutes

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
                  f"‣ If you need help, join my support server: **<https://support.nabbot.xyz>**\n" \
                  f"‣ For more information and links in: `{config.command_prefix[0]}about`"
        async with self.bot.pool.acquire() as conn:
            for member in guild.members:
                if member.id in self.bot.members:
                    self.bot.members[member.id].append(guild.id)
                else:
                    self.bot.members[member.id] = [guild.id]
                await conn.execute("INSERT INTO user_server(user_id, server_id) VALUES($1, $2)", member.id, guild.id)
            await conn.execute("INSERT INTO server_history(server_id, server_count, event_type) VALUES($1, $2, $3)",
                               guild.id, len(self.bot.guilds), "add")
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
        await self.bot.pool.execute("DELETE FROM user_server WHERE server_id = $1 ", guild.id)
        await self.bot.pool.execute("INSERT INTO server_history(server_id, server_count, event_type) VALUES($1,$2,$3)",
                                    guild.id, len(self.bot.guilds), "remove")

    async def on_member_join(self, member: discord.Member):
        """ Called when a member joins a guild (server) the bot is in."""
        # Updating member list
        if member.id in self.bot.members:
            self.bot.members[member.id].append(member.guild.id)
        else:
            self.bot.members[member.id] = [member.guild.id]
        await self.bot.pool.execute("INSERT INTO user_server(user_id, server_id) VALUES($1, $2)",
                                    member.id, member.guild.id)

        if member.bot:
            return
        world = self.bot.tracked_worlds.get(member.guild.id)
        previously_registered = ""
        # If server is not tracking worlds, we don't check the database
        if member.guild.id not in self.bot.config.lite_servers and world is not None:
            rows = await self.bot.pool.fetch("""SELECT name, vocation, abs(level) as level, guild
                                                FROM "character" WHERE user_id = $1 AND world = $2""", member.id, world)
            if rows:
                characters = join_list([r['name'] for r in rows], ', ', ' and ')
                previously_registered = f"\n\nYou already have these characters in {world} registered: *{characters}*"

        welcome_message = await get_server_property(self.bot.pool, member.guild.id, "welcome")
        welcome_channel_id = await get_server_property(self.bot.pool, member.guild.id, "welcome_channel")
        if welcome_message is None:
            return
        message = welcome_message.format(user=member, server=member.guild, bot=self.bot, owner=member.guild.owner)
        message += previously_registered
        channel = member.guild.get_channel(welcome_channel_id)
        # If channel is not found, send via pm as fallback
        if channel is None:
            channel = member
        try:
            await channel.send(message)
        except discord.Forbidden:
            try:
                # If bot has no permissions to send the message on that channel, send on private message
                # If the channel was already a private message, don't try it again
                if welcome_channel_id is None:
                    return
                await member.send(message)
            except discord.Forbidden:
                pass

    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves or is kicked from a guild."""
        self.bot.members[member.id].remove(member.guild.id)
        await self.bot.pool.execute("DELETE FROM user_server WHERE user_id = $1 AND server_id = $2",
                                    member.id, member.guild.id)

    def __unload(self):
        self.game_update_task.cancel()


def setup(bot):
    bot.add_cog(Core(bot))
