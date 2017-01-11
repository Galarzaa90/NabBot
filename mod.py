import asyncio
import discord
from discord.ext import commands

from config import lite_mode, tracked_worlds, mod_ids, owner_ids
from utils.database import userDatabase
from utils.messages import split_message
from utils.tibia import get_character, ERROR_NETWORK, ERROR_DOESNTEXIST
from utils.general import is_numeric
from utils.discord import get_member, get_member_by_name, get_user_servers, get_user_worlds, send_log_message, \
    get_user_admin_servers
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
    @checks.is_not_lite()
    @asyncio.coroutine
    def stalk(self, ctx):
        """Manipulate the user database. See subcommands

        Check the available subcommands for more info.
        Commands and subcommands can only be used on pm"""
        if not ctx.message.channel.is_private:
            return True
        yield from self.bot.say("To see valid subcommands use ´/help stalk´")

    @stalk.command(pass_context=True, name="addchar", aliases=["char"])
    @checks.is_mod()
    @checks.is_not_lite()
    @asyncio.coroutine
    def add_char(self, ctx, *, params):
        """Registers a tibia character to a discord user.

        The syntax is:
        /stalk addchar user,character"""
        if not ctx.message.channel.is_private:
            return True
        params = params.split(",")
        if len(params) != 2:
            yield from self.bot.say("The correct syntax is: ``/stalk addchar username,character``")
            return

        author = ctx.message.author
        if author.id in mod_ids+owner_ids:
            author_servers = get_user_servers(self.bot, author.id)
        else:
            author_servers = get_user_admin_servers(self.bot, author.id)
        author_worlds = get_user_worlds(self.bot, author.id)

        # Only search in the servers the command author is
        user = get_member_by_name(self.bot, params[0], server_list=author_servers)
        user_servers = get_user_servers(self.bot, user.id)
        user_worlds = get_user_worlds(self.bot, author.id)

        common_worlds = list(set(author_worlds) & set(user_worlds))

        yield from self.bot.send_typing(ctx.message.channel)
        char = yield from get_character(params[1])

        if user is None:
            yield from self.bot.say("I don't see any user named **{0}** in the servers you manage.".format(params[0]))
            return
        if type(char) is not dict:
            if char == ERROR_NETWORK:
                yield from self.bot.say("I couldn't fetch the character, please try again.")
            elif char == ERROR_DOESNTEXIST:
                yield from self.bot.say("That character doesn't exists.")
            return
        if char["world"] not in common_worlds:
            yield from self.bot.say("**{name}** ({world}) is not in a world you can manage.".format(**char))
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
                        # Log on relevant servers
                        for server in user_servers:
                            world = tracked_worlds.get(server.id, None)
                            if world == char["world"]:
                                log_msg = "{0.mention} registered **{1}** ({2} {3}) to {4.mention}."
                                yield from send_log_message(self.bot, server, log_msg.format(author, char["name"],
                                                                                             char["level"],
                                                                                             char["vocation"], user))
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
            yield from self.bot.say("**{0}** was registered successfully to this user.".format(char['name']))
            # Log on relevant servers
            for server in user_servers:
                world = tracked_worlds.get(server.id, None)
                if world == char["world"]:
                    char["guild"] = char.get("guild", "No guild")
                    log_msg = "{0.mention} registered **{1}** ({2} {3}, {4}) to {5.mention}."
                    yield from send_log_message(self.bot, server, log_msg.format(author, char["name"], char["level"],
                                                                                 char["vocation"], char["guild"], user))
            return
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(pass_context=True, name="addacc", aliases=["account", "addaccount", "acc"])
    @checks.is_mod()
    @checks.is_not_lite()
    @asyncio.coroutine
    def add_account(self, ctx, *, params):
        """Register a character and all other visible characters to a discord user.

        If a character is hidden, only that character will be added. Characters in other worlds are skipped.

        The syntax is the following:
        /stalk addacc user,char"""
        if not ctx.message.channel.is_private:
            return True
        params = params.split(",")
        if len(params) != 2:
            yield from self.bot.say("The correct syntax is: ``/stalk addacc username,character``")
            return

        author = ctx.message.author
        if author.id in mod_ids+owner_ids:
            author_servers = get_user_servers(self.bot, author.id)
        else:
            author_servers = get_user_admin_servers(self.bot, author.id)
        author_worlds = get_user_worlds(self.bot, author.id)

        user = get_member_by_name(self.bot, params[0], server_list=author_servers)
        user_servers = get_user_servers(self.bot, user.id)
        user_worlds = get_user_worlds(self.bot, user.id)

        common_worlds = list(set(author_worlds) & set(user_worlds))
        yield from self.bot.send_typing(ctx.message.channel)
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
            skipped = list()
            added = list()
            added_tuples = list()
            reassigned_tuples = list()
            existent = list()
            error = list()
            for char in chars:
                # Character not in followed server(s), skip.
                if char['world'] not in common_worlds:
                    skipped.append([char["name"], char["world"]])
                    continue
                name = char["name"]
                if len(chars) != 1:
                    char = yield from get_character(char["name"])
                if type(char) is not dict:
                    error.append(name)
                    continue
                c.execute("SELECT id, name,user_id FROM chars WHERE name LIKE ?", (char['name'],))
                result = c.fetchone()
                # Char is already in database
                if result is not None:
                    # Registered to different user
                    if str(result["user_id"]) != user.id:
                        current_user = get_member(self.bot, result["user_id"])
                        # Char is registered to user no longer in server
                        if current_user is None:
                            added.append(char)
                            reassigned_tuples.append((user.id, result["id"],))
                            continue
                        else:
                            yield from self.bot.say("{0} is already assigned to {1}. We can't add any other of these "
                                                    "characters.".format(char["name"], current_user.display_name))
                            return
                    # Registered to current user
                    existent.append(char)
                    continue
                added.append(char)
                added_tuples.append((char["name"], char["level"]*-1, char["vocation"], user.id, char["world"],))
            c.execute("SELECT id from users WHERE id = ?", (user.id,))
            result = c.fetchone()
            if result is None:
                c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))

            c.executemany("INSERT INTO chars(name,last_level,vocation,user_id, world) VALUES (?,?,?,?,?)", added_tuples)
            c.executemany("UPDATE chars SET user_id = ? WHERE id = ?", reassigned_tuples)
            reply = ""
            log_reply = dict().fromkeys([server.id for server in user_servers], "")
            if added:
                reply += "\nThe following characters were registered or reassigned successfully:"
                for char in added:
                    char["guild"] = char.get("guild", "No guild")
                    reply += "\n\t**{name}** ({level} {vocation}) - **{guild}**".format(**char)
                    # Announce on server log of each server
                    for server in user_servers:
                        # Only announce on worlds where the character's world is tracked
                        if tracked_worlds.get(server.id, None) == char["world"]:
                            log_reply[server.id] += "\n\t{name} - {level} {vocation} - **{guild}**".format(**char)
            if existent:
                reply += "\nThe following characters were already registered to this user:"
                for char in existent:
                    char["guild"] = char.get("guild", "No guild")
                    reply += "\n\t**{name}** ({level} {vocation}) - **{guild}**".format(**char)
            if skipped:
                reply += "\nThe following characters were skipped (not in tracked worlds):"
                for char, world in skipped:
                    reply += "\n\t{0} ({1})".format(char, world)
            if error:
                reply += "\nThe following characters couldn't be fetched: "
                reply += ", ".join(error)
            yield from self.bot.say(reply)
            for server_id, message in log_reply.items():
                if message:
                    message = "{0.mention} registered the following characters to {1.mention}: {2}".format(author, user,
                                                                                                           message)
                    yield from send_log_message(self.bot, self.bot.get_server(server_id), message)
            return
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(pass_context=True, name="removechar", aliases=["deletechar"])
    @checks.is_owner()
    @checks.is_not_lite()
    @asyncio.coroutine
    def remove_char(self, ctx, *, name):
        """Removes a registered character.

        The syntax is:
        /stalk removechar name"""
        if not ctx.message.channel.is_private:
            return True
        # This could be used to remove deleted chars so we don't need to check anything
        # Except if the char exists in the database...
        yield from self.bot.send_typing(ctx.message.channel)
        c = userDatabase.cursor()
        try:
            c.execute("SELECT name, user_id, world, ABS(last_level) as level, vocation "
                      "FROM chars WHERE name LIKE ?", (name,))
            result = c.fetchone()
            if result is None:
                yield from self.bot.say("There's no character with that name registered.")
                return
            user = get_member(self.bot, result["user_id"])
            username = "unknown" if user is None else user.display_name
            c.execute("DELETE FROM chars WHERE name LIKE ?", (name,))
            yield from self.bot.say("**{0}** was removed successfully from **@{1}**.".format(name, username))
            if user is not None:
                for server in get_user_servers(self.bot, user.id):
                    world = tracked_worlds.get(server.id, None)
                    if world != result["world"]:
                        continue
                    log_msg = "{0.mention} removed **{1}** ({2} {3}) from {4.mention}.".\
                        format(ctx.message.author, result["name"], result["level"], result["vocation"], user)
                    yield from send_log_message(self.bot, server, log_msg)

            return
        finally:
            c.close()
            userDatabase.commit()

    @stalk.command(name="remove", aliases=["delete", "deleteuser", "removeuser"], pass_context=True)
    @checks.is_owner()
    @checks.is_not_lite()
    @asyncio.coroutine
    def remove_user(self, ctx, *, name):
        """Removes a discord user from the database

        The syntax is:
        /stalk remove name"""
        if not ctx.message.channel.is_private:
            return True
        c = userDatabase.cursor()
        yield from self.bot.send_typing(ctx.message.channel)
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

    # Todo: Add server-log entry
    @stalk.command(name="namelock", pass_context=True, aliases=["namechange","rename"])
    @checks.is_mod()
    @checks.is_not_lite()
    @asyncio.coroutine
    def stalk_namelock(self, ctx, *, params):
        """Register the name of a new character that was namelocked.

        Characters that get namelocked can't be searched by their old name, so they must be reassigned manually.

        If the character got a name change (from the store), searching the old name redirects to the new name, so
        this are usually reassigned automatically.

        The syntax is:
        /stalk namelock oldname,newname"""
        if not ctx.message.channel.is_private:
            return True
        params = params.split(",")
        if len(params) != 2:
            yield from self.bot.say("The correct syntax is: `/stalk namelock oldname,newname")
            return

        old_name = params[0]
        new_name = params[1]
        yield from self.bot.send_typing(ctx.message.channel)
        c = userDatabase.cursor()
        try:
            c.execute("SELECT * FROM chars WHERE name LIKE ? LIMIT 1", (old_name,))
            old_char_db = c.fetchone()
            # If character wasn't registered, there's nothing to do.
            if old_char_db is None:
                yield from self.bot.say("I don't have a character registered with the name: **{0}**".format(old_name))
                return
            # Search old name to see if there's a result
            old_char = yield from get_character(old_name)
            if old_char == ERROR_NETWORK:
                yield from self.bot.say("I'm having problem with 'the internet' as you humans say, try again.")
                return
            # Check if returns a result
            if type(old_char) is dict:
                if old_name.lower() == old_char["name"].lower():
                    yield from self.bot.say("The character **{0}** wasn't namelocked.".format(old_char["name"]))
                else:
                    yield from self.bot.say("The character **{0}** was renamed to **{1}**.".format(old_name,
                                                                                                   old_char["name"]))
                    # Renaming is actually done in get_character(), no need to do anything.
                return

            # Check if new name exists
            new_char = yield from get_character(new_name)
            if new_char == ERROR_NETWORK:
                yield from self.bot.say("I'm having problem with 'the internet' as you humans say, try again.")
                return
            if new_char == ERROR_DOESNTEXIST:
                yield from self.bot.say("The character **{0}** doesn't exists.".format(new_name))
                return
            # Check if vocations are similar
            if not (old_char_db["vocation"].lower() in new_char["vocation"].lower()
                    or new_char["vocation"].lower() in old_char_db["vocation"].lower()):
                yield from self.bot.say("**{0}** was a *{1}* and **{2}** is a *{3}*. I think you're making a mistake."
                                        .format(old_char_db["name"], old_char_db["vocation"],
                                                new_char["name"], new_char["vocation"]))
                return
            confirm_message = "Are you sure **{0}** ({1} {2}) is **{3}** ({4} {5}) now? `yes/no`"
            yield from self.bot.say(confirm_message.format(old_char_db["name"], abs(old_char_db["last_level"]),
                                                           old_char_db["vocation"], new_char["name"], new_char["level"],
                                                           new_char["vocation"]))
            reply = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                         timeout=50.0)
            if reply is None:
                yield from self.bot.say("No answer? I guess you changed your mind.")
                return
            elif reply.content.lower() not in ["yes", "y"]:
                yield from self.bot.say("No then? Alright.")
                return

            # Check if new name was already registered
            c.execute("SELECT * FROM chars WHERE name LIKE ?", (new_char["name"],))
            new_char_db = c.fetchone()

            if new_char_db is None:
                c.execute("UPDATE chars SET name = ?, vocation = ?, last_level = ? WHERE id = ?", (new_char["name"],
                                                                                                   new_char["vocation"],
                                                                                                   new_char["level"],
                                                                                                   old_char_db["id"],))
            else:
                # Replace new char with old char id and delete old char, reassign deaths and levelups
                c.execute("DELETE FROM chars WHERE id = ?", (old_char_db["id"]),)
                c.execute("UPDATE chars SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))
                c.execute("UPDATE char_deaths SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))
                c.execute("UPDATE char_levelups SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))

            yield from self.bot.say("Character renamed successfully.")
        finally:
            c.close()
            userDatabase.commit()

    # Todo: Reduce number of messages
    @stalk.command(pass_context=True, aliases=["clean"])
    @checks.is_owner()
    @checks.is_not_lite()
    @asyncio.coroutine
    def purge(self, ctx):
        """Performs a database cleanup

        Removes characters that have been deleted and users with no characters or no longer in server."""
        if not ctx.message.channel.is_private:
            return True
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
    @checks.is_not_lite()
    @asyncio.coroutine
    def check(self, ctx):
        """Check which users are currently not registered."""
        if not ctx.message.channel.is_private:
            return True

        author = ctx.message.author
        if author.id in mod_ids+owner_ids:
            author_servers = get_user_servers(self.bot, author.id)
        else:
            author_servers = get_user_admin_servers(self.bot, author.id)

        embed = discord.Embed(description="Members with unregistered users.")

        yield from self.bot.send_typing(ctx.message.channel)
        c = userDatabase.cursor()
        try:
            for server in author_servers:
                world = tracked_worlds.get(server.id, None)
                if world is None:
                    continue
                c.execute("SELECT user_id FROM chars WHERE world LIKE ? GROUP BY user_id", (world,))
                result = c.fetchall()
                if len(result) <= 0:
                    embed.add_field(name=server.name, value="There are no registered characters.", inline=False)
                    continue
                users = [str(i["user_id"]) for i in result]
                empty_members = list()
                for member in server.members:
                    if member.id == self.bot.user.id:
                        continue
                    if member.id not in users:
                        empty_members.append("**@" + member.display_name + "**")
                if len(empty_members) == 0:
                    embed.add_field(name=server.name, value="There are no unregistered users.", inline=False)
                    continue
                field_value = "\n{0}".format("\n".join(empty_members))
                split_value = split_message(field_value, 1024)
                for empty_member in split_value:
                    if empty_member == split_value[0]:
                        name = server.name
                    else:
                        name = "\u200F"
                    embed.add_field(name=name, value=empty_member, inline=False)
        yield from self.bot.say(embed=embed)
        finally:
            c.close()

    @stalk.command(pass_context=True, name="refreshnames")
    @checks.is_mod()
    @checks.is_not_lite()
    @asyncio.coroutine
    def refresh_names(self, ctx):
        """Checks and updates user names on the database."""
        if not ctx.message.channel.is_private:
            return True
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
