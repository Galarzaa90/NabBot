from utils import *


@asyncio.coroutine
def getPlayerDeaths(name, single_death=False, tries=5):
    """Returns a list with the player's deaths
    
    Each list element is a dictionary with the following keys: time, level, killer, byPlayer.
    If single_death is true, it stops looking after fetching the first death.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly"""
    url = "https://secure.tibia.com/community/?subtopic=characters&name="+urllib.parse.quote(name)
    deathList = []

    # Fetch website
    try:
        page = yield from aiohttp.get(url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if tries == 0:
            log.error("getPlayerDeaths: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayerDeaths(name, single_death, tries)
            return ret

    if not content:
        log.error("getPlayerDeaths: Couldn't fetch {0}, network error.".format(name))
        return ERROR_NETWORK

    # Trimming content to reduce load
    try:
        start_index = content.index('<div class="BoxContent"')
        end_index = content.index("<B>Search Character</B>")
        content = content[start_index:end_index]
    except ValueError:
        # Website fetch was incomplete, due to a network error
        if tries == 0:
            log.error("getPlayerDeaths: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayerDeaths(name, single_death, tries)
            return ret

    # Check if player exists
    if "Name:</td><td>" not in content:
        return ERROR_DOESNTEXIST

    # Check if player has recent deaths, return empty list if not
    if "<b>Character Deaths</b>" not in content:
        return deathList

    # Trimming content again once we've checked char exists and has deaths
    start_index = content.index("<b>Character Deaths</b>")
    content = content[start_index:]

    regex_deaths = r'valign="top" >([^<]+)</td><td>(.+?)</td></tr>'
    pattern = re.compile(regex_deaths, re.MULTILINE+re.S)
    matches = re.findall(pattern, content)

    for m in matches:
        deathTime = ""
        deathLevel = ""
        deathKiller = ""
        deathByPlayer = False
        regex_deathtime = r'(\w+).+?;(\d+).+?;(\d+).+?;(\d+):(\d+):(\d+).+?;(\w+)'
        pattern = re.compile(regex_deathtime, re.MULTILINE+re.S)
        m_deathtime = re.search(pattern, m[0])

        if m_deathtime:
            deathTime = "{0} {1} {2} {3}:{4}:{5} {6}".format(m_deathtime.group(1), m_deathtime.group(2), m_deathtime.group(3), m_deathtime.group(4), m_deathtime.group(5), m_deathtime.group(6), m_deathtime.group(7))

        if m[1].find("Died") != -1:
            regex_deathinfo_monster = r'Level (\d+) by ([^.]+)'
            pattern = re.compile(regex_deathinfo_monster, re.MULTILINE+re.S)
            m_deathinfo_monster = re.search(pattern, m[1])
            if m_deathinfo_monster:
                deathLevel = m_deathinfo_monster.group(1)
                deathKiller = m_deathinfo_monster.group(2)
        else:
            regex_deathinfo_player = r'Level (\d+) by .+?name=([^"]+)'
            pattern = re.compile(regex_deathinfo_player, re.MULTILINE+re.S)
            m_deathinfo_player = re.search(pattern, m[1])
            if m_deathinfo_player:
                deathLevel = m_deathinfo_player.group(1)
                deathKiller = urllib.parse.unquote_plus(m_deathinfo_player.group(2))
                deathByPlayer = True

        deathList.append({'time': deathTime, 'level': deathLevel, 'killer': deathKiller, 'byPlayer': deathByPlayer})
        if single_death:
            break
    return deathList


@asyncio.coroutine
def getServerOnline(server, tries=5):
    """Returns a list of all the online players in current server.
    
    Each list element is a dictionary with the following keys: name, level"""
    url = 'https://secure.tibia.com/community/?subtopic=worlds&world='+server
    onlineList = []

    # Fetch website
    try:
        page = yield from aiohttp.get(url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if tries == 0:
            log.error("getServerOnline: Couldn't fetch {0}, network error.".format(server))
            # This should return ERROR_NETWORK, but requires error handling where this function is used
            return onlineList
        else:
            tries -= 1
            ret = yield from getServerOnline(server,tries)
            return ret

    while not content and tries > 0:
        try:
            page = yield from aiohttp.get(url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            tries -= 1

    # Trimming content to reduce load
    try:
        start_index = content.index('<div class="BoxContent"')
        end_index = content.index('<div id="ThemeboxesColumn" >')
        content = content[start_index:end_index]
    except ValueError:
        # Website fetch was incomplete due to a network error
        if tries == 0:
            log.error("getServerOnline: Couldn't fetch {0}, network error.".format(server))
            # This should return ERROR_NETWORK, but requires error handling where this function is used
            return onlineList
        else:
            tries -= 1
            ret = yield from getServerOnline(server, tries)
            return ret


    regex_members = r'<a href="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)" >.+?</a></td><td style="width:10%;" >(.+?)</td>'
    pattern = re.compile(regex_members,re.MULTILINE+re.S)
    m = re.findall(pattern,content)
    # Check if list is empty
    if m:
        # Building dictionary list from online players
        for (name, level) in m:
            name = urllib.parse.unquote_plus(name)
            onlineList.append({'name': name, 'level': int(level)})
    return onlineList


@asyncio.coroutine
def getGuildOnline(guildname, titlecase=True, tries=5):
    """Returns a guild's world and online member list in a dictionary.

    The dictionary contains the following keys: name, logo_url, world and members.
    The key members contains a list where each element is a dictionary with the following keys:
        rank, name, title, vocation, level, joined.
    Guilds are case sensitive on tibia.com so guildstats.eu is checked for correct case.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly."""
    gstats_url = 'http://guildstats.eu/guild?guild='+urllib.parse.quote(guildname)
    guild = {}
    # Fix casing using guildstats.eu if needed
    # Sorry guildstats.eu :D
    if not titlecase:
        # Fetch website
        try:
            page = yield from aiohttp.get(gstats_url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            if tries == 0:
                log.error("getGuildOnline: Couldn't fetch {0} from guildstats.eu, network error.".format(guildname))
                return ERROR_NETWORK
            else:
                tries -= 1
                ret = yield from getGuildOnline(guildname, titlecase, tries)
                return ret

        # Make sure we got a healthy fetch
        try:
            content.index('<div class="footer">')
        except ValueError:
            # Website fetch was incomplete, due to a network error
            if tries == 0:
                log.error("getGuildOnline: Couldn't fetch {0} from guildstats.eu, network error.".format(guildname))
                return ERROR_NETWORK
            else:
                tries -= 1
                ret = yield from getGuildOnline(guildname, titlecase, tries)
                return ret

        # Check if the guild doesn't exist
        if "<div>Sorry!" in content:
            return ERROR_DOESNTEXIST

        # Failsafe in case guildstats.eu changes their websites format
        try:
            content.index("General info")
            content.index("Recruitment")
        except Exception:
            log.error("getGuildOnline: -IMPORTANT- guildstats.eu seems to have changed their websites format.")
            return ERROR_NETWORK

        startIndex = content.index("General info")
        endIndex = content.index("Recruitment")
        content = content[startIndex:endIndex]
        m = re.search(r'<a href="set=(.+?)"', content)
        if m:
            guildname = urllib.parse.unquote_plus(m.group(1))
    else:
        guildname = guildname.title()

    tibia_url = 'https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName='+urllib.parse.quote(guildname)+'&onlyshowonline=1'
    # Fetch website
    try:
        page = yield from aiohttp.get(tibia_url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if tries == 0:
            log.error("getGuildOnline: Couldn't fetch {0}, network error.".format(guildname))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getGuildOnline(guildname, titlecase, tries)
            return ret

    # Trimming content to reduce load and making sure we got a healthy fetch
    try:
        startIndex = content.index('<div class="BoxContent"')
        endIndex = content.index('<div id="ThemeboxesColumn" >')
        content = content[startIndex:endIndex]
    except ValueError:
        # Website fetch was incomplete, due to a network error
        if tries == 0:
            log.error("getGuildOnline: Couldn't fetch {0}, network error.".format(guildname))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getGuildOnline(guildname, titlecase, tries)
            return ret

    # Check if the guild doesn't exist
    # Tibia.com has no search function, so there's no guild doesn't exist page cause you're not supposed to get to a
    # guild that doesn't exists. So the message displayed is "An internal error has ocurred. Please try again later!".
    if '<div class="Text" >Error</div>' in content:
        if titlecase:
            ret = yield from getGuildOnline(guildname,False)
            return ret
        else:
            return ERROR_DOESNTEXIST

    # Regex pattern to fetch world and founding date
    m = re.search(r'founded on (\w+) on ([^.]+)', content)
    if m:
        guild['world'] = m.group(1)

    # Logo URL
    m = re.search(r'<IMG SRC=\"([^\"]+)\" W', content)
    if m:
        guild['logo_url'] = m.group(1)

    # Regex pattern to fetch members
    regex_members = r'<TR BGCOLOR=#[\dABCDEF]+><TD>(.+?)</TD>\s</td><TD><A HREF="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)">.+?</A> *\(*(.*?)\)*</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>'
    pattern = re.compile(regex_members, re.MULTILINE+re.S)

    m = re.findall(pattern, content)
    guild['members'] = []
    # Check if list is empty
    if m:
        # Building dictionary list from members
        for (rank, name, title, vocation, level, joined) in m:
            rank = '' if (rank == '&#160;') else rank
            name = urllib.parse.unquote_plus(name)
            joined = joined.replace('&#160;', '-')
            guild['members'].append({'rank': rank, 'name': name, 'title': title,
            'vocation': vocation, 'level': level, 'joined': joined})
    guild['name'] = guildname
    return guild


@asyncio.coroutine
def getPlayer(name, tries=5):
    """Returns a dictionary with a player's info
    
    The dictionary contains the following keys: name, deleted, level, vocation, world, residence,
    married, gender, guild, last,login, chars*.
        *chars is list that contains other characters in the same account (if not hidden).
        Each list element is dictionary with the keys: name, world.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly."""
    url = "https://secure.tibia.com/community/?subtopic=characters&name="+urllib.parse.quote(name)
    content = ""
    char = dict()

    # Fetch website
    try:
        page = yield from aiohttp.get(url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if tries == 0:
            log.error("getPlayer: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayer(name,tries)
            return ret

    # Trimming content to reduce load
    try:
        startIndex = content.index('<div class="BoxContent"')
        endIndex = content.index("<B>Search Character</B>")
        content = content[startIndex:endIndex]
    except ValueError:
        # Website fetch was incomplete, due to a network error
        if tries == 0:
            log.error("getPlayer: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayer(name, tries)
            return ret
    # Check if player exists
    if "Name:</td><td>" not in content:
        return ERROR_DOESNTEXIST

    # TODO: Is there a way to reduce this part?
    # Name
    m = re.search(r'Name:</td><td>([^<,]+)', content)
    if m:
        char['name'] = m.group(1).strip()

    # Deleted
    m = re.search(r', will be deleted at ([^<]+)', content)
    if m:
        char['deleted'] = True

    # Vocation
    m = re.search(r'Vocation:</td><td>([^<]+)', content)
    if m:
        char['vocation'] = m.group(1)

    # Level
    m = re.search(r'Level:</td><td>(\d+)', content)
    if m:
        char['level'] = int(m.group(1))
    # Use database levels for online characters
    for onchar in globalOnlineList:
        if onchar.split("_", 1)[1] == char['name']:
            c = userDatabase.cursor()
            c.execute("SELECT last_level FROM chars WHERE name LIKE ?", (char['name'],))
            result = c.fetchone()
            if result:
                char['level'] = abs(result["last_level"])
            c.close()
            break

    # World
    m = re.search(r'World:</td><td>([^<]+)', content)
    if m:
        char['world'] = m.group(1)

    # Residence (City)
    m = re.search(r'Residence:</td><td>([^<]+)', content)
    if m:
        char['residence'] = m.group(1)

    # Marriage
    m = re.search(r'Married to:</td><td>?.+name=([^"]+)', content)
    if m:
        char['married'] = urllib.parse.unquote_plus(m.group(1))

    # Sex
    m = re.search(r'Sex:</td><td>([^<]+)', content)
    if m:
        if m.group(1) == 'male':
            char['gender'] = 'male'
        else:
            char['gender'] = 'female'

    # Guild rank
    m = re.search(r'membership:</td><td>([^<]+)\sof the', content)
    if m:
        char['rank'] = m.group(1)
        # Guild membership
        m = re.search(r'GuildName=.*?([^"]+).+', content)
        if m:
            char['guild'] = urllib.parse.unquote_plus(m.group(1))

    # Last login
    m = re.search(r'Last login:</td><td>([^<]+)', content)
    if m:
        lastLogin = m.group(1).replace("&#160;", " ").replace(",", "")
        if "never" in lastLogin:
            char['last_login'] = None
        else:
            char['last_login'] = lastLogin

    # Discord owner
    c = userDatabase.cursor()
    c.execute("SELECT user_id FROM chars WHERE name LIKE ?", (char["name"],))
    result = c.fetchone()
    char["owner_id"] = None if result is None else result["user_id"]

    # Update name and vocation in chars database if necessary
    c = userDatabase.cursor()
    c.execute("SELECT vocation FROM chars WHERE name LIKE ?",(name,))
    result = c.fetchone()
    if result:
        if result["vocation"] != char['vocation']:
            c.execute("UPDATE chars SET vocation = ? WHERE name LIKE ?",(char['vocation'],name,))
            log.info("{0}'s vocation was set to {1} from {2} during getPlayer()".format(char['name'],char['vocation'],result["vocation"]))
        # if name != char['name']:
        #     c.execute("UPDATE chars SET name = ? WHERE name LIKE ?",(char['name'],name,))
        #     yield from bot.say("**{0}** was renamed to **{1}**, updating...".format(name,char['name']))

    # Other chars
    # note that an empty char list means the character is hidden
    # otherwise you'd have at least the same char in the list
    char['chars'] = []
    try:
        # See if there is a character list
        startIndex = content.index("<B>Characters</B>")
        content = content[startIndex:]

        # Find characters
        regex_chars = r'<TD WIDTH=10%><NOBR>([^<]+)[^?]+.+?VALUE=\"([^\"]+)'
        pattern = re.compile(regex_chars, re.MULTILINE+re.S)
        m = re.findall(pattern, content)

        if m:
            for (world,name) in m:
                name = urllib.parse.unquote_plus(name)
                char['chars'].append({'name': name, 'world': world})
    except Exception:
        pass
    return char


def getRashidCity() -> str:
    """Returns the city Rashid is currently in."""
    offset = getTibiaTimeZone() - getLocalTimezone()
    # Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = datetime.now()+timedelta(hours=offset-10)
    return ["Svargrond",
            "Liberty Bay",
            "Port Hope",
            "Ankrahmun",
            "Darashia",
            "Edron",
            "Carlin"][tibia_time.weekday()]


# TODO: Merge this into getMonster()
def getLoot(id):
    """Returns a tuple of a monster's item drops.
    
    Each tuple element is a dictionary with the following keys: itemid, percentage, min, max"""
    c = tibiaDatabase.cursor()
    c.execute("SELECT itemid FROM CreatureDrops WHERE creatureid LIKE ?", (id,))
    result = c.fetchone()
    try:
        if result is not None:
            c.execute("SELECT Items.title as name, percentage, min, max "
                      "FROM CreatureDrops, Items "
                      "WHERE Items.id = CreatureDrops.itemid AND creatureid LIKE ? "
                      "ORDER BY percentage DESC",
                      (id,)
            )
            result = c.fetchall()
            if result is not None:
                return result
    finally:
        c.close()
    return


def getMonster(name):
    """Returns a dictionary with a monster's info.
    
    The dictionary has the following keys: name, id, hp, exp, maxdmg, elem_physical, elem_holy, 
    elem_death, elem_fire, elem_energy, elem_ice, elem_earth, elem_drown, elem_lifedrain, senseinvis,
    arm, image."""

    # Reading monster database
    c = tibiaDatabase.cursor()
    c.execute("SELECT * FROM Creatures WHERE name LIKE ?", (name,))
    monster = c.fetchone()
    try:
        # Checking if monster exists
        if monster is not None:
            if monster['health'] is None or monster['health'] < 1:
                monster['health'] = 1
            if monster['experience'] is None or monster['experience'] < 1:
                monster['experience'] = 1
            return monster
    finally:
        c.close()
    return


def getItem(itemname):
    """Returns a dictionary containing an item's info.
    
    The dictionary has the following keys: name, look_text, npcs_sold*, value_sell, npcs_bought*, value_buy.
        *npcs_sold and npcs_bought are list, each element is a dictionary with the keys: name, city."""

    # Reading item database
    c = tibiaDatabase.cursor()

    # Search query
    c.execute("SELECT * FROM Items WHERE name LIKE ?",(itemname,))
    item = c.fetchone()
    try:
        # Checking if item exists
        if item is not None:
            # Turning result tuple into dictionary

            # Checking NPCs that buy the item
            c.execute("SELECT NPCs.title, city, value "
                      "FROM Items, SellItems, NPCs "
                      "WHERE Items.name LIKE ? AND SellItems.itemid = Items.id AND NPCs.id = vendorid "
                      "ORDER BY value DESC", (itemname,))
            npcs = []
            value_sell = None
            for npc in c:
                name = npc["title"]
                city = npc["city"].title()
                if value_sell is None:
                    value_sell = npc["value"]
                elif npc["value"] != value_sell:
                    break
                # Replacing cities for special npcs
                if name == 'Alesar' or name == 'Yaman':
                    city = 'Green Djinn\'s Fortress'
                elif name == 'Nah\'Bob' or name == 'Haroun':
                    city = 'Blue Djinn\'s Fortress'
                elif name == 'Rashid':
                    city = getRashidCity()
                elif name == 'Yasir':
                    city = 'his boat'
                npcs.append({"name": name, "city": city})
            item['npcs_sold'] = npcs
            item['value_sell'] = value_sell

            # Checking NPCs that sell the item
            c.execute("SELECT NPCs.title, city, value "
                      "FROM Items, BuyItems, NPCs "
                      "WHERE Items.name LIKE ? AND BuyItems.itemid = Items.id AND NPCs.id = vendorid "
                      "ORDER BY value ASC", (itemname,))
            npcs = []
            value_buy = None
            for npc in c:
                name = npc["title"]
                city = npc["city"].title()
                if value_buy is None:
                    value_buy = npc["value"]
                elif npc["value"] != value_buy:
                    break
                # Replacing cities for special npcs
                if name == 'Alesar' or name == 'Yaman':
                    city = 'Green Djinn\'s Fortress'
                elif name == 'Nah\'Bob' or name == 'Haroun':
                    city = 'Blue Djinn\'s Fortress'
                elif name == 'Rashid':
                    offset = getTibiaTimeZone() - getLocalTimezone()
                    # Server save is at 10am, so in tibia a new day starts at that hour
                    tibia_time = datetime.now()+timedelta(hours=offset-10)
                    city = [
                        "Svargrond",
                        "Liberty Bay",
                        "Port Hope",
                        "Ankrahmun",
                        "Darashia",
                        "Edron",
                        "Carlin"][tibia_time.weekday()]
                elif name == 'Yasir':
                    city = 'his boat'
                npcs.append({"name": name, "city": city})
            item['npcs_bought'] = npcs
            item['value_buy'] = value_buy

            # Get creatures that drop it
            c.execute("SELECT Creatures.title as name, CreatureDrops.percentage "
                      "FROM CreatureDrops, Creatures "
                      "WHERE CreatureDrops.creatureid = Creatures.id AND CreatureDrops.itemid = ? "
                      "ORDER BY percentage DESC", (item["id"],))
            drops = c.fetchall()
            if drops is not None:
                item["dropped_by"] = drops
            else:
                item["dropped_by"] = None
            return item
    finally:
        c.close()
    return


def getLocalTime(tibiaTime):
    """Gets a time object from a time string from tibia.com"""
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    local_utc_offset = ((timegm(t) - timegm(u))/60/60)

    # Convert time string to time object
    # Removing timezone cause CEST and CET are not supported
    t = datetime.strptime(tibiaTime[:-4].strip(), "%b %d %Y %H:%M:%S")
    # Extracting timezone
    tz = tibiaTime[-4:].strip()

    # Getting the offset
    if tz == "CET":
        utc_offset = 1
    elif tz == "CEST":
        utc_offset = 2
    else:
        return None
    # Add/subtract hours to get the real time
    return t + timedelta(hours=(local_utc_offset - utc_offset))


def getStats(level, vocation):
    """Returns a dictionary with the stats for a character of a certain vocation and level.
    
    The dictionary has the following keys: vocation, hp, mp, cap."""
    try:
        level = int(level)
    except ValueError:
        return "bad level"
    if level <= 0:
        return "low level"
    elif level > 2000:
        return "high level"

    vocation = vocation.lower().lstrip().rstrip()
    if vocation in ["knight", "k", "elite knight", "kina", "kinight", "ek", "eliteknight"]:
        hp = 5*(3*level - 2*8 + 29)
        mp = 5*level + 50
        cap = 5*(5*level - 5*8 + 94)
        vocation = "knight"
    elif vocation in ["paladin", "royal paladin", "rp", "pally", "royal pally", "p"]:
        hp = 5*(2*level - 8 + 29)
        mp = 5*(3*level - 2*8) + 50
        cap = 10*(2*level - 8 + 39)
        vocation = "paladin"
    elif vocation in ["mage","druid","elder druid","elder","ed","d","sorc","sorcerer","master sorcerer","ms","s"]:
        hp = 5*(level+29)
        mp = 5*(6*level - 5*8) + 50
        cap = 10*(level + 39)
        vocation = "mage"
    elif vocation in ["no vocation" ,"no voc", "novoc", "nv", "n v", "none", "no", "n", "noob", "noobie", "rook", "rookie"]:
        vocation = "no vocation"
    else:
        return "bad vocation"

    if level < 8 or vocation == "no vocation":
        hp = 5*(level+29)
        mp = 5*level + 50
        cap = 10*(level + 39)

    return {"vocation": vocation, "hp": hp, "mp": mp, "cap": cap}


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
        time_diff = now-last_login
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
        c.execute("SELECT name, ABS(last_level) as level, vocation FROM chars WHERE user_id = ? ORDER BY level DESC", (user.id,))
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
                character["url"] = url_character+urllib.parse.quote(character["name"])
                # charList.append("[{name}]({url}) (Lvl {level} {vocation})".format(**character))
                charList.append("{name} (Lvl {level} {vocation})".format(**character))

            charString = "@**{0.display_name}**'s character{1}: {2}"
            plural = "s are" if len(charList) > 1 else " is"
            reply = charString.format(user, plural, joinList(charList, ", ",  " and "))
        else:
            reply = "I don't know who @**{0.display_name}** is...".format(user)
        return reply
    finally:
        c.close()


def getMonsterString(monster, short=True):
    """Returns a formatted string containing a character's info.
    
    If short is true, it returns a shorter version."""

    reply = monster['title']+"\r\n```"
    reply += "HP:"+str(monster['health'])+"   Exp:"+str(monster['experience'])+"\r\n"
    reply += "HP/Exp Ratio: "+"{0:.2f}".format(monster['experience']/monster['health']).zfill(4)
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
        reply += 'Weak to:'+"\r\n"
        for element in sorted(weak, key=lambda elem: elem[1]):
            reply += "\t+"+str(element[1]-100)+"%  "+element[0]+"\r\n"
    if len(resist) >= 1:
        reply += 'Resistant to:'+"\r\n"
        for element in sorted(resist, key=lambda elem: elem[1]):
            reply += "\t"+((" -"+str(100-element[1])+"% ") if 100-element[1] < 100 else "Immune")+" "+element[0]+"\r\n"
    reply += "\r\n```"
    reply += "```"
    reply += ("Can" if monster['senseinvis'] else "Can't")+" sense invisibility"+"\r\n"
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
                    item["percentage"] = "{0:.2f}".format(item['percentage']).zfill(5)+"%"
                if item["max"] > 1:
                    item["count"] = "({min}-{max})".format(**item)
                else:
                    item["count"] = ""
                reply += "{percentage} {name} {count}\r\n".format(**item)

        else:
            reply += "Doesn't drop anything"
        reply += "\r\n```"
        reply += "```"
        reply += "Max damage:"+str(monster["maxdamage"]) if monster["maxdamage"] is not None else "???"+"\r\n"
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
            reply += "\n\tAnd {0} others.".format(count-3)
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
            reply += "\n\tAnd {0} others.".format(count-3)
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


# TODO: Improve formatting to match /monster and /item
def getSpell(name):
    """Returns a formatted string containing a spell's info."""
    c = tibiaDatabase.cursor()
    try:
        c.execute("""SELECT * FROM Spells WHERE words LIKE ? OR name LIKE ?""", (name+"%", name,))
        spell = c.fetchone()
        if spell is None:
            return None
        spell["npcs"] = []

        c.execute("""SELECT NPCs.title as name, NPCs.city, SpellNPCs.knight, SpellNPCs.paladin,
                  SpellNPCs.sorcerer, SpellNPCs.druid FROM NPCs, SpellNPCs
                  WHERE SpellNPCs.spellid = ? AND SpellNPCs.npcid = NPCs.id""", (spell["id"],))
        result = c.fetchall()
        # This should always be true
        if result is not None:
            for npc in result:
                npc["city"] = npc["city"].title()
                spell["npcs"].append(npc)
        return spell

    finally:
        c.close()


# Commands
class Tibia:
    """Tibia related commands."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['check', 'player', 'checkplayer', 'char', 'character'],pass_context=True)
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
                yield from self.bot.say(getCharString(char))
            return

        if name is None:
            yield from self.bot.say("Tell me which character or user you want to check.")

        char = yield from getPlayer(name)
        charString = getCharString(char)
        user = getUserByName(name)
        userString = getUserString(name)
        embed = discord.Embed()
        embed.description = ""

        # No user or char with that name
        if char == ERROR_DOESNTEXIST and user is None:
            yield from self.bot.say("I don't see any user or character with that name.")
            return
        # We found an user
        if user is not None:
            embed.description = userString
            color = getUserColor(user, ctx.message.server)
            if color is not discord.Colour.default():
                embed.colour = color
            if "I don't know" not in userString:
                embed.set_thumbnail(url=user.avatar_url)
            # Check if we found a char too
            if type(char) is dict:
                embed.description += "\n\nThe character "+charString
            elif char == ERROR_NETWORK:
                embed.description += "I failed to do a character search for some reason "+EMOJI[":astonished:"]
        else:
            if type(char) is dict:
                if char == ERROR_NETWORK:
                    embed.description += "I failed to do a character search for some reason " + EMOJI[":astonished:"]
                # Char is owned by a discord user
                else:
                    if char["owner_id"] is not None and getUserById(char["owner_id"]):
                        owner = getUserById(char["owner_id"])
                        embed.set_thumbnail(url=owner.avatar_url)
                        color = getUserColor(owner, ctx.message.server)
                        if color is not discord.Colour.default():
                            embed.colour = color
                        embed.description += "**{0}** is a character of @**{1.display_name}**\n".format(char["name"], owner)
                    embed.description += charString
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


def setup(bot):
    bot.add_cog(Tibia(bot))

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")