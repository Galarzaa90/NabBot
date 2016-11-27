import asyncio
from discord.ext import commands
import discord
from utils import *


# Commands
class Tibia:
    """Tibia related commands."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['check', 'player', 'checkplayer', 'char', 'character'], pass_context=True)
    @asyncio.coroutine
    def whois(self, ctx, *, name=None):
        """Tells you the characters of a user or the owner of a character and/or information of a tibia character

        Note that the bot has no way to know the characters of a member that just joined.
        The bot has to be taught about the character's of an user."""
        if lite_mode:
            if name is None:
                yield from self.bot.say("Tell me which character you want to check.")
            char = yield from getPlayer(name)
            if char == ERROR_DOESNTEXIST:
                yield from self.bot.say("I couldn't find a character with that name")
            elif char == ERROR_NETWORK:
                yield from self.bot.say("Sorry, I couldn't fetch the character's info, maybe you should try again...")
            else:
                embed = discord.Embed(description=getCharString(char))
                embed.set_author(name=char["name"],
                                 url=url_character + urllib.parse.quote(char["name"]),
                                 icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                 )
                yield from self.bot.say(embed=embed)
            return
        if name.lower() == self.bot.user.name.lower():
            yield from self.bot.say(embed=getAboutContent())
            return

        if name is None:
            yield from self.bot.say("Tell me which character or user you want to check.")

        char = yield from getPlayer(name)
        char_string = getCharString(char)
        user = getUserByName(name)
        user_string = getUserString(name)
        embed = discord.Embed()
        embed.description = ""

        # No user or char with that name
        if char == ERROR_DOESNTEXIST and user is None:
            yield from self.bot.say("I don't see any user or character with that name.")
            return
        # We found an user
        if user is not None:
            embed.description = user_string
            color = getUserColor(user, ctx.message.server)
            if color is not discord.Colour.default():
                embed.colour = color
            if "I don't know" not in user_string:
                embed.set_thumbnail(url=user.avatar_url)
            # Check if we found a char too
            if type(char) is dict:
                # If it's owned by the user, we append it to the same embed.
                if char["owner_id"] == int(user.id):
                    embed.description += "\n\nThe character "+char_string
                    yield from self.bot.say(embed=embed)
                    return
                # Not owned by same user, we display a separate embed
                else:
                    char_embed = discord.Embed(description=char_string)
                    char_embed.set_author(name=char["name"],
                                          url=url_character+urllib.parse.quote(char["name"]),
                                          icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                          )
                    yield from self.bot.say(embed=embed)
                    yield from self.bot.say(embed=char_embed)
            elif char == ERROR_NETWORK:
                yield from self.bot.say("I failed to do a character search for some reason "+EMOJI[":astonished:"])
        else:
            if char == ERROR_NETWORK:
                yield from self.bot.say("I failed to do a character search for some reason " + EMOJI[":astonished:"])
            elif type(char) is dict:
                embed.set_author(name=char["name"],
                                 url=url_character + urllib.parse.quote(char["name"]),
                                 icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                 )
                # Char is owned by a discord user
                owner = getUserById(char["owner_id"])
                if owner is not None:
                    embed.set_thumbnail(url=owner.avatar_url)
                    color = getUserColor(owner, ctx.message.server)
                    if color is not discord.Colour.default():
                        embed.colour = color
                    embed.description += "A character of @**{1.display_name}**\n".format(char["name"], owner)

                embed.description += char_string

            yield from self.bot.say(embed=embed)

    @commands.command(aliases=['expshare', 'party'])
    @asyncio.coroutine
    def share(self, *param: str):
        """Shows the sharing range for that level or character"""
        level = 0
        name = ''
        # Check if param is numeric
        try:
            level = int(param[0])
        # If it's not numeric, then it must be a char's name
        except ValueError:
            name = " ".join(param)
            char = yield from getPlayer(name)
            if type(char) is dict:
                level = int(char['level'])
                name = char['name']
            else:
                yield from self.bot.say('There is no character with that name.')
                return
        if level <= 0:
            replies = ["Invalid level.",
                       "I don't think that's a valid level.",
                       "You're doing it wrong!",
                       "Nope, you can't share with anyone.",
                       "You probably need a couple more levels"
                       ]
            yield from self.bot.say(random.choice(replies))
            return
        low = int(round(level*2/3, 0))
        high = int(round(level*3/2, 0))
        if name == '':
            reply = 'A level {0} can share experience with levels **{1}** to **{2}**.'.format(level, low, high)
        else:
            reply = '**{0}** ({1}) can share experience with levels **{2}** to **{3}**.'.format(name, level, low, high)
        yield from self.bot.say(reply)

    @commands.command(aliases=['guildcheck', 'checkguild'])
    @asyncio.coroutine
    def guild(self, *, guildname=None):
        """Checks who is online in a guild"""
        if guildname is None:
            return
        guild = yield from getGuildOnline(guildname)
        if guild == ERROR_DOESNTEXIST:
            yield from self.bot.say("The guild {0} doesn't exist.".format(guildname))
            return
        if guild == ERROR_NETWORK:
            yield from self.bot.say("Can you repeat that?")
            return

        embed = discord.Embed()
        embed.set_author(name="{name} ({world})".format(**guild),
                         url=url_guild + urllib.parse.quote(guild["name"]),
                         )
        embed.set_thumbnail(url=guild["logo_url"])
        if len(guild['members']) < 1:
            embed.description = "Nobody is online."
            yield from self.bot.say(embed=embed)
            return

        plural = ""
        if len(guild['members']) > 1:
            plural = "s"
        result = "It has {0} player{1} online:".format(len(guild['members']), plural)
        for member in guild['members']:
            result += '\n'
            if member['rank'] != '':
                result += '__'+member['rank']+'__\n'

            member["title"] = ' (*' + member['title'] + '*)' if member['title'] != '' else ''
            member["vocation"] = vocAbb(member["vocation"])

            result += "\t{name} {title} -- {level} {vocation}".format(**member)
        embed.description = result
        yield from self.bot.say(embed=embed)

    @commands.command(pass_context=True, aliases=['checkprice', 'item'])
    @asyncio.coroutine
    def itemprice(self, ctx, *, itemname: str):
        """Checks an item's highest NPC price"""
        item = getItem(itemname)
        if item is not None:
            filename = item['name'] + ".png"
            while os.path.isfile(filename):
                filename = "_" + filename
            with open(filename, "w+b") as f:
                f.write(bytearray(item['image']))
                f.close()

            with open(filename, "r+b") as f:
                yield from self.bot.send_file(ctx.message.channel, f)
                f.close()
            os.remove(filename)

            if ctx.message.channel.is_private or ctx.message.channel.name == askchannel:
                yield from self.bot.say(getItemString(item, False))
            else:
                yield from self.bot.say(getItemString(item))
                if len(item['npcs_bought']) > 3 or len(item['npcs_sold']) > 3 or item["dropped_by"] is not None:
                    if ctx.message.author is not None:
                        yield from self.bot.send_message(ctx.message.author, getItemString(item, False))
        else:
            yield from self.bot.say("I couldn't find an item with that name.")

    @commands.command(pass_context=True, aliases=['mon', 'mob', 'creature'])
    @asyncio.coroutine
    def monster(self, ctx, *, monstername: str):
        """Gives information about a monster"""
        if monstername.lower() == "nab bot":
            yield from self.bot.say(random.choice(["**Nab Bot** is too strong for you to hunt!","Sure, you kill *one* child and suddenly you're a monster!","I'M NOT A MONSTER"]))
            return
        monster = getMonster(monstername)
        if monster is not None:
            filename = monster['name']+".png"
            while os.path.isfile(filename):
                filename = "_"+filename
            with open(filename, "w+b") as f:
                f.write(bytearray(monster['image']))
                f.close()

            if ctx.message.channel.is_private or ctx.message.channel.name == askchannel:
                with open(filename, "r+b") as f:
                    yield from self.bot.send_file(ctx.message.channel, f)
                    f.close()
                yield from self.bot.say(getMonsterString(monster, False))
            else:
                with open(filename, "r+b") as f:
                    yield from self.bot.send_file(ctx.message.channel, f)
                    f.close()
                yield from self.bot.say(getMonsterString(monster))
                if ctx.message.author is not None:
                    with open(filename, "r+b") as f:
                        yield from self.bot.send_file(ctx.message.author, f)
                        f.close()
                    yield from self.bot.send_message(ctx.message.author, getMonsterString(monster, False))
            os.remove(filename)
        else:
            yield from self.bot.say("I couldn't find a monster with that name.")

    @commands.command(aliases=['deathlist', 'death'])
    @asyncio.coroutine
    def deaths(self, *name: str):
        """Shows a player's recent deaths or global deaths if no player is specified"""
        name = " ".join(name).strip()
        if not name and lite_mode:
            return
        if not name:
            c = userDatabase.cursor()
            try:
                c.execute("SELECT level, date, name, user_id, byplayer, killer "
                          "FROM char_deaths, chars "
                          "WHERE char_id = id "
                          "ORDER BY date DESC LIMIT 15")
                result = c.fetchall()
                if len(result) < 1:
                    yield from self.bot.say("No one has died recently")
                    return
                now = time.time()
                reply = "Latest deaths:"
                for death in result:
                    timediff = timedelta(seconds=now-death["date"])
                    died = "Killed" if death["byplayer"] else "Died"
                    user = getUserById(death["user_id"])
                    username = "unknown"
                    if user:
                        username = user.display_name
                    reply += "\n\t{4} (**@{5}**) - {0} at level **{1}** by {2} - *{3} ago*".format(died, death["level"], death["killer"], getTimeDiff(timediff), death["name"], username)
                yield from self.bot.say(reply)
                return
            finally:
                c.close()
        if name.lower() == "nab bot":
            yield from self.bot.say("**Nab Bot** never dies.")
            return
        deaths = yield from getPlayerDeaths(name)
        if deaths == ERROR_DOESNTEXIST:
            yield from self.bot.say("That character doesn't exist!")
            return
        if deaths == ERROR_NETWORK:
            yield from self.bot.say("Sorry, try it again, I'll do it right this time.")
            return
        if len(deaths) == 0:
            yield from self.bot.say(name.title()+" hasn't died recently.")
            return
        tooMany = False
        if len(deaths) > 15:
            tooMany = True
            deaths = deaths[:15]

        reply = name.title()+" recent deaths:"

        for death in deaths:
            diff = getTimeDiff(datetime.now() - getLocalTime(death['time']))
            died = "Killed" if death['byPlayer'] else "Died"
            reply += "\n\t{0} at level **{1}** by {2} - *{3} ago*".format(died, death['level'], death['killer'], diff)
        if tooMany:
            reply += "\n*This person dies too much, I can't show you all the deaths!*"

        yield from self.bot.say(reply)

    @commands.command(pass_context=True,aliases=['levelups', 'lvl', 'level', 'lvls'],hidden=lite_mode)
    @asyncio.coroutine
    def levels(self, ctx, *name: str):
        """Shows a player's recent level ups or global leveups if no player is specified

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        if lite_mode:
            return
        name = " ".join(name)
        c = userDatabase.cursor()
        limit = 10
        if ctx.message.channel.is_private or ctx.message.channel.name == askchannel:
            limit = 20
        try:
            if not name:
                c.execute("SELECT level, date, name, user_id FROM char_levelups, chars WHERE char_id = id AND level >= ? ORDER BY date DESC LIMIT ?", (announceTreshold, limit,))
                result = c.fetchall()
                if len(result) < 1:
                    yield from self.bot.say("No one has leveled up recently")
                    return
                now = time.time()
                reply = "Latest level ups:"
                for levelup in result:
                    timediff = timedelta(seconds=now-levelup["date"])
                    user = getUserById(levelup["user_id"])
                    username = "unkown"
                    if user:
                        username = user.display_name
                    reply += "\n\tLevel **{0}** - {2} (**@{3}**) - *{1} ago*".format(levelup["level"], getTimeDiff(timediff), levelup["name"], username)
                if siteEnabled:
                    reply += "\nSee more levels check: <{0}{1}>".format(baseUrl, levelsPage)
                yield from self.bot.say(reply)
                return
            # Checking if character exists in db and get id while we're at it
            c.execute("SELECT id, name FROM chars WHERE name LIKE ?", (name,))
            result = c.fetchone()
            if result is None:
                yield from self.bot.say("I don't have a character with that name registered.")
                return
            # Getting correct capitalization
            name = result["name"]
            id = result["id"]
            c.execute("SELECT level, date FROM char_levelups WHERE char_id = ? ORDER BY date DESC LIMIT ?", (id, limit,))
            result = c.fetchall()
            # Checking number of level ups
            if len(result) < 1:
                yield from self.bot.say("I haven't seen **{0}** level up.".format(name))
                return
            now = time.time()
            reply = "**{0}** latest level ups:".format(name)
            for levelup in result:
                timediff = timedelta(seconds=now-levelup["date"])
                reply += "\n\tLevel **{0}** - *{1} ago*".format(levelup["level"], getTimeDiff(timediff))

            reply += "\nSee more levels at: <{0}{1}?name={2}>".format(baseUrl, charactersPage, urllib.parse.quote(name))
            yield from self.bot.say(reply)
        finally:
            c.close()

    @commands.command()
    @asyncio.coroutine
    def stats(self, *params: str):
        """Calculates the stats for a certain level and vocation, or a certain player"""
        paramsError = "You're doing it wrong! Do it like this: ``/stats player`` or ``/stats level,vocation`` or ``/stats vocation,level``"
        params = " ".join(params).split(",")
        char = None
        if len(params) == 1:
            _digits = re.compile('\d')
            if _digits.search(params[0]) is not None:
                yield from self.bot.say(paramsError)
                return
            else:
                char = yield from getPlayer(params[0])
                if char == ERROR_NETWORK:
                    yield from self.bot.say("Sorry, can you try it again?")
                    return
                if char == ERROR_DOESNTEXIST:
                    yield from self.bot.say("Player **{0}** doesn't exist!".format(params[0]))
                    return
                level = int(char['level'])
                vocation = char['vocation']
        elif len(params) == 2:
            try:
                level = int(params[0])
                vocation = params[1]
            except ValueError:
                try:
                    level = int(params[1])
                    vocation = params[0]
                except ValueError:
                    yield from self.bot.say(paramsError)
                    return
        else:
            yield from self.bot.say(paramsError)
            return
        stats = getStats(level, vocation)
        if stats == "low level":
            yield from self.bot.say("Not even *you* can go down so low!")
        elif stats == "high level":
            yield from self.bot.say("Why do you care? You will __**never**__ reach this level "+str(chr(0x1f644)))
        elif stats == "bad vocation":
            yield from self.bot.say("I don't know what vocation that is...")
        elif stats == "bad level":
            yield from self.bot.say("Level needs to be a number!")
        elif isinstance(stats, dict):
            if stats["vocation"] == "no vocation":
                stats["vocation"] = "with no vocation"
            if char:
                pronoun = "he" if char['gender'] == "male" else "she"
                yield from self.bot.say("**{5}** is a level **{0}** {1}, {6} has:\n\t**{2:,}** HP\n\t**{3:,}** MP\n\t**{4:,}** Capacity".format(level, char["vocation"].lower(), stats["hp"], stats["mp"], stats["cap"], char['name'], pronoun))
            else:
                yield from self.bot.say("A level **{0}** {1} has:\n\t**{2:,}** HP\n\t**{3:,}** MP\n\t**{4:,}** Capacity".format(level, stats["vocation"], stats["hp"], stats["mp"], stats["cap"]))
        else:
            yield from self.bot.say("Are you sure that is correct?")

    @commands.command(aliases=['bless'])
    @asyncio.coroutine
    def blessings(self, level: int):
        """Calculates the price of blessings at a specific level"""
        if level < 1:
            yield from self.bot.say("Very funny...")
            return
        price = 200 * (level - 20)
        if level <= 30:
            price = 2000
        if level >= 120:
            price = 20000
        inquisition = ""
        if level >= 100:
            inquisition = "\nBlessing of the Inquisition costs **{0:,}** gold coins.".format(int(price*5*1.1))
        yield from self.bot.say(
                "At that level, you will pay **{0:,}** gold coins per blessing for a total of **{1:,}** gold coins.{2}"
                .format(price, price*5, inquisition))

    @commands.command()
    @asyncio.coroutine
    def spell(self, *, name: str):
        """Tells you information about a certain spell."""
        spell = getSpell(name)
        if spell is None:
            yield from self.bot.say("I don't know any spell with that name or words.")
            return
        mana = spell["manacost"]
        if mana < 0:
            mana = "variable"
        words = spell["words"]
        if "exani hur" in words:
            words = "exani hur up/down"
        vocs = list()
        if spell['knight']: vocs.append("knights")
        if spell['paladin']: vocs.append("paladins")
        if spell['druid']: vocs.append("druids")
        if spell['sorcerer']: vocs.append("sorcerers")
        voc = joinList(vocs, ", ", " and ")
        reply = "**{0}** (*{1}*) is a {2}spell for level **{3}** and up. It uses **{4}** mana."
        reply = reply.format(spell["name"], words, "premium " if spell["premium"] else "",
                            spell["levelrequired"], mana)
        reply += " It can be used by {0}.".format(voc)
        if spell["goldcost"] == 0:
            reply += "\nIt can be obtained for free."
        else:
            reply += "\nIt can be bought for {0:,} gold coins.".format(spell["goldcost"])
        # Todo: Show which NPCs sell the spell
        """if(len(spell['npcs']) > 0):
            for npc in spell['npcs']:
                vocs = list()
                if(npc['knight']): vocs.append("knights")
                if(npc['paladin']): vocs.append("paladins")
                if(npc['druid']): vocs.append("druids")
                if(npc['sorcerer']): vocs.append("sorcerers")
                voc = ", ".join(vocs)
                print("{0} ({1}) - {2}".format(npc['name'],npc['city'],voc))"""
        yield from self.bot.say(reply)

    @commands.command(aliases=['serversave','ss'])
    @asyncio.coroutine
    def time(self):
        """Displays tibia server's time and time until server save"""
        offset = getTibiaTimeZone() - getLocalTimezone()
        tibia_time = datetime.now()+timedelta(hours=offset)
        server_save = tibia_time
        if tibia_time.hour >= 10:
            server_save += timedelta(days=1)
        server_save = server_save.replace(hour=10,minute=0,second=0,microsecond=0)
        time_until_ss = server_save - tibia_time
        hours, remainder = divmod(int(time_until_ss.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        timestrtibia = tibia_time.strftime("%H:%M")
        server_save_str = '{h} hours and {m} minutes'.format(h=hours, m=minutes)

        reply = "It's currently **{0}** in Tibia's servers.".format(timestrtibia)
        if displayBrasiliaTime:
            offsetbrasilia = getBrasiliaTimeZone() - getLocalTimezone()
            brasilia_time = datetime.now()+timedelta(hours=offsetbrasilia)
            timestrbrasilia = brasilia_time.strftime("%H:%M")
            reply += "\n**{0}** in Brazil (Brasilia).".format(timestrbrasilia)
        if displaySonoraTime:
            offsetsonora = -7 - getLocalTimezone()
            sonora_time = datetime.now()+timedelta(hours=offsetsonora)
            timestrsonora = sonora_time.strftime("%H:%M")
            reply += "\n**{0}** in Mexico (Sonora).".format(timestrsonora)
        reply += "\nServer save is in {0}.\nRashid is in **{1}** today.".format(server_save_str,getRashidCity())
        yield from self.bot.say(reply)


def getCharString(char):
    """Returns a formatted string containing a character's info."""
    # Todo: Links in embed descriptions are not supported on mobile, readd when/if they are supported
    if char == ERROR_NETWORK or char == ERROR_DOESNTEXIST:
        return char
    pronoun = "He"
    if char['gender'] == "female":
        pronoun = "She"
    # url = url_character + urllib.parse.quote(char["name"])
    # reply_format = "**[{1}]({9})** is a level {2} __{3}__. {0} resides in __{4}__ in the world __{5}__.{6}{7}{8}"
    reply_format = "**{1}** is a level {2} __{3}__. {0} resides in __{4}__ in the world __{5}__.{6}{7}{8}"
    # guild_format = "\n{0} is __{1}__ of the **[{2}]({3})**."
    guild_format = "\n{0} is __{1}__ of the **{2}**."
    # married_format = "\n{0} is married to **[{1}]({2})**."
    married_format = "\n{0} is married to **{1}**."
    login_format = "\n{0} hasn't logged in for **{1}**."
    guild = ""
    married = ""
    login = "\n{0} has **never** logged in.".format(pronoun)
    if char.get('guild', None):
        # guild_url = url_guild+urllib.parse.quote(char["guild"])
        # guild = guild_format.format(pronoun, char['rank'], char['guild'],guild_url)
        guild = guild_format.format(pronoun, char['rank'], char['guild'])
    if char.get('married', None):
        # married_url = url_character + urllib.parse.quote(char["name"])
        # married = married_format.format(pronoun, char['married'], married_url)
        married = married_format.format(pronoun, char['married'])

    if char['last_login'] is not None:
        last_login = getLocalTime(char['last_login'])
        now = datetime.now()
        time_diff = now - last_login
        if time_diff.days > last_login_days:
            login = login_format.format(pronoun, getTimeDiff(time_diff))
        else:
            login = ""

    # reply = reply_format.format(pronoun, char['name'], char['level'], char['vocation'], char['residence'],
    #                            char['world'], guild, married, login, url)
    reply = reply_format.format(pronoun, char['name'], char['level'], char['vocation'], char['residence'],
                                char['world'], guild, married, login)
    return reply


def getUserString(username):
    user = getUserByName(username)
    c = userDatabase.cursor()
    if user is None:
        return ERROR_DOESNTEXIST
    try:
        c.execute("SELECT name, ABS(last_level) as level, vocation FROM chars WHERE user_id = ? ORDER BY level DESC",
                  (user.id,))
        result = c.fetchall()
        if result:
            charList = []
            for character in result:
                try:
                    character["level"] = int(character["level"])
                except ValueError:
                    character["level"] = ""
                character["vocation"] = vocAbb(character["vocation"])
                # Todo: Links in embed descriptions are not supported on mobile, readd when/if they are supported
                # character["url"] = url_character+urllib.parse.quote(character["name"])
                character["url"] = url_character + urllib.parse.quote(character["name"])
                # charList.append("[{name}]({url}) (Lvl {level} {vocation})".format(**character))
                charList.append("{name} (Lvl {level} {vocation})".format(**character))

            charString = "@**{0.display_name}**'s character{1}: {2}"
            plural = "s are" if len(charList) > 1 else " is"
            reply = charString.format(user, plural, joinList(charList, ", ", " and "))
        else:
            reply = "I don't know who @**{0.display_name}** is...".format(user)
        return reply
    finally:
        c.close()


def getMonsterString(monster, short=True):
    """Returns a formatted string containing a character's info.

    If short is true, it returns a shorter version."""

    reply = monster['title'] + "\r\n```"
    reply += "HP:" + str(monster['health']) + "   Exp:" + str(monster['experience']) + "\r\n"
    reply += "HP/Exp Ratio: " + "{0:.2f}".format(monster['experience'] / monster['health']).zfill(4)
    reply += "\r\n```"
    reply += "```"
    loot = getLoot(monster['id'])
    weak = []
    resist = []
    elements = ["physical", "holy", "death", "fire", "ice", "energy", "earth", "drown", "lifedrain"]
    for index, value in monster.items():
        if index in elements:
            if monster[index] > 100:
                weak.append([index.title(), monster[index]])
            if monster[index] < 100:
                resist.append([index.title(), monster[index]])
    if len(weak) >= 1:
        reply += 'Weak to:' + "\r\n"
        for element in sorted(weak, key=lambda elem: elem[1]):
            reply += "\t+" + str(element[1] - 100) + "%  " + element[0] + "\r\n"
    if len(resist) >= 1:
        reply += 'Resistant to:' + "\r\n"
        for element in sorted(resist, key=lambda elem: elem[1]):
            reply += "\t" + ((" -" + str(100 - element[1]) + "% ") if 100 - element[1] < 100 else "Immune") + " " + \
                     element[0] + "\r\n"
    reply += "\r\n```"
    reply += "```"
    reply += ("Can" if monster['senseinvis'] else "Can't") + " sense invisibility" + "\r\n"
    reply += "\r\n```"
    if not short:
        reply += "```"
        reply += "\r\nLoot:\r\n"
        if loot is not None:
            for item in loot:
                if item["percentage"] is None:
                    item["percentage"] = "??.??%"
                elif item["percentage"] >= 100:
                    item["percentage"] = "Always"
                else:
                    item["percentage"] = "{0:.2f}".format(item['percentage']).zfill(5) + "%"
                if item["max"] > 1:
                    item["count"] = "({min}-{max})".format(**item)
                else:
                    item["count"] = ""
                reply += "{percentage} {name} {count}\r\n".format(**item)

        else:
            reply += "Doesn't drop anything"
        reply += "\r\n```"
        reply += "```"
        reply += "Max damage:" + str(monster["maxdamage"]) if monster["maxdamage"] is not None else "???" + "\r\n"
        reply += "\r\n```"
        reply += "```"
        if monster['abilities'] is not None:
            reply += "Abilities:\r\n"
            reply += monster['abilities']
        reply += "\r\n```"
    else:
        reply += '*I also PM\'d you this monster\'s full information with loot and abilities.*'
    return reply


def getItemString(item, short=True):
    """Returns a formatted string with an item's info.

    If short is true, it returns a shorter version."""
    reply = "**{0}**\n".format(item["title"])

    if 'look_text' in item:
        reply += "```{0}```".format(item['look_text'])

    if 'npcs_bought' in item and len(item['npcs_bought']) > 0:
        reply += "```Can be bought for {0:,} gold coins from:".format(item['value_buy'])
        count = 0
        for npc in item['npcs_bought']:
            if count < 3 or not short:
                reply += "\n\t{0} in {1}".format(npc['name'], npc['city'])
            count += 1
        if count >= 3 and short:
            reply += "\n\tAnd {0} others.".format(count - 3)
        reply += "```"
    else:
        reply += "```\nCan't be bought from NPCs```"

    if 'npcs_sold' in item and len(item['npcs_sold']) > 0:
        reply += "```Can be sold for {1:,} gold coins to:".format(item['name'], item['value_sell'])
        count = 0
        for npc in item['npcs_sold']:
            if count < 3 or not short:
                reply += "\n\t{0} in {1}".format(npc['name'], npc['city'])
            count += 1
        if count >= 3 and short:
            reply += "\n\tAnd {0} others.".format(count - 3)
        reply += "```"
    else:
        reply += "```\nCan't be sold to NPCs```"

    if (len(item['npcs_bought']) > 3 or len(item['npcs_sold']) > 3) and short:
        reply += '\n\n*The list of NPCs was too long, so I PM\'d you an extended version.*'

    if item["dropped_by"] is not None and not short:
        reply += "```Dropped by:"
        if len(item["dropped_by"]) > 20:
            item["dropped_by"] = item["dropped_by"][:20]
        for creature in item["dropped_by"]:
            if creature["percentage"] is None:
                creature["percentage"] = "??.??"
            reply += "\n\t{name} ({percentage}%)".format(**creature)
        reply += "```"

    if len(item['npcs_bought']) > 3 or len(item['npcs_sold']) > 3 or item["dropped_by"] is not None and short:
        reply += "*I also PM'd you this item's complete NPC list and creatures that drop it.*"
    return reply


def setup(bot):
    bot.add_cog(Tibia(bot))

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")