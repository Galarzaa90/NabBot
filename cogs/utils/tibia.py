import asyncio
import datetime as dt
import io
import json
import logging
from collections import defaultdict

import math
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, List, Optional, Union

import aiohttp
import asyncpg
import bs4
import cachetools
import tibiapy
from PIL import Image, ImageDraw
from tibiapy import Category, Character, Guild, Highscores, House, ListedWorld, OnlineCharacter, Sex, Vocation, \
    VocationFilter, World

from cogs.utils.timing import get_local_timezone
from . import config, errors, online_characters
from .database import DbChar, wiki_db

log = logging.getLogger("nabbot")

# Tibia.com URLs:
TIBIA_URL = "https://www.tibia.com/"

TIBIACOM_ICON = "https://ssl-static-tibia.akamaized.net/images/global/general/apple-touch-icon-72x72.png"

# Possible spellings for vocations
KNIGHT = ["knight", "elite knight", "ek", "k", "kina", "eliteknight", "elite",
          Vocation.KNIGHT, Vocation.ELITE_KNIGHT]
PALADIN = ["paladin", "royal paladin", "rp", "p", "pally", "royalpaladin", "royalpally",
           Vocation.PALADIN, Vocation.ROYAL_PALADIN]
DRUID = ["druid", "elder druid", "ed", "d", "elderdruid", "elder",
         Vocation.DRUID, Vocation.ELDER_DRUID]
SORCERER = ["sorcerer", "master sorcerer", "ms", "s", "sorc", "mastersorcerer", "master",
            Vocation.SORCERER, Vocation.MASTER_SORCERER]
MAGE = DRUID + SORCERER + ["mage"]
NO_VOCATION = ["no vocation", "no voc", "novoc", "nv", "n v", "none", "no", "n", "noob", "noobñie", "rook", "rookie",
               Vocation.NONE]

invalid_name = re.compile(r"[^\sA-Za-zÀ-ÖØ-öø-ÿ'\-.]")
"""Regex used to validate names to avoid doing unnecessary fetches"""

boss_pattern = re.compile(r'<i style=\"color:\w+;\">(?:<br\s*/>)?\s*([^<]+)\s*</i>\s*<a href=\"([^\"]+)\">'
                          r'<img src=\"([^\"]+)\"\s*/></a>[\n\s]+(Expect in|Last seen)\s:\s(\d+)')
unpredicted_pattern = re.compile(r'<a href="([^"]+)"><img src="([^"]+)"/></a>[\n\s]+(Expect in|Last seen)\s:\s(\d+)')


HIGHSCORE_CATEGORIES = {"experience": (Category.EXPERIENCE, VocationFilter.ALL),
                        "sword": (Category.SWORD_FIGHTING, VocationFilter.ALL),
                        "axe": (Category.AXE_FIGHTING, VocationFilter.ALL),
                        "club": (Category.CLUB_FIGHTING, VocationFilter.ALL),
                        "distance": (Category.DISTANCE_FIGHTING, VocationFilter.ALL),
                        "shielding": (Category.SHIELDING, VocationFilter.ALL),
                        "fist": (Category.FIST_FIGHTING, VocationFilter.ALL),
                        "fishing": (Category.FISHING, VocationFilter.ALL),
                        "magic": (Category.MAGIC_LEVEL, VocationFilter.ALL),
                        "magic_knights": (Category.MAGIC_LEVEL, VocationFilter.KNIGHTS),
                        "magic_paladins": (Category.MAGIC_LEVEL, VocationFilter.PALADINS),
                        "loyalty": (Category.LOYALTY_POINTS, VocationFilter.ALL),
                        "achievements": (Category.ACHIEVEMENTS, VocationFilter.ALL)}
"""Dictionary with categories tracked by NabBot in its database.

Contains a tuple with the corresponding category and vocation filter,"""

