from discord.ext import commands
import platform

# Eeverything is imported to put it in /debug scope
from nabbot import announce_death, announce_level
from utils.discord import *
from utils.database import *
from utils.general import *
from utils.messages import *
from utils.tibia import *
from utils import checks


class Owner:
    """Commands exclusive to bot owners"""
    def __init__(self, bot: discord.Client):
        self.bot = bot

    @commands.command(pass_context=True, aliases=["reset", "reload"])
    @checks.is_owner()
    @asyncio.coroutine
    def restart(self, ctx: discord.ext.commands.Context):
        """Shutdowns and starts the bot again.

        This command can only be used on pms"""
        if not ctx.message.channel.is_private:
            return True
        yield from self.bot.say('Restarting...')
        self.bot.logout()
        log.warning("Restarting NabBot")
        # If it was run using the restarter, this command still works the same
        if platform.system() == "Linux":
            os.system("python3 restart.py {0}".format(ctx.message.author.id))
        else:
            os.system("python restart.py {0}".format(ctx.message.author.id))

        quit()

    @commands.command(pass_context=True)
    @checks.is_owner()
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

    @commands.command()
    @checks.is_owner()
    @asyncio.coroutine
    def servers(self):
        """Lists the servers the bot is in"""
        reply = "I'm in the following servers:"
        for server in self.bot.servers:
            reply += "\n\t**{0.name}** - (Owner: {0.owner.name}#{0.owner.discriminator}) - {1}"\
                .format(server, tracked_worlds.get(server.id, "No world tracked."))
        yield from self.bot.say(reply)

def setup(bot):
    bot.add_cog(Owner(bot))