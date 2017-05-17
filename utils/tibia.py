import asyncio

import io
from html.parser import HTMLParser

from PIL import Image
from PIL import ImageDraw
from bs4 import BeautifulSoup
from discord import Colour
import datetime
import urllib.parse
import aiohttp
import re
from datetime import datetime, date, timedelta
from calendar import timegm
import time

from utils.database import userDatabase, tibiaDatabase
from config import highscores_categories, network_retry_delay
from utils.messages import EMOJI
from .general import log, global_online_list, get_local_timezone

# Constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1
ERROR_NOTINDATABASE = 2

# Tibia.com URLs:
url_character = "https://secure.tibia.com/community/?subtopic=characters&name="
url_guild = "https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName="
url_guild_online = "https://secure.tibia.com/community/?subtopic=guilds&page=view&onlyshowonline=1&"
url_house = "https://secure.tibia.com/community/?subtopic=houses&page=view&houseid={id}&world={world}"
url_highscores = "https://secure.tibia.com/community/?subtopic=highscores&world={0}&list={1}&profession={2}&currentpage={3}"

KNIGHT = ["knight", "elite knight", "ek", "k", "kina", "eliteknight","elite"]
PALADIN = ["paladin", "royal paladin", "rp", "p", "pally", "royalpaladin", "royalpally"]
DRUID = ["druid", "elder druid", "ed", "d", "elderdruid", "elder"]
SORCERER = ["sorcerer", "master sorcerer", "ms", "s", "sorc", "mastersorcerer", "master"]
MAGE = DRUID + SORCERER + ["mage"]
NO_VOCATION = ["no vocation", "no voc", "novoc", "nv", "n v", "none", "no", "n", "noob", "noobie", "rook", "rookie"]

highscore_format = {"achievements": "{0} __achievement points__ are **{1}**, on rank **{2}**",
                    "axe": "{0} __axe fighting__ level is **{1}**, on rank **{2}**",
                    "club": "{0} __club fighting__ level is **{1}**, on rank **{2}**",
                    "distance": "{0} __distance fighting__ level is **{1}**, on rank **{2}**",
                    "fishing": "{0} __fishing__ level is **{1}**, on rank **{2}**",
                    "fist": "{0} __fist fighting__ level is **{1}**, on rank **{2}**",
                    "loyalty": "{0} __loyalty points__ are **{1}**, on rank **{2}**",
                    "magic": "{0} __magic level__ is **{1}**, on rank **{2}**",
                    "magic_ek": "{0} __magic level__ is **{1}**, on rank **{2}** (knights)",
                    "magic_rp": "{0} __magic level__ is **{1}**, on rank **{2}** (paladins)",
                    "shielding": "{0} __shielding__ level is **{1}**, on rank **{2}**",
                    "sword": "{0} __sword fighting__ level is **{1}**, on rank **{2}**"}

tibia_worlds = ["Amera", "Antica", "Astera", "Aurera", "Aurora", "Bellona", "Belobra", "Beneva", "Calmera", "Calva",
                "Calvera", "Candia", "Celesta", "Chrona", "Danera", "Dolera", "Efidia", "Eldera", "Ferobra", "Fidera",
                "Fortera", "Garnera", "Guardia", "Harmonia", "Honera", "Hydera", "Inferna", "Iona", "Irmada", "Julera",
                "Justera", "Kenora", "Kronera", "Laudera", "Luminera", "Magera", "Menera", "Morta", "Mortera",
                "Neptera", "Nerana", "Nika", "Olympa", "Osera", "Pacera", "Premia", "Pythera", "Guilia", "Refugia",
                "Rowana", "Secura", "Serdebra", "Shivera", "Silvera", "Solera", "Tavara", "Thera", "Umera", "Unitera",
                "Veludera", "Verlana", "Xantera", "Xylana", "Yanara", "Zanera", "Zeluna", "Honbra", "Noctera", "Vita",
                "Duna", "Relembra"]