HIGHSCORES_FORMAT = {"achievements": "In __achievement points__, {0} has rank **{2}**, with **{1}**",
                     "axe": "In __axe fighting__, {0} has rank **{2}**, with level **{1}**",
                     "club": "In __club fighting__, {0} has rank **{2}**, with level **{1}**",
                     "experience": "In __experience points__, {0} has rank **{2}**",
                     "distance": "In __distance fighting__, {0} has rank **{2}**, with level **{1}**",
                     "fishing": "In __fishing__, {0} has rank **{2}**, with level **{1}**",
                     "fist": "In __fist fighting__, {0} has rank **{2}**, with level **{1}**",
                     "loyalty": "In __loyalty points__, {0} has rank **{2}**, with **{1}**",
                     "magic": "In __magic level__, {0} has rank **{2}**, with level **{1}**",
                     "magic_knights": "In __magic level__ (knights), {0} has rank **{2}**, with level **{1}**",
                     "magic_paladins": "In __magic level__ (paladins), {0} has rank **{2}**, with level **{1}**",
                     "shielding": "In __shielding__, {0} has rank **{2}**, with level **{1}**",
                     "sword": "In __sword fighting__, {0} has rank **{2}**, with level **{1}**"}
"""Format strings for each tracked category.

Parameters: pronoun, value, rank"""

# Factors per vocation to calculate character stats for a given level, where each tuple corresponds to (a, b, c)
# Formula: (level - a) * b + c
# Inverse formula: (s - c + ab)/b
HP_FACTORS = {
    "knight": (8, 15, 185),
    "paladin": (8, 10, 185),
    "druid": (0, 5, 145),
    "sorcerer": (0, 5, 145),
    "none": (0, 5, 145),
}

MP_FACTORS = {
        "knight": (0, 5, 50),
        "paladin": (8, 15, 90),
        "druid": (8, 30, 90),
        "sorcerer": (8, 30, 90),
        "none": (0, 5, 50),
}

CAP_FACTORS = {
        "knight": (8, 25, 470),
        "paladin": (8, 20, 470),
        "druid": (0, 10, 390),
        "sorcerer": (0, 10, 390),
        "none": (0, 10, 390),
    }

# This is preloaded on startup
tibia_worlds: List[str] = []


# Cache storages, the first parameter is the number of entries, the second the amount of seconds to live of each entry
CACHE_CHARACTERS = cachetools.TTLCache(1000, 30)
CACHE_GUILDS = cachetools.TTLCache(1000, 120)
CACHE_WORLDS = cachetools.TTLCache(100, 50)
CACHE_NEWS = cachetools.TTLCache(100, 1800)
CACHE_WORLD_LIST = cachetools.TTLCache(1, 120)
CACHE_BOSSES = cachetools.TTLCache(100, 3600)


class NabChar(Character):
    """Adds extra attributes to the Character class."""
    __slots__ = ("id", "highscores", "owner_id")

    def __init__(self, name=None, world=None, vocation=None, level=0, sex=None, **kwargs):
        super().__init__(name, world, vocation, level, sex, **kwargs)
        self.id = 0
        self.owner_id = 0
        self.highscores = {}  # type: Dict[Dict[str, int]]

    @classmethod
    def from_online(cls, o_char: OnlineCharacter, sex=None, owner_id=0):
        """Creates a NabChar from an OnlineCharacter"""
        char = cls(o_char.name, o_char.world, o_char.vocation, o_char.level, tibiapy.utils.try_enum(Sex, sex))
        char.owner_id = owner_id
        return char

    @property
    def he_she(self) -> str:
        return "He" if self.sex == Sex.MALE else "She"

    @property
    def his_her(self) -> str:
        return "His" if self.sex == Sex.MALE else "Her"

    @property
    def him_her(self) -> str:
        return "Him" if self.sex == Sex.MALE else "Her"


# region Fetching and parsing

async def get_character(bot, name, *, tries=5) -> Optional[NabChar]:
    """Fetches a character from TibiaData, parses and returns a Character object

    The character object contains all the information available on Tibia.com
    Information from the user's database is also added, like owner and highscores.
    If the character can't be fetch due to a network error, an NetworkError exception is raised
    If the character doesn't exist, None is returned.
    """
    if tries == 0:
        raise errors.NetworkError(f"get_character({name})")
    try:
        url = Character.get_url_tibiadata(name)
    except UnicodeEncodeError:
        return None

    if invalid_name.search(name):
        return None
    # Fetch website
    try:
        character = CACHE_CHARACTERS[name.lower()]
    except KeyError:
        try:
            async with bot.session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                character = NabChar.from_tibiadata(content)
        except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
            await asyncio.sleep(config.network_retry_delay)
            return await get_character(bot, name, tries=tries - 1)
        CACHE_CHARACTERS[name.lower()] = character
    if character is None:
        return None

    if character.house:
        house_id = get_house_id(character.house.name)
        if house_id:
            character.house.id = house_id

    # If the character exists in the online list use data from there where possible
    try:
        for c in online_characters[character.world]:
            if c == character:
                character.level = c.level
                character.vocation = c.vocation
                break
    except KeyError:
        pass

    await bind_database_character(bot, character)
    return character


