import inspect
import platform
import textwrap
import traceback
from collections import defaultdict
from contextlib import redirect_stdout
from distutils.version import StrictVersion

import pkg_resources

# Exposing for /debug command
from .utils.database import get_affected_count
from nabbot import NabBot
from .utils import *
from .utils import checks
from .utils.context import NabCtx
from .utils.messages import *
from .utils.errors import *
from .utils.timing import *
from .utils.pages import Pages
from .utils.errors import CannotPaginate
from .utils.tibia import *

log = logging.getLogger("nabbot")

req_pattern = re.compile(r"([\w.]+)([><=]+)([\d.]+),([><=]+)([\d.]+)")
dpy_commit = re.compile(r"a(\d+)\+g([\w]+)")


class Owner(commands.Cog, CogUtils):
    """Commands exclusive to bot owners"""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self._last_result = None
        self.sessions = set()

    # region Commands
    @commands.command(aliases=["notifyadmins"])
    @checks.owner_only()
    async def admins_message(self, ctx: NabCtx, *, content: str = None):
        """Sends a private message to all server owners.

        Notifies all the owners of the servers where the bot is in.
        If no message is specified at first, the bot will ask for a message to send.

        The message contains a signature to indicate who wrote the message.
        """
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
        await ctx.send("Message sent to "+join_list(["@"+a.name for a in guild_admins], ", ", " and "))

    @checks.owner_only()
    @commands.command()
    async def announcement(self, ctx: NabCtx, *, message):
        """Sends an announcement to all servers with a sererlog."""
        embed = discord.Embed(title="📣 Owner Announcement", colour=discord.Colour.blurple(),
                              timestamp=dt.datetime.now())
        embed.set_author(name="Support Server", url="https://discord.gg/NmDvhpY", icon_url=self.bot.user.avatar_url)
        embed.set_footer(text=f"By {ctx.author}", icon_url=get_user_avatar(ctx.author))
        embed.description = message

        msg = await ctx.send("This message will be sent to all serverlogs. Do you want to send it?", embed=embed)
        confirm = await ctx.react_confirm(msg, delete_after=True)
        if not confirm:
            await ctx.send("Ok then.")
            return
        count = 0
        msg = await ctx.send(f"{config.loading_emoji} Sending messages...")
        for guild in self.bot.guilds:
            success = await self.bot.send_log_message(guild, embed=embed)
            if success:
                count += 1
        await safe_delete_message(msg)
        await ctx.success(f"Message sent to {count:,} servers.")

    # noinspection PyBroadException
    @checks.owner_only()
    @commands.command(name="eval")
    async def _eval(self, ctx: NabCtx, *, body: str):
        """Evaluates Python code.

        This commands lets you evaluate python code. If no errors are returned, the bot will react to the command call.
        To show the result, you have to use `print()`.
        Asynchronous functions must be waited for using `await`.
        To show the results of the last command, use `print(_)`.
        """
        if "os." in body:
            await ctx.send("I won't run that.")
            return
        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "server": ctx.guild,
            "guild": ctx.guild,
            "message": ctx.message,
            "_": self._last_result
        }

        env.update(globals())

        body = self.cleanup_code(body)
        stdout = io.StringIO()

        to_compile = f"async def func():\n{textwrap.indent(body, '  ')}"

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env["func"]
        try:
            with redirect_stdout(stdout):
                start = time.perf_counter()
                ret = await func()
                run_time = time.perf_counter()-start
        except Exception:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction(config.true_emoji.replace("<", "").replace(">", ""))
            except discord.HTTPException:
                pass

            embed = discord.Embed(colour=discord.Colour.teal())
            embed.set_footer(text=f"Executed in {run_time*1000:,.4f} ms")
            embed.set_author(name=ctx.author.name, icon_url=get_user_avatar(ctx.author))
            if ret is not None:
                self._last_result = ret

            if ret is None and value:
                embed.title = "Output"
                embed.description = f'```py\n{value}\n```'
            elif ret and value:
                embed.title = "Output"
                embed.description = f'```py\n{value}\n```'
                embed.add_field(name=f"Result (Type: {type(ret).__name__})", value=f'```py\n{ret}\n```', inline=False)
            elif ret and not value:
                embed.title = f"Result (Type: {type(ret).__name__})"
                embed.description = f'```py\n{ret}\n```'
            else:
                return
            await ctx.send(embed=embed)

    @checks.owner_only()
    @commands.command(name="invalidworlds")
    async def invalid_worlds(self, ctx: NabCtx):
        """Checks if there are any characters in invalid worlds or servers tracking invalid worlds.

        They can be fixed by using the merge command to rename them to their corresponding new name."""
        async with ctx.pool.acquire() as conn:
            invalid = defaultdict(lambda: {"servers": 0, "characters": 0})
            # Count servers tracking other worlds
            rows = await conn.fetch("SELECT count(*), value as world FROM server_property "
                                    "WHERE key = 'world' AND NOT value = ANY($1) "
                                    "GROUP BY 2", tibia_worlds)
            for row in rows:
                invalid[row["world"]]["servers"] = row["count"]
            # Count characters in other worlds
            rows = await conn.fetch('SELECT count(*), world FROM "character" '
                                    'WHERE NOT world = ANY($1) '
                                    'GROUP BY 2', tibia_worlds)
            for row in rows:
                invalid[row["world"]]["characters"] = row["count"]

            entries = [f"**{k}** - {v['servers']} servers, {v['characters']} characters" for k, v in invalid.items()]

            pages = Pages(ctx, entries=entries, per_page=10)
            pages.embed.title = f"Invalid worlds"
            try:
                await pages.paginate()
            except CannotPaginate as e:
                await ctx.error(e)

    @commands.command()
    @checks.owner_only()
    async def leave(self, ctx: NabCtx, *, server: str):
        """Makes the bot leave a server.

        The bot will ask for confirmation before leaving the server.

        Once the bot has left a server, only a server administrator can add it back.
        """
        id_regex = re.compile(r'([0-9]{15,21})$')
        match = id_regex.match(server)
        if match:
            guild = self.bot.get_guild(int(match.group(1)))
            if guild is None:
                await ctx.error(f"I'm not in any server with the id {server}.")
                return
        else:
            guild = self.bot.get_guild_by_name(server)
            if guild is None:
                await ctx.error(f"I'm not in any server named {server}")
                return

        embed = discord.Embed(title=guild.name, timestamp=guild.created_at)
        embed.set_footer(text="Created")
        embed.set_author(name=guild.owner.name, icon_url=get_user_avatar(guild.owner))
        embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="Members", value=str(guild.member_count))
        embed.add_field(name="Joined", value=str(guild.me.joined_at))

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
            await ctx.success(f"I just left the server **{guild.name}**.")
        except discord.HTTPException as e:
            log.warning(f"{self.tag} Could not leave server: {e}")
            await ctx.error("Something went wrong, I guess they don't want to let me go.")

    @commands.command(name="load")
    @checks.owner_only()
    async def load_cog(self, ctx: NabCtx, cog: str):
        """Loads a cog.

        If there's an error while compiling, it will be displayed here.
        Any cog can be loaded here, including cogs made by user.

        When loading and unloading cogs in subdirectories, periods (`.`) are used instead of slashes (`/`).
        For example, a cog found in `cogs/tibia.py` would be loaded as `cogs.tibia`.
        """
        try:
            self.bot.load_extension(cog)
            await ctx.send(f"{ctx.tick()} Cog loaded successfully.")
        except Exception as e:
            await ctx.send('{}: {}'.format(type(e).__name__, e))

    @commands.command(usage="<old world> <new world>")
    @checks.owner_only()
    async def merge(self, ctx: NabCtx, old_world: str, new_world: str):
        """Renames all references of an old world to a new one.

        This command should updates all the database entries, changing all references of the old world to the new one

        This updates all characters' worlds and discord guild's tracked worlds to the new world.
        All the highscores entries of the old world will be deleted.

        This should be done immediately after the world merge occurs and not before, or else tracking will stop.

        Use this with caution as the damage can be irreversible.

        Example: `merge Fidera Gladera`
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
        async with ctx.pool.acquire() as conn:
            result = await conn.execute('UPDATE "character" SET world = $1 WHERE world = $2', new_world, old_world)
            affected_chars = get_affected_count(result)
            result = await conn.execute("UPDATE server_property SET VALUE = $1 WHERE key = 'world' AND value = $2",
                                        new_world, old_world)
            affected_guilds = get_affected_count(result)
            await conn.execute("DELETE FROM highscores WHERE world = $1", old_world)
            await ctx.send(f"Moved **{affected_chars:,}** characters to {new_world}. "
                           f"**{affected_guilds}** discord servers were affected.\n\n"
                           f"Enjoy **{new_world}**! 🔥♋")
            await self.bot.reload_worlds()

    @commands.command(aliases=["namechange", "rename"], usage="<old name>,<new name>")
    @checks.owner_only()
    @checks.not_lite_only()
    @commands.guild_only()
    async def namelock(self, ctx: NabCtx, *, params):
        """Register the name of a new character that was namelocked.

        Characters that get namelocked can't be searched by their old name, so they must be reassigned manually.

        If the character got a name change (from the store), searching the old name redirects to the new name, so
        these are usually reassigned automatically.

        In order for the command to work, the following conditions must be met:

        - The old name must exist in NabBot's characters database.
        - The old name must not be a valid character in Tibia.com
        - The new name must be a valid character in Tibia.com
        - They must have the same vocation, not considering promotions.
        """
        params = params.split(",")
        if len(params) != 2:
            await ctx.send("The correct syntax is: `/namelock oldname,newname")
            return

        old_name = params[0]
        new_name = params[1]

        with ctx.typing():
            old_char_db = await DbChar.get_by_name(ctx.pool, old_name)
            # If character wasn't registered, there's nothing to do.
            if old_char_db is None:
                await ctx.error(f"I don't have a character registered with the name: **{old_name}**")
                return
            # Search old name to see if there's a result
            try:
                old_char = await get_character(ctx.bot, old_name)
            except NetworkError:
                await ctx.error("I'm having problem with 'the internet' as you humans say, try again.")
                return
            # Check if returns a result
            if old_char is not None:
                if old_name.lower() == old_char.name.lower():
                    await ctx.error(f"The character **{old_char.name}** wasn't namelocked.")
                else:
                    await ctx.success(f"The character **{old_name}** was renamed to **{old_char.name}**.")
                    # Renaming is actually done in get_character(), no need to do anything.
                return

            # Check if new name exists
            try:
                new_char = await get_character(ctx.bot, new_name)
                if new_char is None:
                    await ctx.error(f"The character **{new_name}** doesn't exist.")
                    return
            except NetworkError:
                await ctx.error("I'm having problem with 'the internet' as you humans say, try again.")
                return

            # Check if vocations are similar
            if not (old_char_db.vocation.lower() in new_char.vocation.value.lower()
                    or new_char.vocation.value.lower() in old_char_db.vocation.lower()):
                await ctx.error(f"**{old_char_db.name}** was a *{old_char_db.vocation}* and "
                                f"**{new_char.name}** is a *{new_char.vocation.value}*. "
                                f"I think you're making a mistake.")
                return

            await ctx.send(f"Are you sure **{old_char_db.name}** ({abs(old_char_db.level)} {old_char_db.vocation}) is"
                           f" **{new_char.name}** ({new_char.level} {new_char.vocation}) now? `yes/no`")

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
            new_char_db = await DbChar.get_by_name(ctx.pool, new_char.name)

            async with ctx.pool.acquire() as conn:
                if new_char_db is None:
                    await old_char_db.update_level(conn, new_char.level)
                    await old_char_db.update_name(conn, new_char.name)
                    await old_char_db.update_vocation(conn, new_char.vocation.value)
                else:
                    # Replace new char with old char id and delete old char, reassign deaths and levelups
                    # TODO: Handle conflicts, specially in deaths
                    await conn.execute('DELETE FROM "character" WHERE id = $1', old_char_db.id)
                    await conn.execute('UPDATE "character" SET id = $1 WHERE id = $2',
                                       old_char_db.id, new_char_db.id)
                    await conn.execute("UPDATE character_death SET id = $1 WHERE id = $2",
                                       old_char_db.id, new_char_db.id)
                    await conn.execute("UPDATE character_levelup SET id = $1 WHERE id = $2",
                                       old_char_db.id, new_char_db.id)

            await ctx.success("Character renamed successfully.")

    @checks.owner_only()
    @commands.command()
    async def ping(self, ctx: NabCtx):
        """Shows the bot's response times."""
        resp = await ctx.send('Pong! Loading...')
        diff = resp.created_at - ctx.message.created_at
        await resp.edit(content=f'Pong! That took {1000*diff.total_seconds():.1f}ms.\n'
                                f'Socket latency is {1000*self.bot.latency:.1f}ms')

    @checks.owner_only()
    @commands.command(name="reload")
    async def reload_cog(self, ctx: NabCtx, *, cog):
        """Reloads a cog (module)"""
        # noinspection PyBroadException
        try:
            self.bot.unload_extension(cog)
            self.bot.load_extension(cog)
        except ModuleNotFoundError:
            await ctx.error("Cog not found.")
        except Exception:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')
        else:
            await ctx.success(f"Cog reloaded successfully.")

    @checks.owner_only()
    @commands.command(name="reloadconfig")
    async def reload_config(self, ctx: NabCtx):
        """Reloads the configuration file."""
        try:
            config.parse()
            await ctx.success(f"Config file reloaded.")
        except Exception:
            await ctx.send(f'```py\n{traceback.format_exc()}\n```')

    @commands.command(hidden=True)
    @checks.owner_only()
    async def repl(self, ctx: NabCtx):
        """Starts a REPL session in the current channel.

        Similar to `eval`, but this keeps a running sesion where variables and results are stored.```.
        """
        variables = {
            "ctx": ctx,
            "bot": self.bot,
            "message": ctx.message,
            "server": ctx.guild,
            "guild": ctx.guild,
            "channel": ctx.channel,
            "author": ctx.author,
            "_": None
        }

        variables.update(globals())

        if ctx.channel.id in self.sessions:
            await ctx.send('Already running a REPL session in this channel. Exit it with `quit`.')
            return

        self.sessions.add(ctx.channel.id)
        await ctx.send('Enter code to execute or evaluate. `exit()` or `quit` to exit.')

        while True:
            def check(m):
                return m.content.startswith('`') and m.author == ctx.author and m.channel == ctx.channel

            try:
                response = await self.bot.wait_for("message", check=check, timeout=10.0*60.0)
            except asyncio.TimeoutError:
                await ctx.send('Exiting REPL session.')
                self.sessions.remove(ctx.channel.id)
                break

            cleaned = self.cleanup_code(response.content)

            if cleaned in ('quit', 'exit', 'exit()'):
                await ctx.send('Exiting.')
                self.sessions.remove(ctx.channel.id)
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
            except Exception:
                value = stdout.getvalue()
                fmt = f'```py\n{value}{traceback.format_exc()}\n```'
            else:
                value = stdout.getvalue()
                if result is not None:
                    fmt = f'```py\n{value}{result}\n```'
                    variables['_'] = result
                elif value:
                    fmt = f'```py\n{value}\n```'

            try:
                if fmt is not None:
                    if len(fmt) > 2000:
                        await ctx.send("Content too big to be printed.")
                    else:
                        await ctx.send(fmt)
            except discord.Forbidden:
                pass
            except discord.HTTPException as e:
                await ctx.send(f'Unexpected error: `{e}`')

    @commands.command()
    @checks.owner_only()
    async def shutdown(self, ctx: NabCtx):
        """Shutdowns the bot."""
        await ctx.send('Shutting down...')
        await self.bot.logout()

    @commands.command()
    @checks.owner_only()
    async def sql(self, ctx: NabCtx, *, query: str):
        """Executes a SQL query and shows the results.

        If the results are too long to display, a text file is generated and uploaded."""
        query = self.cleanup_code(query)
        async with ctx.pool.acquire() as conn:
            try:
                start = time.perf_counter()
                results = await conn.fetch(query)
                delta = (time.perf_counter() - start) * 1000.0
            except asyncpg.PostgresError as e:
                return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')
        rows = len(results)
        if rows == 0:
            return await ctx.send(f'`{delta:.2f}ms: {results}`')

        headers = list(results[0].keys())
        table = TabularData()
        table.set_columns(headers)
        table.add_rows(list(r.values()) for r in results)
        render = table.render()

        fmt = f'```\n{render}\n```\n*Returned {rows} rows in {delta:2f}ms*'
        if len(fmt) > 2000:
            fp = io.BytesIO(fmt.encode('utf-8'))
            await ctx.send('Too many results to display here', file=discord.File(fp, 'results.txt'))
        else:
            await ctx.send(fmt)

    @checks.owner_only()
    @checks.can_embed()
    @commands.command()
    async def servers(self, ctx: NabCtx, sort=None):
        """Shows a list of servers the bot is in.

        Further information can be obtained using `serverinfo [id]`.

        Values can be sorted by using one of the following values for sort:
        - name
        - members
        - world
        - created
        - joined"""
        entries = []

        sorters = {
            "name": (lambda g: g.name, False, lambda g: self.bot.tracked_worlds.get(g.id, 'None')),
            "members": (lambda g: len(g.members), True, lambda g: f"{len(g.members):,} users"),
            "world": (lambda g: self.bot.tracked_worlds.get(g.id, "|"), False,
                      lambda g: self.bot.tracked_worlds.get(g.id, 'None')),
            "created": (lambda g: g.created_at, False, lambda g: f"Created: {g.created_at.date()}"),
            "joined": (lambda g: g.me.joined_at, False, lambda g: f"Joined: {g.me.joined_at.date()}")
        }

        if sort is None:
            sort = "name"
        if sort not in sorters:
            return await ctx.error(f"Invalid sort value. Valid values are: `{', '.join(sorters)}`")
        guilds = sorted(self.bot.guilds, key=sorters[sort][0], reverse=sorters[sort][1])
        for guild in guilds:
            entries.append(f"**{guild.name}** (ID: **{guild.id}**) - {sorters[sort][2](guild)}")
        pages = Pages(ctx, entries=entries, per_page=10)
        pages.embed.title = f"Servers with {ctx.me.name}"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.error(e)

    @commands.command(name="unload")
    @checks.owner_only()
    async def unload_cog(self, ctx: NabCtx, cog: str):
        """Unloads a cog."""
        try:
            self.bot.unload_extension(cog)
            await ctx.success("Cog unloaded successfully.")
        except Exception as e:
            await ctx.error('{}: {}'.format(type(e).__name__, e))

    @commands.command()
    @checks.owner_only()
    async def versions(self, ctx: NabCtx):
        """Shows version info about NabBot and its dependencies.

        An X is displayed if the minimum required version is not met, this is likely to cause problems.
        A warning sign is displayed when the version installed exceeds the highest version supported
           This means there might be breaking changes, causing the bot to malfunction. This is not always the case.
        A checkmark indicates that the dependency is inside the recommended range."""
        def comp(operator, object1, object2):
            if operator == ">=":
                return object1 >= object2
            elif operator == ">":
                return object1 > object2
            elif operator == "==":
                return object1 == object2
            elif operator == "<":
                return object1 < object2
            elif operator == "<=":
                return object1 <= object2

        discordpy_version = pkg_resources.get_distribution("discord.py").version
        m = dpy_commit.search(discordpy_version)
        dpy = f"v{discordpy_version}"
        if m:
            revision, commit = m.groups()
            is_valid = int(revision) >= self.bot.__min_discord__
            discordpy_url = f"https://github.com/Rapptz/discord.py/commit/{commit}"
            dpy = f"{ctx.tick(is_valid)}[v{discordpy_version}]({discordpy_url})"
            if not is_valid:
                dpy += f"\n`{self.bot.__min_discord__ - int(revision)} commits behind`"

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
            print(package)
            version = pkg_resources.get_distribution(package[0]).version
            if not comp(package[1], StrictVersion(version), StrictVersion(package[2])):
                value = f"{ctx.tick(False)}v{version}\n`At least v{package[2]} expected`"
            elif not comp(package[3], StrictVersion(version), StrictVersion(package[4])):
                value = f"{config.warn_emoji}v{version}\n`Only below v{package[4]} tested`"
            else:
                value = f"{ctx.tick(True)}v{version}"
            embed.add_field(name=package[0], value=value)
        await ctx.send(embed=embed)
    # endregion

    # region Auxiliary functions
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
    # endregion


def setup(bot):
    bot.add_cog(Owner(bot))
