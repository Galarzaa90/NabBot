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

from config import network_retry_delay
from utils.database import userDatabase, tibiaDatabase
from utils.messages import EMOJI
from .general import log

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

HIGHSCORE_CATEGORIES = ["sword", "axe", "club", "distance", "shielding", "fist", "fishing", "magic",
                         "magic_ek", "magic_rp", "loyalty", "achievements"]


class NetworkError(Exception):
    pass


# TODO: Generate character from tibia.com response
class Character:
    SEX_MALE = 0
    SEX_FEMALE = 1

    FREE_ACCOUNT = 0
    PREMIUM_ACCOUNT = 1

    URL_CHAR = "https://secure.tibia.com/community/?subtopic=characters&name="

    def __init__(self, name: str, world: str, **kwargs):
        self.name = name
        self.world = world
        self.level = kwargs.get("level", 0)
        self.achievement_points = kwargs.get("achievement_points", 0)
        self.sex = kwargs.get("sex", 0)
        self.former_world = kwargs.get("former_world")
        self.residence = kwargs.get("residence")
        self.vocation = kwargs.get("vocation")
        self.married_to = kwargs.get("married_to")
        self.guild = kwargs.get("guild")
        self.house = kwargs.get("house")
        self.last_login = kwargs.get("last_login")  # type: dt.datetime
        self.deleted = kwargs.get("last_login")  # type: dt.datetime
        self.online = kwargs.get("online") # type: bool
        self.achievements = kwargs.get("achivements", []) # type: List[Achievement]
        self.deaths = kwargs.get("deaths", [])  # type: List[Death]
        self.other_characters = kwargs.get("other_characters", [])
        self.account_status = kwargs.get("account_status", 0)

        # NabBot specific attributes:
        self.highscores = []
        self.owner = 0

    def __repr__(self) -> str:
        kwargs = vars(self)
        attributes = ""
        for k, v in kwargs.items():
            if k in ["name", "world"]:
                continue
            if v is None:
                continue
            if isinstance(v, int) and v == 0:
                continue
            if isinstance(v, list) and len(v) == 0:
                continue
            attributes += f", {k} = {v.__repr__()}"
        return f"Character({self.name!r}, {self.world!r}{attributes})"

    def __eq__(self, o: object) -> bool:
        """Overrides the default implementation"""
        if isinstance(o, self.__class__):
            return self.name.lower() == o.name.lower()
        return False

    @property
    def he_she(self) -> str:
        return ["He", "She"][self.sex]

    @property
    def his_her(self) -> str:
        return ["His", "Her"][self.sex]

    @property
    def him_her(self) -> str:
        return ["Him", "Her"][self.sex]

    @property
    def url(self) -> str:
        return self.get_url(self.name)

    @property
    def guild_name(self) -> Optional[str]:
        return None if self.guild is None else self.guild["name"]

    @property
    def guild_rank(self) -> Optional[str]:
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
        character = Character(data["name"], data["world"])
        character.level = int(data["level"])
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
                level = int(death["level"])
                death_time = parse_tibiadata_time(death["date"])
                by_player = False

                match = re.search("by ([^.]+)", death["reason"])
                killed_by = match.group(1).strip()  # Complete list of killers
                killers = [k.strip() for k in killed_by.replace(" and ", " ,").split(",")]
                participants = []
                if death["involved"]:
                    involved = [x["name"] for x in death["involved"]]
                    killer = killers[0]
                    # If killer is player, and there's another player in killers, assume it was the other player
                    if killer == character.name:
                        next_player = next((p for p in killers if p in involved and p != character.name), None)
                        if next_player is not None:
                            killer = next_player
                    by_player = True
                    for i, name in enumerate(killers):
                        # If the name is not in involved list, it's a creature
                        if name not in involved:
                            # If the only other killer is the player itself, only count the creature
                            if len(involved) == 1 and involved[0] == character.name:
                                killer = name
                                by_player = False
                                break
                        elif name != character.name and i != 0 and killer != name:
                            participants.append(name)

                else:
                    killer = killers[0]
                character.deaths.append(Death(level, killer, death_time, by_player, participants))
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

    def __repr__(self) -> str:
        return f"Achievement({self.name!r},{self.grade})"


