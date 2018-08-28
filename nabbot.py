import datetime as dt
import re
import sys
import traceback
from typing import Union, List, Optional, Dict

import discord
from discord.ext import commands

from utils import context
from utils.config import config
from utils.database import init_database, userDatabase, get_server_property
from utils.general import join_list, get_token, get_user_avatar, get_region_string, CannotEmbed
from utils.general import log
from utils.help_format import NabHelpFormat
from utils.tibia import populate_worlds, tibia_worlds, get_voc_abb_and_emoji

initial_cogs = {"cogs.tracking", "cogs.owner", "cogs.mod", "cogs.admin", "cogs.tibia", "cogs.general", "cogs.loot",
                "cogs.tibiawiki", "cogs.roles", "cogs.settings", "cogs.info"}


def _prefix_callable(bot, msg):
    user_id = bot.user.id
    base = [f'<@!{user_id}> ', f'<@{user_id}> ']
    if msg.guild is None:
        base.extend(config.command_prefix)
    else:
        base.extend(get_server_property(msg.guild.id, "prefixes", deserialize=True, default=config.command_prefix))
    base = sorted(base, reverse=True)
    return base


class NabBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=_prefix_callable, case_insensitive=True,
                         description="Discord bot with functions for the MMORPG Tibia.",
                         formatter=NabHelpFormat(), pm_help=True)
        self.remove_command("help")
        self.members = {}
        self.start_time = dt.datetime.utcnow()
        # Dictionary of worlds tracked by nabbot, key:value = server_id:world
        # Dictionary is populated from database
        # A list version is created from the dictionary
        self.tracked_worlds = {}
        self.tracked_worlds_list = []
        self.__version__ = "1.6.0"
        self.__min_discord__ = 1480

    async def on_ready(self):
        """Called when the bot is ready."""
        print('Logged in as')
        print(self.user)
        print(self.user.id)
        print(f"Version {self.__version__}")
        print('------')

        # Notify reset author
        if len(sys.argv) > 1:
            user = self.get_member(int(sys.argv[1]))
            sys.argv[1] = 0
            if user is not None:
                await user.send("Restart complete")

        # Populating members's guild list
        self.members = {}
        for guild in self.guilds:
            for member in guild.members:
                if member.id in self.members:
                    self.members[member.id].append(guild.id)
                else:
                    self.members[member.id] = [guild.id]

        log.info('Bot is online and ready')

    async def on_message(self, message: discord.Message):
        """Called every time a message is sent on a visible channel."""
        # Ignore if message is from any bot
        if message.author.bot:
            return

        ctx = await self.get_context(message, cls=context.NabCtx)
        if ctx.command is not None:
            await self.invoke(ctx)
            return
        # This is a PM, no further info needed
        if message.guild is None:
            return
        if message.content.strip() == f"<@{self.user.id}>":
            prefixes = list(config.command_prefix)
            if ctx.guild:
                prefixes = get_server_property(ctx.guild.id, "prefixes", deserialize=True, default=prefixes)
            if prefixes:
                prefixes_str = ", ".join(f"`{p}`" for p in prefixes)
                return await ctx.send(f"My command prefixes are: {prefixes_str}, and mentions. "
                                      f"To see my commands, try: `{prefixes[0]}help.`", delete_after=10)
            else:
                return await ctx.send(f"My command prefix is mentions. "
                                      f"To see my commands, try: `@{self.user.name} help.`", delete_after=10)

        server_delete = get_server_property(message.guild.id, "commandsonly", is_int=True)
        global_delete = config.ask_channel_delete
        if (server_delete is None and global_delete) or server_delete:
            if ctx.is_askchannel:
                try:
                    await message.delete()
                except discord.Forbidden:
                    # Bot doesn't have permission to delete message
                    pass

    async def on_command_error(self, ctx: context.NabCtx, error):
        """Handles command errors"""
        if isinstance(error, commands.errors.CommandNotFound):
            return
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(error)
        elif isinstance(error, CannotEmbed):
            await ctx.send(f"{ctx.tick(False)} Sorry, `Embed Links` permission is required for this command.")
        elif isinstance(error, commands.CommandInvokeError):
            log.error(f"Exception in command: {ctx.message.clean_content}", exc_info=error.original)
            if isinstance(error.original, discord.HTTPException):
                await ctx.send("Sorry, the message was too long to send.")
            else:
                if ctx.bot_permissions.embed_links:
                    embed = discord.Embed(colour=discord.Colour(0xff1414))
                    embed.set_author(name="Support Server", url="https://discord.gg/NmDvhpY",
                                     icon_url=self.user.avatar_url)
                    embed.set_footer(text="Please report this bug in the support server.")
                    embed.add_field(name=f"{ctx.tick(False)}Command Error",
                                    value=f"```py\n{error.original.__class__.__name__}: {error.original}```",
                                    inline=False)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f'{ctx.tick(False)} Command error:\n```py\n{error.original.__class__.__name__}:'
                                   f'{error.original}```')

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
            if member.id in self.members:
                self.members[member.id].append(guild.id)
            else:
                self.members[member.id] = [guild.id]
        try:
            channel = self.get_top_channel(guild)
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
            if member.id in self.members:
                self.members[member.id].remove(guild.id)

    async def on_member_join(self, member: discord.Member):
        """ Called when a member joins a guild (server) the bot is in."""
        log.info("{0.display_name} (ID: {0.id}) joined {0.guild.name}".format(member))
        # Updating member list
        if member.id in self.members:
            self.members[member.id].append(member.guild.id)
        else:
            self.members[member.id] = [member.guild.id]

        embed = discord.Embed(description="{0.mention} joined.".format(member), color=discord.Color.green())
        embed.set_author(name="{0.name}#{0.discriminator} (ID: {0.id})".format(member), icon_url=get_user_avatar(member))

        previously_registered = ""
        # If server is not tracking worlds, we don't check the database
        if member.guild.id in config.lite_servers or self.tracked_worlds.get(member.guild.id) is None:
            await self.send_log_message(member.guild, embed=embed)
        else:
            # Check if user already has characters registered and announce them on log_channel
            # This could be because he rejoined the server or is in another server tracking the same worlds
            world = self.tracked_worlds.get(member.guild.id)
            previously_registered = ""
            if world is not None:
                c = userDatabase.cursor()
                try:
                    c.execute("SELECT name, vocation, ABS(level) as level, guild "
                              "FROM chars WHERE user_id = ? and world = ?", (member.id, world,))
                    results = c.fetchall()
                    if len(results) > 0:
                        previously_registered = "\n\nYou already have these characters in {0} registered to you: *{1}*"\
                            .format(world, join_list([r["name"] for r in results], ", ", " and "))
                        characters = ["\u2023 {name} - Level {level} {voc} - **{guild}**"
                                      .format(**c, voc=get_voc_abb_and_emoji(c["vocation"])) for c in results]
                        embed.add_field(name="Registered characters", value="\n".join(characters))
                finally:
                    c.close()
            self.dispatch("character_change", member.id)
            await self.send_log_message(member.guild, embed=embed)

        welcome_message = get_server_property(member.guild.id, "welcome")
        welcome_channel_id = get_server_property(member.guild.id, "welcome_channel", is_int=True)
        if welcome_message is None:
            return
        message = welcome_message.format(user=member, server=member.guild, bot=self, owner=member.guild.owner)
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
        now = dt.datetime.utcnow()
        self.members[member.id].remove(member.guild.id)
        bot_member: discord.Member = member.guild.me

        embed = discord.Embed(description="Left the server or was kicked", colour=discord.Colour(0xffff00))
        embed.set_author(name="{0.name}#{0.discriminator} (ID: {0.id})".format(member), icon_url=get_user_avatar(member))

        # If bot can see audit log, he can see if it was a kick or member left on it's own
        if bot_member.guild_permissions.view_audit_log:
            async for entry in member.guild.audit_logs(limit=20, reverse=False, action=discord.AuditLogAction.kick,
                                                       after=now-dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at-now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == member.id:
                    embed.description = "Kicked"
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                                     icon_url=get_user_avatar(entry.user))
                    embed.colour = discord.Colour(0xff0000)
                    if entry.reason:
                        embed.description += f"\n**Reason:** {entry.reason}"
                    await self.send_log_message(member.guild, embed=embed)
                    return
            embed.description = "Left the server"
            await self.send_log_message(member.guild, embed=embed)
            return
        # Otherwise, we are not certain
        await self.send_log_message(member.guild, embed=embed)

    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is banned from a guild."""
        now = dt.datetime.utcnow()
        bot_member: discord.Member = guild.me

        embed = discord.Embed(description="Banned", color=discord.Color(0x7a0d0d))
        embed.set_author(name="{0.name}#{0.discriminator}".format(user), icon_url=get_user_avatar(user))

        # If bot can see audit log, we can get more details of the ban
        if bot_member.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=10, reverse=False, action=discord.AuditLogAction.ban,
                                                after=now-dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at-now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == user.id:
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                                     icon_url=get_user_avatar(entry.user))
                    if entry.reason:
                        embed.description += f"\n**Reason:** {entry.reason}"
                    break
        await self.send_log_message(guild, embed=embed)

    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is unbanned from a guild"""
        now = dt.datetime.utcnow()
        bot_member: discord.Member = guild.me

        embed = discord.Embed(description="Unbanned", color=discord.Color(0xff9000))
        embed.set_author(name="{0.name}#{0.discriminator} (ID {0.id})".format(user), icon_url=get_user_avatar(user))

        if bot_member.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=10, reverse=False, action=discord.AuditLogAction.unban,
                                                after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at - now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == user.id:
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                                     icon_url=get_user_avatar(entry.user))
                    break
        await self.send_log_message(guild, embed=embed)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called every time a member is updated"""
        now = dt.datetime.utcnow()
        guild = after.guild
        bot_member = guild.me

        embed = discord.Embed(description=f"{after.mention}: ", color=discord.Colour.blue())
        embed.set_author(name=f"{after.name}#{after.discriminator} (ID: {after.id})", icon_url=get_user_avatar(after))
        changes = True
        if f"{before.name}#{before.discriminator}" != f"{after.name}#{after.discriminator}":
            embed.description += "Name changed from **{0.name}#{0.discriminator}** to **{1.name}#{1.discriminator}**."\
                .format(before, after)
        elif before.nick != after.nick:
            if before.nick is None:
                embed.description += f"Nickname set to **{after.nick}**"
            elif after.nick is None:
                embed.description += f"Nickname **{before.nick}** deleted"
            else:
                embed.description += f"Nickname changed from **{before.nick}** to **{after.nick}**"
            if bot_member.guild_permissions.view_audit_log:
                async for entry in guild.audit_logs(limit=10, reverse=False, action=discord.AuditLogAction.member_update,
                                                    after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                    if abs((entry.created_at - now).total_seconds()) >= 5:
                        # After is broken in the API, so we must check if entry is too old.
                        break
                    if entry.target.id == after.id:
                        # If the user changed their own nickname, no need to specify
                        if entry.user.id == after.id:
                            break
                        icon_url = get_user_avatar(entry.user)
                        embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user), icon_url=icon_url)
                        break
        else:
            changes = False
        if changes:
            await self.send_log_message(after.guild, embed=embed)
        return

    async def on_guild_emojis_update(self, guild: discord.Guild, before: List[discord.Emoji],
                                     after: List[discord.Emoji]):
        """Called every time an emoji is created, deleted or updated."""
        now = dt.datetime.utcnow()
        embed = discord.Embed(color=discord.Color.dark_orange())
        emoji: discord.Emoji = None
        # Emoji deleted
        if len(before) > len(after):
            emoji = discord.utils.find(lambda e: e not in after, before)
            if emoji is None:
                return
            fix = ":" if emoji.require_colons else ""
            embed.set_author(name=f"{fix}{emoji.name}{fix} (ID: {emoji.id})", icon_url=emoji.url)
            embed.description = f"Emoji deleted."
            action = discord.AuditLogAction.emoji_delete
        # Emoji added
        elif len(after) > len(before):
            emoji = discord.utils.find(lambda e: e not in before, after)
            if emoji is None:
                return
            fix = ":" if emoji.require_colons else ""
            embed.set_author(name=f"{fix}{emoji.name}{fix} (ID: {emoji.id})", icon_url=emoji.url)
            embed.description = f"Emoji added."
            action = discord.AuditLogAction.emoji_create
        else:
            old_name = ""
            for new_emoji in after:
                for old_emoji in before:
                    if new_emoji == old_emoji and new_emoji.name != old_emoji.name:
                        old_name = old_emoji.name
                        emoji = new_emoji
                        break
            if emoji is None:
                return
            fix = ":" if emoji.require_colons else ""
            embed.set_author(name=f"{fix}{emoji.name}{fix} (ID: {emoji.id})", icon_url=emoji.url)
            embed.description = f"Emoji renamed from `{fix}{old_name}{fix}` to `{fix}{emoji.name}{fix}`"
            action = discord.AuditLogAction.emoji_update

        # Find author
        if action is not None and guild.me.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=10, reverse=False, action=action,
                                                after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at - now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == emoji.id:
                    icon_url = get_user_avatar(entry.user)
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user), icon_url=icon_url)
                    break
        if emoji:
            await self.send_log_message(guild, embed=embed)

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Called every time a guild is updated"""
        now = dt.datetime.utcnow()
        guild = after
        bot_member = guild.me

        embed = discord.Embed(color=discord.Colour(value=0x9b3ee8))
        embed.set_author(name=after.name, icon_url=after.icon_url)

        changes = True
        if before.name != after.name:
            embed.description = "Name changed from **{0.name}** to **{1.name}**".format(before, after)
        elif before.region != after.region:
            embed.description = "Region changed from **{0}** to **{1}**".format(get_region_string(before.region),
                                                                                get_region_string(after.region))
        elif before.icon_url != after.icon_url:
            embed.description = "Icon changed"
            embed.set_thumbnail(url=after.icon_url)
        elif before.owner_id != after.owner_id:
            embed.description = f"Ownership transferred to {after.owner.mention}"
        else:
            changes = False
        if changes:
            if bot_member.guild_permissions.view_audit_log:
                async for entry in guild.audit_logs(limit=1, reverse=False, action=discord.AuditLogAction.guild_update,
                                                    after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                    icon_url = get_user_avatar(entry.user)
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user), icon_url=icon_url)
                    break
            await self.send_log_message(after, embed=embed)

    # ------------ Utility methods ------------

    def get_member(self, argument: Union[str, int], guild: Union[discord.Guild, List[discord.Guild]] = None) \
            -> Union[discord.Member, discord.User]:
        """Returns a member matching the arguments provided.

        If a guild or guild list is specified, then only members from those guilds will be searched. If no guild is
        specified, the first member instance will be returned.
        :param argument: The argument to search for, can be an id, name#disctriminator, nickname or name
        :param guild: The guild or list of guilds that limit the search.
        :return: The member found or None.
        """
        id_regex = re.compile(r'([0-9]{15,21})$')
        mention_regex = re.compile(r'<@!?([0-9]+)>$')
        match = id_regex.match(str(argument)) or mention_regex.match(str(argument))
        if match is None:
            return self.get_member_named(argument, guild)
        else:
            user_id = int(match.group(1))
            if guild is None:
                return discord.utils.get(self.get_all_members(), id=user_id)
            if type(guild) is list and len(guild) > 0:
                members = [m for ml in [g.members for g in guild] for m in ml]
                return discord.utils.find(lambda m: m.id == user_id, members)
            return guild.get_member(user_id)

    def get_member_named(self, name: str, guild: Union[discord.Guild, List[discord.Guild]] = None) -> discord.Member:
        """Returns a member matching the name

        If a guild or guild list is specified, then only members from those guilds will be searched. If no guild is
        specified, the first member instance will be returned.

        :param name: The name, nickname or name#discriminator of the member
        :param guild: The guild or list of guilds to limit the search
        :return: The member found or none
        """
        name = str(name)
        members = self.get_all_members()
        if type(guild) is discord.Guild:
            members = guild.members
        if type(guild) is list and len(guild) > 0:
            members = [m for ml in [g.members for g in guild] for m in ml]

        if len(name) > 5 and name[-5] == '#':
            potential_discriminator = name[-4:]
            result = discord.utils.get(members, name=name[:-5], discriminator=potential_discriminator)
            if result is not None:
                return result
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower() or m.name.lower == name.lower(),
                                  members)

    def get_user_guilds(self, user_id: int) -> List[discord.Guild]:
        """Returns a list of the user's shared guilds with the bot"""
        try:
            return [self.get_guild(gid) for gid in self.members[user_id]]
        except KeyError:
            return []

    def get_user_worlds(self, user_id: int, guild_list=None) -> List[str]:
        """Returns a list of all the tibia worlds the user is tracked in.

        This is based on the tracked world of each guild the user belongs to.
        guild_list can be passed to search in a specific set of guilds. Note that the user may not belong to them."""
        if guild_list is None:
            guild_list = self.get_user_guilds(user_id)
        return list(set([world for guild, world in self.tracked_worlds.items() if guild in [g.id for g in guild_list]]))

    def get_channel_or_top(self, guild: discord.Guild, channel_id: int) -> discord.TextChannel:
        """Returns a guild's channel by id, returns none if channel doesn't exist

        It also checks if the bot has permissions on that channel, if not, it will return the top channel too."""
        if channel_id is None:
            return self.get_top_channel(guild)
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            return self.get_top_channel(guild)
        permissions = channel.permissions_for(guild.me)
        if not permissions.read_messages or not permissions.send_messages:
            return self.get_top_channel(guild)
        return channel

    async def send_log_message(self, guild: discord.Guild, content=None, *, embed: discord.Embed = None):
        """Sends a message on the server-log channel

        If the channel doesn't exist, it doesn't send anything or give of any warnings as it meant to be an optional
        feature"""
        channel = self.get_channel_by_name(config.log_channel_name, guild)
        if channel is None:
            return
        try:
            await channel.send(content=content, embed=embed)
        except discord.HTTPException:
            pass

    def get_channel_by_name(self, name: str, guild: discord.Guild) -> discord.TextChannel:
        """Finds a channel by name on all the servers the bot is in.

        If guild is specified, only channels in that guild will be searched"""
        if guild is None:
            channel = discord.utils.find(lambda m: m.name == name and not type(m) == discord.ChannelType.voice,
                                         self.get_all_channels())
        else:
            channel = discord.utils.find(lambda m: m.name == name and not type(m) == discord.ChannelType.voice,
                                         guild.channels)
        return channel

    def get_guild_by_name(self, name: str) -> discord.Guild:
        """Returns a guild by its name"""

        guild = discord.utils.find(lambda m: m.name.lower() == name.lower(), self.guilds)
        return guild

    async def show_help(self, ctx, command=None):
        """Shows the help command for the specified command if given.
        If no command is given, then it'll show help for the current
        command.
        """
        cmd = self.get_command('help')
        command = command or ctx.command.qualified_name
        await ctx.invoke(cmd, command=command)

    @staticmethod
    def get_top_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Returns the highest text channel on the list.

        If writeable_only is set, the first channel where the bot can write is returned
        If None it returned, the guild has no channels or the bot can't write on any channel"""
        if guild is None:
            return None
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                return channel
        return None

    def reload_worlds(self):
        """Refresh the world list from the database

        This is used to avoid reading the database every time the world list is needed.
        A global variable holding the world list is loaded on startup and refreshed only when worlds are modified"""
        c = userDatabase.cursor()
        tibia_servers_dict_temp = {}
        try:
            c.execute("SELECT server_id, value FROM server_properties WHERE name = 'world' ORDER BY value ASC")
            result: Dict = c.fetchall()
            del self.tracked_worlds_list[:]
            if len(result) > 0:
                for row in result:
                    if row["value"] not in self.tracked_worlds_list:
                        self.tracked_worlds_list.append(row["value"])
                    tibia_servers_dict_temp[int(row["server_id"])] = row["value"]

            self.tracked_worlds.clear()
            self.tracked_worlds.update(tibia_servers_dict_temp)
        finally:
            c.close()


