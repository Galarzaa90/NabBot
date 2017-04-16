import asyncio
import random
import sys
import traceback

import discord
from discord import abc
from discord.ext import commands

from config import *
from utils.database import init_database, userDatabase, reload_worlds, tracked_worlds, reload_welcome_messages, \
    welcome_messages, reload_announce_channels
from utils.general import command_list, join_list, get_token
from utils.general import log
from utils.help_format import NabHelpFormat
from utils.messages import decode_emoji, EMOJI


class NabBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=["/"], description='Mission: Destroy all humans.', pm_help=True,
                         formatter=NabHelpFormat())
        self.remove_command("help")
        self.members = {}

    async def on_ready(self):
        self.load_extension("cogs.owner")
        self.load_extension("cogs.admin")
        self.load_extension("cogs.tibia")
        self.load_extension("cogs.mod")
        self.load_extension("cogs.tracking")
        self.load_extension("cogs.general")
        print('Logged in as')
        print(self.user)
        print(self.user.id)
        print('------')
        log.info('Bot is online and ready')

        # Populate command_list
        for command in self.commands:
            command_list.append(command.name)
            command_list.extend(command.aliases)

        # Notify reset author
        if len(sys.argv) > 1:
            user = self.get_member(sys.argv[1])
            sys.argv[1] = 0
            if user is not None:
                await user.send("Restart complete")

        # Background tasks
        self.loop.create_task(self.game_update())

        for guild in self.guilds:
            for member in guild.members:
                if member.id in self.members:
                    self.members[member.id].append(guild.id)
                else:
                    self.members[member.id] = [guild.id]

    async def on_command(self, ctx):
        """Called when a command is called. Used to log commands on a file."""
        if isinstance(ctx.message.channel, abc.PrivateChannel):
            destination = 'PM'
        else:
            destination = '#{0.channel.name} ({0.guild.name})'.format(ctx.message)
        message_decoded = decode_emoji(ctx.message.content)
        log.info('Command by {0} in {1}: {2}'.format(ctx.message.author.display_name, destination, message_decoded))

    async def on_command_error(self, error, ctx):
        if isinstance(error, commands.errors.CommandNotFound):
            return
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in private messages.")
        elif isinstance(error, commands.CommandInvokeError):
            print('In {0.command.qualified_name}:'.format(ctx), file=sys.stderr)
            traceback.print_tb(error.original.__traceback__)
            print('{0.__class__.__name__}: {0}'.format(error.original), file=sys.stderr)
            # Bot returns error message on discord if an owner called the command
            if ctx.message.author.id in owner_ids:
                await ctx.send('```Py\n{0.__class__.__name__}: {0}```'.format(error.original))

    async def on_message(self, message: discord.Message):
        """Called every time a message is sent on a visible channel.
    
        This is used to make commands case insensitive."""
        # Ignore if message is from any bot
        if message.author.bot:
            return

        split = message.content.split(" ", 1)
        if split[0][:1] == "/" and split[0].lower()[1:] in command_list:
            if len(split) > 1:
                message.content = split[0].lower()+" "+split[1]
            else:
                message.content = message.content.lower()
        if len(split) == 2:
            if message.author.id != self.user.id and (not split[0].lower()[1:] in command_list or not split[0][:1] == "/")\
                    and not isinstance(message.channel, abc.PrivateChannel) and message.channel.name == ask_channel_name:
                await message.delete()
                return
        elif ask_channel_delete:
            # Delete messages in askchannel
            if message.author.id != self.user.id \
                    and (not message.content.lower()[1:] in command_list or not message.content[:1] == "/") \
                    and not isinstance(message.channel, abc.PrivateChannel) and message.channel.name == ask_channel_name:
                await message.delete()
                return
        await self.process_commands(message)

    async def on_server_join(self, server: discord.Guild):
        log.info("Nab Bot added to server: {0.name} (ID: {0.id})".format(server))
        message = "Hello! I'm now in **{0.name}**. To see my available commands, type \help\n" \
                  "I will reply to commands from any channel I can see, but if you create a channel called *{1}*, I will " \
                  "give longer replies and more information there.\n" \
                  "If you want a server log channel, create a channel called *{2}*, I will post logs in there. You might " \
                  "want to make it private though.\n" \
                  "To have all of Nab Bot's features, use `/setworld <tibia_world>`"
        formatted_message = message.format(server, ask_channel_name, log_channel_name)
        await server.owner.send(formatted_message)

    async def on_member_join(self, member: discord.Member):
        """Called every time a member joins a server visible by the bot."""
        log.info("{0.display_name} (ID: {0.id}) joined {0.guild.name}".format(member))
        if member.id in self.members:
            self.members[member.id].append(member.guild.id)
        else:
            self.members[member.id] = [member.guild.id]

        if member.guild.id in lite_servers:
            return
        guild_id = member.guild.id
        server_welcome = welcome_messages.get(guild_id, "")
        pm = (welcome_pm+"\n"+server_welcome).format(member, self)
        log_message = "{0.mention} joined.".format(member)

        # Check if user already has characters registered
        # This could be because he rejoined the server or is in another server tracking the same worlds
        world = tracked_worlds.get(member.guild.id)
        if world is not None:
            c = userDatabase.cursor()
            try:
                c.execute("SELECT name, vocation, ABS(last_level) as level, guild "
                          "FROM chars WHERE user_id = ? and world = ?", (member.id, world,))
                results = c.fetchall()
                if len(results) > 0:
                    pm += "\nYou already have these characters in {0} registered to you: {1}"\
                        .format(world, join_list([r["name"] for r in results], ", ", " and "))
                    log_message += "\nPreviously registered characters:\n\t"
                    log_message += "\n\t".join("{name} - {level} {vocation} - **{guild}**".format(**r) for r in results)
            finally:
                c.close()

        await self.send_log_message(member.guild, log_message)
        await member.send(pm)
        await member.guild.default_channel.send("Look who just joined! Welcome {0.mention}!".format(member))

    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves or is kicked from a guild."""
        self.members[member.id].remove(member.guild.id)
        log.info("{0.display_name} (ID:{0.id}) left or was kicked from {0.guild.name}".format(member))
        await self.send_log_message(member.guild, "**{0.name}#{0.discriminator}** left or was kicked.".format(member))

    async def on_member_ban(self, member: discord.Member):
        """Called when a member is banned from a guild."""
        log.warning("{0.display_name} (ID:{0.id}) was banned from {0.guild.name}".format(member))
        await self.send_log_message(member.guild, "**{0.name}#{0.discriminator}** was banned.".format(member))

    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is unbanned from a guild"""
        log.warning("{1.name} (ID:{1.id}) was unbanned from {0.name}".format(guild, user))
        await self.send_log_message(guild, "**{0.name}#{0.discriminator}** was unbanned.".format(user))

    async def on_message_delete(self, message: discord.Message):
        """Called every time a message is deleted."""
        if message.channel.name == ask_channel_name:
            return

        message_decoded = decode_emoji(message.clean_content)
        attachment = ""
        if message.attachments:
            attachment = "\n\tAttached file: "+message.attachments[0]['filename']
        log.info("A message by @{0} was deleted in #{2} ({3}):\n\t'{1}'{4}".format(message.author.display_name,
                                                                                   message_decoded, message.channel.name,
                                                                                   message.guild.name, attachment))

    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Called every time a message is edited."""

        if before.author.id == self.user.id:
            return

        if isinstance(before.channel, abc.PrivateChannel):
            return

        if before.content == after.content:
            return

        before_decoded = decode_emoji(before.clean_content)
        after_decoded = decode_emoji(after.clean_content)

        log.info("@{0} edited a message in #{3} ({4}):\n\t'{1}'\n\t'{2}'".format(before.author.name, before_decoded,
                                                                                 after_decoded, before.channel,
                                                                                 before.guild))

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            reply = "{1.mention}: Nickname changed from **{0.nick}** to **{1.nick}**".format(before, after)
            await self.send_log_message(after.guild, reply)
        elif before.name != after.name:
            reply = "{1.mention}: Name changed from **{0.name}** to **{1.name}**".format(before, after)
            await self.send_log_message(after.guild, reply)
        return

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name != after.name:
            reply = "Server name changed from **{0.name}** to **{1.name}**".format(before, after)
            await self.send_log_message(after, reply)
        elif before.region != after.region:
            reply = "Server region changed from {0} to {1}".format(get_region_string(before.region),
                                                                   get_region_string(after.region))
            await self.send_log_message(after, reply)

    async def game_update(self):
        game_list = ["Half-Life 3", "Tibia on Steam", "DOTA 3", "Human Simulator 2017", "Russian Roulette",
                     "with my toy humans", "with fire"+EMOJI[":fire:"], "God", "innocent", "the part", "hard to get",
                     "with my human minions", "Singularity", "Portal 3", "Dank Souls"]
        await self.wait_until_ready()
        while not self.is_closed():
            await self.change_presence(game=discord.Game(name=random.choice(game_list)))
            await asyncio.sleep(60*20)  # Change game every 20 minutes

    async def send_log_message(self, guild: discord.Guild, content=None, embed: discord.Embed = None):
        """Sends a message on the server-log channel

        If the channel doesn't exist, it doesn't send anything or give of any warnings as it meant to be an optional
        feature"""
        channel = self.get_channel_by_name(log_channel_name, guild)
        if channel is None:
            return
        await channel.send(content=content, embed=embed)

    def get_channel_by_name(self, name: str, guild: discord.Guild = None,
                            guild_id: int = 0, guild_name: str = None) -> discord.TextChannel:
        """Finds a channel by name on all the channels visible by the bot.

        If server, server_id or server_name is specified, only channels in that server will be searched"""
        if guild is None and guild_id != 0:
            guild = bot.get_guild(guild_id)
        if guild is None and guild_name is not None:
            guild = get_guild_by_name(bot, guild_name)
        if guild is None:
            channel = discord.utils.find(lambda m: m.name == name and not type(m) == discord.ChannelType.voice,
                                         bot.get_all_channels())
        else:
            channel = discord.utils.find(lambda m: m.name == name and not type(m) == discord.ChannelType.voice,
                                         guild.channels)
        return channel

    def get_guild_by_name(self, name: str) -> discord.Guild:
        """Returns a guild by its name"""
        guild = discord.utils.find(lambda m: m.name.lower() == name.lower(), self.guilds)
        return guild

nabbot = NabBot()

if __name__ == "__main__":
    init_database()
    reload_worlds()
    reload_welcome_messages()
    reload_announce_channels()

    print("Attempting login...")

    token = get_token()

    try:
        nabbot.run(token)
    except discord.errors.LoginFailure:
        print("Invalid token. Edit token.txt to fix it.")
        input("\nPress any key to continue...")
        quit()
    finally:
        nabbot.logout()

    log.error("NabBot crashed")