# TODO: Handle deaths by multiple killers
class Death:
    def __init__(self, level: int, killer: str, time: dt.datetime, by_player: bool, participants=None):
        if participants is None:
            participants = []
        self.level = level
        self.killer = killer
        self.time = time
        self.by_player = by_player
        self.participants = participants

    def __repr__(self) -> str:
        return f"Death({self.level},{self.killer!r},{self.time!r},{self.by_player},{self.participants!r})"


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
        world.online = int(world_info.get("players_online", 0))
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


class Guild:
    def __init__(self, name, world, **kwargs):
        self.name = name
        self.world = world
        self.application = kwargs.get("application", False)
        self.description = kwargs.get("description")
        self.founded = kwargs.get("founded")
        self.logo = kwargs.get("logo")
        self.homepage = kwargs.get("homepage")
        self.guildhall = kwargs.get("guildhall")
        self.members = kwargs.get("members", [])
        self.invited = kwargs.get("invited", [])

    @property
    def url(self) -> str:
        return self.get_url(self.name)

    @property
    def online(self) -> List:
        return [m for m in self.members if m["status"] == "online"]

    @classmethod
    def get_url(cls, name: str) -> str:
        """Returns the url pointing to the character's tibia.com page

        :param name: Name of the character
        :return: url of the character's information
        """
        return url_guild + urllib.parse.quote(name.encode('iso-8859-1'))

    @classmethod
    def parse_from_tibiadata(cls, content_json: Dict):
        guild = content_json["guild"]
        if "error" in guild:
            return None
        data = guild["data"]
        tibia_guild = Guild(data["name"], data["world"])
        tibia_guild.application = data["application"]
        tibia_guild.description = data["description"]
        tibia_guild.founded = data["founded"]
        tibia_guild.logo = data["guildlogo"]
        tibia_guild.members = []
        for rank in guild["members"]:
            rank_name = rank["rank_title"]
            for member in rank["characters"]:
                member["rank"] = rank_name
                tibia_guild.members.append(member)
        tibia_guild.invited = guild["invited"]
        if "homepage" in data:
            tibia_guild.homepage = data["homepage"]
        if type(data["guildhall"]) is dict:
            tibia_guild.guildhall = data["guildhall"]
        else:
            tibia_guild.guildhall = None

        return tibia_guild


async def get_character(name, tries=5) -> Optional[Character]:
    """Fetches a character from TibiaData, parses and returns a Character object

    The character object contains all the information available on Tibia.com
    Information from the user's database is also added, like owner and highscores.
    If the character can't be fetch due to a network error, an NetworkError exception is raised
    If the character doesn 't exist, None is returned.
    """
    if tries == 0:
        log.error("get_character: Couldn't fetch {0}, network error.".format(name))
        raise NetworkError()
    try:
        url = f"https://api.tibiadata.com/v1/characters/{urllib.parse.quote(name, safe='')}.json"
    except UnicodeEncodeError:
        return None
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
            c.execute("SELECT id FROM houses WHERE name LIKE ?", (character.house["name"].strip(),))
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
        log.error("get_world: Couldn't fetch {0}, network error.".format(name))
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


