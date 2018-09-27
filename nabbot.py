import datetime as dt
import os
import re
import sys
import traceback
from typing import Union, List, Optional, Dict

import discord
from discord.ext import commands

from cogs.utils import context
from cogs.utils.database import init_database, userDatabase, get_server_property
from cogs.utils import config, log
from cogs.utils.help_format import NabHelpFormat
from cogs.utils.tibia import populate_worlds, tibia_worlds

initial_cogs = {"cogs.core", "cogs.tracking", "cogs.owner", "cogs.mod", "cogs.admin", "cogs.tibia", "cogs.general",
                "cogs.loot", "cogs.tibiawiki", "cogs.roles", "cogs.settings", "cogs.info"}


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
        self.__version__ = "1.6.1"
        self.__min_discord__ = 1580

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
            return await self.invoke(ctx)
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
        if (server_delete is None and global_delete or server_delete) and ctx.is_askchannel:
            try:
                await message.delete()
            except discord.Forbidden:
                # Bot doesn't have permission to delete message
                pass

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


def get_token():
    """When the bot is run without a login.py file, it prompts the user for login info"""
    if not os.path.isfile("token.txt"):
        print("This seems to be the first time NabBot is ran (or token.txt is missing)")
        print("To run your own instance of NabBot you need to create a new bot account to get a bot token")
        print("https://discordapp.com/developers/applications/me")
        print("Enter the token:")
        token = input(">>")
        if len(token) < 50:
            input("What you entered isn't a token. Restart NabBot to retry.")
            quit()
        f = open("token.txt", "w+")
        f.write(token)
        f.close()
        print("Token has been saved to token.txt, you can edit this file later to change it.")
        input("Press any key to start NabBot now...")
        return token
    else:
        with open("token.txt") as f:
            return f.read()


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
