import asyncio
import datetime as dt
import io
import json
import re
import time
import urllib.parse
from calendar import timegm
from contextlib import closing
from html.parser import HTMLParser
from typing import List, Union, Dict, Optional

import aiohttp
from PIL import Image
from PIL import ImageDraw
from bs4 import BeautifulSoup
from discord import Colour

from config import network_retry_delay
from utils.database import userDatabase, tibiaDatabase
from utils.messages import EMOJI
from .general import log, get_local_timezone

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

KNIGHT = ["knight", "elite knight", "ek", "k", "kina", "eliteknight", "elite"]
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


class NetworkError(Exception):
    pass


# TODO: Generate character from tibia.com response
class Character:
    SEX_MALE = 0
    SEX_FEMALE = 1

    FREE_ACCOUNT = 0
    PREMIUM_ACCOUNT = 1

    URL_CHAR = "https://secure.tibia.com/community/?subtopic=characters&name="

    def __init__(self, name: str, world: str, *, online: bool=False, level: int =0, vocation: str=None):
        self.name = name
        self.level = level
        self.world = world
        self.achievement_points = 0
        self.sex = 0
        self.former_world = None
        self.residence = None
        self.vocation = vocation
        self.married_to = None
        self.guild = None
        self.house = None
        self.last_login = None  # type: dt.datetime
        self.deleted = None  # type: dt.datetime
        self.online = online
        self.achievements = []
        self.deaths = []  # type: List[Death]
        self.other_characters = []
        self.account_status = 0

        # NabBot specific attributes:
        self.highscores = []
        self.owner = 0

    @property
    def he_she(self):
        return ["He", "She"][self.sex]

    @property
    def his_her(self):
        return ["His", "Her"][self.sex]

    @property
    def him_her(self):
        return ["Him", "Her"][self.sex]

    @property
    def url(self):
        return self.get_url(self.name)

    @property
    def guild_name(self):
        return None if self.guild is None else self.guild["name"]

    @property
    def guild_rank(self):
        return None if self.guild is None else self.guild["rank"]

    @classmethod
    def get_url(cls, name: str) -> str:
        """Returns the url pointing to the character's tibia.com page

        :param name: Name of the character
        :return: url of the character's information
        """
        return cls.URL_CHAR + urllib.parse.quote(name.encode('iso-8859-1'))

    @classmethod
    def parse_from_tibiadata(cls, content_json: Dict):
        """Parses the response from TibiaData and returns a Character

        :param content_json: The json object returned by TibiaData
        :return: a Character object or None if the character doesn't exist.
        """
        char = content_json["characters"]
        if "error" in char:
            return None
        data = char["data"]
        character = Character(data["name"],
                              data["world"],
                              level = int(data["level"]))
        character.achievement_points = int(data["achievement_points"])
        character.sex = cls.SEX_MALE if data["sex"] == "male" else cls.SEX_FEMALE
        character.vocation = data["vocation"]
        character.residence = data["residence"]
        if "deleted" in data:
            character.deleted = parse_tibiadata_time(data["deleted"])
        if "married_to" in data:
            character.married_to = data["married_to"]
        if "former_world" in data:
            character.former_world = data["former_world"]
        if "guild" in data:
            character.guild = data["guild"]
        if "house" in data:
            match = re.search(r'(?P<name>.*) \((?P<town>[^\)]+)\)$', data["house"])
            if match:
                character.house = match.groupdict()
        character.account_status = cls.PREMIUM_ACCOUNT if data["account_status"] == "Premium Account" else cls.FREE_ACCOUNT
        if len(data["last_login"]) > 0:
            character.last_login = parse_tibiadata_time(data["last_login"][0])

        for achievement in char["achievements"]:
            character.achievements.append(Achievement(achievement["name"], int(achievement["stars"])))

        for death in char["deaths"]:
            try:
                match = re.search("by ([^.]+)", death["reason"])
                killer = match.group(1)
                level = int(death["level"])
                death_time = parse_tibiadata_time(death["date"])
                by_player = False
                if death["involved"]:
                    by_player = True
                    killer = death["involved"][0]["name"]
                character.deaths.append(Death(level, killer, death_time, by_player))
            except ValueError:
                # TODO: Handle deaths with no level
                continue

        for other_character in char["other_characters"]:
            online = other_character["status"] == "online"
            character.other_characters.append(Character(other_character["name"],
                                                        other_character["world"],
                                                        online=online))

        return character


class Achievement:
    def __init__(self, name: str, grade: int):
        self.name = name
        self.grade = grade


# TODO: Handle deaths by multiple killers
class Death:
    def __init__(self, level: int, killer: str, time: dt.datetime, by_player: bool):
        self.level = level
        self.killer = killer
        self.time = time
        self.by_player = by_player

