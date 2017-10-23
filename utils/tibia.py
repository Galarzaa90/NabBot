import asyncio
import io

from html.parser import HTMLParser
from typing import List, Union, Dict

from PIL import Image
from PIL import ImageDraw
from bs4 import BeautifulSoup, SoupStrainer
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
import json

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

tibia_worlds = []

async def get_character(name, tries=5) -> Union[Dict[str, Union[str, int]], int]:
    """Returns a dictionary with a player's info

    The dictionary contains the following keys: name, deleted, level, vocation, world, residence,
    married, sex, guild, last,login, chars*.
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

    parsed_content = BeautifulSoup(content, 'html.parser', parse_only=SoupStrainer("div", class_="BoxContent"))
    tables = parsed_content.find_all('table')
    if len(tables) <= 2:
        return ERROR_DOESNTEXIST
    for table in tables:
        header = table.find('td')
        rows = table.find_all('tr')
        if "Could not find" in header.text:
            return ERROR_DOESNTEXIST
        if "Character Information" in header.text:
            for row in rows:
                cols_raw = row.find_all('td')
                cols = [ele.text.strip() for ele in cols_raw]
                if len(cols) != 2:
                    continue
                field, value = cols
                field = field.replace("\xa0", "_").replace(" ","_").replace(":","").lower()
                value = value.replace("\xa0", " ")
                # This is a special case cause we need to see the link
                if field == "house":
                    house = cols_raw[1].find('a')
                    url = urllib.parse.urlparse(house["href"])
                    query = urllib.parse.parse_qs(url.query)
                    char["house_town"] = query["town"][0]
                    char["house_id"] = query["houseid"][0]
                    char["house"] = house.text.strip()
                    continue
                char[field] = value
        elif "Achievements" in header.text:
            char["displayed_achievements"] = []
            for row in rows:
                cols_raw = row.find_all('td')
                cols = [ele.text.strip() for ele in cols_raw]
                if len(cols) != 2:
                    continue
                field, value = cols
                char["displayed_achievements"].append(value)
        elif "Deaths" in header.text:
            char["deaths"] = []
            for row in rows:
                cols_raw = row.find_all('td')
                cols = [ele.text.strip() for ele in cols_raw]
                if len(cols) != 2:
                    continue
                death_time, death = cols
                death_time = death_time.replace("\xa0", " ")
                regex_death = r'Level (\d+) by ([^.]+)'
                pattern = re.compile(regex_death)
                death_info = re.search(pattern, death)
                if death_info:
                    level = death_info.group(1)
                    killer = death_info.group(2)
                else:
                    continue
                death_link = cols_raw[1].find('a')
                death_player = False
                if death_link:
                    death_player = True
                    killer = death_link.text.strip().replace("\xa0", " ")
                try:
                    char["deaths"].append({'time': death_time, 'level': int(level), 'killer': killer,
                                           'by_player': death_player})
                except ValueError:
                    # Some pvp deaths have no level, so they are raising a ValueError, they will be ignored for now.
                    continue
        elif "Account Information" in header.text:
            for row in rows:
                cols_raw = row.find_all('td')
                cols = [ele.text.strip() for ele in cols_raw]
                if len(cols) != 2:
                    continue
                field, value = cols
                field = field.replace("\xa0", "_").replace(" ", "_").replace(":", "").lower()
                value = value.replace("\xa0", " ")
                char[field] = value
        elif "Characters" in header.text:
            char["chars"] = []
            for row in rows:
                cols_raw = row.find_all('td')
                cols = [ele.text.strip() for ele in cols_raw]
                if len(cols) != 5:
                    continue
                _name, world, status, __, __ = cols
                _name = _name.replace("\xa0", " ").split(". ")[1]
                char['chars'].append({'name': _name, 'world': world, 'status': status})

    # Formatting special fields:
    try:
        if "," in char["name"]:
            char["name"], _ = char["name"].split(",", 1)
            char["deleted"] = True
        char["premium"] = ("Premium" in char["account_status"])
        char.pop("account_status")
        if "former_names" in char:
            char["former_names"] = char["former_names"].split(", ")
        char["level"] = int(char["level"])
        char["achievement_points"] = int(char["achievement_points"])
        char["guild"] = None
        if "guild_membership" in char:
            char["rank"], char["guild"] = char["guild_membership"].split(" of the ")
            char.pop("guild_membership")
        if "never" in char["last_login"]:
            char["last_login"] = None
    except KeyError:
        await asyncio.sleep(network_retry_delay)
        return await get_character(name, tries - 1)

    # Database operations
    c = userDatabase.cursor()
    # Skills from highscores
    c.execute("SELECT category, rank, value FROM highscores WHERE name LIKE ?", (char["name"],))
    result = c.fetchall()
    for row in result:
        char[row["category"]] = row["value"]
        char[row["category"] + '_rank'] = row["rank"]

    # Discord owner
    c.execute("SELECT user_id, vocation, name, id, world, guild FROM chars WHERE name LIKE ?", (name,))
    result = c.fetchone()
    if result is None:
        # Untracked character
        char["owner_id"] = None
        return char

    char["owner_id"] = result["user_id"]
    if result["vocation"] != char['vocation']:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET vocation = ? WHERE id = ?", (char['vocation'], result["id"],))
            log.info("{0}'s vocation was set to {1} from {2} during get_character()".format(char['name'],
                                                                                            char['vocation'],
                                                                                            result["vocation"]))
    if result["name"] != char["name"]:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET name = ? WHERE id = ?", (char['name'], result["id"],))
            log.info("{0} was renamed to {1} during get_character()".format(result["name"], char['name']))

    if result["world"] != char["world"]:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET world = ? WHERE id = ?", (char['world'], result["id"],))
            log.info("{0}'s world was set to {1} from {2} during get_character()".format(char['name'],
                                                                                         char['world'],
                                                                                         result["world"]))
    if result["guild"] != char["guild"]:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET guild = ? WHERE id = ?", (char['guild'], result["id"],))
            log.info("{0}'s guild was set to {1} from {2} during get_character()".format(char['name'],
                                                                                         char['guild'],
                                                                                         result["guild"]))
    return char


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
        regex_deaths = r'<td>([^<]+)</TD><td><a href="https://secure.tibia.com/community/\?subtopic=characters&name=[^"]+" >([^<]+)</a></td><td>([^<]+)</TD><td>[^<]+</TD><td style="text-align: right;" >([^<]+)</TD></TR>'
        pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
        matches = re.findall(pattern, content)
        score_list = []
        for m in matches:
            score_list.append({'rank': m[0], 'name': m[1], 'vocation': m[2], 'value': m[3].replace(',', '')})
    else:
        regex_deaths = r'<td>([^<]+)</TD><td><a href="https://secure.tibia.com/community/\?subtopic=characters&name=[^"]+" >([^<]+)</a></td><td>([^<]+)</TD><td style="text-align: right;" >([^<]+)</TD></TR>'
        pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
        matches = re.findall(pattern, content)
        score_list = []
        for m in matches:
            score_list.append({'rank': m[0], 'name': m[1], 'vocation': m[2], 'value': m[3].replace(',', '')})
    return score_list

async def get_world(world, tries=5):
    """Returns a list of all the online players in current server.

    Each list element is a dictionary with the following keys: name, level"""
    world = world.capitalize()
    url = 'https://secure.tibia.com/community/?subtopic=worlds&world=' + world

    if tries == 0:
        log.error("get_world_online: Couldn't fetch {0}, network error.".format(world))
        return None

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_world(world, tries - 1)

    # Trimming content to reduce load
    try:
        start_index = content.index('<div class="BoxContent"')
        end_index = content.index('<div id="ThemeboxesColumn" >')
        content = content[start_index:end_index]
    except ValueError:
        await asyncio.sleep(network_retry_delay)
        return await get_world(world, tries - 1)

    if "World with this name doesn't exist!" in content:
        return None

    world = {}
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

    world["online_list"] = list()
    regex_members = r'<a href="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)" >.+?</a></td><td style="width:10%;" >(.+?)</td><td style="width:20%;" >([^<]+)'
    pattern = re.compile(regex_members, re.MULTILINE + re.S)
    m = re.findall(pattern, content)
    # Check if list is empty
    if m:
        # Building dictionary list from online players
        for (name, level,vocation) in m:
            name = urllib.parse.unquote_plus(name)
            vocation = vocation.replace('&#160;', ' ')
            world["online_list"].append({'name': name, 'level': int(level), 'vocation': vocation})
    return world


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
                      "ORDER BY value DESC", (item["name"],))
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
                      "ORDER BY value ASC", (item["name"],))
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
                      "WHERE Quests.id = QuestRewards.questid AND itemid = ?", (item["id"],))
            quests = c.fetchall()
            item["quests"] = list()
            for quest in quests:
                item["quests"].append(quest["title"])
            # Get item's properties:
            c.execute("SELECT * FROM ItemProperties WHERE itemid = ?", (item["id"],))
            results = c.fetchall()
            item["properties"] = {}
            for row in results:
                if row["property"] == "Imbuement":
                    temp = item["properties"].get("imbuements", list())
                    temp.append(row["value"])
                    item["properties"]["imbuements"] = temp
                else:
                    item["properties"][row["property"]] = row["value"]
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
            m = re.search(r'<BR>(.+)<BR><BR>(.+)', content)
            if not m:
                return house
            house["fetch"] = True
            house_info = m.group(1)
            house_status = m.group(2)
            m = re.search(r'monthly rent is <B>(\d+)', house_info)
            if m:
                house["rent"] = int(m.group(1))
            if "rented" in house_status:
                house["status"] = "rented"
                m = re.search(r'rented by <A?.+name=([^\"]+).+(He|She) has paid the rent until <B>([^<]+)</B>',
                              house_status)
                if m:
                    house["owner"] = urllib.parse.unquote_plus(m.group(1))
                    house["owner_pronoun"] = m.group(2)
                    house["until"] = m.group(3).replace("&#160;", " ")
                if "move out" in house_status:
                    house["status"] = "moving"
                    m = re.search(r'will move out on <B>([^<]+)</B> \(time of daily server save\)', house_status)
                    if m:
                        house["move_date"] = m.group(1).replace("&#160;", " ")
                    else:
                        break
                    m = re.search(r' and (?:will|wants to) pass the house to <A.+name=([^\"]+).+ for <B>(\d+) gold',
                                  house_status)
                    if m:
                        house["status"] = "transfering"
                        house["transferee"] = urllib.parse.unquote_plus(m.group(1))
                        house["transfer_price"] = int(m.group(2))
                        house["accepted"] = ("will pass " in m.group(0))
            elif "auctioned" in house_status:
                house["status"] = "auctioned"
                if ". No bid has" in content:
                    house["status"] = "empty"
                    break
                m = re.search(r'The auction (?:has ended|will end) at <B>([^\<]+)</B>\. '
                              r'The highest bid so far is <B>(\d+).+ by .+name=([^\"]+)\"', house_status)
                if m:
                    house["auction_end"] = m.group(1).replace("&#160;", " ")
                    house["top_bid"] = int(m.group(2))
                    house["top_bidder"] = urllib.parse.unquote_plus(m.group(3))
                    break
                pass
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


def get_pronouns(gender: str) -> List[str]:
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


async def populate_worlds():
    """Populate the list of currently available Tibia worlds"""

    print('Searching list of available Tibia worlds.')
    all_worlds = await load_tibia_worlds_from_url()
    if all_worlds is None:
        all_worlds = load_tibia_worlds_from_file()

    if all_worlds is not None:
        try:
            if len(all_worlds) > 0:
                for world in all_worlds:
                    tibia_worlds.append(world["name"])

            print("Finished fetching list of Tibia worlds.")
        except Exception:
            log.error("Error populate_worlds(): Unexpected JSON format")


async def load_tibia_worlds_from_url(tries=3):
    """Fetch the list of Tibia worlds from TibiaData"""

    if tries == 0:
        log.error("populate_worlds(): Couldn't fetch TibiaData for the worlds list, network error.")
        return

    try:
        url = "https://api.tibiadata.com/v1/worlds.json"
    except UnicodeEncodeError:
        return

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        print('Error fetching URL.')
        return await load_tibia_worlds_from_url(tries - 1)

    all_worlds = json.loads(content)["worlds"]["allworlds"]
    write_tibia_worlds_json_backup(all_worlds)
    return all_worlds


def write_tibia_worlds_json_backup(all_worlds):
    """Receives JSON content and writes to a backup file."""

    try:
        with open("utils/tibia_worlds.json", "w+") as json_file:
            json.dump(all_worlds, json_file)
    except Exception:
        print("Error populate_worlds(): could not save JSON to file.")


def load_tibia_worlds_from_file():
    """Loading Tibia worlds list from an existing .json backup file."""

    try:
        with open("utils/tibia_worlds.json") as json_file:
            all_worlds = json.load(json_file)
            return all_worlds
    except Exception:
        log.error("Error loading backup .json file.")