async def get_guild(name, title_case=True, *, tries=5) -> Optional[Guild]:
    """Fetches a guild from TibiaData, parses and returns a Guild object

    The Guild object contains all the information available on Tibia.com
    Guilds are case sensitive on tibia.com so guildstats.eu is checked for correct case.
    If the guild can't be fetched due to a network error, an NetworkError exception is raised
    If the character doesn't exist, None is returned."""
    if tries == 0:
        raise errors.NetworkError(f"get_guild({name})")

    # Fix casing using guildstats.eu if needed
    # Sorry guildstats.eu :D
    try:
        guild = CACHE_GUILDS[name.lower()]
        return guild
    except KeyError:
        pass

    if not title_case:
        guild_name = await get_guild_name_from_guildstats(name, tries=tries)
        name = guild_name if guild_name else name
    else:
        name = name.title()

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(Guild.get_url_tibiadata(name)) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                guild = Guild.from_tibiadata(content)
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_guild(name, title_case, tries=tries - 1)

    if guild is None:
        if title_case:
            return await get_guild(name, False)
        else:
            return None
    CACHE_GUILDS[name.lower()] = guild
    return guild


async def get_guild_name_from_guildstats(name, title_case=True, tries=5):
    if tries == 0:
        raise errors.NetworkError(f"get_guild_name_from_guildstats({name})")
    guildstats_url = f"http://guildstats.eu/guild?guild={urllib.parse.quote(name)}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(guildstats_url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_guild_name_from_guildstats(name, title_case, tries - 1)

    # Make sure we got a healthy fetch
    try:
        content.index('<div class="footer">')
    except ValueError:
        await asyncio.sleep(config.network_retry_delay)
        return await get_guild_name_from_guildstats(name, title_case, tries - 1)

    # Check if the guild doesn't exist
    if "<div>Sorry!" in content:
        return None

    # Failsafe in case guildstats.eu changes their websites format
    try:
        content.index("General info")
        content.index("Recruitment")
    except ValueError:
        raise errors.NetworkError(f"get_guild_name_from_guildstats({name}): Guildstats.eu format might have changed.")

    start_index = content.index("General info")
    end_index = content.index("Recruitment")
    content = content[start_index:end_index]
    m = re.search(r'<a href="set=(.+?)"', content)
    if m:
        return urllib.parse.unquote_plus(m.group(1))
    raise errors.NetworkError(f"get_guild_name_from_guildstats({name}): Guildstats.eu format might have changed.")


async def get_highscores(world, category=Category.EXPERIENCE, vocation=VocationFilter.ALL, *, tries=5) \
        -> Optional[Highscores]:
    """Gets all the highscores entries of a world, category and vocation."""
    # TODO: Add caching
    if tries == 0:
        raise errors.NetworkError(f"get_highscores({world},{category},{vocation})")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(Highscores.get_url_tibiadata(world, category, vocation)) as resp:
                content = await resp.text()
                highscores = Highscores.from_tibiadata(content, vocation)
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_highscores(world, category, vocation, tries=tries - 1)

    return highscores


def get_house_id(name) -> Optional[int]:
    """Gets the house id of a house with a given name.

    Name is lowercase."""
    try:
        return wiki_db.execute("SELECT house_id FROM house WHERE name LIKE ?", (name,)).fetchone()["house_id"]
    except (AttributeError, KeyError, TypeError):
        log.debug(f"Couldn't find house_id of house '{name}'")
        return None


async def get_house(house_id, world, *, tries=5) -> House:
    """Returns a dictionary containing a house's info, a list of possible matches or None.

    If world is specified, it will also find the current status of the house in that world."""
    if tries == 0:
        raise errors.NetworkError(f"get_house({house_id},{world})")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(House.get_url_tibiadata(house_id, world)) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                house = House.from_tibiadata(content)
    except aiohttp.ClientError:
        await asyncio.sleep(config.network_retry_delay)
        return await get_house(house_id, world, tries=tries - 1)
    return house