class World:
    def __init__(self, name, **kwargs):
        self.name = name
        self.online = kwargs.get("online", 0)
        self.record_online = kwargs.get("record_online", 0)
        self.record_date = None  # type: dt.datetime
        self.creation = None
        self.pvp_type = kwargs.get("pvp_type")
        self.premium_type = kwargs.get("premium_type")
        self.transfer_type = kwargs.get("transfer_type")
        self.location = kwargs.get("location")
        self.players_online = []  # type: List[Character]
        self.quests = None  # type: List[str]

    @classmethod
    def parse_from_tibiadata(cls, name: str, content_json: Dict):
        _world = content_json["worlds"]
        if "error" in _world:
            return None
        world_info = _world["world_information"]
        world = World(name.capitalize())
        world.online = int(world_info["players_online"])
        if "online_record" in world_info:
            world.record_online = int(world_info["online_record"]["players"])
            world.record_date = parse_tibiadata_time(world_info["online_record"]["date"])
        world.creation = world_info["creation_date"]
        world.location = world_info["location"]
        world.pvp_type = world_info["pvp_type"]
        world.premium_type = world_info.get("premium_type")
        world.transfer_type = world_info.get("transfer_type")
        # TODO: Parse battleye status
        if "world_quest_titles" in world_info:
            world.quests = world_info["world_quest_titles"]

        for player in _world.get("players_online", []):
            world.players_online.append(Character(player["name"], world.name, level=int(player["level"]),
                                                  vocation=player["vocation"], online=True))
        return world


async def get_character(name, tries=5) -> Optional[Character]:
    """Fetches a character from TibiaData, parses and returns a Character object

    The character object contains all the information available on Tibia.com
    Infomration from the user's database is also added, like owner and highscores.
    If the character can't be fetch due to a network error, an NetworkError exception is raised
    If the character doens't exist, None is returned.
    """
    if tries == 0:
        log.error("get_character: Couldn't fetch {0}, network error.".format(name))
        raise NetworkError()
    url = f"https://api.tibiadata.com/v1/characters/{name}.json"
    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_character(name, tries - 1)

    content_json = json.loads(content)
    character = Character.parse_from_tibiadata(content_json)
    if character is None:
        return None
    if character.house is not None:
        with closing(tibiaDatabase.cursor()) as c:
            c.execute("SELECT id FROM houses WHERE name LIKE ?", (character.house["name"],))
            result = c.fetchone()
            if result:
                character.house["id"] = result["id"]

    # Database operations
    c = userDatabase.cursor()
    # Skills from highscores
    c.execute("SELECT category, rank, value FROM highscores WHERE name LIKE ?", (character.name,))
    results = c.fetchall()
    if len(results) > 0:
        character.highscores = results

    # Discord owner
    c.execute("SELECT user_id, vocation, name, id, world, guild FROM chars WHERE name LIKE ?", (name,))
    result = c.fetchone()
    if result is None:
        # Untracked character
        return character

    character.owner = result["user_id"]
    if result["vocation"] != character.vocation:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET vocation = ? WHERE id = ?", (character.vocation, result["id"],))
            log.info("{0}'s vocation was set to {1} from {2} during get_character()".format(character.name,
                                                                                            character.vocation,
                                                                                            result["vocation"]))
    if result["name"] != character.name:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET name = ? WHERE id = ?", (character.name, result["id"],))
            log.info("{0} was renamed to {1} during get_character()".format(result["name"], character.name))

    if result["world"] != character.world:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET world = ? WHERE id = ?", (character.world, result["id"],))
            log.info("{0}'s world was set to {1} from {2} during get_character()".format(character.name,
                                                                                         character.world,
                                                                                         result["world"]))
    if character.guild is not None and result["guild"] != character.guild["name"]:
        with userDatabase as conn:
            conn.execute("UPDATE chars SET guild = ? WHERE id = ?", (character.guild["name"], result["id"],))
            log.info("{0}'s guild was set to {1} from {2} during get_character()".format(character.name,
                                                                                         character.guild["name"],
                                                                                         result["guild"]))
    return character


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