nabbot = None

if __name__ == "__main__":
    init_database()

    print("Loading config...")
    config.parse()

    nabbot = NabBot()

    # List of tracked worlds for NabBot
    nabbot.reload_worlds()
    # List of all Tibia worlds
    nabbot.loop.run_until_complete(populate_worlds())

    if len(tibia_worlds) == 0:
        print("Critical information was not available: NabBot can not start without the World List.")
        quit()
    token = get_token()

    print("Loading cogs...")
    for cog in initial_cogs:
        try:
            nabbot.load_extension(cog)
            print(f"Cog {cog} loaded successfully.")
        except ModuleNotFoundError:
            print(f"Could not find cog: {cog}")
        except Exception as e:
            print(f'Cog {cog} failed to load:')
            traceback.print_exc(limit=-1)

    for extra in config.extra_cogs:
        try:
            nabbot.load_extension(extra)
            print(f"Extra cog {extra} loaded successfully.")
        except ModuleNotFoundError:
            print(f"Could not find extra cog: {extra}")
        except Exception as e:
            print(f'Extra og {extra} failed to load:')
            traceback.print_exc(limit=-1)

    try:
        print("Attempting login...")
        nabbot.run(token)
    except discord.errors.LoginFailure:
        print("Invalid token. Edit token.txt to fix it.")
        input("\nPress any key to continue...")
        quit()

    log.error("NabBot crashed")
