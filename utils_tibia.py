import asyncio
from discord import Colour
import datetime
import urllib
import urllib.request
import aiohttp
import re
from datetime import datetime, date, timedelta
from calendar import timegm
import time

from utils import log, globalOnlineList, tibiaDatabase, userDatabase, get_local_timezone

# Constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1
ERROR_NOTINDATABASE = 2

# Tibia.com URLs:
url_character = "https://secure.tibia.com/community/?subtopic=characters&name="
url_guild = "https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName="
url_guild_online = "https://secure.tibia.com/community/?subtopic=guilds&page=view&onlyshowonline=1&"

KNIGHT = ["knight", "elite knight", "ek", "k", "kina", "eliteknight","elite"]
PALADIN = ["paladin", "royal paladin", "rp", "p", "pally", "royalpaladin", "royalpally"]
DRUID = ["druid", "elder druid", "ed", "d", "elderdruid", "elder"]
SORCERER = ["sorcerer", "master sorcerer", "ms", "s", "sorc", "mastersorcerer", "master"]
MAGE = DRUID + SORCERER + ["mage"]
NO_VOCATION = ["no vocation", "no voc", "novoc", "nv", "n v", "none", "no", "n", "noob", "noobie", "rook", "rookie"]


@asyncio.coroutine
def get_character_deaths(name, single_death=False, tries=5):
    """Returns a list with the player's deaths

    Each list element is a dictionary with the following keys: time, level, killer, byPlayer.
    If single_death is true, it stops looking after fetching the first death.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly"""
    url = url_character + urllib.parse.quote(name)
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
            ret = yield from get_character_deaths(name, single_death, tries)
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
            ret = yield from get_character_deaths(name, single_death, tries)
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
    pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
    matches = re.findall(pattern, content)

    for m in matches:
        deathTime = ""
        deathLevel = ""
        deathKiller = ""
        deathByPlayer = False
        regex_deathtime = r'(\w+).+?;(\d+).+?;(\d+).+?;(\d+):(\d+):(\d+).+?;(\w+)'
        pattern = re.compile(regex_deathtime, re.MULTILINE + re.S)
        m_deathtime = re.search(pattern, m[0])

        if m_deathtime:
            deathTime = "{0} {1} {2} {3}:{4}:{5} {6}".format(m_deathtime.group(1), m_deathtime.group(2),
                                                             m_deathtime.group(3), m_deathtime.group(4),
                                                             m_deathtime.group(5), m_deathtime.group(6),
                                                             m_deathtime.group(7))

        if m[1].find("Died") != -1:
            regex_deathinfo_monster = r'Level (\d+) by ([^.]+)'
            pattern = re.compile(regex_deathinfo_monster, re.MULTILINE + re.S)
            m_deathinfo_monster = re.search(pattern, m[1])
            if m_deathinfo_monster:
                deathLevel = m_deathinfo_monster.group(1)
                deathKiller = m_deathinfo_monster.group(2)
        else:
            regex_deathinfo_player = r'Level (\d+) by .+?name=([^"]+)'
            pattern = re.compile(regex_deathinfo_player, re.MULTILINE + re.S)
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
def get_server_online(server, tries=5):
    """Returns a list of all the online players in current server.

    Each list element is a dictionary with the following keys: name, level"""
    url = 'https://secure.tibia.com/community/?subtopic=worlds&world=' + server
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
            ret = yield from get_server_online(server, tries)
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
            ret = yield from get_server_online(server, tries)
            return ret

    regex_members = r'<a href="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)" >.+?</a></td><td style="width:10%;" >(.+?)</td>'
    pattern = re.compile(regex_members, re.MULTILINE + re.S)
    m = re.findall(pattern, content)
    # Check if list is empty
    if m:
        # Building dictionary list from online players
        for (name, level) in m:
            name = urllib.parse.unquote_plus(name)
            onlineList.append({'name': name, 'level': int(level)})
    return onlineList


