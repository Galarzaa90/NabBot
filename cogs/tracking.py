import discord
from discord.ext import commands
import asyncio
import time

from config import death_scan_interval, highscores_delay, highscores_categories, highscores_page_delay, \
    online_scan_interval, announce_threshold, owner_ids, mod_ids
from nabbot import NabBot
from utils import checks
from utils.database import tracked_worlds_list, userDatabase, tracked_worlds
from utils.discord import is_private
from utils.general import global_online_list, log, join_list
from utils.messages import weighed_choice, death_messages_player, death_messages_monster, format_message, EMOJI, \
    level_messages
from utils.tibia import get_highscores, ERROR_NETWORK, tibia_worlds, get_world_online, get_character, ERROR_DOESNTEXIST, \
    parse_tibia_time, get_pronouns, get_voc_emoji, get_guild_online


class Tracking:
    """Commands related to Nab Bot's tracking system."""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.scan_deaths_task = self.bot.loop.create_task(self.scan_deaths())
        self.scan_online_chars_task = bot.loop.create_task(self.scan_online_chars())
        self.scan_highscores_task = bot.loop.create_task(self.scan_highscores())

        self.watched_channels = dict()
        self.watched_messages = dict()
        self.reload_watched()

    async def scan_deaths(self):
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(death_scan_interval)
            if len(global_online_list) == 0:
                continue
            # Pop last char in queue, reinsert it at the beginning
            current_char = global_online_list.pop()
            global_online_list.insert(0, current_char)

            # Get rid of server name
            current_char = current_char.split("_", 1)[1]
            # Check for new death
            await self.check_death(current_char)

    async def scan_highscores(self):
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            if len(tracked_worlds_list) == 0:
                # If no worlds are tracked, just sleep, worlds might get registered later
                await asyncio.sleep(highscores_delay)
                continue
            for server in tracked_worlds_list:
                for category in highscores_categories:
                    highscores = []
                    for pagenum in range(1, 13):
                        # Special cases (ek/rp mls)
                        if category == "magic_ek":
                            scores = await get_highscores(server, "magic", pagenum, 3)
                        elif category == "magic_rp":
                            scores = await get_highscores(server, "magic", pagenum, 4)
                        else:
                            scores = await get_highscores(server, category, pagenum)
                        if not (scores == ERROR_NETWORK):
                            highscores += scores
                        await asyncio.sleep(highscores_page_delay)
                    # Open connection to users.db
                    c = userDatabase.cursor()
                    scores_tuple = []
                    ranks_tuple = []
                    for score in highscores:
                        scores_tuple.append((score['rank'], score['value'], score['name']))
                        ranks_tuple.append((score['rank'], server))
                    # Clear out old rankings
                    c.executemany(
                        "UPDATE chars SET " + category + " = NULL, " + category + "_rank" + " = NULL WHERE " + category
                        + "_rank" + " LIKE ? AND world LIKE ?",
                        ranks_tuple
                    )
                    # Add new rankings
                    c.executemany(
                        "UPDATE chars SET " + category + "_rank" + " = ?, " + category + " = ? WHERE name LIKE ?",
                        scores_tuple
                    )
                    userDatabase.commit()
                    c.close()
                await asyncio.sleep(0.1)

    async def scan_online_chars(self):
        #################################################
        #             Nezune's cave                     #
        # Do not touch anything, enter at your own risk #
        #################################################
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            # Pop last server in queue, reinsert it at the beginning
            current_world = tibia_worlds.pop()
            tibia_worlds.insert(0, current_world)

            if current_world.capitalize() not in tracked_worlds_list:
                await asyncio.sleep(0.1)
                continue

            await asyncio.sleep(online_scan_interval)
            # Get online list for this server
            curent_world_online = await get_world_online(current_world)
            if len(curent_world_online) > 0:
                # Open connection to users.db
                c = userDatabase.cursor()

                # Remove chars that are no longer online from the globalOnlineList
                offline_list = []
                for char in global_online_list:
                    if char.split("_", 1)[0] == current_world:
                        offline = True
                        for server_char in curent_world_online:
                            if server_char['name'] == char.split("_", 1)[1]:
                                offline = False
                                break
                        if offline:
                            offline_list.append(char)
                for now_offline_char in offline_list:
                    global_online_list.remove(now_offline_char)
                    # Check for deaths and level ups when removing from online list
                    now_offline_char = await get_character(now_offline_char.split("_", 1)[1])
                    if not (now_offline_char == ERROR_NETWORK or now_offline_char == ERROR_DOESNTEXIST):
                        c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?",
                                  (now_offline_char['name'],))
                        result = c.fetchone()
                        if result:
                            last_level = result["last_level"]
                            c.execute(
                                "UPDATE chars SET last_level = ? WHERE name LIKE ?",
                                (now_offline_char['level'], now_offline_char['name'],)
                            )
                            if now_offline_char['level'] > last_level > 0:
                                # Saving level up date in database
                                c.execute(
                                    "INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",
                                    (result["id"], now_offline_char['level'], time.time(),)
                                )
                                # Announce the level up
                                await self.announce_level(now_offline_char['level'], char=now_offline_char)
                        await self.check_death(now_offline_char['name'])

                # Add new online chars and announce level differences
                for server_char in curent_world_online:
                    c.execute("SELECT name, last_level, id, user_id FROM chars WHERE name LIKE ?",
                              (server_char['name'],))
                    result = c.fetchone()
                    if result:
                        # If its a stalked character
                        last_level = result["last_level"]
                        # We update their last level in the db
                        c.execute(
                            "UPDATE chars SET last_level = ? WHERE name LIKE ?",
                            (server_char['level'], server_char['name'],)
                        )

                        if not (current_world + "_" + server_char['name']) in global_online_list:
                            # If the character wasn't in the globalOnlineList we add them
                            # (We insert them at the beginning of the list to avoid messing with the death checks order)
                            global_online_list.insert(0, (current_world + "_" + server_char['name']))
                            # Since this is the first time we see them online we flag their last death time
                            # to avoid backlogged death announces
                            c.execute(
                                "UPDATE chars SET last_death_time = ? WHERE name LIKE ?",
                                (None, server_char['name'],)
                            )
                            await self.check_death(server_char['name'])

                        # Else we check for levelup
                        elif server_char['level'] > last_level > 0:
                            # Saving level up date in database
                            c.execute(
                                "INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",
                                (result["id"], server_char['level'], time.time(),)
                            )
                            # Announce the level up
                            await self.announce_level(server_char['level'], char_name=server_char["name"])
                # Watched List checking
                # Iterate through servers with tracked world to find one that matches the current world
                for server, world in tracked_worlds.items():
                    if world == current_world:
                        watched_channel_id = self.watched_channels.get(server, None)
                        if watched_channel_id is None:
                            # This server doesn't have watch list enabled
                            continue
                        watched_channel = self.bot.get_channel(watched_channel_id)  # type: discord.abc.Messageable
                        if watched_channel is None:
                            # This server's watched channel is not available to the bot anymore.
                            continue
                        # Get watched list
                        c.execute("SELECT * FROM watched_list WHERE server_id = ?", (server,))
                        results = c.fetchall()
                        if not results:
                            # List is empty
                            continue
                        # Online watched characters
                        currently_online = []
                        # Watched guilds
                        guild_online = dict()
                        for watched in results:
                            if watched["is_guild"]:
                                guild = await get_guild_online(watched["name"])
                                # Todo: Remove deleted guilds from list to avoid unnecesary checks, notify
                                if guild == ERROR_NETWORK or guild == ERROR_DOESNTEXIST:
                                    continue
                                # If there's at least one member online, add guild to list
                                if len(guild["members"]):
                                    guild_online[guild["name"]] = guild["members"]
                            # If it is a character, check if he's in the online list
                            for online_char in curent_world_online:
                                if online_char["name"] == watched["name"]:
                                    # Add to online list
                                    currently_online.append(online_char)
                        watched_message_id = self.watched_messages.get(server, None)
                        # We try to get the watched message, if the bot can't find it, we just create a new one
                        # This may be because the old message was deleted or this is the first time the list is checked
                        try:
                            watched_message = await watched_channel.get_message(watched_message_id)
                        except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                            watched_message = None
                        items = [f"\t{x['name']} - Level {x['level']} {get_voc_emoji(x['vocation'])}"
                                for x in currently_online]
                        if len(items) > 0 or len(guild_online.keys()) > 0:
                            content = "These watched characters are online:\n"
                            content += "\n".join(items)
                            for guild, members in guild_online.items():
                                content += f"\nGuild: **{guild}**\n"
                                content += "\n".join([f"\t{x['name']} - Level {x['level']} {get_voc_emoji(x['vocation'])}"
                                                      for x in members])
                        else:
                            content = "There are no watched characters online."
                        # Send new watched message or edit last one
                        if watched_message is None:
                            new_watched_message = await watched_channel.send(content)
                            c.execute("DELETE FROM server_properties WHERE server_id = ? "
                                      "AND name LIKE ?", (server, "watched_message",))
                            c.execute("INSERT INTO server_properties(server_id, name, value) VALUES(?,?,?)",
                                      (server, "watched_message", new_watched_message.id))
                            self.watched_messages[server] = new_watched_message.id
                        else:
                            await watched_message.edit(content=content)
                # Close cursor and commit changes
                userDatabase.commit()
                c.close()

    async def check_death(self, character):
        """Checks if the player has new deaths"""
        char = await get_character(character)
        if type(char) is not dict:
            log.warning("check_death: couldn't fetch {0}".format(character))
            return
        character_deaths = char["deaths"]

        if character_deaths:
            c = userDatabase.cursor()
            c.execute("SELECT name, last_death_time, id FROM chars WHERE name LIKE ?", (character,))
            result = c.fetchone()
            if result:
                last_death = character_deaths[0]
                death_time = parse_tibia_time(last_death["time"]).timestamp()
                # Check if we have a death that matches the time
                c.execute("SELECT * FROM char_deaths "
                          "WHERE char_id = ? AND date >= ? AND date <= ? AND level = ? AND killer LIKE ?",
                          (result["id"], death_time - 200, death_time + 200, last_death["level"], last_death["killer"]))
                last_saved_death = c.fetchone()
                if last_saved_death is not None:
                    # This death is already saved, so nothing else to do here.
                    return

                c.execute(
                    "INSERT INTO char_deaths (char_id,level,killer,byplayer,date) VALUES(?,?,?,?,?)",
                    (result["id"], int(last_death['level']), last_death['killer'], last_death['byPlayer'], death_time,)
                )

                # If the death happened more than 1 hour ago, we don't announce it, but it's saved already.
                if time.time() - death_time >= (1 * 60 * 60):
                    log.info("Death detected, but too old to announce: {0}({1}) | {2}".format(character,
                                                                                              last_death['level'],
                                                                                              last_death['killer']))
                else:
                    await self.announce_death(last_death['level'], last_death['killer'], last_death['byPlayer'],
                                              max(last_death["level"] - char["level"], 0), char)

            # Close cursor and commit changes
            userDatabase.commit()
            c.close()

    async def announce_death(self, level, killer, by_player, levels_lost=0, char=None, char_name=None):
        """Announces a level up on the corresponding servers"""
        # Don't announce for low level players
        if int(level) < announce_threshold:
            return
        if char is None:
            if char_name is None:
                log.error("announce_death: no character or character name passed.")
                return
            char = await get_character(char_name)
        if type(char) is not dict:
            log.warning("announce_death: couldn't fetch character (" + char_name + ")")
            return

        log.info("Announcing death: {0}({1}) | {2}".format(char["name"], level, killer))

        # Get correct pronouns
        pronoun = get_pronouns(char["gender"])

        # Find killer article (a/an)
        killer_article = ""
        if not by_player:
            killer_article = killer.split(" ", 1)
            if killer_article[0] in ["a", "an"] and len(killer_article) > 1:
                killer = killer_article[1]
                killer_article = killer_article[0] + " "
            else:
                killer_article = ""

        # Select a message
        if by_player:
            message = weighed_choice(death_messages_player, vocation=char['vocation'], level=int(level),
                                     levels_lost=levels_lost)
        else:
            message = weighed_choice(death_messages_monster, vocation=char['vocation'], level=int(level),
                                     levels_lost=levels_lost, killer=killer)
        # Format message with death information
        death_info = {'name': char["name"], 'level': level, 'killer': killer, 'killer_article': killer_article,
                      'he_she': pronoun[0], 'his_her': pronoun[1], 'him_her': pronoun[2]}
        message = message.format(**death_info)
        # Format extra stylization
        message = format_message(message)
        if by_player:
            message = EMOJI[":skull:"] + " " + message
        else:
            message = EMOJI[":skull_crossbones:"] + " " + message

        for guild_id, tracked_world in tracked_worlds.items():
            guild = self.bot.get_guild(guild_id)
            if char["world"] == tracked_world and guild is not None \
                    and guild.get_member(char["owner_id"]) is not None:
                await self.bot.get_announce_channel(guild).send(message[:1].upper() + message[1:])

    async def announce_level(self, level, char_name=None, char=None):
        """Announces a level up on corresponding servers

        One of these must be passed:
        char is a character dictionary
        char_name is a character's name

        If char_name is passed, the character is fetched here."""
        # Don't announce low level players
        if int(level) < announce_threshold:
            return
        if char is None:
            if char_name is None:
                log.error("announce_level: no character or character name passed.")
                return
            char = await get_character(char_name)
        if type(char) is not dict:
            log.warning("announce_level: couldn't fetch character (" + char_name + ")")
            return

        log.info("Announcing level up: {0} ({1})".format(char["name"], level))

        # Get pronouns based on gender
        pronoun = get_pronouns(char['gender'])

        # Select a message
        message = weighed_choice(level_messages, vocation=char['vocation'], level=int(level))
        # Format message with level information
        level_info = {'name': char["name"], 'level': level, 'he_she': pronoun[0], 'his_her': pronoun[1],
                      'him_her': pronoun[2]}
        message = message.format(**level_info)
        # Format extra stylization
        message = format_message(message)
        message = EMOJI[":star2:"] + " " + message

        for server_id, tracked_world in tracked_worlds.items():
            server = self.bot.get_guild(server_id)
            if char["world"] == tracked_world and server is not None \
                    and server.get_member(char["owner_id"]) is not None:
                await self.bot.get_announce_channel(server).send(message)

    @checks.is_not_lite()
    @commands.command(aliases=["i'm", "iam"])
    async def im(self, ctx, *, char_name: str):
        """Lets you add your tibia character(s) for the bot to track.

        If you need to add any more characters or made a mistake, please message an admin."""
        # This is equivalent to someone using /stalk addacc on themselves.
        user = ctx.message.author
        # List of servers the user shares with the self.bot
        user_guilds = self.bot.get_user_guilds(user.id)
        # List of Tibia worlds tracked in the servers the user is
        user_tibia_worlds = [world for guild, world in tracked_worlds.items() if guild in [g.id for g in user_guilds]]
        # Remove duplicate entries from list
        user_tibia_worlds = list(set(user_tibia_worlds))

        if not is_private(ctx.message.channel) and tracked_worlds.get(ctx.message.guild.id) is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        if len(user_tibia_worlds) == 0:
            return

        c = userDatabase.cursor()
        try:
            valid_mods = []
            for id in (owner_ids + mod_ids):
                mod = self.bot.get_member(id, ctx.message.guild)
                if mod is not None:
                    valid_mods.append(mod.mention)
            admins_message = join_list(valid_mods, ", ", " or ")
            await ctx.trigger_typing()
            char = await get_character(char_name)
            if type(char) is not dict:
                if char == ERROR_NETWORK:
                    await ctx.send("I couldn't fetch the character, please try again.")
                elif char == ERROR_DOESNTEXIST:
                    await ctx.send("That character doesn't exists.")
                return
            chars = char['chars']
            # If the char is hidden,we still add the searched character, if we have just one, we replace it with the
            # searched char, so we don't have to look him up again
            if len(chars) == 0 or len(chars) == 1:
                chars = [char]

            skipped = []
            updated = []
            added = []
            existent = []
            for char in chars:
                # Skip chars in non-tracked worlds
                if char["world"] not in user_tibia_worlds:
                    skipped.append(char)
                    continue
                c.execute("SELECT name, guild, user_id as owner FROM chars WHERE name LIKE ?", (char["name"],))
                db_char = c.fetchone()
                if db_char is not None:
                    owner = self.bot.get_member(db_char["owner"])
                    print(owner)
                    # Previous owner doesn't exist anymore
                    if owner is None:
                        updated.append({'name': char['name'], 'world': char['world'], 'prevowner': db_char["owner"]})
                        continue
                    # Char already registered to this user
                    elif owner.id == user.id:
                        existent.append("{name} ({world})".format(**char))
                        continue
                    # Character is registered to another user
                    else:
                        reply = "Sorry, a character in that account ({0}) is already claimed by **{1.mention}**.\n" \
                                "Maybe you made a mistake? Or someone claimed a character of yours?"
                        await ctx.send(reply.format(db_char["name"], owner, admins_message))
                        return
                # If we only have one char, it already contains full data
                if len(chars) > 1:
                    await ctx.message.channel.trigger_typing()
                    char = await get_character(char["name"])
                    if char == ERROR_NETWORK:
                        await ctx.send("I'm having network troubles, please try again.")
                        return
                if char.get("deleted", False):
                    skipped.append(char)
                    continue
                added.append(char)

            if len(skipped) == len(chars):
                reply = "Sorry, I couldn't find any characters from the servers I track ({0})."
                await ctx.send(reply.format(join_list(user_tibia_worlds, ", ", " and ")))
                return

            reply = ""
            log_reply = dict().fromkeys([server.id for server in user_guilds], "")
            if len(existent) > 0:
                reply += "\nThe following characters were already registered to you: {0}" \
                    .format(join_list(existent, ", ", " and "))

            if len(added) > 0:
                reply += "\nThe following characters were added to your account: {0}" \
                    .format(join_list(["{name} ({world})".format(**c) for c in added], ", ", " and "))
                for char in added:
                    log.info("Character {0} was assigned to {1.display_name} (ID: {1.id})".format(char['name'], user))
                    # Announce on server log of each server
                    for guild in user_guilds:
                        # Only announce on worlds where the character's world is tracked
                        if tracked_worlds.get(guild.id, None) == char["world"]:
                            _guild = "No guild" if char["guild"] is None else char["guild"]
                            log_reply[guild.id] += "\n\t{name} - {level} {vocation} - **{0}**".format(_guild, **char)

            if len(updated) > 0:
                reply += "\nThe following characters were reassigned to you: {0}" \
                    .format(join_list(["{name} ({world})".format(**c) for c in updated], ", ", " and "))
                for char in updated:
                    log.info("Character {0} was reassigned to {1.display_name} (ID: {1.id})".format(char['name'], user))
                    # Announce on server log of each server
                    for guild in user_guilds:
                        # Only announce on worlds where the character's world is tracked
                        if tracked_worlds.get(guild.id, None) == char["world"]:
                            log_reply[guild.id] += "\n\t{name} (Reassigned)".format(**char)

            for char in updated:
                c.execute("UPDATE chars SET user_id = ? WHERE name LIKE ?", (user.id, char['name']))
            for char in added:
                c.execute(
                    "INSERT INTO chars (name,last_level,vocation,user_id, world, guild) VALUES (?,?,?,?,?,?)",
                    (char['name'], char['level'] * -1, char['vocation'], user.id, char["world"], char["guild"])
                )

            c.execute("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (user.id, user.display_name,))
            c.execute("UPDATE users SET name = ? WHERE id = ?", (user.display_name, user.id,))

            await ctx.send(reply)
            for server_id, message in log_reply.items():
                if message:
                    message = user.mention + " registered the following characters: " + message
                    await self.bot.send_log_message(self.bot.get_guild(server_id), message)

        finally:
            c.close()
            userDatabase.commit()

    @checks.is_not_lite()
    @commands.command(aliases=["i'mnot"])
    async def imnot(self, ctx, *, name):
        """Removes a character assigned to you

        All registered level ups and deaths will be lost forever."""
        c = userDatabase.cursor()
        try:
            c.execute("SELECT id, name, ABS(last_level) as level, user_id, vocation, world "
                      "FROM chars WHERE name LIKE ?", (name,))
            char = c.fetchone()
            if char is None:
                await ctx.send("There's no character registered with that name.")
                return
            if char["user_id"] != ctx.message.author.id:
                await ctx.send("The character **{0}** is not registered to you.".format(char["name"]))
                return

            await ctx.send("Are you sure you want to unregister **{name}** ({level} {vocation})? `yes/no`"
                           "\n*All registered level ups and deaths will be lost forever.*"
                           .format(**char))

            def check(m):
                return m.channel == ctx.channel and m.author == ctx.author

            try:
                reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                if reply.content.lower() not in ["yes", "y"]:
                    await ctx.send("No then? Ok.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("I guess you changed your mind.")
                return

            c.execute("DELETE FROM chars WHERE id = ?", (char["id"],))
            c.execute("DELETE FROM char_levelups WHERE char_id = ?", (char["id"],))
            c.execute("DELETE FROM char_deaths WHERE char_id = ?", (char["id"],))
            await ctx.send("**{0}** is no longer registered to you.".format(char["name"]))

            user_servers = [s.id for s in self.bot.get_user_guilds(ctx.message.author.id)]
            for server_id, world in tracked_worlds.items():
                if char["world"] == world and server_id in user_servers:
                    message = "{0} unregistered **{1}**".format(ctx.message.author.mention, char["name"])
                    await self.bot.send_log_message(self.bot.get_guild(server_id), message)
        finally:
            userDatabase.commit()
            c.close()

    @commands.group(invoke_without_command=True, aliases=["watchlist", "hunted", "huntedlist"])
    @checks.is_admin()
    @commands.guild_only()
    async def watched(self, ctx, *, name="watched-list"):
        """Sets the watched list channel for this server

        Creates a new channel with the specified name.
        If no name is specified, the default name "watched-list" is used."""

        guild = ctx.message.guild  # type: discord.Guild
        watched_channel_id = self.watched_channels.get(guild.id)
        watched_channel = self.bot.get_channel(watched_channel_id)

        world = tracked_worlds.get(ctx.guild.id, None)
        if world is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        if watched_channel is not None:
            await ctx.send(f"This server already has a watched list channel: {watched_channel.mention}")
            return
        permissions = ctx.message.channel.permissions_for(ctx.me)  # type: discord.Permissions
        if not permissions.manage_channels and not permissions.manage_roles:
            await ctx.send("I need to have `Manage Channels` and `Manage Roles` permissions to use this command.")
            return
        c = userDatabase.cursor()
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            channel = await guild.create_text_channel(name, overwrites=overwrites)
        except discord.Forbidden:
            await ctx.send("Sorry, I don't have permissions to create channels. Either you give me `Manage Channels`")
        except discord.HTTPException:
            await ctx.send("Something went wrong, the channel name you chose is probably unvalid.")
        else:
            await ctx.send(f"Channel created successfully: {channel.mention}\n")
            await channel.send("This is where I will post a list of online watched characters."
                               "Right now only **admins** are able to read this.\n"
                               "Edit this channel's permissions to allow the roles you want.\n"
                               "This channel can be renamed freely."
                               "**It is important to not allow anyone to write in here**\n"
                               "*This message can be deleted now.*")
            c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'watched_channel'", (guild.id,))
            c.execute("INSERT INTO server_properties(server_id, name, value) VALUES (?, 'watched_channel', ?)",
                      (guild.id, channel.id,))
            self.reload_watched()
        finally:
            userDatabase.commit()
            c.close()

    @watched.command(name="add")
    @commands.guild_only()
    @checks.is_admin()
    async def watched_add(self, ctx, *, name=None):
        if name is None:
            ctx.send("You need to tell me the name of the person you want to add to the list.")

        world = tracked_worlds.get(ctx.guild.id, None)
        if world is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        char = await get_character(name)
        if char == ERROR_DOESNTEXIST:
            await ctx.send("There's no character with that name.")
            return
        elif char == ERROR_NETWORK:
            await ctx.send("I couldn't fetch that character right now, please try again.")
            return

        if char["world"] != world:
            await ctx.send(f"This character is not in **{world}**.")
            return
        c = userDatabase.cursor()
        try:
            c.execute("SELECT * FROM watched_list WHERE server_id = ? AND name LIKE ? and is_guild = 0",
                      (ctx.guild.id, char["name"]))
            result = c.fetchone()
            if result is not None:
                await ctx.send("This character is already in the watched list.")
                return

            message = await ctx.send("Do you want to add **{name}** (Level {level} {vocation}) to the watched list? "
                                     .format(**char))
            confirm = await self.bot.wait_for_confirmation_reaction(ctx, message,
                                                                    "Ok then, guess you changed your mind.")
            if not confirm:
                return

            c.execute("INSERT INTO watched_list(name, server_id) VALUES(?, ?)", (char["name"], ctx.guild.id,))
            await ctx.send("Character added to the watched list.")
        finally:
            userDatabase.commit()
            c.close()

    @watched.command(name="remove")
    @commands.guild_only()
    @checks.is_admin()
    async def watched_remove(self, ctx, *, name=None):
        if name is None:
            ctx.send("You need to tell me the name of the person you want to remove from the list.")

        world = tracked_worlds.get(ctx.guild.id, None)
        if world is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        c = userDatabase.cursor()
        try:
            c.execute("SELECT * FROM watched_list WHERE server_id = ? AND name LIKE ? and is_guild = 0",
                      (ctx.guild.id, name))
            result = c.fetchone()
            if result is None:
                await ctx.send("This character is not in the watched list.")
                return

            message = await ctx.send(f"Do you want to remove **{name}** from the watched list?")
            confirm = await self.bot.wait_for_confirmation_reaction(ctx, message,
                                                                    "Ok then, guess you changed your mind.")
            if not confirm:
                return

            c.execute("DELETE FROM watched_list WHERE server_id = ? AND name LIKE ?", (ctx.guild.id, name,))
            await ctx.send("Character removed from the watched list.")
        finally:
            userDatabase.commit()
            c.close()

    @watched.command(name="addguild")
    @commands.guild_only()
    @checks.is_admin()
    async def watched_addguild(self, ctx, *, name=None):
        if name is None:
            ctx.send("You need to tell me the name of the guild you want to add.")

        world = tracked_worlds.get(ctx.guild.id, None)
        if world is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        guild = await get_guild_online(name)
        if guild == ERROR_DOESNTEXIST:
            await ctx.send("There's no character with that name.")
            return
        elif guild == ERROR_NETWORK:
            await ctx.send("I couldn't fetch that guild right now, please try again.")
            return

        if guild["world"] != world:
            await ctx.send(f"This guild is not in **{world}**.")
            return
        c = userDatabase.cursor()
        try:
            c.execute("SELECT * FROM watched_list WHERE server_id = ? AND name LIKE ? and is_guild = 1",
                      (ctx.guild.id, guild["name"]))
            result = c.fetchone()
            if result is not None:
                await ctx.send("This guild is already in the watched list.")
                return

            message = await ctx.send("Do you want to add the guild **{name}** to the watched list?".format(**guild))
            confirm = await self.bot.wait_for_confirmation_reaction(ctx, message,
                                                                    "Ok then, guess you changed your mind.")
            if not confirm:
                return

            c.execute("INSERT INTO watched_list(name, server_id, is_guild) VALUES(?, ?, 1)",
                      (guild["name"], ctx.guild.id,))
            await ctx.send("Guild added to the watched list.")
        finally:
            userDatabase.commit()
            c.close()

    @watched.command(name="removeguild")
    @commands.guild_only()
    @checks.is_admin()
    async def watched_removeguild(self, ctx, *, name=None):
        if name is None:
            ctx.send("You need to tell me the name of the guild you want to remove from the list.")

        world = tracked_worlds.get(ctx.guild.id, None)
        if world is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        c = userDatabase.cursor()
        try:
            c.execute("SELECT * FROM watched_list WHERE server_id = ? AND name LIKE ? and is_guild = 1",
                      (ctx.guild.id, name))
            result = c.fetchone()
            if result is None:
                await ctx.send("This guild is not in the watched list.")
                return

            message = await ctx.send(f"Do you want to remove **{name}** from the watched list?")
            confirm = await self.bot.wait_for_confirmation_reaction(ctx, message,
                                                                    "Ok then, guess you changed your mind.")
            if not confirm:
                return

            c.execute("DELETE FROM watched_list WHERE server_id = ? AND name LIKE ? AND is_guild = 1",
                      (ctx.guild.id, name,))
            await ctx.send("Character removed from the watched list.")
        finally:
            userDatabase.commit()
            c.close()

    def reload_watched(self):
        c = userDatabase.cursor()
        watched_channels_temp = {}
        watched_messages_temp = {}
        try:
            c.execute("SELECT server_id, value FROM server_properties WHERE name = 'watched_channel'")
            result = c.fetchall()
            if len(result) > 0:
                for row in result:
                    try:
                        watched_channels_temp[int(row["server_id"])] = int(row["value"])
                    except ValueError:
                        continue
                self.watched_channels.clear()
                self.watched_channels.update(watched_channels_temp)
            c.execute("SELECT server_id, value FROM server_properties WHERE name = 'watched_message'")
            result = c.fetchall()
            if len(result) > 0:
                for row in result:
                    try:
                        watched_messages_temp[int(row["server_id"])] = int(row["value"])
                    except ValueError:
                        continue
                self.watched_messages.clear()
                self.watched_messages.update(watched_messages_temp)
        finally:
            c.close()

    def __unload(self):
        print("cogs.tracking: Cancelling pending tasks...")
        self.scan_deaths_task.cancel()
        self.scan_highscores_task.cancel()
        self.scan_online_chars_task.cancel()


def setup(bot):
    bot.add_cog(Tracking(bot))
