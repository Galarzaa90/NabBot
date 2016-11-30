import asyncio
from discord.ext import commands
import platform

from utils import *


class Owner:
    def __init__(self, bot: discord.Client):
        self.bot = bot

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    @is_pm()
    @asyncio.coroutine
    def restart(self, ctx):
        if not (ctx.message.channel.is_private and ctx.message.author.id in owner_ids):
            return
        yield from self.bot.say('Restarting...')
        self.bot.logout()
        log.warning("Closing NabBot")
        if platform.system() == "Linux":
            os.system("python3 restart.py {0}".format(ctx.message.author.id))
        else:
            os.system("python restart.py {0}".format(ctx.message.author.id))

        quit()

    # Shutdown command
    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    @is_pm()
    @asyncio.coroutine
    def shutdown(self, ctx):
        yield from self.bot.say('Shutdown...')
        self.bot.logout()
        log.warning("Closing NabBot")
        quit()

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    @asyncio.coroutine
    def debug(self, ctx, *, code: str):
        """Evaluates code."""
        if "os." in code:
            yield from self.bot.say("I won't run that.")
            return
        code = code.strip('` ')
        python = '```py\n{}\n```'
        result = None

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

    @commands.command(pass_context=True, hidden=True)
    @is_owner()
    @asyncio.coroutine
    def permissions(self, ctx, *, server_name=None):
        print(server_name)
        if server_name is None and ctx.message.channel.is_private:
            yield from self.bot.say("This commands requires a parameter when used in private channels.\n "
                                    "Specify the server you want to check permissions for.")
            return
        elif server_name is not None:
            server = getServerByName(self.bot, server_name)
            if server is None:
                yield from self.bot.say("I couldn't find a server with that name.")
                return
        else:
            server = ctx.message.server
        member = getMember(self.bot, self.bot.user.id, server)
        server_permissions = member.server_permissions
        reply_format = "\n\t{0} Read Messages\n\t{1} Send Messages\n\t{2} Manage Messages\n\t" \
                       "{3} Embed Links\n\t{4} Attach Files\n\t{5} Mention Everyone"
        reply = reply_format.format(getCheckEmoji(server_permissions.read_messages),
                                    getCheckEmoji(server_permissions.send_messages),
                                    getCheckEmoji(server_permissions.manage_messages),
                                    getCheckEmoji(server_permissions.embed_links),
                                    getCheckEmoji(server_permissions.attach_files),
                                    getCheckEmoji(server_permissions.mention_everyone))
        yield from self.bot.say("Server permissions:"+reply)
        channels = server.channels
        for channel in channels:
            if channel.type == discord.ChannelType.voice:
                continue
            channel_permissions = channel.permissions_for(member)
            reply = reply_format.format(getCheckEmoji(channel_permissions.read_messages),
                                        getCheckEmoji(channel_permissions.send_messages),
                                        getCheckEmoji(channel_permissions.manage_messages),
                                        getCheckEmoji(channel_permissions.embed_links),
                                        getCheckEmoji(channel_permissions.attach_files),
                                        getCheckEmoji(channel_permissions.mention_everyone))
            yield from self.bot.say("#{0} permissions:{1}".format(channel.name, reply))


def getCheckEmoji(check: bool):
    return EMOJI[":white_check_mark:"] if check else EMOJI[":x:"]


def setup(bot):
    bot.add_cog(Owner(bot))