async def get_guild(name, title_case=True, tries=5) -> Optional[Guild]:
    """Fetches a guild from TibiaData, parses and returns a Guild object

    The Guild object contains all the information available on Tibia.com
    Guilds are case sensitive on tibia.com so guildstats.eu is checked for correct case.
    If the guild can't be fetched due to a network error, an NetworkError exception is raised
    If the character doesn't exist, None is returned."""
    guildstats_url = f"http://guildstats.eu/guild?guild={urllib.parse.quote(name)}"

    if tries == 0:
        log.error("get_guild_online: Couldn't fetch {0}, network error.".format(name))
        raise NetworkError()

    # Fix casing using guildstats.eu if needed
    # Sorry guildstats.eu :D
    if not title_case:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(guildstats_url) as resp:
                    content = await resp.text(encoding='ISO-8859-1')
        except Exception:
            await asyncio.sleep(network_retry_delay)
            return await get_guild(name, title_case, tries - 1)

        # Make sure we got a healthy fetch
        try:
            content.index('<div class="footer">')
        except ValueError:
            await asyncio.sleep(network_retry_delay)
            return await get_guild(name, title_case, tries - 1)

        # Check if the guild doesn't exist
        if "<div>Sorry!" in content:
            return None

        # Failsafe in case guildstats.eu changes their websites format
        try:
            content.index("General info")
            content.index("Recruitment")
        except Exception:
            log.error("get_guild_online: -IMPORTANT- guildstats.eu seems to have changed their websites format.")
            raise NetworkError

        start_index = content.index("General info")
        end_index = content.index("Recruitment")
        content = content[start_index:end_index]
        m = re.search(r'<a href="set=(.+?)"', content)
        if m:
            name = urllib.parse.unquote_plus(m.group(1))
    else:
        name = name.title()

    tibiadata_url = f"https://api.tibiadata.com/v2/guild/{urllib.parse.quote(name)}.json"

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(tibiadata_url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_guild(name, title_case, tries - 1)

    content_json = json.loads(content)
    guild = Guild.parse_from_tibiadata(content_json)
    if guild is None:
        if title_case:
            return await get_guild(name, False)
        else:
            return None
    if guild.guildhall is not None:
        with closing(tibiaDatabase.cursor()) as c:
            c.execute("SELECT id FROM houses WHERE name LIKE ?", (guild.guildhall["name"].strip(),))
            result = c.fetchone()
            if result:
                guild.guildhall["id"] = result["id"]
    return guild


async def get_recent_news(tries = 5):
    if tries == 0:
        log.error("get_recent_news: network error.")
        raise NetworkError()
    try:
        url = f"https://api.tibiadata.com/v1/news.json"
    except UnicodeEncodeError:
        return None
    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_recent_news(tries - 1)

    content_json = json.loads(content)
    try:
        news = content_json["news"]
    except KeyError:
        return None
    for article in news:
        article["date"] = parse_tibiadata_time(article["date"]).date()
    return news


async def get_news_article(article_id: int, tries=5) -> Optional[Dict[str, Union[str, dt.date]]]:
    """Returns a news article with the specified id or None if it doesn't exist

    If there's a network error, NetworkError exception is raised"""
    if tries == 0:
        log.error("get_recent_news: network error.")
        raise NetworkError()
    try:
        url = f"https://api.tibiadata.com/v1/news/{article_id}.json"
    except UnicodeEncodeError:
        return None
    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(network_retry_delay)
        return await get_recent_news(tries - 1)

    content_json = json.loads(content)
    try:
        news = content_json["news"]
    except KeyError:
        return None
    if "error" in news:
        return None
    article = news[0]
    article["id"] = article_id
    article["date"] = parse_tibiadata_time(article["date"]).date()
    return article


def get_character_url(name):
    """Gets a character's tibia.com URL"""
    return url_character + urllib.parse.quote(name.encode('iso-8859-1'))


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

    if time_dict["timezone_type"] == 2:
        if time_dict["timezone"] == "CET":
            timezone_offset = 1
        elif time_dict["timezone"] == "CEST":
            timezone_offset = 2
        else:
            return None
    else:
        timezone_offset = 1
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
        sections = soup.find_all('div', class_="execphpwidget")
    except HTMLParser.HTMLParseError:
        print("parse error")
        return
    if sections is None:
        print("section was none")
        return
    bosses = {}
    boss_pattern = re.compile(r'<i style=\"color:\w+;\">(?:<br\s*/>)?\s*([^<]+)\s*</i>\s*<a href=\"([^\"]+)\">'
                              r'<img src=\"([^\"]+)\"\s*/></a>[\n\s]+(Expect in|Last seen)\s:\s(\d+)')
    unpredicted_pattern = re.compile(r'<a href="([^"]+)"><img src="([^"]+)"/></a>[\n\s]+(Expect in|Last seen)\s:\s(\d+)')
    for section in sections:
        m = boss_pattern.findall(str(section))
        if m:
            for (chance, link, image, expect_last, days) in m:
                name = link.split("/")[-1].replace("-", " ").lower()
                bosses[name] = {"chance": chance.strip(), "url": link, "image": image, "type": expect_last,
                                "days": int(days)}
        else:
            # This regex is for bosses without prediction
            m = unpredicted_pattern.findall(str(section))
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
            try:
                world["online"] = int(world["online"])
            except ValueError:
                world["online"] = 0
            worlds.append(World(name=world["name"], online=world["online"], location=world["location"]))
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