async def get_news_article(article_id: int, *, tries=5) -> Optional[Dict[str, Union[str, dt.date]]]:
    """Returns a news article with the specified id or None if it doesn't exist

    If there's a network error, NetworkError exception is raised"""
    if tries == 0:
        raise errors.NetworkError(f"get_news_article({article_id})")
    try:
        url = f"https://api.tibiadata.com/v2/news/{article_id}.json"
    except UnicodeEncodeError:
        return None

    try:
        article = CACHE_NEWS[article_id]
        return article
    except KeyError:
        pass
    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_news_article(tries=tries - 1)

    content_json = json.loads(content)
    try:
        article = content_json["news"]
    except KeyError:
        return None
    if "error" in article:
        return None
    article["id"] = article_id
    article["date"] = parse_tibiadata_time(article["date"]).date()
    CACHE_NEWS[article_id] = article
    return article


async def get_recent_news(*, tries=5):
    if tries == 0:
        raise errors.NetworkError(f"get_recent_news()")

    url = f"https://api.tibiadata.com/v2/latestnews.json"
    # Fetch website
    try:
        news = CACHE_NEWS["recent"]
        return news
    except KeyError:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_recent_news(tries=tries - 1)

    content_json = json.loads(content)
    try:
        newslist = content_json["newslist"]
    except KeyError:
        return None
    for article in newslist["data"]:
        article["date"] = parse_tibiadata_time(article["date"]).date()
        article["news"] = article["news"].replace("\u00a0", " ")
    CACHE_NEWS["recent"] = newslist["data"]
    return newslist["data"]


async def get_recent_news_tickers(*, tries=5):
    if tries == 0:
        raise errors.NetworkError(f"get_recent_newstickers()")
    url = f"https://api.tibiadata.com/v2/newstickers.json"
    # Fetch website
    try:
        news = CACHE_NEWS["recent_tickers"]
        return news
    except KeyError:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_recent_news_tickers(tries=tries - 1)

    content_json = json.loads(content)
    try:
        newslist = content_json["newslist"]
    except KeyError:
        return None
    for article in newslist["data"]:
        article["date"] = parse_tibiadata_time(article["date"]).date()
        article["news"] = article["news"].replace("\u00a0", " ")
    CACHE_NEWS["recent_tickers"] = newslist["data"]
    return newslist["data"]


async def get_world(name, *, tries=5) -> Optional[World]:
    name = name.strip().title()
    if tries == 0:
        raise errors.NetworkError(f"get_world({name})")
    try:
        world = CACHE_WORLDS[name]
        return world
    except KeyError:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(World.get_url_tibiadata(name)) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                world = World.from_tibiadata(content)
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_world(name, tries=tries - 1)
    CACHE_WORLDS[name] = world
    return world


async def fetch_tibia_bosses_world(world: str):
    url = f"https://www.tibiabosses.com/{world}/"

    try:
        bosses = CACHE_BOSSES[world]
        return bosses
    except KeyError:
        bosses = defaultdict(list)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise errors.NetworkError(f"get_world_bosses({world})")

    try:
        parsed_content = bs4.BeautifulSoup(content, "lxml", parse_only=bs4.SoupStrainer("div", class_="panel-layout"))
        _sections = parsed_content.find_all('div', class_="widget_execphp")
        for section in _sections:
            heading = section.find('h3')
            if heading is None:
                continue
            title = heading.text
            section_content = section.find('div', class_="execphpwidget")
            m = boss_pattern.findall(str(section_content))
            if m:
                for (chance, link, image, expect_last, days) in m:
                    name = link.split("/")[-1].replace("-", " ").lower()
                    bosses[title].append(dict(name=name, chance=chance.strip(), url=link, image=image, type=expect_last,
                                              days=int(days)))
            else:
                # This regex is for bosses without prediction
                m = unpredicted_pattern.findall(str(section_content))
                for (link, image, expect_last, days) in m:
                    name = link.split("/")[-1].replace("-", " ").lower()
                    bosses[title].append(dict(name=name, chance="Unpredicted", url=link, image=image, type=expect_last,
                                              days=int(days)))
    except:
        pass
    CACHE_BOSSES[world] = bosses
    return bosses