async def get_highscores(world, category, pagenum, profession=0, tries=5):
    """Gets a specific page of the highscores
    Each list element is a dictionary with the following keys: rank, name, value.
    May return ERROR_NETWORK"""
    url = url_highscores.format(world, category, profession, pagenum)

    if tries == 0:
        log.error("get_highscores: Couldn't fetch {0}, {1}, page {2}, network error.".format(world, category, pagenum))
        return ERROR_NETWORK

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_highscores(world, category, pagenum, profession, tries - 1)

    # Trimming content to reduce load
    try:
        start_index = content.index('<td style="width: 20%;" >Vocation</td>')
        end_index = content.index('<div style="float: left;"><b>&raquo; Pages:')
        content = content[start_index:end_index]
    except ValueError:
        await asyncio.sleep(network_retry_delay)
        return await get_highscores(world, category, pagenum, profession, tries - 1)
    
    if category == "loyalty":
        regex_deaths = r'<td>([^<]+)</TD><td><a href="https://secure.tibia.com/community/\?subtopic=characters&name=[^"]+" >([^<]+)</a></td><td>[^<]+</TD><td>[^<]+</TD><td style="text-align: right;" >([^<]+)</TD></TR>'
        pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
        matches = re.findall(pattern, content)
        score_list = []
        for m in matches:
            score_list.append({'rank': m[0], 'name': m[1], 'value': m[2].replace(',', '')})
    else:
        regex_deaths = r'<td>([^<]+)</TD><td><a href="https://secure.tibia.com/community/\?subtopic=characters&name=[^"]+" >([^<]+)</a></td><td>[^<]+</TD><td style="text-align: right;" >([^<]+)</TD></TR>'
        pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
        matches = re.findall(pattern, content)
        score_list = []
        for m in matches:
            score_list.append({'rank': m[0], 'name': m[1], 'value': m[2].replace(',', '')})
    return score_list

async def get_world_info(name, tries = 5):
    """Returns a dictionary with a world's information"""
    name = name.capitalize()
    url = 'https://secure.tibia.com/community/?subtopic=worlds&world=' + name
    world = {}

    if tries == 0:
        log.error(f"get_world_info: Couldn't fetch {name}, network error.")
        return ERROR_NETWORK

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_world_info(name, tries - 1)

    # Trimming content to reduce load
    try:
        start_index = content.index('<div class="InnerTableContainer"')
        end_index = content.index('<div id="ThemeboxesColumn" >')
        content = content[start_index:end_index]
    except ValueError:
        await asyncio.sleep(network_retry_delay)
        return await get_world_online(world, tries - 1)

    if "World with this name doesn't exist!" in content:
        return None

    # Status
    m = re.search(r'alt=\"Server PVP Type\" /></div>(\w+)<', content)
    if m:
        world["status"] = m.group(1)
    # Players online
    m = re.search(r'Players Online:</td><td>(\d+)</td>', content)
    if m:
        try:
            world["online"] = int(m.group(1))
        except ValueError:
            world["online"] = 0

    # Online record
    m = re.search(r'Online Record:</td><td>(\d+) players \(on ([^)]+)', content)
    if m:
        try:
            world["record_date"] = m.group(2).replace('&#160;', ' ')
            world["record_online"] = int(m.group(1))
        except ValueError:
            world["record_online"] = 0

    # Creation Date
    m = re.search(r'Creation Date:</td><td>([^<]+)', content)
    if m:
        world["created"] = m.group(1)

    # Location
    m = re.search(r'Location:</td><td>([^<]+)', content)
    if m:
        world["location"] = m.group(1).replace('&#160;', ' ')

    # PvP
    m = re.search(r'PvP Type:</td><td>([^<]+)', content)
    if m:
        world["pvp"] = m.group(1).replace('&#160;', ' ')

    # Premium
    m = re.search(r'Premium Type:</td><td>(\w+)', content)
    if m:
        world["premium"] = m.group(1).replace('&#160;', ' ')

    # Transfer type
    m = re.search(r'Transfer Type:</td><td>([\w\s]+)', content)
    if m:
        world["transfer"] = m.group(1).replace('&#160;', ' ')

    return world


