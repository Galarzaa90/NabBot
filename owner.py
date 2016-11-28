import asyncio
from discord.ext import commands
import platform

from utils import *


class Owner:
    def __init__(self, bot):
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


def setup(bot):
    bot.add_cog(Owner(bot))