async def get_world_list(*, tries=3) -> List[ListedWorld]:
    """Fetch the list of Tibia worlds from TibiaData.

    :raises NetworkError: If the world list couldn't be fetched after all the attempts.
    """
    if tries == 0:
        raise errors.NetworkError("get_world_list()")

    # Fetch website
    try:
        worlds = CACHE_WORLD_LIST[0]
        return worlds
    except KeyError:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(ListedWorld.get_list_url_tibiadata()) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                worlds = ListedWorld.list_from_tibiadata(content)
    except (aiohttp.ClientError, asyncio.TimeoutError, tibiapy.TibiapyException):
        await asyncio.sleep(config.network_retry_delay)
        return await get_world_list(tries=tries - 1)

    CACHE_WORLD_LIST[0] = worlds
    return worlds

# endregion


# region Math

def get_capacity(level: int, vocation: str) -> int:
    """Gets the capacity a character of a certain level and vocation has.

    :param level: The character's level.
    :param vocation: The character's vocation.
    :return: Ounces of capacity.
    """
    if level < 8:
        vocation = "none"
    vb = normalize_vocation(vocation)
    return (level - CAP_FACTORS[vb][0]) * CAP_FACTORS[vb][1] + CAP_FACTORS[vb][2]


def get_experience_for_level(level: int) -> int:
    """Gets the total experience needed for a specific level.

    :param level: The desired level.
    :return: The total experience needed for the level."""
    return int(math.ceil((50 * math.pow(level, 3) / 3) - 100 * math.pow(level, 2) + 850 * level / 3 - 200))


def get_experience_for_next_level(level: int) -> int:
    """Gets the amount of experience needed to advance from the specified level to the next one.

    :param level: The current level.
    :return: The experience needed to advance to the next level.
    """
    return 50 * level * level - 150 * level + 200


def get_hitpoints(level: int, vocation: str) -> int:
    """Gets the hitpoints a character of a certain level and vocation has.

    :param level: The character's level.
    :param vocation: The character's vocation.
    :return: Number of hitpoints.
    """
    if level < 8:
        vocation = "none"
    vb = normalize_vocation(vocation)
    return (level - HP_FACTORS[vb][0]) * HP_FACTORS[vb][1] + HP_FACTORS[vb][2]


def get_mana(level: int, vocation: str) -> int:
    """Gets the hitpoints a character of a certain level and vocation has.

    :param level: The character's level.
    :param vocation: The character's vocation.
    :return: Number of hitpoints.
    """
    if level < 8:
        vocation = "none"
    vb = normalize_vocation(vocation)
    return (level - MP_FACTORS[vb][0]) * MP_FACTORS[vb][1] + MP_FACTORS[vb][2]


def get_level_by_experience(experience: int) -> int:
    """Gets the level a character would have with the specified experience.

    :param experience: Current experience points.
    :return: The level a character would have with the specified experience."""
    level = 1
    # TODO: Solve by math
    while True:
        if get_experience_for_level(level+1) > experience:
            return level
        level += 1


def get_level_by_capacity(cap: int, vocation: str):
    """Gets the level required for a character of a specific vocation to get number of capacity.

    :param cap: The desired number of capacity.
    :param vocation: The character's vocation.
    :return: The level where the desired capacity will be achieved.
    """
    vb = normalize_vocation(vocation)
    return int(math.ceil((cap - CAP_FACTORS[vb][2] + (CAP_FACTORS[vb][0] * CAP_FACTORS[vb][1])) / CAP_FACTORS[vb][1]))


def get_level_by_hitpoints(hitpoints: int, vocation: str):
    """Gets the level required for a character of a specific vocation to get number of hitpoints.

    :param hitpoints: The desired number of hitpoints.
    :param vocation: The character's vocation.
    :return: The level where the desired hitpoints will be achieved.
    """
    vb = normalize_vocation(vocation)
    return int(math.ceil((hitpoints - HP_FACTORS[vb][2] + (HP_FACTORS[vb][0] * HP_FACTORS[vb][1]))/HP_FACTORS[vb][1]))


def get_level_by_mana(mana: int, vocation: str):
    """Gets the level required for a character of a specific vocation to get number of mana points.

    :param mana: The desired number of mana points.
    :param vocation: The character's vocation.
    :return: The level where the desired mana will be achieved.
    """
    vb = normalize_vocation(vocation)
    return int(math.ceil((mana - MP_FACTORS[vb][2] + (MP_FACTORS[vb][0] * MP_FACTORS[vb][1]))/MP_FACTORS[vb][1]))


