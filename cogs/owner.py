from discord.ext import commands
import platform

# Everything is imported to put it in /debug scope
from nabbot import announce_death, announce_level
from utils import checks
from utils.discord import *
from utils.database import *
from utils.general import *
from utils.messages import *
from utils.tibia import *


class Owner:
    """Commands exclusive to bot owners"""
    def __init__(self, bot: discord.Client):
        self.bot = bot

    @commands.command(aliases=["reset", "reload"])
    @checks.is_owner()
    @asyncio.coroutine
    def restart(self, ctx: discord.ext.commands.Context):
        """Shutdowns and starts the bot again.

        This command can only be used on pms"""
        if not is_private(ctx.message.channel):
            return True
        yield from ctx.send('Restarting...')
        self.bot.logout()
        log.warning("Restarting NabBot")
        # If it was run using the restarter, this command still works the same
        if platform.system() == "Linux":
            os.system("python3 restart.py {0}".format(ctx.message.author.id))
        else:
            os.system("python restart.py {0}".format(ctx.message.author.id))
        quit()

    @commands.command()
    @checks.is_owner()
    @asyncio.coroutine
    def debug(self, ctx, *, code: str):
        """Evaluates code."""
        if "os." in code:
            yield from ctx.send("I won't run that.")
            return
        code = code.strip('` ')
        python = '```py\n{}\n```'

        env = {
            'bot': self.bot,
            'ctx': ctx,
            'message': ctx.message,
            'guild': ctx.message.guild,
            'server': ctx.message.guild,
            'channel': ctx.message.channel,
            'author': ctx.message.author
        }

        env.update(globals())

        try:
            result = eval(code, env)
            if asyncio.iscoroutine(result):
                result = yield from result
        except Exception as e:
            yield from ctx.send(python.format(type(e).__name__ + ': ' + str(e)))
            return

        yield from ctx.send(python.format(result))

    @commands.command()
    @checks.is_owner()
    @asyncio.coroutine
    def servers(self, ctx):
        """Lists the servers the bot is in"""
        reply = "I'm in the following servers:"
        for guild in self.bot.guilds:
            reply += "\n\t**{0.name}** - (Owner: {0.owner.name}#{0.owner.discriminator}) - {1}"\
                .format(guild, tracked_worlds.get(guild.id, "No world tracked."))
        yield from ctx.send(reply)

    @commands.command(aliases=["message_admins", "adminsmessage", "msgadmins", "adminsmsg"])
    @checks.is_owner()
    @asyncio.coroutine
    def admins_message(self, ctx, *, content: str=None):
        """Sends a message to all server owners."""
        if content is None:
            yield from ctx.send("Tell me the message you want to sent to server admins."
                                "\nReply `cancel/none` to cancel.")

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author
            try:
                answer = yield from self.bot.wait_for("message", timeout=60.0, check=check)
                if answer.content.lower().strip() in ["cancel", "none"]:
                    yield from ctx.send("Nevermind then.")
                    return
                content = answer
            except asyncio.TimeoutError:
                yield from ctx.send("You changed your mind then?")
                return
        guild_admins = list(set([g.owner for g in self.bot.guilds]))
        for admin in guild_admins:
            yield from admin.send("{0}\n\t-{1.mention}".format(content, ctx.message.author))
            pass
        yield from ctx.send("Message sent to "+join_list(["@"+a.name for a in guild_admins], ", ", " and "))


def setup(bot):
    bot.add_cog(Owner(bot))