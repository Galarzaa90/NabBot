from discord.ext import commands
import platform

# Eeverything is imported to put it in /debug scope
from nabbot import announce_death, announce_level
from utils.checks import is_owner_check
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

    def __local_check(self, ctx):
        return is_owner_check(ctx)

    @commands.command(pass_context=True, aliases=["reset", "reload"])
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
    @asyncio.coroutine
    def servers(self):
        """Lists the servers the bot is in"""
        reply = "I'm in the following servers:"
        for server in self.bot.servers:
            reply += "\n\t**{0.name}** - (Owner: {0.owner.name}#{0.owner.discriminator}) - {1}"\
                .format(server, tracked_worlds.get(server.id, "No world tracked."))
        yield from self.bot.say(reply)

    @commands.command(pass_context=True,aliases=["message_admins", "adminsmessage", "msgadmins", "adminsmsg"])
    @asyncio.coroutine
    def admins_message(self, ctx, *, content: str=None):
        if content is None:
            yield from self.bot.say("Tell me the message you want to sent to server admins."
                                    "\nReply `cancel/none` to cancel.")
            answer = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                          timeout=60.0)
            if answer is None:
                yield from self.bot.say("You changed your mind then?")
                return
            if answer.content.lower().strip() in ["cancel", "none"]:
                yield from self.bot.say("Nevermind then.")
                return
            content = answer
        server_admins = list(set([s.owner for s in self.bot.servers]))
        for admin in server_admins:
            yield from self.bot.send_message(admin, "{0}\n\t-{1.mention}".format(content, ctx.message.author))
            pass
        yield from self.bot.say("Message sent to "+join_list(["@"+a.name for a in server_admins], ", ", " and "))


def setup(bot):
    bot.add_cog(Owner(bot))