@asyncio.coroutine
def get_guild_online(guildname, titlecase=True, tries=5):
    """Returns a guild's world and online member list in a dictionary.

    The dictionary contains the following keys: name, logo_url, world and members.
    The key members contains a list where each element is a dictionary with the following keys:
        rank, name, title, vocation, level, joined.
    Guilds are case sensitive on tibia.com so guildstats.eu is checked for correct case.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly."""
    gstats_url = 'http://guildstats.eu/guild?guild=' + urllib.parse.quote(guildname)
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
                ret = yield from get_guild_online(guildname, titlecase, tries)
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
                ret = yield from get_guild_online(guildname, titlecase, tries)
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

    tibia_url = 'https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName=' + urllib.parse.quote(
        guildname) + '&onlyshowonline=1'
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
            ret = yield from get_guild_online(guildname, titlecase, tries)
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
            ret = yield from get_guild_online(guildname, titlecase, tries)
            return ret

    # Check if the guild doesn't exist
    # Tibia.com has no search function, so there's no guild doesn't exist page cause you're not supposed to get to a
    # guild that doesn't exists. So the message displayed is "An internal error has ocurred. Please try again later!".
    if '<div class="Text" >Error</div>' in content:
        if titlecase:
            ret = yield from get_guild_online(guildname, False)
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
    pattern = re.compile(regex_members, re.MULTILINE + re.S)

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
def get_character(name, tries=5):
    """Returns a dictionary with a player's info

    The dictionary contains the following keys: name, deleted, level, vocation, world, residence,
    married, gender, guild, last,login, chars*.
        *chars is list that contains other characters in the same account (if not hidden).
        Each list element is dictionary with the keys: name, world.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly."""
    url = url_character + urllib.parse.quote(name)
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
            ret = yield from get_character(name, tries)
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
            ret = yield from get_character(name, tries)
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
    m = re.search(r'Married To:</td><td>?.+name=([^"]+)', content)
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
    m = re.search(r'Membership:</td><td>([^<]+)\sof the', content)
    if m:
        char['rank'] = m.group(1)
        # Guild membership
        m = re.search(r'GuildName=.*?([^&]+).+', content)
        if m:
            char['guild'] = urllib.parse.unquote_plus(m.group(1))

    # Last login
    m = re.search(r'Last Login:</td><td>([^<]+)', content)
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
    c.execute("SELECT vocation FROM chars WHERE name LIKE ?", (name,))
    result = c.fetchone()
    if result:
        if result["vocation"] != char['vocation']:
            c.execute("UPDATE chars SET vocation = ? WHERE name LIKE ?", (char['vocation'], name,))
            log.info("{0}'s vocation was set to {1} from {2} during getPlayer()".format(char['name'], char['vocation'],
                                                                                        result["vocation"]))
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
        pattern = re.compile(regex_chars, re.MULTILINE + re.S)
        m = re.findall(pattern, content)

        if m:
            for (world, name) in m:
                name = urllib.parse.unquote_plus(name)
                char['chars'].append({'name': name, 'world': world})
    except Exception:
        pass
    return char


def get_rashid_city() -> str:
    """Returns the city Rashid is currently in."""
    offset = get_tibia_time_zone() - get_local_timezone()
    # Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = datetime.now() + timedelta(hours=offset - 10)
    return ["Svargrond",
            "Liberty Bay",
            "Port Hope",
            "Ankrahmun",
            "Darashia",
            "Edron",
            "Carlin"][tibia_time.weekday()]


def get_monster(name):
    """Returns a dictionary with a monster's info, if no exact match was found, it returns a list of suggestions.

    The dictionary has the following keys: name, id, hp, exp, maxdmg, elem_physical, elem_holy,
    elem_death, elem_fire, elem_energy, elem_ice, elem_earth, elem_drown, elem_lifedrain, senseinvis,
    arm, image."""

    # Reading monster database
    c = tibiaDatabase.cursor()
    c.execute("SELECT * FROM Creatures WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%"+name+"%",))
    result = c.fetchall()
    if len(result) == 0:
        return None
    elif result[0]["title"].lower() == name.lower() or len(result) == 1:
        monster = result[0]
    else:
        return [x['title'] for x in result]
    try:
        if monster['health'] is None or monster['health'] < 1:
            monster['health'] = None
        c.execute("SELECT Items.title as name, percentage, min, max "
                  "FROM CreatureDrops, Items "
                  "WHERE Items.id = CreatureDrops.itemid AND creatureid = ? "
                  "ORDER BY percentage DESC",
                  (monster["id"],))
        monster["loot"] = c.fetchall()
        return monster
    finally:
        c.close()