async def get_world(name, tries=5) -> Optional[World]:
    url = f"https://api.tibiadata.com/v1/worlds/{name}.json"
    if tries == 0:
        log.error("get_world_online: Couldn't fetch {0}, network error.".format(name))
        raise NetworkError()
        # Fetch website

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_world(name, tries - 1)

    content_json = json.loads(content)
    world = World.parse_from_tibiadata(name, content_json)
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
    tibia_time = dt.datetime.now() + dt.timedelta(hours=offset - 10)
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
    c.execute("SELECT * FROM creatures WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
    result = c.fetchall()
    if len(result) == 0:
        return None
    elif result[0]["title"].lower() == name.lower() or len(result) == 1:
        monster = result[0]
    else:
        return [x['title'] for x in result]
    try:
        if monster['hitpoints'] is None or monster['hitpoints'] < 1:
            monster['hitpoints'] = None
        c.execute("SELECT items.title as item, chance, min, max "
                  "FROM creatures_drops, items "
                  "WHERE items.id = creatures_drops.item_id AND creature_id = ? "
                  "ORDER BY chance DESC",
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
    c.execute("SELECT * FROM items WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
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
            c.execute("SELECT npcs.title, city, npcs_buying.value "
                      "FROM items, npcs_buying, npcs "
                      "WHERE items.name LIKE ? AND npcs_buying.item_id = items.id AND npcs.id = npc_id "
                      "ORDER BY npcs_buying.value DESC", (item["name"],))
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
            c.execute("SELECT npcs.title, city, npcs_selling.value "
                      "FROM items, npcs_selling, NPCs "
                      "WHERE items.name LIKE ? AND npcs_selling.item_id = items.id AND npcs.id = npc_id "
                      "ORDER BY npcs_selling.value ASC", (item["name"],))
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
                    tibia_time = dt.datetime.now() + dt.timedelta(hours=offset - 10)
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
            c.execute("SELECT creatures.title as name, creatures_drops.chance as percentage "
                      "FROM creatures_drops, creatures "
                      "WHERE creatures_drops.creature_id = creatures.id AND creatures_drops.item_id = ? "
                      "ORDER BY percentage DESC", (item["id"],))
            item["dropped_by"] = c.fetchall()
            # Checking quest rewards:
            c.execute("SELECT quests.name FROM quests, quests_rewards "
                      "WHERE quests.id = quests_rewards.quest_id AND item_id = ?", (item["id"],))
            quests = c.fetchall()
            item["quests"] = list()
            for quest in quests:
                item["quests"].append(quest["name"])
            # Get item's properties:
            c.execute("SELECT * FROM items_attributes WHERE item_id = ?", (item["id"],))
            results = c.fetchall()
            item["attributes"] = {}
            for row in results:
                if row["attribute"] == "imbuement":
                    temp = item["attributes"].get("imbuements", list())
                    temp.append(row["value"])
                    item["attributes"]["imbuements"] = temp
                else:
                    item["attributes"][row["attribute"]] = row["value"]
            return item
    finally:
        c.close()
    return


def parse_tibia_time(tibia_time: str) -> Optional[dt.datetime]:
    """Gets a time object from a time string from tibia.com"""
    tibia_time = tibia_time.replace(",", "").replace("&#160;", " ")
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
        t = dt.datetime.strptime(tibia_time[:-4].strip(), "%b %d %Y %H:%M:%S")
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
    return t + dt.timedelta(hours=(local_utc_offset - utc_offset))


def parse_tibiadata_time(time_dict: Dict[str, Union[int, str]]) -> Optional[dt.datetime]:
    """Parses the time objects from TibiaData API

    Time objects are made of a dictionary with three keys:
        date: contains a string representation of the time
        timezone: a string representation of the timezone the date time is based on
        timezone_type: the type of representation used in the timezone key

    :param time_dict: dictionary representing the time object.
    :return: A UTC datetime object (timezone-aware) or None if a parsing error occurred
    """
    try:
        t = dt.datetime.strptime(time_dict["date"], "%Y-%m-%d %H:%M:%S.%f")
    except (KeyError, ValueError):
        return None

    if time_dict["timezone"] == "CET":
        timezone_offset = 1
    elif time_dict["timezone"] == "CEST":
        timezone_offset = 2
    else:
        return None
    # We substract the offset to convert the time to UTC
    t = t - dt.timedelta(hours=timezone_offset)
    return t.replace(tzinfo=dt.timezone.utc)


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

    exp = (50 * pow(level, 3) / 3) - 100 * pow(level, 2) + (850 * level / 3) - 200
    exp_tnl = 50 * level * level - 150 * level + 200

    return {"vocation": vocation, "hp": hp, "mp": mp, "cap": cap, "exp": int(exp), "exp_tnl": exp_tnl}


def get_share_range(level: int):
    """Returns the share range for a specific level

    The returned value is a list with the lower limit and the upper limit in that order."""
    return int(round(level * 2 / 3, 0)), int(round(level * 3 / 2, 0))


def get_spell(name):
    """Returns a dictionary containing a spell's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        c.execute("""SELECT * FROM spells WHERE words LIKE ? OR name LIKE ? ORDER BY LENGTH(name) LIMIT 15""",
                  ("%" + name + "%", "%" + name + "%"))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["name"].lower() == name.lower() or result[0]["words"].lower() == name.lower() or len(
                result) == 1:
            spell = result[0]
        else:
            return ["{name} ({words})".format(**x) for x in result]

        spell["npcs"] = []
        c.execute("""SELECT npcs.title as name, npcs.city, npcs_spells.knight, npcs_spells.paladin,
                  npcs_spells.sorcerer, npcs_spells.druid FROM npcs, npcs_spells
                  WHERE npcs_spells.spell_id = ? AND npcs_spells.npc_id = npcs.id""", (spell["id"],))
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
                name = link.split("/")[-1].replace("-", " ").lower()
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


async def get_house(name, world=None):
    """Returns a dictionary containing a house's info, a list of possible matches or None.

    If world is specified, it will also find the current status of the house in that world."""
    c = tibiaDatabase.cursor()
    try:
        # Search query
        c.execute("SELECT * FROM houses WHERE name LIKE ? ORDER BY LENGTH(name) ASC LIMIT 15", ("%" + name + "%",))
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
        c.execute("SELECT * FROM achievements WHERE name LIKE ? ORDER BY LENGTH(name) ASC LIMIT 15",
                  ("%" + name + "%",))
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
    gt = dt.datetime.utcnow() + dt.timedelta(hours=1)
    germany_date = dt.date(gt.year, gt.month, gt.day)
    dst_start = dt.date(gt.year, 3, (31 - (int(((5 * gt.year) / 4) + 4) % int(7))))
    dst_end = dt.date(gt.year, 10, (31 - (int(((5 * gt.year) / 4) + 1) % int(7))))
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
    emoji = {'none': EMOJI[":hatching_chick:"], 'druid': EMOJI[":snowflake:"], 'sorcerer': EMOJI[":flame:"],
             'paladin': EMOJI[":archery:"],
             'knight': EMOJI[":shield:"], 'elder druid': EMOJI[":snowflake:"],
             'master sorcerer': EMOJI[":flame:"], 'royal paladin': EMOJI[":archery:"],
             'elite knight': EMOJI[":shield:"]}
    try:
        return emoji[vocation.lower()]
    except KeyError:
        return EMOJI[":question:"]


def get_map_area(x, y, z, size=15, scale=8, crosshair=True, client_coordinates=True):
    """Gets a minimap picture of a map area

    size refers to the radius of the image in actual tibia sqm
    scale is how much the image will be streched (1 = 1 sqm = 1 pixel)
    client_coordinates means the coordinate origin used is the same used for the Tibia Client
        If set to False, the origin will be based on the top left corner of the map.
    """
    if client_coordinates:
        x -= 124 * 256
        y -= 121 * 256
    c = tibiaDatabase.cursor()
    c.execute("SELECT * FROM map WHERE z LIKE ?", (z,))
    result = c.fetchone()
    im = Image.open(io.BytesIO(bytearray(result['image'])))
    im = im.crop((x - size, y - size, x + size, y + size))
    im = im.resize((size * scale, size * scale))
    if crosshair:
        draw = ImageDraw.Draw(im)
        width, height = im.size
        draw.line((0, height / 2, width, height / 2), fill=128)
        draw.line((width / 2, 0, width / 2, height), fill=128)

    img_byte_arr = io.BytesIO()
    im.save(img_byte_arr, format='png')
    img_byte_arr = img_byte_arr.getvalue()
    return img_byte_arr


async def populate_worlds():
    """Populate the list of currently available Tibia worlds"""

    print('Fetching list of Tibia worlds...')
    worlds = await get_world_list()
    # Couldn't fetch world list, getting json backup
    if worlds is None:
        world_list = load_tibia_worlds_file()
    else:
        # Convert list of World objects to simple list of world names.
        world_list = [w.name for w in worlds]
        save_tibia_worlds_file(world_list)
    tibia_worlds.extend(world_list)
    print("\tDone")


async def get_world_list(tries=3) -> Optional[List[World]]:
    """Fetch the list of Tibia worlds from TibiaData"""
    if tries == 0:
        log.error("get_world_list(): Couldn't fetch TibiaData for the worlds list, network error.")
        return

    url = "https://api.tibiadata.com/v1/worlds.json"

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_world_list(tries - 1)

    try:
        json_content = json.loads(content)
    except ValueError:
        return

    worlds = []
    try:
        for world in json_content["worlds"]["allworlds"]:
            worlds.append(World(name=world["name"], online=int(world["online"]), location=world["location"]))
    except KeyError:
        return
    return worlds


def save_tibia_worlds_file(world_list: List[str]):
    """Receives JSON content and writes to a backup file."""

    try:
        with open("data/tibia_worlds.json", "w+") as json_file:
            json.dump(world_list, json_file)
    except Exception:
        log.error("save_tibia_worlds_file(): Could not save JSON to file.")


def load_tibia_worlds_file():
    """Loading Tibia worlds list from an existing .json backup file."""

    try:
        with open("data/tibia_worlds.json") as json_file:
            return json.load(json_file)
    except Exception:
        log.error("load_tibia_worlds_file(): Error loading backup .json file.")
