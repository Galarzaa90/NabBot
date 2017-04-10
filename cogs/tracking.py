import discord
import asyncio
import time

from config import death_scan_interval, highscores_delay, highscores_categories, highscores_page_delay, \
    online_scan_interval, announce_threshold
from utils.database import tracked_worlds_list, userDatabase, tracked_worlds
from utils.discord import get_announce_channel
from utils.general import global_online_list, log
from utils.messages import weighed_choice, deathmessages_player, deathmessages_monster, format_message, EMOJI, \
    levelmessages
from utils.tibia import get_highscores, ERROR_NETWORK, tibia_worlds, get_world_online, get_character, ERROR_DOESNTEXIST, \
    parse_tibia_time, get_pronouns


class Tracking:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.bot.loop.create_task(self.scan_deaths())
        self.bot.loop.create_task(self.scan_online_chars())
        self.bot.loop.create_task(self.scan_highscores())

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
                        "UPDATE chars SET " + category + " = NULL, " + category + "_rank" + " = NULL WHERE " + category + "_rank" + " LIKE ? AND world LIKE ?",
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

    async def announce_death(self, death_level, death_killer, death_by_player, levels_lost=0, char=None, char_name=None):
        """Announces a level up on the corresponding servers"""
        # Don't announce for low level players
        if int(death_level) < announce_threshold:
            return
        if char is None:
            if char_name is None:
                log.error("announce_death: no character or character name passed.")
                return
            char = await get_character(char_name)
        if type(char) is not dict:
            log.warning("announce_death: couldn't fetch character (" + char_name + ")")
            return

        log.info("Announcing death: {0}({1}) | {2}".format(char["name"], death_level, death_killer))

        # Get correct pronouns
        pronoun = get_pronouns(char["gender"])

        # Find killer article (a/an)
        death_killer_article = ""
        if not death_by_player:
            death_killer_article = death_killer.split(" ", 1)
            if death_killer_article[0] in ["a", "an"] and len(death_killer_article) > 1:
                death_killer = death_killer_article[1]
                death_killer_article = death_killer_article[0] + " "
            else:
                death_killer_article = ""

        # Select a message
        if death_by_player:
            message = weighed_choice(deathmessages_player, vocation=char['vocation'], level=int(death_level),
                                     levels_lost=levels_lost)
        else:
            message = weighed_choice(deathmessages_monster, vocation=char['vocation'], level=int(death_level),
                                     levels_lost=levels_lost, killer=death_killer)
        # Format message with death information
        deathInfo = {'charName': char["name"], 'deathLevel': death_level, 'deathKiller': death_killer,
                     'deathKillerArticle': death_killer_article, 'pronoun1': pronoun[0], 'pronoun2': pronoun[1],
                     'pronoun3': pronoun[2]}
        message = message.format(**deathInfo)
        # Format extra stylization
        message = format_message(message)
        message = EMOJI[":skull_crossbones:"] + " " + message

        for guild_id, tracked_world in tracked_worlds.items():
            guild = self.bot.get_guild(guild_id)
            if char["world"] == tracked_world and guild is not None \
                    and guild.get_member(char["owner_id"]) is not None:
                await get_announce_channel(self.bot, guild).send(message[:1].upper() + message[1:])

    async def announce_level(self, new_level, char_name=None, char=None):
        """Announces a level up on corresponding servers

        One of these must be passed:
        char is a character dictionary
        char_name is a character's name

        If char_name is passed, the character is fetched here."""
        # Don't announce low level players
        if int(new_level) < announce_threshold:
            return
        if char is None:
            if char_name is None:
                log.error("announce_level: no character or character name passed.")
                return
            char = await get_character(char_name)
        if type(char) is not dict:
            log.warning("announce_level: couldn't fetch character (" + char_name + ")")
            return

        log.info("Announcing level up: {0} ({1})".format(char["name"], new_level))

        # Get pronouns based on gender
        pronoun = get_pronouns(char['gender'])

        # Select a message
        message = weighed_choice(levelmessages, vocation=char['vocation'], level=int(new_level))
        # Format message with level information
        level_info = {'charName': char["name"], 'newLevel': new_level, 'pronoun1': pronoun[0], 'pronoun2': pronoun[1],
                      'pronoun3': pronoun[2]}
        message = message.format(**level_info)
        # Format extra stylization
        message = format_message(message)
        message = EMOJI[":star2:"] + " " + message

        for server_id, tracked_world in tracked_worlds.items():
            server = self.bot.get_guild(server_id)
            if char["world"] == tracked_world and server is not None \
                    and server.get_member(char["owner_id"]) is not None:
                await get_announce_channel(self.bot, server).send(message)


def setup(bot):
    bot.add_cog(Tracking(bot))
