import traceback

from discord.ext import commands

# Everything is imported to put it in /debug scope
from nabbot import NabBot
from utils import checks
from utils.discord import *
from utils.database import *
from utils.general import *
from utils.messages import *
from utils.tibia import *


class Owner:
    """Commands exclusive to bot owners"""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.command(aliases=["reset"])
    @checks.is_owner()
    async def restart(self, ctx: discord.ext.commands.Context):
        """Shutdowns and starts the bot again.

        This command can only be used on pms"""
        if not is_private(ctx.message.channel):
            return True
        await ctx.send('Restarting...')
        self.bot.logout()
        log.warning("Restarting NabBot")
        # If it was run using the restarter, this command still works the same
        os.system("python restart.py {0}".format(ctx.message.author.id))
        quit()

    @commands.command(name="load")
    @checks.is_owner()
    async def load_cog(self, ctx, cog : str):
        """Loads a cog"""
        try:
            self.bot.load_extension(cog)
            await ctx.send("Cog loaded successfully.")
        except Exception as e:
            await ctx.send('{}: {}'.format(type(e).__name__, e))

    @commands.command(name="unload")
    @checks.is_owner()
    async def unload_cog(self, ctx, cog: str):
        """Unloads a cog"""
        try:
            self.bot.unload_extension(cog)
            await ctx.send("Cog unloaded successfully.")
        except Exception as e:
            await ctx.send('{}: {}'.format(type(e).__name__, e))

    @commands.command()
    @checks.is_owner()
    async def debug(self, ctx, *, code: str):
        """Evaluates code."""
        if "os." in code:
            await ctx.send("I won't run that.")
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
                result = await result
        except Exception:
            await ctx.send(python.format(traceback.format_exc()))
            return

        await ctx.send(python.format(result))

    @commands.command()
    @checks.is_owner()
    async def servers(self, ctx):
        """Lists the servers the bot is in"""
        reply = "I'm in the following servers:"
        for guild in self.bot.guilds:
            reply += "\n\t**{0.name}** - (Owner: {0.owner.name}#{0.owner.discriminator}) - {1}"\
                .format(guild, tracked_worlds.get(guild.id, "No world tracked."))
        await ctx.send(reply)

    @commands.command(aliases=["message_admins", "adminsmessage", "msgadmins", "adminsmsg"])
    @checks.is_owner()
    async def admins_message(self, ctx, *, content: str=None):
        """Sends a message to all server owners."""
        if content is None:
            await ctx.send("Tell me the message you want to send to server admins.\nReply `cancel/none` to cancel.")

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author
            try:
                answer = await self.bot.wait_for("message", timeout=60.0, check=check)
                if answer.content.lower().strip() in ["cancel", "none"]:
                    await ctx.send("Nevermind then.")
                    return
                content = answer
            except asyncio.TimeoutError:
                await ctx.send("You changed your mind then?")
                return
        guild_admins = list(set([g.owner for g in self.bot.guilds]))
        for admin in guild_admins:
            await admin.send("{0}\n\t-{1.mention}".format(content, ctx.message.author))
            pass
        await ctx.send("Message sent to "+join_list(["@"+a.name for a in guild_admins], ", ", " and "))


def setup(bot):
    bot.add_cog(Owner(bot))