def get_item(name):
    """Returns a dictionary containing an item's info, if no exact match was found, it returns a list of suggestions.

    The dictionary has the following keys: name, look_text, npcs_sold*, value_sell, npcs_bought*, value_buy.
        *npcs_sold and npcs_bought are list, each element is a dictionary with the keys: name, city."""

    # Reading item database
    c = tibiaDatabase.cursor()

    # Search query
    c.execute("SELECT * FROM Items WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
    result = c.fetchall()
    if len(result) == 0:
        return None
    elif result[0]["title"].lower() == name.lower() or len(result) == 1:
        item = result[0]
    else:
        return [x['title'] for x in result]
    try:
        # Checking if item exists
        if item is not None:
            # Checking NPCs that buy the item
            c.execute("SELECT NPCs.title, city, value "
                      "FROM Items, SellItems, NPCs "
                      "WHERE Items.name LIKE ? AND SellItems.itemid = Items.id AND NPCs.id = vendorid "
                      "ORDER BY value DESC", (name,))
            npcs = []
            value_sell = None
            for npc in c:
                name = npc["title"]
                city = npc["city"].title()
                if value_sell is None:
                    value_sell = npc["value"]
                elif npc["value"] != value_sell:
                    break
                # Replacing cities for special npcs and adding colors
                if name == 'Alesar' or name == 'Yaman':
                    city = 'Green Djinn\'s Fortress'
                    item["color"] = Colour.green()
                elif name == 'Nah\'Bob' or name == 'Haroun':
                    city = 'Blue Djinn\'s Fortress'
                    item["color"] = Colour.blue()
                elif name == 'Rashid':
                    city = get_rashid_city()
                    item["color"] = Colour(0xF0E916)
                elif name == 'Yasir':
                    city = 'his boat'
                elif name == 'Briasol':
                    item["color"] = Colour(0xA958C4)
                npcs.append({"name": name, "city": city})
            item['npcs_sold'] = npcs
            item['value_sell'] = value_sell

            # Checking NPCs that sell the item
            c.execute("SELECT NPCs.title, city, value "
                      "FROM Items, BuyItems, NPCs "
                      "WHERE Items.name LIKE ? AND BuyItems.itemid = Items.id AND NPCs.id = vendorid "
                      "ORDER BY value ASC", (name,))
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
                    offset = get_tibia_time_zone() - get_local_timezone()
                    # Server save is at 10am, so in tibia a new day starts at that hour
                    tibia_time = datetime.now() + timedelta(hours=offset - 10)
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
            item["dropped_by"] = c.fetchall()
            return item
    finally:
        c.close()
    return


def get_local_time(tibia_time) -> timedelta:
    """Gets a time object from a time string from tibia.com"""
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    local_utc_offset = ((timegm(t) - timegm(u)) / 60 / 60)

    # Convert time string to time object
    # Removing timezone cause CEST and CET are not supported
    t = datetime.strptime(tibia_time[:-4].strip(), "%b %d %Y %H:%M:%S")
    # Extracting timezone
    tz = tibia_time[-4:].strip()

    # Getting the offset
    if tz == "CET":
        utc_offset = 1
    elif tz == "CEST":
        utc_offset = 2
    else:
        return None
    # Add/subtract hours to get the real time
    return t + timedelta(hours=(local_utc_offset - utc_offset))


def get_stats(level: int, vocation: str):
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
    if vocation in KNIGHT:
        hp = 5 * (3 * level - 2 * 8 + 29)
        mp = 5 * level + 50
        cap = 5 * (5 * level - 5 * 8 + 94)
        vocation = "knight"
    elif vocation in PALADIN:
        hp = 5 * (2 * level - 8 + 29)
        mp = 5 * (3 * level - 2 * 8) + 50
        cap = 10 * (2 * level - 8 + 39)
        vocation = "paladin"
    elif vocation in MAGE:
        hp = 5 * (level + 29)
        mp = 5 * (6 * level - 5 * 8) + 50
        cap = 10 * (level + 39)
        vocation = "mage"
    elif vocation in NO_VOCATION:
        vocation = "no vocation"
    else:
        return "bad vocation"

    if level < 8 or vocation == "no vocation":
        hp = 5 * (level + 29)
        mp = 5 * level + 50
        cap = 10 * (level + 39)

    return {"vocation": vocation, "hp": hp, "mp": mp, "cap": cap}



def get_share_range(level: int):
    """Returns the share range for a specific level

    The returned value is a list with the lower limit and the upper limit in that order."""
    return int(round(level * 2 / 3, 0)), int(round(level * 3 / 2, 0))


# TODO: Improve formatting to match /monster and /item
def get_spell(name):
    """Returns a formatted string containing a spell's info."""
    c = tibiaDatabase.cursor()
    try:
        c.execute("""SELECT * FROM Spells WHERE words LIKE ? OR name LIKE ?""", (name + "%", name,))
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


def get_tibia_time_zone() -> int:
    """Returns Germany's timezone, considering their daylight saving time dates"""
    # Find date in Germany
    gt = datetime.utcnow() + timedelta(hours=1)
    germany_date = date(gt.year, gt.month, gt.day)
    dst_start = date(gt.year, 3, (31 - (int(((5 * gt.year) / 4) + 4) % int(7))))
    dst_end = date(gt.year, 10, (31 - (int(((5 * gt.year) / 4) + 1) % int(7))))
    if dst_start < germany_date < dst_end:
        return 2
    return 1


def get_voc_abb(vocation: str) -> str:
    """Given a vocation name, it returns an abbreviated string """
    abbrev = {'None': 'N', 'Druid': 'D', 'Sorcerer': 'S', 'Paladin': 'P', 'Knight': 'K', 'Elder Druid': 'ED',
              'Master Sorcerer': 'MS', 'Royal Paladin': 'RP', 'Elite Knight': 'EK'}
    try:
        return abbrev[vocation]
    except KeyError:
        return 'N'
