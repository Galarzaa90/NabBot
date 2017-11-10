import inspect
import traceback
from contextlib import redirect_stdout

from discord.ext import commands

# Everything is imported to put it in /debug scope
from nabbot import NabBot
from utils import checks
from utils.database import *
from utils.discord import *
from utils.general import *
from utils.messages import *
from utils.tibia import *


class Owner:
    """Commands exclusive to bot owners"""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.sessions = set()

    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    def get_syntax_error(self, e):
        if e.text is None:
            return '```py\n{0.__class__.__name__}: {0}\n```'.format(e)
        return '```py\n{0.text}{1:>{0.offset}}\n{2}: {0}```'.format(e, '^', type(e).__name__)

    @commands.command(aliases=["reset"])
    @checks.is_owner()
    async def restart(self, ctx: discord.ext.commands.Context):
        """Shutdowns and starts the bot again.

        This command can only be used on pms"""
        if not is_private(ctx.message.channel):
            return True
        await ctx.send('Restarting...')
        await self.bot.logout()
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
            reply += "\n\t**{0.name}** - (Owner: {0.owner.name}#{0.owner.discriminator}) - {1} - {2} members"\
                .format(guild, tracked_worlds.get(guild.id, "No world tracked"), len(guild.members))
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

    @commands.command(hidden=True)
    @checks.is_owner()
    async def repl(self, ctx):
        """Starts a REPL session.
        
        While the session is active, python code can be run enclosing it with `single quotes`.
        To stop the REPL session, type `quit`, `exit` or `exit()`"""
        msg = ctx.message

        variables = {
            'ctx': ctx,
            'bot': self.bot,
            'message': msg,
            'server': msg.guild,
            'guild': msg.guild,
            'channel': msg.channel,
            'author': msg.author,
        }

        variables.update(globals())

        if msg.channel.id in self.sessions:
            await ctx.send('Already running a REPL session in this channel. Exit it with `quit`.')
            return

        self.sessions.add(msg.channel.id)
        await ctx.send('Enter code to execute or evaluate. `exit()` or `quit` to exit.')
        while True:
            def check(m):
                return m.content.startswith('`') and m.author == ctx.message.author and m.channel == ctx.message.channel
            try:
                response = await self.bot.wait_for("message", check=check)
            except asyncio.TimeoutError:
                return

            cleaned = self.cleanup_code(response.content)

            if cleaned in ('quit', 'exit', 'exit()'):
                await ctx.send('Exiting.')
                self.sessions.remove(msg.channel.id)
                return

            executor = exec
            if cleaned.count('\n') == 0:
                # single statement, potentially 'eval'
                try:
                    code = compile(cleaned, '<repl session>', 'eval')
                except SyntaxError:
                    pass
                else:
                    executor = eval

            if executor is exec:
                try:
                    code = compile(cleaned, '<repl session>', 'exec')
                except SyntaxError as e:
                    await ctx.send(self.get_syntax_error(e))
                    continue

            variables['message'] = response

            fmt = None
            stdout = io.StringIO()

            try:
                with redirect_stdout(stdout):
                    result = executor(code, variables)
                    if inspect.isawaitable(result):
                        result = await result
            except Exception as e:
                value = stdout.getvalue()
                fmt = '```py\n{}{}\n```'.format(value, traceback.format_exc())
            else:
                value = stdout.getvalue()
                if result is not None:
                    fmt = '```py\n{}{}\n```'.format(value, result)
                    variables['_'] = result
                elif value:
                    fmt = '```py\n{}\n```'.format(value)

            try:
                if fmt is not None:
                    if len(fmt) > 2000:
                        await msg.channel.send('Content too big to be printed.')
                    else:
                        await msg.channel.send(fmt)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                await msg.channel.send('Unexpected error: `{}`'.format(e))

    # Todo: Reduce number of messages

    @commands.command(aliases=["clean"])
    @checks.is_owner()
    @checks.is_not_lite()
    async def purge(self, ctx):
        """Performs a database cleanup

        Removes characters that have been deleted and users with no characters or no longer in server."""
        if not is_private(ctx.message.channel):
            return True
        c = userDatabase.cursor()
        try:
            c.execute("SELECT id FROM users")
            result = c.fetchall()
            if result is None:
                await ctx.send("There are no users registered.")
                return
            delete_users = list()
            await ctx.send("Initiating purge...")
            # Deleting users no longer in server
            for row in result:
                user = self.bot.get_member(row["id"])
                if user is None:
                    delete_users.append((row["id"],))
            if len(delete_users) > 0:
                c.executemany("DELETE FROM users WHERE id = ?", delete_users)
                await ctx.send("{0} user(s) no longer in the server were removed.".format(c.rowcount))

            # Deleting chars with non-existent user
            c.execute("SELECT name FROM chars WHERE user_id NOT IN (SELECT id FROM users)")
            result = c.fetchall()
            if len(result) >= 1:
                chars = ["**" + i["name"] + "**" for i in result]
                reply = "{0} char(s) were assigned to a non-existent user and were deleted:\n\t".format(len(result))
                reply += "\n\t".join(chars)
                await ctx.send(reply)
                c.execute("DELETE FROM chars WHERE user_id NOT IN (SELECT id FROM users)")

            # Removing deleted chars
            c.execute("SELECT name,last_level,vocation FROM chars")
            result = c.fetchall()
            if result is None:
                return
            delete_chars = list()
            rename_chars = list()
            # revoc_chars = list()
            for row in result:
                char = await get_character(row["name"])
                if char == ERROR_NETWORK:
                    await ctx.send("Couldn't fetch **{0}**, skipping...".format(row["name"]))
                    continue
                # Char was deleted
                if char == ERROR_DOESNTEXIST:
                    delete_chars.append((row["name"],))
                    await ctx.send("**{0}** doesn't exists, deleting...".format(row["name"]))
                    continue
                # Char was renamed
                if char['name'] != row["name"]:
                    rename_chars.append((char['name'], row["name"],))
                    await ctx.send(
                        "**{0}** was renamed to **{1}**, updating...".format(row["name"], char['name']))

            # No need to check if user exists cause those were removed already
            if len(delete_chars) > 0:
                c.executemany("DELETE FROM chars WHERE name LIKE ?", delete_chars)
                await ctx.send("{0} char(s) were removed.".format(c.rowcount))
            if len(rename_chars) > 0:
                c.executemany("UPDATE chars SET name = ? WHERE name LIKE ?", rename_chars)
                await ctx.send("{0} char(s) were renamed.".format(c.rowcount))

            # Remove users with no chars
            c.execute("SELECT id FROM users WHERE id NOT IN (SELECT user_id FROM chars)")
            result = c.fetchall()
            if len(result) >= 1:
                c.execute("DELETE FROM users WHERE id NOT IN (SELECT user_id FROM chars)")
                await ctx.send("{0} user(s) with no characters were removed.".format(c.rowcount))

            # Remove level ups of removed characters
            c.execute("DELETE FROM char_levelups WHERE char_id NOT IN (SELECT id FROM chars)")
            if c.rowcount > 0:
                await ctx.send(
                    "{0} level up registries from removed characters were deleted.".format(c.rowcount))
            c.execute("DELETE FROM char_deaths WHERE char_id NOT IN (SELECT id FROM chars)")
            # Remove deaths of removed characters
            if c.rowcount > 0:
                await ctx.send("{0} death registries from removed characters were deleted.".format(c.rowcount))
            await ctx.send("Purge done.")
            return
        finally:
            userDatabase.commit()
            c.close()


def setup(bot):
    bot.add_cog(Owner(bot))
