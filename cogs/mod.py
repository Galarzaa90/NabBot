import asyncio
from typing import List, Dict

import discord
from discord.ext import commands

from config import mod_ids, owner_ids
from nabbot import NabBot
from utils.database import userDatabase, tracked_worlds
from utils.messages import split_message
from utils.paginator import Paginator, CannotPaginate
from utils.tibia import get_character, ERROR_NETWORK, ERROR_DOESNTEXIST
from utils.discord import FIELD_VALUE_LIMIT, is_private
from utils import checks


class Mod:
    """Commands for bot/server moderators."""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.ignored = {}
        self.reload_ignored()

    def __global_check(self, ctx):
        return is_private(ctx.channel) or \
               ctx.channel.id not in self.ignored.get(ctx.guild.id, []) or\
               checks.is_admin_check(ctx)

    # Admin only commands #
    @commands.command()
    @checks.is_mod()
    async def makesay(self, ctx: discord.ext.commands.Context, *, message: str):
        """Makes the bot say a message
        If it's used directly on a text channel, the bot will delete the command's message and repeat it itself

        If it's used on a private message, the bot will ask on which channel he should say the message."""
        if is_private(ctx.message.channel):
            description_list = []
            channel_list = []
            prev_server = None
            num = 1
            for server in self.bot.guilds:
                author = self.bot.get_member(ctx.message.author.id, server)
                bot_member = self.bot.get_member(self.bot.user.id, server)
                # Skip servers where the command user is not in
                if author is None:
                    continue
                # Check for every channel
                for channel in server.text_channels:
                    author_permissions = author.permissions_in(channel)  # type: discord.Permissions
                    bot_permissions = bot_member.permissions_in(channel)  # type: discord.Permissions
                    # Check if both the author and the bot have permissions to send messages and add channel to list
                    if (author_permissions.send_messages and bot_permissions.send_messages) and \
                            (ctx.message.author.id in owner_ids or author_permissions.administrator):
                        separator = ""
                        if prev_server is not server:
                            separator = "---------------\n\t"
                        description_list.append("{2}{3}: **#{0}** in **{1}**".format(channel.name, server.name,
                                                                                     separator, num))
                        channel_list.append(channel)
                        prev_server = server
                        num += 1
            if len(description_list) < 1:
                await ctx.send("We don't have channels in common with permissions.")
                return
            await ctx.send("Choose a channel for me to send your message (number only): \n\t0: *Cancel*\n\t" +
                                "\n\t".join(["{0}".format(i) for i in description_list]))

            def check(m):
                return m.author == ctx.message.author and m.channel == ctx.message.channel
            try:
                answer = await self.bot.wait_for("message",timeout=60.0, check=check)
                answer = int(answer.content)
                if answer == 0:
                    await ctx.send("Changed your mind? Typical human.")
                    return
                await channel_list[answer-1].send(message)
                await ctx.send("Message sent on {0} ({1})".format(channel_list[answer-1].mention,
                                                                       channel_list[answer-1].guild))
            except IndexError:
                await ctx.send("That wasn't in the choices, you ruined it. Start from the beginning.")
            except ValueError:
                await ctx.send("That's not a valid answer!")
            except asyncio.TimeoutError:
                await ctx.send("... are you there? Fine, nevermind!")
        else:
            await ctx.message.delete()
            await ctx.message.channel.send(message)

    @commands.group(invoke_without_command=True)
    @checks.is_mod()
    @checks.is_not_lite()
    async def stalk(self, ctx):
        """Manipulate the user database. See subcommands

        Check the available subcommands for more info.
        Commands and subcommands can only be used on pm"""
        if not is_private(ctx.message.channel):
            return True
        await ctx.send("To see valid subcommands use `/help stalk`")

    @stalk.command(name="addchar", aliases=["char"])
    @checks.is_mod()
    @checks.is_not_lite()
    async def add_char(self, ctx, *, params):
        """Registers a tibia character to a discord user.

        The syntax is:
        /stalk addchar user,character"""
        if not is_private(ctx.message.channel):
            return True
        params = params.split(",")
        if len(params) != 2:
            await ctx.send("The correct syntax is: ``/stalk addchar username,character``")
            return

        author = ctx.message.author
        if author.id in mod_ids+owner_ids:
            author_servers = self.bot.get_user_guilds(author.id)
        else:
            author_servers = self.bot.get_user_admin_guilds(author.id)
        author_worlds = self.bot.get_user_worlds(author.id)

        # Only search in the servers the command author is
        user = self.bot.get_member_named(params[0], author_servers)
        if user is None:
            await ctx.send("I don't see any user named **{0}** in the servers you manage.".format(params[0]))
            return
        user_servers = self.bot.get_user_guilds(user.id)
        user_worlds = self.bot.get_user_worlds(author.id)

        common_worlds = list(set(author_worlds) & set(user_worlds))

        with ctx.typing():
            char = await get_character(params[1])
            if type(char) is not dict:
                if char == ERROR_NETWORK:
                    await ctx.send("I couldn't fetch the character, please try again.")
                elif char == ERROR_DOESNTEXIST:
                    await ctx.send("That character doesn't exists.")
                return
            if char["world"] not in common_worlds:
                await ctx.send("**{name}** ({world}) is not in a world you can manage.".format(**char))
                return
            if char.get("deleted", False):
                await ctx.send("**{name}** ({world}) is scheduled for deletion and can't be added.".format(**char))
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
                        await ctx.send("This character's name was changed from **{0}** to **{1}**".format(
                            params[1], char['name'])
                        )
                    # Registered to a different user
                    if result["user_id"] != user.id:
                        current_user = self.bot.get_member(result["user_id"])
                        # User no longer in server
                        if current_user is None:
                            c.execute("UPDATE chars SET user_id = ? WHERE id = ?", (user.id, result["id"],))
                            await ctx.send("This character was registered to a user no longer in server. "
                                           "It was assigned to this user successfully.")
                            # Log on relevant servers
                            for server in user_servers:
                                world = tracked_worlds.get(server.id, None)
                                if world == char["world"]:
                                    log_msg = "{0.mention} registered **{1}** ({2} {3}) to {4.mention}."
                                    await self.bot.send_log_message(server, log_msg.format(author, char["name"],
                                                                                           char["level"],
                                                                                           char["vocation"],
                                                                                           user))
                        else:
                            await ctx.send("This character is already registered to **@{0}**".format(
                                current_user.display_name)
                            )
                        return
                    # Registered to current user
                    await ctx.send("This character is already registered to this user.")
                    return
                c.execute("INSERT INTO chars (name,last_level,vocation,user_id, world, guild) VALUES (?,?,?,?,?,?)",
                          (char["name"], char["level"] * -1, char["vocation"], user.id, char["world"], char["guild"]))
                # Check if user is already registered
                c.execute("SELECT id from users WHERE id = ?", (user.id,))
                result = c.fetchone()
                if result is None:
                    c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
                await ctx.send("**{0}** was registered successfully to this user.".format(char['name']))
                # Log on relevant servers
                for server in user_servers:
                    world = tracked_worlds.get(server.id, None)
                    if world == char["world"]:
                        char["guild"] = char.get("guild", "No guild")
                        log_msg = "{0.mention} registered **{1}** ({2} {3}, {4}) to {5.mention}."
                        await self.bot.send_log_message(server, log_msg.format(author, char["name"],char["level"],
                                                                               char["vocation"], char["guild"], user))
                return
            finally:
                c.close()
                userDatabase.commit()

    @stalk.command(name="addacc", aliases=["account", "addaccount", "acc"])
    @checks.is_mod()
    @checks.is_not_lite()
    async def add_account(self, ctx, *, params):
        """Register a character and all other visible characters to a discord user.

        If a character is hidden, only that character will be added. Characters in other worlds are skipped.

        The syntax is the following:
        /stalk addacc user,char"""
        if not is_private(ctx.message.channel):
            return True
        params = params.split(",")
        if len(params) != 2:
            await ctx.send("The correct syntax is: ``/stalk addacc username,character``")
            return

        author = ctx.message.author
        if author.id in mod_ids+owner_ids:
            author_guilds = self.bot.get_user_guilds(author.id)
        else:
            author_guilds = self.bot.get_user_admin_guilds(author.id)
        author_worlds = self.bot.get_user_worlds(author.id)

        user = self.bot.get_member_named(params[0], author_guilds)
        if user is None:
            await ctx.send("I don't see any user named **{0}** in the servers you manage.".format(params[0]))
            return
        user_servers = self.bot.get_user_guilds(user.id)
        user_worlds = self.bot.get_user_worlds(user.id)

        common_worlds = list(set(author_worlds) & set(user_worlds))
        with ctx.typing():
            character = await get_character(params[1])
            if type(character) is not dict:
                if character == ERROR_NETWORK:
                    await ctx.send("I couldn't fetch the character, please try again.")
                elif character == ERROR_DOESNTEXIST:
                    await ctx.send("That character doesn't exists.")
                return
            c = userDatabase.cursor()
            try:
                chars = character.get("chars",[])
                # If the char is hidden,we still add the searched character
                if len(chars) == 0:
                    await ctx.send("Character is hidden.")
                    chars = [character]
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
                    # If char is the same we already looked up, no need to look him up again
                    if character["name"] == char["name"]:
                        char = character
                    else:
                        char = await get_character(char["name"])
                    if type(char) is not dict:
                        error.append(name)
                        continue
                    # Skip characters scheduled for deletion
                    if char.get("deleted", False):
                        skipped.append([char["name"], char["world"]])
                        continue
                    c.execute("SELECT id, name,user_id FROM chars WHERE name LIKE ?", (char['name'],))
                    result = c.fetchone()
                    # Char is already in database
                    if result is not None:
                        # Registered to different user
                        if result["user_id"] != user.id:
                            current_user = self.bot.get_member(result["user_id"])
                            # Char is registered to user no longer in server
                            if current_user is None:
                                added.append(char)
                                reassigned_tuples.append((user.id, result["id"],))
                                continue
                            else:
                                await ctx.send("{0} is already assigned to {1}. We can't add any other of these "
                                                    "characters.".format(char["name"], current_user.display_name))
                                return
                        # Registered to current user
                        existent.append(char)
                        continue
                    added.append(char)
                    added_tuples.append((char["name"], char["level"]*-1, char["vocation"], user.id, char["world"],
                                         char["guild"],))
                c.execute("SELECT id from users WHERE id = ?", (user.id,))
                result = c.fetchone()
                if result is None:
                    c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))

                c.executemany("INSERT INTO chars(name,last_level,vocation,user_id, world, guild) VALUES (?,?,?,?,?,?)",
                              added_tuples)
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
                    reply += "\nThe following characters were skipped (not in tracked worlds or scheduled deletion):"
                    for char, world in skipped:
                        reply += "\n\t{0} ({1})".format(char, world)
                if error:
                    reply += "\nThe following characters couldn't be fetched: "
                    reply += ", ".join(error)
                await ctx.send(reply)
                for guild_id, message in log_reply.items():
                    if message:
                        message = "{0.mention} registered the following characters to {1.mention}: {2}".format(author,
                                                                                                               user,
                                                                                                               message)
                        await self.bot.send_log_message(self.bot.get_guild(guild_id), message)
                return
            finally:
                c.close()
                userDatabase.commit()

    @stalk.command(name="removechar", aliases=["deletechar"])
    @checks.is_owner()
    @checks.is_not_lite()
    async def remove_char(self, ctx, *, name):
        """Removes a registered character.

        The syntax is:
        /stalk removechar name"""
        if not is_private(ctx.message.channel):
            return True
        # This could be used to remove deleted chars so we don't need to check anything
        # Except if the char exists in the database...
        c = userDatabase.cursor()
        with ctx.typing():
            try:
                c.execute("SELECT name, user_id, world, ABS(last_level) as level, vocation "
                          "FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is None:
                    await ctx.send("There's no character with that name registered.")
                    return
                user = self.bot.get_member(result["user_id"])
                username = "unknown" if user is None else user.display_name
                c.execute("DELETE FROM chars WHERE name LIKE ?", (name,))
                await ctx.send("**{0}** was removed successfully from **@{1}**.".format(result["name"], username))
                if user is not None:
                    for server in self.bot.get_user_guilds(user.id):
                        world = tracked_worlds.get(server.id, None)
                        if world != result["world"]:
                            continue
                        log_msg = "{0.mention} removed **{1}** ({2} {3}) from {4.mention}.".\
                            format(ctx.message.author, result["name"], result["level"], result["vocation"], user)
                        await self.bot.send_log_message(server, log_msg)

                return
            finally:
                c.close()
                userDatabase.commit()

    @stalk.command(name="remove", aliases=["delete", "deleteuser", "removeuser"])
    @checks.is_owner()
    @checks.is_not_lite()
    async def remove_user(self, ctx, *, name):
        """Removes a discord user from the database

        The syntax is:
        /stalk remove name"""
        if not is_private(ctx.message.channel):
            return True
        c = userDatabase.cursor()
        with ctx.typing():
            # Searching users in server
            user = self.bot.get_member_named(name)
            # Searching users in database
            try:
                c.execute("SELECT id, name from users WHERE name LIKE ?", (name,))
                result = c.fetchone()
                # Users in database and not in servers
                if result is not None and self.bot.get_member(result['id']) is None:
                    await ctx.send(
                        "**@{0}** was no longer in server and was removed successfully.".format(result["name"]))
                    delete_id = result["id"]
                # User in servers and in database
                elif user is not None and result is not None:
                    await ctx.send("**{0}** was removed successfully.".format(user.display_name))
                    delete_id = user.id
                # User in server but not in database
                elif user is not None and result is None:
                    await ctx.send("**{0}** is not registered.".format(user.display_name))
                    return
                # User not in server or database
                else:
                    await ctx.send("I don't see any user named **{0}**.".format(name))
                    return

                c.execute("DELETE FROM users WHERE id = ?", (delete_id,))
                c.execute("SELECT name FROM chars WHERE user_id = ?", (delete_id,))
                result = c.fetchall()
                if len(result) >= 1:
                    chars = ["**" + i["name"] + "**" for i in result]
                    reply = "The following characters were registered to the user:\n\t"
                    reply += "\n\t".join(chars)
                    reply += "\nDo you want to delete them? ``(yes/no)``"
                    await ctx.send(reply)

                    def check(m):
                        return m.author == ctx.message.author and m.channel == ctx.message.channel
                    try:
                        answer = await self.bot.wait_for("message", timeout=30.0, check=check)
                        if answer.content.lower() in ["yes", "y"]:
                            c.execute("DELETE FROM chars WHERE user_id = ?", (delete_id,))
                            await ctx.send("Characters deleted successfully.")
                        else:
                            await ctx.send("Ok, we are done then.")
                    except asyncio.TimeoutError:
                        await ctx.send("I will take your silence as a no...")
                return
            finally:
                c.close()
                userDatabase.commit()

    # Todo: Add server-log entry
    @stalk.command(name="namelock", aliases=["namechange","rename"])
    @checks.is_mod()
    @checks.is_not_lite()
    async def stalk_namelock(self, ctx, *, params):
        """Register the name of a new character that was namelocked.

        Characters that get namelocked can't be searched by their old name, so they must be reassigned manually.

        If the character got a name change (from the store), searching the old name redirects to the new name, so
        this are usually reassigned automatically.

        The syntax is:
        /stalk namelock oldname,newname"""
        if not is_private(ctx.message.channel):
            return True
        params = params.split(",")
        if len(params) != 2:
            await ctx.send("The correct syntax is: `/stalk namelock oldname,newname")
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
                old_char = await get_character(old_name)
                if old_char == ERROR_NETWORK:
                    await ctx.send("I'm having problem with 'the internet' as you humans say, try again.")
                    return
                # Check if returns a result
                if type(old_char) is dict:
                    if old_name.lower() == old_char["name"].lower():
                        await ctx.send("The character **{0}** wasn't namelocked.".format(old_char["name"]))
                    else:
                        await ctx.send("The character **{0}** was renamed to **{1}**.".format(old_name,
                                                                                                   old_char["name"]))
                        # Renaming is actually done in get_character(), no need to do anything.
                    return

                # Check if new name exists
                new_char = await get_character(new_name)
                if new_char == ERROR_NETWORK:
                    await ctx.send("I'm having problem with 'the internet' as you humans say, try again.")
                    return
                if new_char == ERROR_DOESNTEXIST:
                    await ctx.send("The character **{0}** doesn't exists.".format(new_name))
                    return
                # Check if vocations are similar
                if not (old_char_db["vocation"].lower() in new_char["vocation"].lower()
                        or new_char["vocation"].lower() in old_char_db["vocation"].lower()):
                    await ctx.send("**{0}** was a *{1}* and **{2}** is a *{3}*. I think you're making a mistake."
                                            .format(old_char_db["name"], old_char_db["vocation"],
                                                    new_char["name"], new_char["vocation"]))
                    return
                confirm_message = "Are you sure **{0}** ({1} {2}) is **{3}** ({4} {5}) now? `yes/no`"
                await ctx.send(confirm_message.format(old_char_db["name"], abs(old_char_db["last_level"]),
                                                           old_char_db["vocation"], new_char["name"], new_char["level"],
                                                           new_char["vocation"]))

                def check(m):
                    return m.channel == ctx.message.channel and m.author == ctx.message.author
                try:
                    reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                    if reply.content.lower() not in ["yes", "y"]:
                        await ctx.send("No then? Alright.")
                        return
                except asyncio.TimeoutError:
                    await ctx.send("No answer? I guess you changed your mind.")
                    return

                # Check if new name was already registered
                c.execute("SELECT * FROM chars WHERE name LIKE ?", (new_char["name"],))
                new_char_db = c.fetchone()

                if new_char_db is None:
                    c.execute("UPDATE chars SET name = ?, vocation = ?, last_level = ? WHERE id = ?",
                              (new_char["name"], new_char["vocation"], new_char["level"],old_char_db["id"],))
                else:
                    # Replace new char with old char id and delete old char, reassign deaths and levelups
                    c.execute("DELETE FROM chars WHERE id = ?", (old_char_db["id"]),)
                    c.execute("UPDATE chars SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))
                    c.execute("UPDATE char_deaths SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))
                    c.execute("UPDATE char_levelups SET id = ? WHERE id = ?", (old_char_db["id"], new_char_db["id"],))

                await ctx.send("Character renamed successfully.")
            finally:
                c.close()
                userDatabase.commit()

    @stalk.command()
    @checks.is_mod()
    @checks.is_not_lite()
    async def check(self, ctx):
        """Check which users are currently not registered."""
        if not is_private(ctx.message.channel):
            return True

        author = ctx.message.author
        if author.id in mod_ids+owner_ids:
            author_servers = self.bot.get_user_guilds(author.id)
        else:
            author_servers = self.bot.get_user_admin_guilds(author.id)

        embed = discord.Embed(description="Members with unregistered users.")

        with ctx.typing():
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
                    users = [i["user_id"] for i in result]
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
                    split_value = split_message(field_value, FIELD_VALUE_LIMIT)
                    for empty_member in split_value:
                        if empty_member == split_value[0]:
                            name = server.name
                        else:
                            name = "\u200F"
                        embed.add_field(name=name, value=empty_member, inline=False)
                await ctx.send(embed=embed)
            finally:
                c.close()

    @stalk.command(name="refreshnames")
    @checks.is_mod()
    @checks.is_not_lite()
    async def refresh_names(self, ctx):
        """Checks and updates user names on the database."""
        if not is_private(ctx.message.channel):
            return True
        c = userDatabase.cursor()
        try:
            c.execute("SELECT id FROM users")
            result = c.fetchall()
            if len(result) <= 0:
                await ctx.send("There are no registered users.")
                return
            update_users = list()
            for user in result:
                update_users.append(
                    ("unknown" if self.bot.get_member(user[0]) is None else self.bot.get_member(user[0]).display_name,
                     user["id"]))
            c.executemany("UPDATE users SET name = ? WHERE id LIKE ?", update_users)
            await ctx.send("Usernames updated successfully.")
        finally:
            c.close()
            userDatabase.commit()

    @add_char.error
    @add_account.error
    @remove_char.error
    @remove_user.error
    @check.error
    @refresh_names.error
    async def stalk_error(self, ctx, error):
        if not is_private(ctx.message.channel):
            return
        if isinstance(error, commands.errors.CheckFailure):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send("You're missing a required argument. `Type /help {0}`".format(ctx.invoked_subcommand))

    @commands.guild_only()
    @checks.is_mod()
    @commands.group(invoke_without_command=True)
    async def ignore(self, ctx, *, channel: discord.TextChannel = None):
        """Ignores a channel

        Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

        If the parameter is used with no parameters, it ignores the current channel.

        Note that server administrators can bypass this."""
        if channel is None:
            channel = ctx.channel

        if channel.id in self.ignored.get(ctx.guild.id, []):
            await ctx.send(f"{channel.mention} is already ignored.")
            return

        with userDatabase:
            userDatabase.execute("INSERT INTO ignored_channels(server_id, channel_id) VALUES(?, ?)",
                                 (ctx.guild.id, channel.id))
            await ctx.send(f"{channel.mention} is now ignored.")
            self.reload_ignored()

    @commands.guild_only()
    @checks.is_mod()
    @ignore.command(name="list")
    async def ignore_list(self, ctx):
        """Shows a list of ignored channels"""
        entries = [ctx.guild.get_channel(c).name for c in self.ignored.get(ctx.guild.id, []) if ctx.guild.get_channel(c) is not None]
        if not entries:
            await ctx.send("There are no ignored channels in this server.")
            return
        pages = Paginator(self.bot, message=ctx.message, entries=entries, title="Ignored channels")
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.guild_only()
    @checks.is_mod()
    @commands.command()
    async def unignore(self, ctx, *, channel: discord.TextChannel = None):
        """Unignores a channel

        Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

        If the parameter is used with no parameters, it ignores the current channel."""
        if channel is None:
            channel = ctx.channel

        if channel.id not in self.ignored.get(ctx.guild.id, []):
            await ctx.send(f"{channel.mention} is not ignored.")
            return

        with userDatabase:
            userDatabase.execute("DELETE FROM ignored_channels WHERE channel_id = ?", (channel.id,))
            await ctx.send(f"{channel.mention} is not ignored anymore.")
            self.reload_ignored()

    @ignore.error
    @unignore.error
    async def ignore_error(self, ctx, error):
        if isinstance(error, commands.errors.BadArgument):
            await ctx.send(error)

    def reload_ignored(self):
        """Refresh the world list from the database

        This is used to avoid reading the database everytime the world list is needed.
        A global variable holding the world list is loaded on startup and refreshed only when worlds are modified"""
        c = userDatabase.cursor()
        ignored_dict_temp = {}  # type: Dict[int, List[int]]
        try:
            c.execute("SELECT server_id, channel_id FROM ignored_channels")
            result = c.fetchall()  # type: Dict
            if len(result) > 0:
                for row in result:
                    if not ignored_dict_temp.get(row["server_id"]):
                        ignored_dict_temp[row["server_id"]] = []

                    ignored_dict_temp[row["server_id"]].append(row["channel_id"])

            self.ignored.clear()
            self.ignored.update(ignored_dict_temp)
        finally:
            c.close()

def setup(bot):
    bot.add_cog(Mod(bot))