def get_share_range(level: int):
    """Returns the share range for a specific level

    The returned value is a list with the lower limit and the upper limit in that order."""
    return int(round(level * 2 / 3, 0)), int(round(level * 3 / 2, 0))

# endregion


# region Times and Dates

def get_current_server_save_time(current_time: Optional[dt.datetime] = None) -> dt.datetime:
    """Gets the time of the last server save that occurred.

    :param current_time: The time used to get the current server save time of. By default, datetime.now() is used.
    :return: The time of the last server save that occurred according to the provided time.
    """
    if current_time is None:
        current_time = dt.datetime.now(dt.timezone.utc)

    current_ss = current_time.replace(hour=10 - get_tibia_time_zone(), minute=0, second=0, microsecond=0)
    if current_time < current_ss:
        return current_ss - dt.timedelta(days=1)
    return current_ss


def get_rashid_city() -> Dict[str, Union[str, int]]:
    """Returns a dictionary with rashid's info

    Dictionary contains: the name of the week, city and x,y,z, positions."""
    c = wiki_db.cursor()
    c.execute("SELECT * FROM rashid_position WHERE day = ?", (get_tibia_weekday(),))
    info = c.fetchone()
    c.close()
    return info["city"]


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


def get_tibia_weekday() -> int:
    """Returns the current weekday according to the game.

    Since server save is at 10:00 CET, that's when a new day starts according to the game."""
    offset = get_tibia_time_zone() - get_local_timezone()
    # Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = dt.datetime.now() + dt.timedelta(hours=offset - 10)
    return tibia_time.weekday()


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

# endregion


# region Strings

def normalize_vocation(vocation, allow_no_voc=True) -> Optional[str]:
    """Attempts to normalize a vocation string into a base vocation."""
    if isinstance(vocation, str):
        vocation = vocation.lower()
    if vocation in PALADIN:
        return "paladin"
    if vocation in DRUID:
        return "druid"
    if vocation in SORCERER:
        return "sorcerer"
    if vocation in KNIGHT:
        return "knight"
    if vocation in NO_VOCATION and allow_no_voc:
        return "none"
    return None


def get_voc_abb(vocation: str) -> str:
    """Given a vocation name, it returns an abbreviated string"""
    vocation = str(vocation)
    abbrev = {'none': 'N', 'druid': 'D', 'sorcerer': 'S', 'paladin': 'P', 'knight': 'K', 'elder druid': 'ED',
              'master sorcerer': 'MS', 'royal paladin': 'RP', 'elite knight': 'EK'}
    try:
        return abbrev[vocation.lower()]
    except KeyError:
        return 'N'


def get_voc_emoji(vocation: str) -> str:
    """Given a vocation name, returns a emoji representing it"""
    vocation = str(vocation)

    emoji = {"none": config.novoc_emoji, "druid": config.druid_emoji, "sorcerer": config.sorcerer_emoji,
             "paladin": config.paladin_emoji, "knight": config.knight_emoji, "elder druid": config.druid_emoji,
             "master sorcerer": config.sorcerer_emoji, "royal paladin": config.paladin_emoji,
             "elite knight": config.knight_emoji}
    try:
        return emoji[vocation.lower()]
    except KeyError:
        return "❓"


def get_voc_abb_and_emoji(vocation: str) -> str:
    """Given a vocation name, gets its abbreviation and representative emoji

    This is simply a method to shorten and ease the use of get_voc_abb and get_voc_emoji together"""
    return get_voc_abb(vocation)+get_voc_emoji(vocation)

# endregion


# region Misc

