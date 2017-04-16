import asyncio

import discord
from discord.ext import commands

from config import welcome_pm, ask_channel_name, log_channel_name
from nabbot import NabBot
from utils import checks
from utils.database import *
from utils.discord import get_member, get_user_admin_guilds, is_private
from utils.messages import EMOJI
from utils.tibia import tibia_worlds


class Admin:
    """Commands for server owners and admins"""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.command()
    @checks.is_admin()
    async def diagnose(self, ctx: discord.ext.commands.Context, *, server_name=None):
        """Diagnose the bots permissions and channels"""
        # This will always have at least one server, otherwise this command wouldn't pass the is_admin check.
        admin_guilds = get_user_admin_guilds(self.bot, ctx.message.author.id)

        if server_name is None:
            if not is_private(ctx.message.channel):
                if ctx.message.guild not in admin_guilds:
                    await ctx.send("You don't have permissions to diagnose this server.")
                    return
                guild = ctx.message.guild
            else:
                if len(admin_guilds) == 1:
                    guild = admin_guilds[0]
                else:
                    guild_list = [str(i+1)+": "+admin_guilds[i].name for i in range(len(admin_guilds))]
                    await ctx.send("Which server do you want to check?\n\t0: *Cancel*\n\t"+"\n\t".join(guild_list))

                    def check(m):
                        return m.author == ctx.author and m.channel == ctx.channel
                    try:
                        answer = await self.bot.wait_for("message", timeout=60.0, check=check)
                        answer = int(answer.content)
                        if answer == 0:
                            await ctx.send("Changed your mind? Typical human.")
                            return
                        guild = admin_guilds[answer-1]
                    except IndexError:
                        await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
                        return
                    except ValueError:
                        await ctx.send("That's not a number!")
                        return
                    except asyncio.TimeoutError:
                        await ctx.send("I guess you changed your mind.")
                        return
        else:
            guild = self.bot.get_guild_by_name(server_name)
            if guild is None:
                await ctx.send("I couldn't find a server with that name.")
                return
            if guild not in admin_guilds:
                await ctx.send("You don't have permissions to diagnose **{0}**.".format(guild.name))
                return

        if guild is None:
            return
        member = get_member(self.bot, self.bot.user.id, guild)
        server_perms = member.guild_permissions

        channels = guild.channels
        not_read_messages = []
        not_send_messages = []
        not_manage_messages = []
        not_embed_links = []
        not_attach_files = []
        not_mention_everyone = []
        not_add_reactions = []
        not_read_history = []
        count = 0
        for channel in channels:
            if type(channel) == discord.ChannelType.voice:
                continue
            count += 1
            channel_permissions = channel.permissions_for(member)
            if not channel_permissions.read_messages:
                not_read_messages.append(channel)
            if not channel_permissions.send_messages:
                not_send_messages.append(channel)
            if not channel_permissions.manage_messages:
                not_manage_messages.append(channel)
            if not channel_permissions.embed_links:
                not_embed_links.append(channel)
            if not channel_permissions.attach_files:
                not_attach_files.append(channel)
            if not channel_permissions.mention_everyone:
                not_mention_everyone.append(channel)
            if not channel_permissions.add_reactions:
                not_add_reactions.append(channel)
            if not channel_permissions.read_message_history:
                not_read_history.append(channel)

        channel_lists_list = [not_read_messages, not_send_messages, not_manage_messages, not_embed_links,
                              not_attach_files, not_mention_everyone, not_add_reactions, not_read_history]
        permission_names_list = ["Read Messages", "Send Messages", "Manage Messages", "Embed Links", "Attach Files",
                                 "Mention Everyone", "Add reactions", "Read Message History"]
        server_wide_list = [server_perms.read_messages, server_perms.send_messages, server_perms.manage_messages,
                            server_perms.embed_links, server_perms.attach_files, server_perms.mention_everyone,
                            server_perms.add_reactions, server_perms.read_message_history]

        answer = "Permissions for {0.name}:\n".format(guild)
        i = 0
        while i < len(channel_lists_list):
            answer += "**{0}**\n\t{1} Server wide".format(permission_names_list[i], get_check_emoji(server_wide_list[i]))
            if len(channel_lists_list[i]) == 0:
                answer += "\n\t{0} All channels\n".format(get_check_emoji(True))
            elif len(channel_lists_list[i]) == count:
                answer += "\n\t All channels\n".format(get_check_emoji(False))
            else:
                channel_list = ["#" + x.name for x in channel_lists_list[i]]
                answer += "\n\t{0} Not in: {1}\n".format(get_check_emoji(False), ",".join(channel_list))
            i += 1

        ask_channel = self.bot.get_channel_by_name(ask_channel_name, guild)
        answer += "\nAsk channel:\n\t"
        if ask_channel is not None:
            answer += "{0} Enabled: {1.mention}".format(get_check_emoji(True), ask_channel)
        else:
            answer += "{0} Not enabled".format(get_check_emoji(False))

        log_channel = self.bot.get_channel_by_name(log_channel_name, guild)
        answer += "\nLog channel:\n\t"
        if log_channel is not None:
            answer += "{0} Enabled: {1.mention}".format(get_check_emoji(True), log_channel)
        else:
            answer += "{0} Not enabled".format(get_check_emoji(False))
        await ctx.send(answer)
        return

    @commands.command(name="setworld")
    @checks.is_admin()
    @checks.is_not_lite()
    async def set_world(self, ctx: commands.Context, *, world: str = None):
        """Sets this server's Tibia world.

        If no world is passed, it shows this server's current assigned world."""
        def check(m):
            return m.channel == ctx.message.channel and m.author == ctx.message.author

        admin_guilds = get_user_admin_guilds(self.bot, ctx.message.author.id)

        if not is_private(ctx.message.channel):
            if ctx.message.guild not in admin_guilds:
                await ctx.send("You don't have permissions to diagnose this server.")
                return
            guild = ctx.message.guild
        else:
            if len(admin_guilds) == 1:
                guild = admin_guilds[0]
            else:
                guild_list = [str(i+1)+": "+admin_guilds[i].name for i in range(len(admin_guilds))]
                await ctx.send("For which server do you want to change the world?\n\t0: *Cancel*\n\t"+"\n\t".join(guild_list))

                try:
                    answer = await self.bot.wait_for("message", timeout=60.0)
                    answer = int(answer.content)
                    if answer == 0:
                        await ctx.send("Changed your mind? Typical human.")
                        return
                    guild = admin_guilds[answer-1]
                except IndexError:
                    await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
                    return
                except ValueError:
                    await ctx.send("That's not a valid answer.")
                    return
                except asyncio.TimeoutError:
                    await ctx.send("I guess you changed your mind.")
                    return

        guild_id = guild.id
        if world is None:
            current_world = tracked_worlds.get(guild_id, None)
            if current_world is None:
                await ctx.send("This server has no tibia world assigned.")
            else:
                await ctx.send("This server has **{0}** assigned.".format(current_world))
            return

        if world.lower() in ["clear", "none", "delete", "remove"]:
            await ctx.send("Are you sure you want to delete this server's tracked world? `yes/no`")
            try:
                reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                if reply.content.lower() not in ["yes", "y"]:
                    await ctx.send("No changes were made then.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("I guess you changed your mind...")
                return

            c = userDatabase.cursor()
            try:
                c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'world'", (guild_id,))
            finally:
                c.close()
                userDatabase.commit()
            await ctx.send("This server's tracked world has been removed.")
            reload_worlds()
            return

        world = world.strip().capitalize()
        if world not in tibia_worlds:
            await ctx.send("There's no world with that name.")
            return
        await ctx.send("Are you sure you want to assign **{0}** to this server? Previous worlds will be replaced."
                            .format(world))

        try:
            reply = await self.bot.wait_for("message", timeout=50.0, check=check)
            if reply.content.lower() not in ["yes", "y"]:
                await ctx.send("No changes were made then.")
                return
        except asyncio.TimeoutError:
            await ctx.send("I guess you changed your mind...")
            return

        c = userDatabase.cursor()
        try:
            # Safer to just delete old entry and add new one
            c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'world'", (guild_id,))
            c.execute("INSERT INTO server_properties(server_id, name, value) VALUES (?, 'world', ?)",
                      (guild_id, world,))
            await ctx.send("This server's world has been changed successfully.")
        finally:
            c.close()
            userDatabase.commit()
            reload_worlds()

    @commands.command(name="setwelcome")
    @checks.is_admin()
    @checks.is_not_lite()
    async def set_welcome(self, ctx, *, message: str = None):
        """Changes the messages members get pmed when joining

        A part of the message is already fixed and cannot be changed, but the message can be extended

        Say "clear" to clear the current message.

        The following can be used to get dynamically replaced:
        {0.name} - The joining user's name
        {0.guild.name} - The name of the server the user joined
        {0.guild.owner.name} - The name of the owner of the server the member joined
        {0.guild.owner.mention} - A mention to the owner of the server
        {1.user.name} - The name of the bot"""
        def check(m):
            return m.author == ctx.message.author and m.channel == ctx.message.channel

        admin_guilds = get_user_admin_guilds(self.bot, ctx.message.author.id)

        if not is_private(ctx.message.channel):
            if ctx.message.guild not in admin_guilds:
                await ctx.send("You don't have permissions to diagnose this server.")
                return
            guild = ctx.message.guild
        else:
            if len(admin_guilds) == 1:
                guild = admin_guilds[0]
            else:
                guild_list = [str(i + 1) + ": " + admin_guilds[i].name for i in range(len(admin_guilds))]
                await ctx.send("For which server do you want to change the welcome message?\n\t0: *Cancel*\n\t"
                                    +"\n\t".join(guild_list))
                try:
                    answer = await self.bot.wait_for("message", timeout=60.0, check=check)
                    answer = int(answer.content)
                    if answer == 0:
                        await ctx.send("Changed your mind? Typical human.")
                        return
                    guild = admin_guilds[answer - 1]
                except IndexError:
                    await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
                    return
                except ValueError:
                    await ctx.send("That's not a valid answer.")
                    return
                except asyncio.TimeoutError:
                    await ctx.send("I guess you changed your mind.")
                    return
        if message is None:
            current_message = welcome_messages.get(guild.id, None)
            if current_message is None:
                current_message = welcome_pm.format(ctx.message.author, self.bot)
                await ctx.send("This server has no custom message, joining members get the default message:\n"
                                    "----------\n{0}".format(current_message))
            else:
                current_message = (welcome_pm + "\n" + current_message).format(ctx.message.author, self.bot)
                await ctx.send("This server has the following welcome message:\n"
                                    "----------\n``The first two lines can't be changed``\n{0}"
                                    .format(current_message))
            return
        if message.lower() in ["clear", "none", "delete", "remove"]:
            await ctx.send("Are you sure you want to delete this server's welcome message? `yes/no`\n"
                                "The default welcome message will still be shown.")
            try:
                reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                if reply.content.lower() not in ["yes", "y"]:
                    await ctx.send("No changes were made then.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("I guess you changed your mind...")
                return

            c = userDatabase.cursor()
            try:
                c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'welcome'", (guild.id,))
            finally:
                c.close()
                userDatabase.commit()
            await ctx.send("This server's welcome message was removed.")
            reload_welcome_messages()
            return

        if len(message) > 1200:
            await ctx.send("This message exceeds the character limit! ({0}/{1}".format(len(message), 1200))
            return
        try:
            complete_message = (welcome_pm+"\n"+message).format(ctx.message.author, self.bot)
        except Exception as e:
            await ctx.send("There is something wrong with your message.\n```{0}```".format(e))
            return

        await ctx.send("Are you sure you want this as your private welcome message?\n"
                            "----------\n``The first two lines can't be changed``\n{0}"
                            .format(complete_message))
        try:
            reply = await self.bot.wait_for("message", timeout=120.0, check=check)
            if reply.content.lower() not in ["yes", "y"]:
                await ctx.send("No changes were made then.")
                return
        except asyncio.TimeoutError:
            await ctx.send("I guess you changed your mind...")
            return

        c = userDatabase.cursor()
        try:
            # Safer to just delete old entry and add new one
            c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'welcome'", (guild.id,))
            c.execute("INSERT INTO server_properties(server_id, name, value) VALUES (?, 'welcome', ?)",
                      (guild.id, message,))
            await ctx.send("This server's welcome message has been changed successfully.")
        finally:
            c.close()
            userDatabase.commit()
            reload_welcome_messages()

    @commands.command(name="setchannel")
    @checks.is_admin()
    @checks.is_not_lite()
    async def set_announce_channel(self, ctx: commands.Context, *, name: str = None):
        """Changes the channel used for the bot's announcements

        If no channel is set, the bot will use the server's default channel."""
        def check(m):
            return m.author == ctx.message.author and m.channel == ctx.message.channel

        admin_guilds = get_user_admin_guilds(self.bot, ctx.message.author.id)

        if not is_private(ctx.message.channel):
            if ctx.message.guild not in admin_guilds:
                await ctx.send("You don't have permissions to diagnose this server.")
                return
            guild = ctx.message.guild
        else:
            if len(admin_guilds) == 1:
                guild = admin_guilds[0]
            else:
                server_list = [str(i + 1) + ": " + admin_guilds[i].name for i in range(len(admin_guilds))]
                await ctx.send(
                    "For which server do you want to change the announce channel?\n\t0: *Cancel*\n\t" + "\n\t"
                    .join(server_list))
                try:
                    answer = await self.bot.wait_for("message",timeout=60.0, check=check)
                    answer = int(answer.content)
                    if answer == 0:
                        await ctx.send("Changed your mind? Typical human.")
                        return
                    guild = admin_guilds[answer - 1]
                except ValueError:
                    await ctx.send("That's not a valid answer.")
                    return
                except IndexError:
                    await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
                    return
                except asyncio.TimeoutError:
                    await ctx.send("I guess you changed your mind.")
                    return

        if name is None:
            current_channel = announce_channels.get(guild.id, None)
            if current_channel is None:
                await ctx.send("This server has no custom channel set, {0} is used."
                                    .format(guild.default_channel.mention))
            else:
                channel = self.bot.get_channel_by_name(current_channel, guild)
                if channel is not None:
                    permissions = channel.permissions_for(get_member(self.bot, self.bot.user.id, guild))
                    if not permissions.read_messages or not permissions.send_messages:
                        await ctx.send("This server's announce channel is set to #**{0}** but I don't have "
                                            "permissions to use it. {1.mention} will be used instead."
                                            .format(current_channel, channel))
                        return
                    await ctx.send("This server's announce channel is {0.mention}".format(channel))
                else:
                    await ctx.send("This server's announce channel is set to #**{0}** but it doesn't exist. "
                                        "{1.mention} will be used instead."
                                        .format(current_channel, guild.default_channel))
            return
        if name.lower() in ["clear", "none", "delete", "remove"]:
            await ctx.send("Are you sure you want to delete this server's announce channel? `yes/no`\n"
                                "The server's default channel ({0.mention}) will still be used."
                                .format(guild.default_channel))
            try:
                reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                if reply.content.lower() not in ["yes", "y"]:
                    await ctx.send("No changes were made then.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("I guess you changed your mind...")
                return

            c = userDatabase.cursor()
            try:
                c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'announce_channel'", (guild.id,))
            finally:
                c.close()
                userDatabase.commit()
            await ctx.send("This server's announce channel was removed.")
            reload_welcome_messages()
            return

        channel = self.bot.get_channel_by_name(name, guild)
        if channel is None:
            await ctx.send("There is no channel with that name.")
            return

        permissions = channel.permissions_for(get_member(self.bot, self.bot.user.id, guild))
        if not permissions.read_messages or not permissions.send_messages:
            await ctx.send("I don't have permission to use {0.mention}.".format(channel))
            return

        await ctx.send("Are you sure you want {0.mention} as the announcement channel? `yes/no`"
                                .format(channel))
        try:
            reply = await self.bot.wait_for("message", timeout=120.0, check=check)
            if reply.content.lower() not in ["yes", "y"]:
                await ctx.send("No changes were made then.")
                return
        except asyncio.TimeoutError:
            await ctx.send("I guess you changed your mind...")
            return

        c = userDatabase.cursor()
        try:
            # Safer to just delete old entry and add new one
            c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'announce_channel'", (guild.id,))
            c.execute("INSERT INTO server_properties(server_id, name, value) VALUES (?, 'announce_channel', ?)",
                      (guild.id, channel.name,))
            await ctx.send("This server's announcement channel was changed successfully.\nRemember that if "
                                "the channel is renamed, you must set it again using this command.\nIf the channel "
                                "becomes unavailable for me in any way, {0.mention} will be used."
                                .format(guild.default_channel))
        finally:
            c.close()
            userDatabase.commit()
            reload_announce_channels()


def get_check_emoji(check: bool) -> str:
    return EMOJI[":white_check_mark:"] if check else EMOJI[":x:"]


def setup(bot):
    bot.add_cog(Admin(bot))
