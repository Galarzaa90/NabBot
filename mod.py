import asyncio
import discord
from discord.ext import commands

from config import lite_mode, main_server, tibia_servers
from utils.database import userDatabase
from utils.tibia import get_character, ERROR_NETWORK, ERROR_DOESNTEXIST
from utils.general import is_numeric
from utils.discord import get_member, get_member_by_name
from utils import checks


class Mod:
    """Commands for bot/server moderators."""
    def __init__(self, bot: discord.Client):
        self.bot = bot

    # Admin only commands #
    @commands.command(pass_context=True)
    @checks.is_mod()
    @asyncio.coroutine
    def makesay(self, ctx: discord.ext.commands.Context, *, message: str):
        """Makes the bot say a message
        If it's used directly on a text channel, the bot will delete the command's message and repeat it itself

        If it's used on a private message, the bot will ask on which channel he should say the message."""
        if ctx.message.channel.is_private:
            description_list = []
            channel_list = []
            for server in self.bot.servers:
                author = get_member(self.bot, ctx.message.author.id, server)
                bot_member = get_member(self.bot, self.bot.user.id, server)
                # Skip servers where the command user is not in
                if author is None:
                    continue
                # Check for every channel
                for channel in server.channels:
                    # Skip voice channels
                    if channel.type != discord.ChannelType.text:
                        continue
                    author_permissions = author.permissions_in(channel)  # type: discord.Permissions
                    bot_permissions = bot_member.permissions_in(channel)  # type: discord.Permissions
                    # Check if both the author and the bot have permissions to send messages and add channel to list
                    if author_permissions.send_messages and bot_permissions.send_messages:
                        description_list.append("**#{0}** in **{1}**".format(channel.name, server.name))
                        channel_list.append(channel)
            if len(description_list) < 1:
                yield from self.bot.say("We don't have channels in common with permissions.")
                return
            yield from self.bot.say("Choose a channel for me to send your message (number only):" +
                                    "\n\t0: *Cancel*\n\t" +
                                    "\n\t".join(["{0}: {1}".format(i+1, j) for i, j in enumerate(description_list)]))
            answer = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                          timeout=30.0)
            if answer is None:
                yield from self.bot.say("... are you there? Fine, nevermind!")
            elif is_numeric(answer.content):
                answer = int(answer.content)
                if answer == 0:
                    yield from self.bot.say("Changed your mind? Typical human.")
                    return
                try:
                    yield from self.bot.send_message(channel_list[answer-1], message)
                    yield from self.bot.say("Message sent on #"+channel_list[answer-1].name)
                except IndexError:
                    yield from self.bot.say("That wasn't in the choices, you ruined it. Start from the beginning.")
            else:
                yield from self.bot.say("That's not a valid answer!")

        else:
            yield from self.bot.delete_message(ctx.message)
            yield from self.bot.send_message(ctx.message.channel, message)

    @commands.group(invoke_without_command=True, pass_context=True)
    @checks.is_mod()
    @asyncio.coroutine
    def stalk(self, ctx):
        """Manipulate the user database. See subcommands

        Check the available subcommands for more info.
        Commands and subcommands can only be used on pm"""
        if not ctx.message.channel.is_private:
            return True
        yield from self.bot.say("```Valid subcommands are:\n"
                                "add, addchar, addacc, remove, removechar, purge, check, refreshnames```")

    @stalk.command(pass_context=True, name="add", aliases=["add_user", "register_user", "user"])
    @checks.is_mod()
    @asyncio.coroutine
    def add_user(self, ctx, *, name):
        """Registers an user in the database

        User must be visible by the bot.

        The syntax is:
        /stalk add user"""
        if not ctx.message.channel.is_private:
            return True
        c = userDatabase.cursor()
        try:
            user = get_member_by_name(self.bot, name)
            if user is None:
                yield from self.bot.say("I don't see any user named **{0}**.".format(name))
                return
            c.execute("SELECT id from users WHERE id LIKE ?", (user.id,))
            if c.fetchone() is not None:
                yield from self.bot.say("**@{0}** is already registered.".format(user.display_name))
                return
            c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
            yield from self.bot.say("**@{0}** was registered successfully.".format(user.display_name))
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(pass_context=True, name="addchar", aliases=["char"])
    @checks.is_mod()
    @asyncio.coroutine
    def add_char(self, ctx, *, params):
        """Registers a tibia character to a discord user

        The user is registered automatically if it wasn't registered already.

        The syntax is:
        /stalk addchar user,character"""
        if not ctx.message.channel.is_private:
            return True
        if lite_mode:
            return
        params = params.split(",")
        if len(params) != 2:
            yield from self.bot.say("The correct syntax is: ``/stalk addchar username,character``")
            return
        user = get_member_by_name(self.bot, params[0])
        char = yield from get_character(params[1])
        if user is None:
            yield from self.bot.say("I don't see any user named **{0}**".format(params[0]))
            return
        if type(char) is not dict:
            if char == ERROR_NETWORK:
                yield from self.bot.say("I couldn't fetch the character, please try again.")
            elif char == ERROR_DOESNTEXIST:
                yield from self.bot.say("That character doesn't exists.")
            return
        c = userDatabase.cursor()
        try:
            c.execute("SELECT id, name, user_id FROM chars WHERE name LIKE ?", (char['name'],))
            result = c.fetchone()
            # Char is already in database
            if result is not None:
                # Update name if it was changed
                if char['name'] != params[1]:
                    c.execute("UPDATE chars SET name = ? WHERE id = ?", (char['name'], result["id"],))
                    yield from self.bot.say("This character's name was changed from **{0}** to **{1}**".format(
                        params[1], char['name'])
                    )
                # Registered to a different user
                if result["user_id"] != user.id:
                    current_user = get_member(self.bot, result["user_id"])
                    # User no longer in server
                    if current_user is None:
                        c.execute("UPDATE chars SET user_id = ? WHERE id = ?", (user.id, result["id"],))
                        yield from self.bot.say("This character was registered to a user no longer in server. "
                                                "It was assigned to this user successfully.")
                    else:
                        yield from self.bot.say("This character is already registered to **@{0}**".format(
                            current_user.display_name)
                        )
                    return
                # Registered to current user
                yield from self.bot.say("This character is already registered to this user.")
                return
            c.execute("INSERT INTO chars (name,last_level,vocation,user_id, world) VALUES (?,?,?,?,?)",
                      (char["name"], char["level"] * -1, char["vocation"], user.id, char["world"]))
            # Check if user is already registered
            c.execute("SELECT id from users WHERE id = ?", (user.id,))
            result = c.fetchone()
            if result is None:
                c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
                yield from self.bot.say("**@{0}** was registered successfully.".format(user.display_name))
            yield from self.bot.say("**{0}** was registered successfully to this user.".format(char['name']))
            return
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(pass_context=True, name="addacc", aliases=["account", "addaccount", "acc"])
    @checks.is_mod()
    @asyncio.coroutine
    def add_account(self, ctx, *, params):
        """Register a character and all other visible characters to a discord user.

        If a character is hidden, only that characater will be addeed. Characters in other worlds are skipped.

        The syntax is the following:
        /stalk addacc user,char"""
        if not ctx.message.channel.is_private:
            return True
        if lite_mode:
            return
        params = params.split(",")
        if len(params) != 2:
            yield from self.bot.say("The correct syntax is: ``/stalk addacc username,character``")
            return
        user = get_member_by_name(self.bot, params[0])
        char = yield from get_character(params[1])
        if user is None:
            yield from self.bot.say("I don't see any user named **{0}**".format(params[0]))
            return
        if type(char) is not dict:
            if char == ERROR_NETWORK:
                yield from self.bot.say("I couldn't fetch the character, please try again.")
            elif char == ERROR_DOESNTEXIST:
                yield from self.bot.say("That character doesn't exists.")
            return
        c = userDatabase.cursor()
        try:
            chars = char['chars']
            # If the char is hidden,we still add the searched character
            if len(chars) == 0:
                yield from self.bot.say("Character is hidden.")
                chars = [char]
            for char in chars:
                # Character not in followed server(s), skip.
                if char['world'] not in tibia_servers:
                    yield from self.bot.say("**{0}** skipped, character not in server list.".format(char['name']))
                    continue
                char = yield from get_character(char['name'])
                c.execute("SELECT id, name,user_id FROM chars WHERE name LIKE ?", (char['name'],))
                result = c.fetchone()
                # Char is already in database
                if result is not None:
                    # Registered to different user
                    if result["user_id"] != user.id:
                        current_user = get_member(self.bot, result["user_id"])
                        # Char is registered to user no longer in server
                        if current_user is None:
                            c.execute("UPDATE chars SET user_id = ? WHERE id = ?", (user.id, result["id"],))
                            yield from self.bot.say("**{0}** was registered to a user no longer in server. "
                                                    "It was assigned to this user successfully.".format(char["name"]))
                        else:
                            yield from self.bot.say("**{0}** is already registered to **@{1}**".format(
                                char['name'],
                                current_user.display_name)
                            )
                            continue
                    # Registered to current user
                    yield from self.bot.say("**{0}** is already registered to this user.".format(char['name']))
                    continue
                c.execute(
                    "INSERT INTO chars (name,last_level,vocation,user_id, world) VALUES (?,?,?,?,?)",
                    (char["name"], char["level"]*-1, char["vocation"], user.id, char["world"])
                )
                yield from self.bot.say("**{0}** was registered successfully to this user.".format(char['name']))
            c.execute("SELECT id from users WHERE id = ?", (user.id,))
            result = c.fetchone()
            if result is None:
                c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
                yield from self.bot.say("**@{0}** was registered successfully.".format(user.display_name))
            return
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(pass_context=True, name="removechar", aliases=["deletechar"])
    @checks.is_owner()
    @asyncio.coroutine
    def remove_char(self, ctx, *, name):
        """Removes a registered character.

        The syntax is:
        /stalk removechar name"""
        if not ctx.message.channel.is_private:
            return True
        if lite_mode:
            return
        # This could be used to remove deleted chars so we don't need to check anything
        # Except if the char exists in the database...
        c = userDatabase.cursor()
        try:
            c.execute("SELECT name, user_id FROM chars WHERE name LIKE ?", (name,))
            result = c.fetchone()
            if result is None:
                yield from self.bot.say("There's no character with that name registered.")
                return
            user = get_member(self.bot, result["user_id"])
            username = "unknown" if user is None else user.display_name
            c.execute("DELETE FROM chars WHERE name LIKE ?", (name,))
            yield from self.bot.say("**{0}** was removed successfully from **@{1}**.".format(name, username))
            return
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(name="remove", aliases=["delete", "deleteuser", "removeuser"], pass_context=True)
    @checks.is_owner()
    @asyncio.coroutine
    def remove_user(self, ctx, *, name):
        """Removes a discord user from the database

        The syntax is:
        /stalk remove name"""
        if not ctx.message.channel.is_private:
            return True
        if lite_mode:
            return
        c = userDatabase.cursor()
        # Searching users in server
        user = get_member_by_name(self.bot, name)
        # Searching users in database
        try:
            c.execute("SELECT id, name from users WHERE name LIKE ?", (name,))
            result = c.fetchone()
            # Users in database and not in servers
            if result is not None and get_member(self.bot, result['id']) is None:
                yield from self.bot.say(
                    "**@{0}** was no longer in server and was removed successfully.".format(result["name"]))
                delete_id = result["id"]
            # User in servers and in database
            elif user is not None and result is not None:
                yield from self.bot.say("**{0}** was removed successfully.".format(user.display_name))
                delete_id = user.id
            # User in server but not in database
            elif user is not None and result is None:
                yield from self.bot.say("**{0}** is not registered.".format(user.display_name))
                return
            # User not in server or database
            else:
                yield from self.bot.say("I don't see any user named **{0}**.".format(name))
                return

            c.execute("DELETE FROM users WHERE id = ?", (delete_id,))
            c.execute("SELECT name FROM chars WHERE user_id = ?", (delete_id,))
            result = c.fetchall()
            if len(result) >= 1:
                chars = ["**" + i["name"] + "**" for i in result]
                reply = "The following characters were registered to the user:\n\t"
                reply += "\n\t".join(chars)
                reply += "\nDo you want to delete them? ``(yes/no)``"
                yield from self.bot.say(reply)

                answer = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                         timeout=30.0)
                if answer is None:
                    yield from self.bot.say("I will take your silence as a no...")
                elif answer.content.lower() in ["yes", "y"]:
                    c.execute("DELETE FROM chars WHERE user_id = ?", (delete_id,))
                    yield from self.bot.say("Characters deleted successfully.")
                else:
                    yield from self.bot.say("Ok, we are done then.")
            return
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(pass_context=True, aliases=["clean"])
    @checks.is_owner()
    @asyncio.coroutine
    def purge(self, ctx):
        """Performs a database cleanup

        Removes characters that have been deleted and users with no characters or no longer in server."""
        if not ctx.message.channel.is_private:
            return True
        if lite_mode:
            return
        c = userDatabase.cursor()
        try:
            c.execute("SELECT id FROM users")
            result = c.fetchall()
            if result is None:
                yield from self.bot.say("There are no users registered.")
                return
            delete_users = list()
            yield from self.bot.say("Initiating purge...")
            # Deleting users no longer in server
            for row in result:
                user = get_member(self.bot, row["id"])
                if user is None:
                    delete_users.append((row["id"],))
            if len(delete_users) > 0:
                c.executemany("DELETE FROM users WHERE id = ?", delete_users)
                yield from self.bot.say("{0} user(s) no longer in the server were removed.".format(c.rowcount))

            # Deleting chars with non-existent user
            c.execute("SELECT name FROM chars WHERE user_id NOT IN (SELECT id FROM users)")
            result = c.fetchall()
            if len(result) >= 1:
                chars = ["**" + i["name"] + "**" for i in result]
                reply = "{0} char(s) were assigned to a non-existent user and were deleted:\n\t".format(len(result))
                reply += "\n\t".join(chars)
                yield from self.bot.say(reply)
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
                char = yield from get_character(row["name"])
                if char == ERROR_NETWORK:
                    yield from self.bot.say("Couldn't fetch **{0}**, skipping...".format(row["name"]))
                    continue
                # Char was deleted
                if char == ERROR_DOESNTEXIST:
                    delete_chars.append((row["name"],))
                    yield from self.bot.say("**{0}** doesn't exists, deleting...".format(row["name"]))
                    continue
                # Char was renamed
                if char['name'] != row["name"]:
                    rename_chars.append((char['name'], row["name"],))
                    yield from self.bot.say(
                        "**{0}** was renamed to **{1}**, updating...".format(row["name"], char['name']))

            # No need to check if user exists cause those were removed already
            if len(delete_chars) > 0:
                c.executemany("DELETE FROM chars WHERE name LIKE ?", delete_chars)
                yield from self.bot.say("{0} char(s) were removed.".format(c.rowcount))
            if len(rename_chars) > 0:
                c.executemany("UPDATE chars SET name = ? WHERE name LIKE ?", rename_chars)
                yield from self.bot.say("{0} char(s) were renamed.".format(c.rowcount))

            # Remove users with no chars
            c.execute("SELECT id FROM users WHERE id NOT IN (SELECT user_id FROM chars)")
            result = c.fetchall()
            if len(result) >= 1:
                c.execute("DELETE FROM users WHERE id NOT IN (SELECT user_id FROM chars)")
                yield from self.bot.say("{0} user(s) with no characters were removed.".format(c.rowcount))

            # Remove level ups of removed characters
            c.execute("DELETE FROM char_levelups WHERE char_id NOT IN (SELECT id FROM chars)")
            if c.rowcount > 0:
                yield from self.bot.say(
                    "{0} level up registries from removed characters were deleted.".format(c.rowcount))
            c.execute("DELETE FROM char_deaths WHERE char_id NOT IN (SELECT id FROM chars)")
            # Remove deaths of removed characters
            if c.rowcount > 0:
                yield from self.bot.say("{0} death registries from removed characters were deleted.".format(c.rowcount))
            yield from self.bot.say("Purge done.")
            return
        finally:
            userDatabase.commit()
            c.close()

    @stalk.command(pass_context=True)
    @checks.is_mod()
    @asyncio.coroutine
    def check(self, ctx):
        """Check which users are currently not registered."""
        if not ctx.message.channel.is_private:
            return True
        if lite_mode:
            return
        c = userDatabase.cursor()
        try:
            c.execute("SELECT user_id FROM chars GROUP BY user_id")
            result = c.fetchall()
            if len(result) <= 0:
                yield from self.bot.say("There are no registered characters.")
                return
            users = [str(i["user_id"]) for i in result]
            members = self.bot.get_server(main_server).members
            empty_members = list()
            for member in members:
                if member.id == self.bot.user.id:
                    continue
                if member.id not in users:
                    empty_members.append("**@" + member.display_name + "**")
            if len(empty_members) == 0:
                yield from self.bot.say("There are no unregistered users or users without characters.")
                return
            yield from self.bot.say(
                "The following users are not registered or have no chars registered to them:\n\t{0}".format(
                    "\n\t".join(empty_members)))
        finally:
            c.close()

    @stalk.command(pass_context=True, name="refreshnames")
    @checks.is_mod()
    @asyncio.coroutine
    def refresh_names(self, ctx):
        """Checks and updates user names on the database."""
        if not ctx.message.channel.is_private:
            return True
        if lite_mode:
            return
        c = userDatabase.cursor()
        try:
            c.execute("SELECT id FROM users")
            result = c.fetchall()
            if len(result) <= 0:
                yield from self.bot.say("There are no registered users.")
                return
            update_users = list()
            for user in result:
                update_users.append(
                    ("unknown" if get_member(self.bot, user[0]) is None else get_member(self.bot, user[0]).display_name,
                     user["id"]))
            c.executemany("UPDATE users SET name = ? WHERE id LIKE ?", update_users)
            yield from self.bot.say("Usernames updated successfully.")
        finally:
            c.close()
            userDatabase.commit()

    @add_user.error
    @add_char.error
    @add_account.error
    @remove_char.error
    @remove_user.error
    @purge.error
    @check.error
    @refresh_names.error
    @asyncio.coroutine
    def purge_error(self, error, ctx: discord.ext.commands.Context):
        if not ctx.message.channel.is_private or lite_mode:
            return
        if isinstance(error, commands.errors.CheckFailure):
            yield from self.bot.say("You don't have permission to use this command.")
        elif isinstance(error, commands.errors.MissingRequiredArgument):
            yield from self.bot.say("You're missing a required argument. "
                                    "`Type /help {0}`".format(ctx.invoked_subcommand))


def setup(bot):
    bot.add_cog(Mod(bot))
