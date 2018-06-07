import inspect
import platform
import traceback
from contextlib import redirect_stdout
from distutils.version import StrictVersion

import pkg_resources
from discord.ext import commands

# Everything is imported to put it in /debug scope
from nabbot import NabBot
from utils import checks
from utils.config import *
from utils.database import *
from utils.discord import *
from utils.general import *
from utils.messages import *
from utils.tibia import *
from utils.tibiawiki import *

req_pattern = re.compile(r"([\w]+)([><=]+)([\d.]+),([><=]+)([\d.]+)")
dpy_commit = re.compile(r"a\d+\+g([\w]+)")


class Owner:
    """Commands exclusive to bot owners"""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.sessions = set()

    @staticmethod
    def cleanup_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    @staticmethod
    def get_syntax_error(e):
        if e.text is None:
            return '```py\n{0.__class__.__name__}: {0}\n```'.format(e)
        return '```py\n{0.text}{1:>{0.offset}}\n{2}: {0}```'.format(e, '^', type(e).__name__)

    @commands.command(aliases=["reset"])
    @checks.is_owner()
    async def restart(self, ctx: discord.ext.commands.Context):
        """Shutdowns and starts the bot again.

        This command can only be used on pms"""
        if not is_private(ctx.channel):
            return True
        await ctx.send('Restarting...')
        await self.bot.logout()
        log.warning("Restarting NabBot")
        # If it was run using the restarter, this command still works the same
        os.system("python restart.py {0}".format(ctx.author.id))
        quit()

    @commands.command(name="load")
    @checks.is_owner()
    async def load_cog(self, ctx, cog: str):
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
            'guild': ctx.guild,
            'server': ctx.guild,
            'channel': ctx.channel,
            'author': ctx.author
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
                .format(guild, self.bot.tracked_worlds.get(guild.id, "No world tracked"), len(guild.members))
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
                content = answer.content
            except asyncio.TimeoutError:
                await ctx.send("You changed your mind then?")
                return
        guild_admins = list(set([g.owner for g in self.bot.guilds]))
        for admin in guild_admins:
            await admin.send("{0}\n\t-{1.mention}".format(content, ctx.author))
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
                return m.content.startswith('`') and m.author == ctx.author and m.channel == ctx.channel
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
        if not is_private(ctx.channel):
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
            c.execute("SELECT name,level,vocation FROM chars")
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
                    await ctx.send("**{0}** doesn't exist, deleting...".format(row["name"]))
                    continue
                # Char was renamed
                if char.name != row["name"]:
                    rename_chars.append((char.name, row["name"],))
                    await ctx.send(
                        "**{0}** was renamed to **{1}**, updating...".format(row["name"], char.name))

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

    @commands.command(aliases=["namechange", "rename"])
    @checks.is_owner()
    @checks.is_not_lite()
    @commands.guild_only()
    async def namelock(self, ctx, *, params):
        """Register the name of a new character that was namelocked.

        Characters that get namelocked can't be searched by their old name, so they must be reassigned manually.

        If the character got a name change (from the store), searching the old name redirects to the new name, so
        these are usually reassigned automatically.

        The syntax is:
        /namelock oldname,newname"""
        params = params.split(",")
        if len(params) != 2:
            await ctx.send("The correct syntax is: `/namelock oldname,newname")
            return

        old_name = params[0]
        new_name = params[1]
        with ctx.typing():
            c = userDatabase.cursor()
            try:
                c.execute("SELECT * FROM chars WHERE name LIKE ? LIMIT 1", (old_name,))
                old_char_db = c.fetchone()
                # If character wasn't registered, there's nothing to do.
                if old_char_db is None:
                    await ctx.send("I don't have a character registered with the name: **{0}**".format(old_name))
                    return
                # Search old name to see if there's a result
                try:
                    old_char = await get_character(old_name)
                except NetworkError:
                    await ctx.send("I'm having problem with 'the internet' as you humans say, try again.")
                    return
                # Check if returns a result
                if old_char is not None:
                    if old_name.lower() == old_char.name.lower():
                        await ctx.send("The character **{0}** wasn't namelocked.".format(old_char.name))
                    else:
                        await ctx.send(
                            "The character **{0}** was renamed to **{1}**.".format(old_name, old_char.name))
                        # Renaming is actually done in get_character(), no need to do anything.
                    return

                # Check if new name exists
                try:
                    new_char = await get_character(new_name)
                except NetworkError:
                    await ctx.send("I'm having problem with 'the internet' as you humans say, try again.")
                    return
                if new_char is None:
                    await ctx.send("The character **{0}** doesn't exist.".format(new_name))
                    return
                # Check if vocations are similar
                if not (old_char_db["vocation"].lower() in new_char.vocation.lower()
                        or new_char.vocation.lower() in old_char_db["vocation"].lower()):
                    await ctx.send("**{0}** was a *{1}* and **{2}** is a *{3}*. I think you're making a mistake."
                                   .format(old_char_db["name"], old_char_db["vocation"],
                                           new_char.name, new_char.vocation))
                    return
                confirm_message = "Are you sure **{0}** ({1} {2}) is **{3}** ({4} {5}) now? `yes/no`"
                await ctx.send(confirm_message.format(old_char_db["name"], abs(old_char_db["level"]),
                                                      old_char_db["vocation"], new_char.name, new_char.level,
                                                      new_char.vocation))

                def check(m):
                    return m.channel == ctx.channel and m.author == ctx.author

                try:
                    reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                    if reply.content.lower() not in ["yes", "y"]:
                        await ctx.send("No then? Alright.")
                        return
                except asyncio.TimeoutError:
                    await ctx.send("No answer? I guess you changed your mind.")
                    return

                # Check if new name was already registered
                c.execute("SELECT * FROM chars WHERE name LIKE ?", (new_char.name,))
                new_char_db = c.fetchone()

                if new_char_db is None:
                    c.execute("UPDATE chars SET name = ?, vocation = ?, level = ? WHERE id = ?",
                              (new_char.name, new_char.vocation, new_char.level, old_char_db["id"],))
                else:
                    # Replace new char with old char id and delete old char, reassign deaths and levelups
                    c.execute("DELETE FROM chars WHERE id = ?", (old_char_db["id"]), )
                    c.execute("UPDATE chars SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))
                    c.execute("UPDATE char_deaths SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))
                    c.execute("UPDATE char_levelups SET id = ? WHERE id = ?",
                              (old_char_db["id"], new_char_db["id"],))

                await ctx.send("Character renamed successfully.")
            finally:
                c.close()
                userDatabase.commit()

    @commands.command()
    @checks.is_owner()
    @checks.is_not_lite()
    async def merge(self, ctx, old_world: str, new_world: str):
        """Renames all references of an old world

        This command should updates all the database entries, changing all references of the old world to the new one

        This updates all characters' worlds and discord guild's tracked worlds to the new world.
        All the highscores entries of the old world will be deleted.

        This should be done immediately after the world merge occurs and not before, or else tracking will stop.

        Use this with caution as the damage can be irreversible.

        Example
        /merge Fidera Gladera
        """
        old_world = old_world.capitalize()
        new_world = new_world.capitalize()
        message = await ctx.send(f"Are you sure you want to merge **{old_world}** into **{new_world}**?\n"
                                 f"*This will affect all the Discord servers I'm in, and may be irreversible.*")
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("You took too long!")
            return
        if not confirm:
            await ctx.send("Good, I hate doing that.")
            return
        c = userDatabase.cursor()
        try:
            c.execute("UPDATE chars SET world = ? WHERE world LIKE ? ", (new_world, old_world))
            affected_chars = c.rowcount
            c.execute("UPDATE server_properties SET value = ? WHERE name = ? AND value LIKE ?",
                      (new_world, "world", old_world))
            affected_guilds = c.rowcount
            c.execute("DELETE FROM highscores WHERE world LIKE ?", (old_world,))
            await ctx.send(f"Moved **{affected_chars:,}** characters to {new_world}. "
                           f"**{affected_guilds}** discord servers were affected.\n\n"
                           f"Enjoy **{new_world}**! 🔥♋")
            self.bot.reload_worlds()
        finally:
            c.close()
            userDatabase.commit()

    @commands.command()
    @checks.is_owner()
    async def leave(self, ctx, *, server: str=None):
        """Makes the bot leave a server"""
        if server is None:
            await ctx.send("Tell me the name of id of the server you want me to leave.")
            return

        id_regex = re.compile(r'([0-9]{15,21})$')
        match = id_regex.match(server)
        if match:
            guild = self.bot.get_guild(int(match.group(1)))
            if guild is None:
                await ctx.send(f"I'm not in any server with the id {server}.")
                return
        else:
            guild = self.bot.get_guild_by_name(server)
            if guild is None:
                await ctx.send(f"I'm not in any server named {server}")
                return

        embed = discord.Embed(title=guild.name)
        embed.set_footer(text="Created")
        embed.set_author(name=guild.owner.name, icon_url=get_user_avatar(guild.owner))
        embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="Members", value=str(guild.member_count))
        embed.add_field(name="Joined", value=str(guild.me.joined_at))
        embed.timestamp = guild.created_at

        message = await ctx.send("Are you sure you want me to leave this server?", embed=embed)
        confirm = await ctx.react_confirm(message)
        if confirm is None:
            await ctx.send("Forget it then.")
            return
        if confirm is False:
            await ctx.send("Ok, I will stay there.")
            return

        try:
            await guild.leave()
            await ctx.send(f"I just left the server **{guild.name}**.")
        except discord.HTTPException:
            await ctx.send("Something went wrong, I guess they don't want to let me go.")

    @commands.command()
    @checks.is_owner()
    async def versions(self, ctx):
        """Shows version info about NabBot and its dependencies

        An X is displayed if the minimum required version is not met, this is likely to cause problems.
        An exclamation sign is displayed when the version installed exceeds the highest version supported
           This means there might be breaking changes, causing the bot to malfunction.
        A checkmark indicates that the dependency is inside the allowed range."""
        def comp(operator, object1, object2):
            if operator == ">=":
                return object1 >= object2
            if operator == ">":
                return object1 > object2
            if operator == "==":
                return object1 == object2
            if operator == "<":
                return object1 < object2
            if operator == "<=":
                return object1 <= object2

        discordpy_version = pkg_resources.get_distribution("discord.py").version
        m = dpy_commit.search(discordpy_version)
        if m:
            discordpy_url = f"https://github.com/Rapptz/discord.py/commit/{m.group(1)}"
            dpy = f"[v{discordpy_version}]({discordpy_url})"
        else:
            dpy = f"v{discordpy_version}"

        embed = discord.Embed(title="NabBot", description="v"+self.bot.__version__)
        embed.add_field(name="discord.py", value=dpy)
        embed.set_footer(text=f"Python v{platform.python_version()} on {platform.platform()}",
                         icon_url="https://www.python.org/static/apple-touch-icon-precomposed.png")

        try:
            with open("./requirements.txt") as f:
                requirements = f.read()
        except FileNotFoundError:
            embed.add_field(name="Error", value="`requirements.txt` wasn't found in NabBot's root directory.")
            await ctx.send(embed=embed)
            return

        dependencies = req_pattern.findall(requirements)
        for package in dependencies:
            version = pkg_resources.get_distribution(package[0]).version
            if not comp(package[1], StrictVersion(version), StrictVersion(package[2])):
                value = f"{ctx.tick(False)}v{version}\n`At least v{package[2]} expected`"
            elif not comp(package[3], StrictVersion(version), StrictVersion(package[4])):
                value = f"⚠v{version}\n`Only below v{package[4]} tested`"
            else:
                value = f"{ctx.tick(True)}v{version}"
            embed.add_field(name=package[0], value=value)
        await ctx.send(embed=embed)

    @checks.is_owner()
    @commands.command()
    async def ping(self, ctx):
        """Shows the bot's response times."""
        resp = await ctx.send('Pong! Loading...')
        diff = resp.created_at - ctx.message.created_at
        await resp.edit(content=f'Pong! That took {1000*diff.total_seconds():.1f}ms.\n'
                                f'Socket latency is {1000*self.bot.latency:.1f}ms')


def setup(bot):
    bot.add_cog(Owner(bot))