async def check_former_names(conn, bot, character):
    for old_name in character.former_names:
        # Check if a character with that name currently exists
        former_char = await DbChar.get_by_name(conn, old_name)
        if former_char:
            try:
                row = await conn.fetchrow('UPDATE "character" SET name = $1 WHERE id = $2 RETURNING id, user_id',
                                          character.name, former_char.id)
                # If we got here, it means there was no conflict
                character.owner_id = row["user_id"]
                character.id = row["id"]
                log.info(f"get_character(): {old_name} renamed to {character.name}")
                bot.dispatch("character_rename", character, old_name)
            except asyncpg.UniqueViolationError:
                # An exceptions means the character with the new name is registered as a duplicate.
                new_char = await DbChar.get_by_name(conn, character.name)
                newest_death = await conn.fetchval("SELECT date FROM character_death WHERE character_id = $1 "
                                                   "ORDER BY date DESC", former_char.id)
                # Migrate deaths older than the oldest death
                await conn.execute("UPDATE character_death SET character_id = $3 WHERE character_id = $1 AND date > $2 ",
                                   new_char.id, newest_death, former_char.id)
                await conn.execute("UPDATE character_levelup SET character_id = $2 WHERE character_id = $1",
                                   new_char.id, former_char.id)
                await conn.execute("UPDATE character_levelup SET character_id = $2 WHERE character_id = $1",
                                   new_char.id, former_char.id)
                await conn.execute("UPDATE character_history SET character_id = $2 WHERE character_id = $1",
                                   new_char.id, former_char.id)
                await conn.execute('DELETE FROM "character" WHERE id = $1', new_char.id)
                character.id = former_char.id
                log.info(f"get_character(): {old_name} renamed to {character.name}, "
                         f"duplicate character {new_char.id} deleted.")
                bot.dispatch("character_rename", character, old_name)




async def bind_database_character(bot, character: NabChar):
    """Binds a Tibia.com character with a saved database character

    Compliments information found on the database and performs updating."""
    async with bot.pool.acquire() as conn:
        # Highscore entries
        results = await conn.fetch("SELECT category, rank, value FROM highscores_entry WHERE name = $1",
                                   character.name)
        character.highscores = {category: {'rank': rank, 'value': value} for category, rank, value in results}

        # Check if this user was recently renamed, and update old reference to this
        await check_former_names(conn, bot, character)

        # Get character in database
        db_char = await DbChar.get_by_name(conn, character.name)
        if db_char is None:
            # Untracked character
            return

        character.owner_id = db_char.user_id
        character.id = db_char.id
        _vocation = character.vocation.value
        if db_char.vocation != _vocation:
            await db_char.update_vocation(conn, _vocation, False)
            log.info(f"get_character(): {character.name}'s vocation: {db_char.vocation} -> {_vocation}")

        _sex = character.sex.value
        if db_char.sex != _sex:
            await db_char.update_sex(conn, _sex, False)
            log.info(f"get_character(): {character.name}'s sex: {db_char.sex} -> {_sex}")

        if db_char.name != character.name:
            await db_char.update_name(conn, character.name, False)
            log.info(f"get_character: {db_char.name} renamed to {character.name}")
            bot.dispatch("character_rename", character, db_char.name)

        if db_char.world != character.world:
            await db_char.update_world(conn, character.world, False)
            log.info(f"get_character: {character.name}'s world updated {character.world} -> {db_char.world}")
            bot.dispatch("character_transferred", character, db_char.world)

        if db_char.guild != character.guild_name:
            await db_char.update_guild(conn, character.guild_name, False)
            log.info(f"get_character: {character.name}'s guild updated {db_char.guild!r} -> {character.guild_name!r}")
            bot.dispatch("character_change", character.owner_id)
            bot.dispatch("character_guild_change", character, db_char.guild)


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
    c = wiki_db.cursor()
    c.execute("SELECT * FROM m"
              "ap WHERE z LIKE ?", (z,))
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


def load_tibia_worlds_file():
    """Loading Tibia worlds list from an existing .json backup file."""

    try:
        with open("data/tibia_worlds.json") as json_file:
            return json.load(json_file)
    except (IOError, OSError, json.JSONDecodeError):
        log.error("load_tibia_worlds_file(): Error loading backup .json file.")


async def populate_worlds():
    """Populate the list of currently available Tibia worlds"""

    print('Fetching list of Tibia worlds...')
    worlds = await get_world_list()
    # Couldn't fetch world list, getting json backup
    if not worlds:
        world_list = load_tibia_worlds_file()
    else:
        # Convert list of ListedWorld objects to simple list of world names.
        world_list = [w.name for w in worlds]
        save_tibia_worlds_file(world_list)
    tibia_worlds.extend(world_list)
    print("\tDone")


def save_tibia_worlds_file(world_list: List[str]):
    """Receives JSON content and writes to a backup file."""

    try:
        with open("data/tibia_worlds.json", "w+") as json_file:
            json.dump(world_list, json_file)
    except (IOError, OSError, ValueError):
        log.error("save_tibia_worlds_file(): Could not save JSON to file.")

# endregion