async def get_world_online(world, tries=5):
    """Returns a list of all the online players in current server.

    Each list element is a dictionary with the following keys: name, level"""
    world = world.capitalize()
    url = 'https://secure.tibia.com/community/?subtopic=worlds&world=' + world
    online_list = []

    if tries == 0:
        log.error("get_world_online: Couldn't fetch {0}, network error.".format(world))
        return online_list

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_world_online(world, tries - 1)

    # Trimming content to reduce load
    try:
        start_index = content.index('<div class="BoxContent"')
        end_index = content.index('<div id="ThemeboxesColumn" >')
        content = content[start_index:end_index]
    except ValueError:
        await asyncio.sleep(network_retry_delay)
        return await get_world_online(world, tries - 1)

    regex_members = r'<a href="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)" >.+?</a></td><td style="width:10%;" >(.+?)</td><td style="width:20%;" >([^<]+)'
    pattern = re.compile(regex_members, re.MULTILINE + re.S)
    m = re.findall(pattern, content)
    # Check if list is empty
    if m:
        # Building dictionary list from online players
        for (name, level,vocation) in m:
            name = urllib.parse.unquote_plus(name)
            vocation = vocation.replace('&#160;',' ')
            online_list.append({'name': name, 'level': int(level), 'vocation': vocation})
    return online_list


