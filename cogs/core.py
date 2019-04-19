import asyncio
import datetime as dt
import logging
import random
import re
from typing import Tuple

import discord
from discord.ext import commands

from cogs.utils.database import DbChar
from nabbot import NabBot
from .utils import CogUtils, config, context, errors, join_list, database, timing

log = logging.getLogger("nabbot")

bad_argument_pattern = re.compile(r'Converting to \"([^\"]+)\" failed for parameter \"([^\"]+)\"\.')


class Core(commands.Cog, CogUtils):
    """Cog with NabBot's main functions."""

    def __init__(self, bot: NabBot):
        self.bot = bot
        self.game_update_task = self.bot.loop.create_task(self.game_update())

    def cog_unload(self):
        log.info(f"{self.tag} Unloading cog")
        self.game_update_task.cancel()

    async def game_update(self):
        """Updates the bot's status.

        A random status is selected every 20 minutes.
        """
        tag = f"{self.tag}[game_update]"
        # Entries are prefixed with "Playing "
        # Entries starting with "w:" are prefixed with "Watching "
        # Entries starting with "l:" are prefixed with "Listening to "
        presence_list = [
            # Playing _____
            "Half-Life 3", "Tibia on Steam", "DOTA 3", "Human Simulator 2019", "Russian roulette",
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
        log.info(f"{tag} Task started")
        while not self.bot.is_closed():
            try:
                if random.randint(0, 9) >= 7:
                    choice = f"{len(self.bot.guilds)} servers"
                    activity_type = discord.ActivityType.watching
                else:
                    choice = random.choice(presence_list)
                    activity_type = discord.ActivityType.playing
                    if choice.startswith("w:"):
                        choice = choice[2:]
                        activity_type = discord.ActivityType.watching
                    elif choice.startswith("l:"):
                        choice = choice[2:]
                        activity_type = discord.ActivityType.listening
                log.info(f"{tag} Updating presence | {activity_type.name} | {choice}")
                await self.bot.change_presence(activity=discord.Activity(name=choice, type=activity_type))
            except asyncio.CancelledError:
                log.info(f"{tag} Stopped")
                return
            except discord.DiscordException:
                log.exception(f"{tag} Exception")
                continue
            await asyncio.sleep(60*20)  # Change game every 20 minutes

    # region Discord events

    @commands.Cog.listener()
    async def on_command_error(self, ctx: context.NabCtx, error: commands.CommandError):
        """Handles command errors"""
        if isinstance(error, commands.errors.CommandNotFound):
            return
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.error(f"You're using this too much! "
                            f"Try again {timing.HumanDelta.from_seconds(error.retry_after).long(1)}.")
        elif isinstance(error, commands.CheckFailure):
            await self.process_check_failure(ctx, error)
        elif isinstance(error, commands.UserInputError):
            await self.process_user_input_error(ctx, error)
        elif isinstance(error, commands.CommandInvokeError):
            await self.process_command_invoke_error(ctx, error)
        else:
            log.warning(f"Unhandled command error {error.__class__.__name__}: {error}")

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        """Called every time a command is executed.

        Saves the command use to the database."""
        command = ctx.command.qualified_name
        guild_id = ctx.guild.id if ctx.guild is not None else None
        query = """INSERT INTO command_use(server_id, channel_id, user_id, date, prefix, command)
                   VALUES ($1, $2, $3, $4, $5, $6)
                """
        log.info(f"{self.tag} Invoked command: {ctx.message.clean_content}")
        await self.bot.pool.execute(query, guild_id, ctx.channel.id, ctx.author.id,
                                    ctx.message.created_at.replace(tzinfo=dt.timezone.utc), ctx.prefix, command)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a guild (server)."""
        log.info(f"{self.tag} Bot added | Guild {guild} ({guild.id})")
        # Update in-memory member list
        for member in guild.members:
            if member.id in self.bot.users_servers:
                self.bot.users_servers[member.id].append(guild.id)
            else:
                self.bot.users_servers[member.id] = [guild.id]
        # Update database member list
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                # Make sure there's no leftover data that will make the copy query fail
                await conn.execute("DELETE FROM user_server WHERE server_id = $1", guild.id)
                records = [(user.id, guild.id) for user in guild.members]
                await conn.copy_records_to_table("user_server", columns=["user_id", "server_id"], records=records)
                await conn.execute("INSERT INTO server_history(server_id, server_count, event_type) VALUES($1, $2, $3)",
                                   guild.id, len(self.bot.guilds), "add")
        # Show opening message
        message = f"Hi, I've been added to this server. Some things you should know:\n" \
            f"‣ My command prefix is: `{config.command_prefix[0]}` (it is customizable)\n" \
            f"‣ You can see all my commands with: `{config.command_prefix[0]}help` or " \
            f"`{config.command_prefix[0]}commands`\n" \
            f"‣ You can configure me using: `{config.command_prefix[0]}settings`\n" \
            f"‣ You can set a world for me to track by using `{config.command_prefix[0]}settings world`\n" \
            f"‣ If you want a logging channel, create a channel named `{config.log_channel_name}`\n" \
            f"‣ If you need help, join my support server: **<https://support.nabbot.xyz>**\n" \
            f"‣ For more information and links in: `{config.command_prefix[0]}about`"
        try:
            channel = self.bot.get_top_channel(guild)
            if channel is None:
                log.warning(f"{self.tag} Could not send join message on server: {guild.name}."
                            f"No allowed channel found.")
                return
            await channel.send(message)
        except discord.HTTPException:
            log.exception(f"{self.tag} Could not send join message on server: {guild.name}.")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot leaves a guild (server)."""
        log.info(f"{self.tag} Bot removed | Guild {guild} ({guild.id})")
        for member in guild.members:
            if member.id in self.bot.users_servers:
                self.bot.users_servers[member.id].remove(guild.id)
        await self.bot.pool.execute("DELETE FROM user_server WHERE server_id = $1 ", guild.id)
        await self.bot.pool.execute("INSERT INTO server_history(server_id, server_count, event_type) VALUES($1,$2,$3)",
                                    guild.id, len(self.bot.guilds), "remove")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is banned from a guild."""
        log.info(f"{self.tag} Member banned | Member {user} ({user.id}) | Guild {guild.id}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Called when a member joins a guild (server) the bot is in."""
        log.info(f"{self.tag} Member joined | Member {member} ({member.id}) | Guild {member.guild.id}")
        # Updating member list
        if member.id in self.bot.users_servers:
            self.bot.users_servers[member.id].append(member.guild.id)
        else:
            self.bot.users_servers[member.id] = [member.guild.id]
        await self.bot.pool.execute("INSERT INTO user_server(user_id, server_id) VALUES($1, $2)",
                                    member.id, member.guild.id)

        if member.bot:
            return
        world = self.bot.tracked_worlds.get(member.guild.id)
        previously_registered = ""
        # If server is not tracking worlds, we don't check the database
        if member.guild.id not in self.bot.config.lite_servers and world is not None:
            chars = await DbChar.get_chars_by_user(self.bot.pool, member.id, worlds=world)
            if chars:
                characters = join_list([c.name for c in chars], ', ', ' and ')
                previously_registered = f"\n\nYou already have these characters in {world} registered: *{characters}*"

        welcome_message = await database.get_server_property(self.bot.pool, member.guild.id, "welcome")
        welcome_channel_id = await database.get_server_property(self.bot.pool, member.guild.id, "welcome_channel")
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

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves or is kicked from a guild."""
        log.info(f"{self.tag} Member left/kicked | Member {member} ({member.id}) | Guild {member.guild.id}")
        self.bot.users_servers[member.id].remove(member.guild.id)
        await self.bot.pool.execute("DELETE FROM user_server WHERE user_id = $1 AND server_id = $2",
                                    member.id, member.guild.id)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is unbanned from a guild"""
        log.info(f"{self.tag} Member unbanned | Member {user} ({user.id}) | Guild {guild.id}")

    # endregion

    @classmethod
    def parse_bad_argument(cls, content: str) -> Tuple:
        m = bad_argument_pattern.match(content)
        if not m:
            return None, None
        return m.group(1), m.group(2)

    @classmethod
    async def process_check_failure(cls, ctx: context.NabCtx, error: commands.CheckFailure):
        """Handles CheckFailure errors.

        These are exceptions that may be raised when executing command checks."""
        if isinstance(error, (commands.NoPrivateMessage, errors.NotTracking, errors.UnathorizedUser,
                              commands.MissingPermissions)):
            await ctx.error(error)
        elif isinstance(error, errors.CannotEmbed):
            await ctx.error(f"Sorry, `Embed Links` permission is required for this command.")

    async def process_user_input_error(self, ctx: context.NabCtx, error: commands.UserInputError):
        """Handles UserInput errors.

        These are exceptions raised due to the user providing invalid or incorrect input."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.error(f"The correct syntax is: `{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.usage}`.\n"
                            f"Try `{ctx.clean_prefix}help {ctx.command.qualified_name}` for more info.")
        elif isinstance(error, commands.BadArgument):
            _type, param = self.parse_bad_argument(str(error))
            # Making these errors more understandable.
            if _type == "int":
                error = f"Parameter `{param}` must be numeric."
            await ctx.error(f"{error}\nTry `{ctx.clean_prefix}help {ctx.command.qualified_name}` for more info.")

    async def process_command_invoke_error(self, ctx: context.NabCtx, error: commands.CommandInvokeError):
        """Handles CommandInvokeError.

        This exception is raised when an exception is raised during command execution."""
        error_name = error.original.__class__.__name__
        if isinstance(error.original, errors.NetworkError):
            log.error(f"{error_name} in command {ctx.clean_prefix}{ctx.command.qualified_name}: {error.original}")
            return await ctx.error("I'm having network issues right now. Please try again in a moment.")
        log.error(f"{self.tag} Exception in command: {ctx.message.clean_content}", exc_info=error.original)
        if isinstance(error.original, discord.HTTPException):
            await ctx.error("Sorry, the message was too long to send.")
        else:
            if ctx.bot_permissions.embed_links:
                embed = discord.Embed(colour=discord.Colour(0xff1414))
                embed.set_author(name="Support Server", url="https://discord.gg/NmDvhpY",
                                 icon_url=self.bot.user.avatar_url)
                embed.set_footer(text="Please report this bug in the support server.")
                embed.add_field(name=f"{ctx.tick(False)}Command Error",
                                value=f"```py\n{error_name}: {error.original}```",
                                inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.error(f'Command error:\n```py\n{error_name}: {error.original}```')


def setup(bot):
    bot.add_cog(Core(bot))
