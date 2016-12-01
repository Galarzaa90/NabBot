import platform
from discord.ext import commands
import asyncio

from utils import *
from config import *
from utils_tibia import *


class Mod:
    def __init__(self, bot: discord.Client):
        self.bot = bot

    # Admin only commands #
    @commands.command(pass_context=True, hidden=True)
    @is_mod()
    @asyncio.coroutine
    def makesay(self, ctx, *args: str):
        if ctx.message.channel.is_private:
            channel = getChannelByName(self.bot, mainchannel, mainserver)
            yield from self.bot.send_message(channel, " ".join(args))
        else:
            yield from self.bot.delete_message(ctx.message)
            yield from self.bot.send_message(ctx.message.channel, " ".join(args))

    @commands.command(pass_context=True, hidden=True)
    @is_mod()
    @is_pm()
    @asyncio.coroutine
    def stalk(self, ctx, subcommand, *args: str):
        if lite_mode:
            return
        params = (" ".join(args)).split(",")
        try:
            c = userDatabase.cursor()
            # Add user
            if subcommand == "add":
                if len(params) != 1:
                    yield from self.bot.say("The correct syntax is: ``/stalk add username``")
                    return
                user = getMemberByName(self.bot, params[0])
                if user is None:
                    yield from self.bot.say("I don't see any user named **{0}**.".format(params[0]))
                    return
                c.execute("SELECT id from users WHERE id LIKE ?", (user.id,))
                if c.fetchone() is not None:
                    yield from self.bot.say("**@{0}** is already registered.".format(user.display_name))
                    return
                c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
                yield from self.bot.say("**@{0}** was registered successfully.".format(user.display_name))

            # Add char & Add account common operations
            if subcommand == "addchar" or subcommand == "addacc":
                if len(params) != 2:
                    yield from self.bot.say("The correct syntax is: ``/stalk {0} username,character``".format(subcommand))
                    return
                user = getMemberByName(self.bot, params[0])
                char = yield from getPlayer(params[1])
                if user is None:
                    yield from self.bot.say("I don't see any user named **{0}**".format(params[0]))
                    return
                if type(char) is not dict:
                    if char == ERROR_NETWORK:
                        yield from self.bot.say("I couldn't fetch the character, please try again.")
                    elif char == ERROR_DOESNTEXIST:
                        yield from self.bot.say("That character doesn't exists.")
                    return
                # Add char
                if subcommand == "addchar":
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
                            current_user = getMember(self.bot, result["user_id"])
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
                    c.execute("INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",
                              (char['name'], char['level'] * -1, char['vocation'], user.id))
                    # Check if user is already registered
                    c.execute("SELECT id from users WHERE id = ?", (user.id,))
                    result = c.fetchone()
                    if result is None:
                        c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
                        yield from self.bot.say("**@{0}** was registered successfully.".format(user.display_name))
                    yield from self.bot.say("**{0}** was registered successfully to this user.".format(char['name']))
                    return

                # Add account
                if subcommand == "addacc":
                    chars = char['chars']
                    # If the char is hidden,we still add the searched character
                    if len(chars) == 0:
                        yield from self.bot.say("Character is hidden.")
                        chars = [char]
                    for char in chars:
                        if char['world'] not in tibiaservers:
                            yield from self.bot.say("**{0}** skipped, character not in server list.".format(char['name']))
                            continue
                        char = yield from getPlayer(char['name'])
                        c.execute("SELECT id, name,user_id FROM chars WHERE name LIKE ?", (char['name'],))
                        result = c.fetchone()
                        # Char is already in database
                        if result is not None:
                            # Registered to different user
                            if result["user_id"] != user.id:
                                current_user = getMember(self.bot, result["user_id"])
                                # Char is registered to user no longer in server
                                if current_user is None:
                                    c.execute("UPDATE chars SET user_id = ? WHERE id = ?", (user.id, result["id"],))
                                    yield from self.bot.say("**{0}** was registered to a user no longer in server. "
                                                       "It was assigned to this user successfully.".format(
                                        char["name"]))
                                else:
                                    yield from self.bot.say("**{0}** is already registered to **@{1}**".format(
                                        char['name'],
                                        current_user.display_name)
                                    )
                                    continue
                            # Registered too current user
                            yield from self.bot.say("**{0}** is already registered to this user.".format(char['name']))
                            continue
                        c.execute(
                            "INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",
                            (char['name'], char['level'] * -1, char['vocation'], user.id)
                        )
                        yield from self.bot.say("**{0}** was registered successfully to this user.".format(char['name']))
                    c.execute("SELECT id from users WHERE id = ?", (user.id,))
                    result = c.fetchone()
                    if result is None:
                        c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
                        yield from self.bot.say("**@{0}** was registered successfully.".format(user.display_name))
                    return

            # Remove char
            if subcommand == "removechar":
                if len(params) != 1:
                    yield from self.bot.say("The correct syntax is: ``/stalk {0} character``".format(subcommand))
                    return
                char = params[0]
                # This could be used to remove deleted chars so we don't need to check anything
                # Except if the char exists in the database...
                c.execute("SELECT name, user_id FROM chars WHERE name LIKE ?", (char,))
                result = c.fetchone()
                if result is None:
                    yield from self.bot.say("There's no character with that name registered.")
                    return
                username = "unknown" if getMember(self.bot, result[1]) is None else getMember(self.bot, result[1]).display_name
                c.execute("DELETE FROM chars WHERE name LIKE ?", (result[0],))
                yield from self.bot.say("**{0}** was removed successfully from **@{1}**.".format(result[0], username))
                return
            # Remove user
            if subcommand == "remove":
                if len(params) != 1:
                    yield from self.bot.say("The correct syntax is: ``/stalk {0} user``".format(subcommand))
                    return

                # Searching users in server
                user = getMemberByName(self.bot, params[0])
                # Searching users in database
                c.execute("SELECT id, name from users WHERE name LIKE ?", (params[0],))
                result = c.fetchone()
                # Users in database and not in servers
                if result is not None and getMember(self.bot, result['id']) is None:
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
                    yield from self.bot.say("I don't see any user named **{0}**.".format(params[0]))
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
                                                             timeout=20.0)
                    if answer is None:
                        yield from self.bot.reply("I will take your silence as a no...")
                    elif answer.content.lower() in ["yes", "y"]:
                        c.execute("DELETE FROM chars WHERE user_id = ?", (delete_id,))
                        yield from self.bot.say("Characters deleted successfully.")
                    else:
                        yield from self.bot.say("Ok, we are done then.")
                return
            # Purge
            if subcommand == "purge":
                c.execute("SELECT id FROM users")
                result = c.fetchall()
                if result is None:
                    yield from self.bot.say("There are no users registered.")
                    return
                delete_users = list()
                yield from self.bot.say("Initiating purge...")
                # Deleting users no longer in server
                for row in result:
                    user = getMember(self.bot, row["id"])
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
                    char = yield from getPlayer(row["name"])
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
            # Check
            if subcommand == "check":
                # Fetch a list of users with chars only:
                c.execute("SELECT user_id FROM chars GROUP BY user_id")
                result = c.fetchall()
                print(result)
                if len(result) <= 0:
                    yield from self.bot.say("There are no registered characters.")
                    return
                users = [str(i["user_id"]) for i in result]
                members = getServerByName(self.bot, mainserver).members
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
            # Checknames
            if subcommand == "refreshnames":
                c.execute("SELECT id FROM users")
                result = c.fetchall()
                if len(result) <= 0:
                    yield from self.bot.say("There are no registered users.")
                    return
                update_users = list()
                for user in result:
                    update_users.append(
                        ("unknown" if getMember(self.bot, user[0]) is None else getMember(self.bot, user[0]).display_name, user["id"]))
                c.executemany("UPDATE users SET name = ? WHERE id LIKE ?", update_users)
                yield from self.bot.say("Usernames updated successfully.")
        finally:
            c.close()
            userDatabase.commit()

    @stalk.error
    @asyncio.coroutine
    def stalk_error(self, error, ctx):
        if lite_mode:
            return
        if type(error) is commands.MissingRequiredArgument:
            yield from self.bot.say("""```Valid subcommands are:
            /stalk add user
            /stalk addchar user,char
            /stalk addacc user,char
            /stalk remove user
            /stalk removechar char
            /stalk purge
            /stalk check
            /stalk refreshnames```""")


def setup(bot):
    bot.add_cog(Mod(bot))