async def get_guild_online(name, title_case=True, tries=5):
    """Returns a guild's world and online member list in a dictionary.

    The dictionary contains the following keys: name, logo_url, world and members.
    The key members contains a list where each element is a dictionary with the following keys:
        rank, name, title, vocation, level, joined.
    Guilds are case sensitive on tibia.com so guildstats.eu is checked for correct case.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly."""
    guildstats_url = 'http://guildstats.eu/guild?guild=' + urllib.parse.quote(name)
    guild = {}

    if tries == 0:
        log.error("get_guild_online: Couldn't fetch {0}, network error.".format(name))
        return ERROR_NETWORK

    # Fix casing using guildstats.eu if needed
    # Sorry guildstats.eu :D
    if not title_case:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(guildstats_url) as resp:
                    content = await resp.text(encoding='ISO-8859-1')
        except Exception:
            await asyncio.sleep(network_retry_delay)
            return await get_guild_online(name, title_case, tries - 1)

        # Make sure we got a healthy fetch
        try:
            content.index('<div class="footer">')
        except ValueError:
            await asyncio.sleep(network_retry_delay)
            return await get_guild_online(name, title_case, tries - 1)

        # Check if the guild doesn't exist
        if "<div>Sorry!" in content:
            return ERROR_DOESNTEXIST

        # Failsafe in case guildstats.eu changes their websites format
        try:
            content.index("General info")
            content.index("Recruitment")
        except Exception:
            log.error("get_guild_online: -IMPORTANT- guildstats.eu seems to have changed their websites format.")
            return ERROR_NETWORK

        start_index = content.index("General info")
        end_index = content.index("Recruitment")
        content = content[start_index:end_index]
        m = re.search(r'<a href="set=(.+?)"', content)
        if m:
            name = urllib.parse.unquote_plus(m.group(1))
    else:
        name = name.title()

    tibia_url = 'https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName=' + urllib.parse.quote(
        name) + '&onlyshowonline=1'
    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(tibia_url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_guild_online(name, title_case, tries - 1)

    # Trimming content to reduce load and making sure we got a healthy fetch
    try:
        start_index = content.index('<div class="BoxContent"')
        end_index = content.index('<div id="ThemeboxesColumn" >')
        content = content[start_index:end_index]
    except ValueError:
        # Website fetch was incomplete, due to a network error
        await asyncio.sleep(network_retry_delay)
        return await get_guild_online(name, title_case, tries - 1)

    # Check if the guild doesn't exist
    # Tibia.com has no search function, so there's no guild doesn't exist page cause you're not supposed to get to a
    # guild that doesn't exists. So the message displayed is "An internal error has ocurred. Please try again later!".
    if '<div class="Text" >Error</div>' in content:
        if title_case:
            return await get_guild_online(name, False)
        else:
            return ERROR_DOESNTEXIST
    guild['name'] = name
    # Regex pattern to fetch world, guildhall and founding date
    m = re.search(r'founded on (\w+) on ([^.]+)', content)
    if m:
        guild['world'] = m.group(1)

    m = re.search(r'Their home on \w+ is ([^\.]+)', content)
    if m:
        guild["guildhall"] = m.group(1)

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
    return guild


def get_character_url(name):
    """Gets a character's tibia.com URL"""
    return url_character + urllib.parse.quote(name.encode('iso-8859-1'))


async def get_character(name, tries=5):
    """Returns a dictionary with a player's info

    The dictionary contains the following keys: name, deleted, level, vocation, world, residence,
    married, gender, guild, last,login, chars*.
        *chars is list that contains other characters in the same account (if not hidden).
        Each list element is dictionary with the keys: name, world.
    May return ERROR_DOESNTEXIST or ERROR_NETWORK accordingly."""
    if tries == 0:
        log.error("get_character: Couldn't fetch {0}, network error.".format(name))
        return ERROR_NETWORK
    try:
        url = get_character_url(name)
    except UnicodeEncodeError:
        return ERROR_DOESNTEXIST
    char = dict()

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_character(name, tries-1)

    # Trimming content to reduce load
    try:
        start_index = content.index('<div class="BoxContent"')
        end_index = content.index("<B>Search Character</B>")
        content = content[start_index:end_index]
    except ValueError:
        # Website fetch was incomplete, due to a network error
        await asyncio.sleep(network_retry_delay)
        return await get_character(name, tries - 1)

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
    for onchar in global_online_list:
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

    char["guild"] = None
    # Guild rank
    m = re.search(r'Membership:</td><td>([^<]+)\sof the', content)
    if m:
        char['rank'] = m.group(1)
        # Guild membership
        m = re.search(r'GuildName=.*?([^&]+).+', content)
        if m:
            char['guild'] = urllib.parse.unquote_plus(m.group(1))

    # House
    m = re.search(r'House:</td><td> <a href=\"https://secure\.tibia\.com/community/\?subtopic=houses.+houseid=(\d+)'
                  r'&amp;character=(?:[^&]+)&amp;action=characters\" >([^<]+)</a> \(([^(]+)\) is paid until '
                  r'([A-z]+).*?;(\d+).*?;(\d+)', content)
    if m:
        char["house_id"] = m.group(1)
        char["house"] = m.group(2)
        char["house_town"] = m.group(3)

    # Last login
    m = re.search(r'Last Login:</td><td>([^<]+)', content)
    if m:
        lastLogin = m.group(1).replace("&#160;", " ").replace(",", "")
        if "never" in lastLogin:
            char['last_login'] = None
        else:
            char['last_login'] = lastLogin

    # Character deaths
    char["deaths"] = []
    regex_deaths = r'valign="top" >([^<]+)</td><td>(.+?)</td></tr>'
    pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
    matches = re.findall(pattern, content)

    for m in matches:
        death_time = m[0].replace('&#160;', ' ').replace(",", "")
        death_level = ""
        death_killer = ""
        death_by_player = False

        if m[1].find("Died") != -1:
            regex_deathinfo_monster = r'Level (\d+) by ([^.]+)'
            pattern = re.compile(regex_deathinfo_monster, re.MULTILINE + re.S)
            m_deathinfo_monster = re.search(pattern, m[1])
            if m_deathinfo_monster:
                death_level = m_deathinfo_monster.group(1)
                death_killer = m_deathinfo_monster.group(2)
        else:
            regex_deathinfo_player = r'Level (\d+) by .+?name=([^"]+)'
            pattern = re.compile(regex_deathinfo_player, re.MULTILINE + re.S)
            m_deathinfo_player = re.search(pattern, m[1])
            if m_deathinfo_player:
                death_level = m_deathinfo_player.group(1)
                death_killer = urllib.parse.unquote_plus(m_deathinfo_player.group(2))
                death_by_player = True
        try:
            char["deaths"].append({'time': death_time, 'level': int(death_level), 'killer': death_killer,
                                   'byPlayer': death_by_player})
        except ValueError:
            # Some pvp deaths have no level, so they are raising a ValueError, they will be ignored for now.
            continue

    # Other chars
    # note that an empty char list means the character is hidden
    # otherwise you'd have at least the same char in the list
    char['chars'] = []
    try:
        # See if there is a character list
        start_index = content.index("<B>Characters</B>")
        content = content[start_index:]

        # Find characters
        regex_chars = r'<TD WIDTH=10%><NOBR>([^<]+)[^?]+.+?VALUE=\"([^\"]+)'
        pattern = re.compile(regex_chars, re.MULTILINE + re.S)
        m = re.findall(pattern, content)

        if m:
            for (world, _name) in m:
                _name = urllib.parse.unquote_plus(_name)
                char['chars'].append({'name': _name, 'world': world})
    except Exception:
        pass

    # Database information:
    c = userDatabase.cursor()
    try:
        # Discord owner
        c.execute("SELECT user_id, vocation, name, id, world, guild FROM chars WHERE name LIKE ?", (name,))
        result = c.fetchone()
        char["owner_id"] = None if result is None else result["user_id"]
        if result is None:
            # Untracked character, so there's nothing else to check past here
            return
        if result["vocation"] != char['vocation']:
            c.execute("UPDATE chars SET vocation = ? WHERE id = ?", (char['vocation'], result["id"],))
            log.info("{0}'s vocation was set to {1} from {2} during get_character()".format(char['name'],
                                                                                            char['vocation'],
                                                                                            result["vocation"]))
        if result["name"] != char["name"]:
            c.execute("UPDATE chars SET name = ? WHERE id = ?", (char['name'], result["id"],))
            log.info("{0} was renamed to {1} during get_character()".format(result["name"], char['name']))

        if result["world"] != char["world"]:
            c.execute("UPDATE chars SET world = ? WHERE id = ?", (char['world'], result["id"],))
            log.info("{0}'s world was set to {1} from {2} during get_character()".format(char['name'],
                                                                                         char['world'],
                                                                                         result["world"]))
        if result["guild"] != char["guild"]:
            c.execute("UPDATE chars SET guild = ? WHERE id = ?", (char['guild'], result["id"],))
            log.info("{0}'s guild was set to {1} from {2} during get_character()".format(char['name'],
                                                                                         char['guild'],
                                                                                         result["guild"]))
        # Skills from highscores
        for category in highscores_categories:
            c.execute("SELECT " + category + "," + category + "_rank FROM chars WHERE name LIKE ?", (char["name"],))
            result = c.fetchone()
            if result:
                if result[category] is not None and result[category + '_rank'] is not None:
                    char[category] = result[category]
                    char[category + '_rank'] = result[category + '_rank']
    finally:
        userDatabase.commit()
        c.close()
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
            # Checking quest rewards:
            c.execute("SELECT Quests.title FROM Quests, QuestRewards "
                      "WHERE Quests.id = QuestRewards.questid and itemid = ?", (item["id"],))
            quests = c.fetchall()
            item["quests"] = list()
            for quest in quests:
                item["quests"].append(quest["title"])
            return item
    finally:
        c.close()
    return


def parse_tibia_time(tibia_time: str) -> datetime:
    """Gets a time object from a time string from tibia.com"""
    tibia_time = tibia_time.replace(",","").replace("&#160;", " ")
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    local_utc_offset = ((timegm(t) - timegm(u)) / 60 / 60)
    # Extracting timezone
    tz = tibia_time[-4:].strip()
    try:
        # Convert time string to time object
        # Removing timezone cause CEST and CET are not supported
        t = datetime.strptime(tibia_time[:-4].strip(), "%b %d %Y %H:%M:%S")
    except ValueError:
        log.error("parse_tibia_time: couldn't parse '{0}'".format(tibia_time))
        return None

    # Getting the offset
    if tz == "CET":
        utc_offset = 1
    elif tz == "CEST":
        utc_offset = 2
    else:
        log.error("parse_tibia_time: unknown timezone for '{0}'".format(tibia_time))
        return None
    # Add/subtract hours to get the real time
    return t + timedelta(hours=(local_utc_offset - utc_offset))


def get_stats(level: int, vocation: str):
    """Returns a dictionary with the stats for a character of a certain vocation and level.

    The dictionary has the following keys: vocation, hp, mp, cap, exp, exp_tnl."""
    try:
        level = int(level)
    except ValueError:
        raise ValueError("That's not a valid level.")
    if level <= 0:
        raise ValueError("Level must be higher than 0.")

    vocation = vocation.lower().strip()
    if vocation in KNIGHT:
        hp = (level - 8) * 15 + 185
        mp = (level - 0) * 5 + 50
        cap = (level - 8) * 25 + 470
        vocation = "knight"
    elif vocation in PALADIN:
        hp = (level - 8) * 10 + 185
        mp = (level - 8) * 15 + 90
        cap = (level - 8) * 20 + 470
        vocation = "paladin"
    elif vocation in MAGE:
        hp = (level - 0) * 5 + 145
        mp = (level - 8) * 30 + 90
        cap = (level - 0) * 10 + 390
        vocation = "mage"
    elif vocation in NO_VOCATION or level < 8:
        if vocation in NO_VOCATION:
            vocation = "no vocation"
        hp = (level - 0) * 5 + 145
        mp = (level - 0) * 5 + 50
        cap = (level - 0) * 10 + 390
    else:
        raise ValueError("That's not a valid vocation!")

    exp = (50*pow(level, 3)/3) - 100*pow(level, 2) + (850*level/3) - 200
    exp_tnl = 50*level*level - 150 * level + 200

    return {"vocation": vocation, "hp": hp, "mp": mp, "cap": cap, "exp": int(exp), "exp_tnl": exp_tnl}


def get_share_range(level: int):
    """Returns the share range for a specific level

    The returned value is a list with the lower limit and the upper limit in that order."""
    return int(round(level * 2 / 3, 0)), int(round(level * 3 / 2, 0))


# TODO: Improve formatting to match /monster and /item
def get_spell(name):
    """Returns a dictionary containing a spell's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        c.execute("""SELECT * FROM Spells WHERE words LIKE ? OR name LIKE ? ORDER BY LENGTH(name) LIMIT 15""",
                  ("%" + name + "%", "%" + name + "%"))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["name"].lower() == name.lower() or result[0]["words"].lower() == name.lower() or len(result) == 1:
            spell = result[0]
        else:
            return ["{name} ({words})".format(**x) for x in result]

        spell["npcs"] = []
        c.execute("""SELECT NPCs.title as name, NPCs.city, SpellNPCs.knight, SpellNPCs.paladin,
                  SpellNPCs.sorcerer, SpellNPCs.druid FROM NPCs, SpellNPCs
                  WHERE SpellNPCs.spellid = ? AND SpellNPCs.npcid = NPCs.id""", (spell["id"],))
        result = c.fetchall()
        for npc in result:
            npc["city"] = npc["city"].title()
            spell["npcs"].append(npc)
        return spell

    finally:
        c.close()


def get_npc(name):
    """Returns a dictionary containing a NPC's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        # search query
        c.execute("SELECT * FROM NPCs WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["title"].lower() == name.lower or len(result) == 1:
            npc = result[0]
        else:
            return [x["title"] for x in result]
        npc["image"] = 0

        c.execute("SELECT Items.name, Items.category, BuyItems.value FROM BuyItems, Items "
                  "WHERE Items.id = BuyItems.itemid AND BuyItems.vendorid = ?", (npc["id"],))
        npc["sell_items"] = c.fetchall()

        c.execute("SELECT Items.name, Items.category, SellItems.value FROM SellItems, Items "
                  "WHERE Items.id = SellItems.itemid AND SellItems.vendorid = ?", (npc["id"],))
        npc["buy_items"] = c.fetchall()
        return npc
    finally:
        c.close()

async def get_world_bosses(world):
    url = f"http://www.tibiabosses.com/{world}/"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception as e:
        return ERROR_NETWORK

    try:
        soup = BeautifulSoup(content, 'html.parser')
        entry = soup.find('div', class_='entry')
        sections = entry.find_all('div', class_="execphpwidget")
    except HTMLParser.HTMLParseError:
        print("parse error")
        return
    if sections is None:
        print("section was none")
        return
    bosses = {}
    for section in sections:
        regex = r'<i style="color:\w+;">[\n\s]+([^<]+)</i> <a href="([^"]+)"><img src="([^"]+)"/></a>[\n\s]+(Expect in|Last seen)\s:\s(\d+)'
        m = re.findall(regex, str(section))
        if m:
            for (chance, link, image, expect_last, days) in m:
                name = link.split("/")[-1].replace("-"," ").lower()
                bosses[name] = {"chance": chance.strip(), "url": link, "image": image, "type": expect_last,
                                "days": int(days)}
        else:
            # This regex is for bosses without prediction
            regex = r'<a href="([^"]+)"><img src="([^"]+)"/></a>[\n\s]+(Expect in|Last seen)\s:\s(\d+)'
            m = re.findall(regex, str(section))
            for (link, image, expect_last, days) in m:
                name = link.split("/")[-1].replace("-", " ").lower()
                bosses[name] = {"chance": "Unpredicted", "url": link, "image": image, "type": expect_last,
                                "days": int(days)}
    return bosses


async def get_house(name, world = None):
    """Returns a dictionary containing a house's info, a list of possible matches or None.

    If world is specified, it will also find the current status of the house in that world."""
    c = tibiaDatabase.cursor()
    try:
        # Search query
        c.execute("SELECT * FROM Houses WHERE name LIKE ? ORDER BY LENGTH(name) ASC LIMIT 15", ("%" + name + "%",))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["name"].lower() == name.lower() or len(result) == 1:
            house = result[0]
        else:
            return [x['name'] for x in result]
        if world is None or world not in tibia_worlds:
            house["fetch"] = False
            return house
        house["world"] = world
        house["url"] = url_house.format(id=house["id"], world=world)
        tries = 5
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(house["url"]) as resp:
                        content = await resp.text(encoding='ISO-8859-1')
            except Exception:
                tries -= 1
                if tries == 0:
                    log.error("get_house: Couldn't fetch {0} (id {1}) in {2}, network error.".format(house["name"],
                                                                                                     house["id"],
                                                                                                     world))
                    house["fetch"] = False
                    break
                await asyncio.sleep(network_retry_delay)
                continue

            # Trimming content to reduce load
            try:
                start_index = content.index("\"BoxContent\"")
                end_index = content.index("</TD></TR></TABLE>")
                content = content[start_index:end_index]
            except ValueError:
                if tries == 0:
                    log.error("get_house: Couldn't fetch {0} (id {1}) in {2}, network error.".format(house["name"],
                                                                                                     house["id"],
                                                                                                     world))
                    house["fetch"] = False
                    break
                else:
                    tries -= 1
                    await asyncio.sleep(network_retry_delay)
                    continue
            house["fetch"] = True
            m = re.search(r'monthly rent is <B>(\d+)', content)
            if m:
                house['rent'] = int(m.group(1))

            if "rented" in content:
                house["status"] = "rented"
                m = re.search(r'rented by <A?.+name=([^\"]+).+e has paid the rent until <B>([^<]+)</B>', content)
                if m:
                    house["owner"] = urllib.parse.unquote_plus(m.group(1))
                    house["until"] = m.group(2).replace("&#160;", " ")
                if "move out" in content:
                    house["status"] = "transferred"
                    m = re.search(r'will move out on <B>([^<]+)</B> \(time of daily server save\) and (?:will|wants to)'
                                  r' pass the house to <A.+name=([^\"]+).+ for <B>(\d+) gold', content)
                    if m:
                        house["transfer_date"] =house["until"] = m.group(1).replace("&#160;", " ")
                        house["transferee"] = urllib.parse.unquote_plus(m.group(2))
                        house["transfer_price"] = int(m.group(3))
                        house["accepted"] = ("will pass " in m.group(0))
            elif "auctioned" in content:
                house["status"] = "auctioned"
                if ". No bid has" in content:
                    house["status"] = "empty"
                    break
                m = re.search(r'The auction will end at <B>([^\<]+)</B>\. '
                              r'The highest bid so far is <B>(\d+).+ by .+name=([^\"]+)\"', content)
                if m:
                    house["auction_end"] = m.group(1).replace("&#160;", " ")
                    house["top_bid"] = int(m.group(2))
                    house["top_bidder"] = urllib.parse.unquote_plus(m.group(3))
            break
        return house
    finally:
        c.close()


def get_achievement(name):
    """Returns an achievement (dictionary), a list of possible matches or none"""
    c = tibiaDatabase.cursor()
    try:
        # Search query
        c.execute("SELECT * FROM Achievements WHERE name LIKE ? ORDER BY LENGTH(name) ASC LIMIT 15", ("%" + name + "%",))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["name"].lower() == name.lower() or len(result) == 1:
            return result[0]
        else:
            return [x['name'] for x in result]
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
    """Given a vocation name, it returns an abbreviated string"""
    abbrev = {'none': 'N', 'druid': 'D', 'sorcerer': 'S', 'paladin': 'P', 'knight': 'K', 'elder druid': 'ED',
              'master sorcerer': 'MS', 'royal paladin': 'RP', 'elite knight': 'EK'}
    try:
        return abbrev[vocation.lower()]
    except KeyError:
        return 'N'


def get_voc_emoji(vocation: str) -> str:
    """Given a vocation name, returns a emoji representing it"""
    emoji = {'none': EMOJI[":hatching_chick:"], 'druid': EMOJI[":snowflake:"], 'sorcerer': EMOJI[":flame:"], 'paladin': EMOJI[":archery:"],
              'knight': EMOJI[":shield:"], 'elder druid': EMOJI[":snowflake:"],
              'master sorcerer': EMOJI[":flame:"], 'royal paladin': EMOJI[":archery:"],
              'elite knight': EMOJI[":shield:"]}
    try:
        return emoji[vocation.lower()]
    except KeyError:
        return EMOJI[":question:"]


def get_pronouns(gender: str):
    """Gets a list of pronouns based on the gender given. Only binary genders supported, sorry."""
    gender = gender.lower()
    if gender == "female":
        pronoun = ["she", "her", "her"]
    elif gender == "male":
        pronoun = ["he", "his", "him"]
    else:
        pronoun = ["it", "its", "it"]
    return pronoun


def get_map_area(x, y, z, size=15, scale=8, crosshair=True):
    """Gets a minimap picture of a map area

    size refers to the radius of the image in actual tibia sqm
    scale is how much the image will be streched (1 = 1 sqm = 1 pixel)"""
    c = tibiaDatabase.cursor()
    c.execute("SELECT * FROM WorldMap WHERE z LIKE ?", (z,))
    result = c.fetchone()
    im = Image.open(io.BytesIO(bytearray(result['image'])))
    im = im.crop((x-size, y-size, x+size, y+size))
    im = im.resize((size*scale, size*scale))
    if crosshair:
        draw = ImageDraw.Draw(im)
        width, height = im.size
        draw.line((0, height/2, width, height/2), fill=128)
        draw.line((width/2, 0, width/2, height), fill=128)

    img_byte_arr = io.BytesIO()
    im.save(img_byte_arr, format='png')
    img_byte_arr = img_byte_arr.getvalue()
    return img_byte_arr
