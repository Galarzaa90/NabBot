import asyncio
from discord.ext import commands
import platform

from utils import *
from utils_tibia import *


class Owner:
    """Commands exclusive to bot owners"""
    def __init__(self, bot: discord.Client):
        self.bot = bot

    @commands.command(pass_context=True, aliases=["reset"])
    @is_owner()
    @asyncio.coroutine
    def restart(self, ctx: discord.ext.commands.Context):
        """Shutdowns and starts the bot again.

        This command can only be used on pms"""
        if not ctx.message.channel.is_private:
            return True
        yield from self.bot.say('Restarting...')
        self.bot.logout()
        log.warning("Closing NabBot")
        if platform.system() == "Linux":
            os.system("python3 restart.py {0}".format(ctx.message.author.id))
        else:
            os.system("python restart.py {0}".format(ctx.message.author.id))

        quit()

    # Shutdown command
    @commands.command(pass_context=True, aliases=["close"])
    @is_owner()
    @asyncio.coroutine
    def shutdown(self, ctx):
        """Shutdowns the bot

        This command can only be used on pms"""
        if not ctx.message.channel.is_private:
            return True
        yield from self.bot.say('Shutdown...')
        self.bot.logout()
        log.warning("Closing NabBot")
        quit()

    @commands.command(pass_context=True)
    @is_owner()
    @asyncio.coroutine
    def debug(self, ctx: discord.ext.commands.Context, *, code: str):
        """Evaluates code."""
        if "os." in code:
            yield from self.bot.say("I won't run that.")
            return
        code = code.strip('` ')
        python = '```py\n{}\n```'

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'message': ctx.message,
            'server': ctx.message.server,
            'channel': ctx.message.channel,
            'author': ctx.message.author
        }

        env.update(globals())

        try:
            result = eval(code, env)
            if asyncio.iscoroutine(result):
                result = yield from result
        except Exception as e:
            yield from self.bot.say(python.format(type(e).__name__ + ': ' + str(e)))
            return

        yield from self.bot.say(python.format(result))

    @commands.command(pass_context=True)
    @is_owner()
    @asyncio.coroutine
    def diagnose(self, ctx: discord.ext.commands.Context, *, server_name=None):
        """Checks the bot's necessary permissions and if it has a correct ask channel

        If server_name is specified, the permissions for that server will be checked
        if no server_name is specified, the current server's permissions will be checked
        If it's used from a private message, server_name is required."""
        if server_name is None and ctx.message.channel.is_private:
            yield from self.bot.say("This commands requires a parameter when used in private channels.\n "
                                    "Specify the server you want to check permissions for.")
            return
        elif server_name is not None:
            server = get_server_by_name(self.bot, server_name)
            if server is None:
                yield from self.bot.say("I couldn't find a server with that name.")
                return
        else:
            server = ctx.message.server
        member = get_member(self.bot, self.bot.user.id, server)
        server_perms = member.server_permissions

        channels = server.channels
        not_read_messages = []
        not_send_messages = []
        not_manage_messages = []
        not_embed_links = []
        not_attach_files = []
        not_mention_everyone = []
        count = 0
        for channel in channels:
            if channel.type == discord.ChannelType.voice:
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

        channel_lists_list = [not_read_messages, not_send_messages, not_manage_messages, not_embed_links,
                              not_attach_files, not_mention_everyone]
        permission_names_list = ["Read Messages", "Send Messages", "Manage Messages", "Embed Links", "Attach Files",
                                 "Mention Everyone"]
        server_wide_list = [server_perms.read_messages, server_perms.send_messages, server_perms.manage_messages,
                            server_perms.embed_links, server_perms.attach_files, server_perms.mention_everyone]

        reply = "Permissions for {0.name}:\n".format(server)
        i = 0
        while i < len(channel_lists_list):
            reply += "**{0}**\n\t{1} Server wide".format(permission_names_list[i], get_check_emoji(server_wide_list[i]))
            if len(channel_lists_list[i]) == 0:
                reply += "\n\t{0} All channels\n".format(get_check_emoji(True))
            elif len(channel_lists_list[i]) == count:
                reply += "\n\t All channels\n".format(get_check_emoji(False))
            else:
                channel_list = ["#" + x.name for x in channel_lists_list[i]]
                reply += "\n\t{0} Not in: {1}\n".format(get_check_emoji(False), ",".join(channel_list))
            i += 1

        ask_channel = get_channel_by_name(self.bot, ask_channel_name, server)
        reply += "\nAsk channel:\n\t"
        if ask_channel is not None:
            reply += "{0} Enabled: {1.mention}".format(get_check_emoji(True), ask_channel)
        else:
            reply += "{0} Not enabled".format(get_check_emoji(False))

        log_channel = get_channel_by_name(self.bot, log_channel_name, server)
        reply += "\nLog channel:\n\t"
        if log_channel is not None:
            reply += "{0} Enabled: {1.mention}".format(get_check_emoji(True), log_channel)
        else:
            reply += "{0} Not enabled".format(get_check_emoji(False))
        yield from self.bot.say(reply)
        return


def get_check_emoji(check: bool) -> str:
    return EMOJI[":white_check_mark:"] if check else EMOJI[":x:"]


def setup(bot):
    bot.add_cog(Owner(bot))