import asyncio
import datetime as dt
import io
import json
import logging
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, List, Optional, Union

import aiohttp
import cachetools
import tibiapy
from PIL import Image, ImageDraw
from bs4 import BeautifulSoup
from tibiapy import World, Character, Sex, Guild, ListedWorld, Vocation, House, OnlineCharacter

from . import config, get_local_timezone, online_characters
from .database import wiki_db

log = logging.getLogger("nabbot")

# Constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1
ERROR_NOTINDATABASE = 2

# Tibia.com URLs:
url_highscores = "https://www.tibia.com/community/?subtopic=highscores&world={0}&list={1}&profession={2}&currentpage={3}"

TIBIACOM_ICON = "https://ssl-static-tibia.akamaized.net/images/global/general/apple-touch-icon-72x72.png"

KNIGHT = ["knight", "elite knight", "ek", "k", "kina", "eliteknight", "elite",
          Vocation.KNIGHT, Vocation.ELITE_KNIGHT]
PALADIN = ["paladin", "royal paladin", "rp", "p", "pally", "royalpaladin", "royalpally",
           Vocation.PALADIN, Vocation.ROYAL_PALADIN]
DRUID = ["druid", "elder druid", "ed", "d", "elderdruid", "elder",
         Vocation.DRUID, Vocation.ELDER_DRUID]
SORCERER = ["sorcerer", "master sorcerer", "ms", "s", "sorc", "mastersorcerer", "master",
            Vocation.SORCERER, Vocation.MASTER_SORCERER]
MAGE = DRUID + SORCERER + ["mage"]
NO_VOCATION = ["no vocation", "no voc", "novoc", "nv", "n v", "none", "no", "n", "noob", "noobie", "rook", "rookie",
               Vocation.NONE]

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

# This is preloaded on startup
tibia_worlds: List[str] = []

HIGHSCORE_CATEGORIES = ["sword", "axe", "club", "distance", "shielding", "fist", "fishing", "magic",
                        "magic_ek", "magic_rp", "loyalty", "achievements"]

# Cache storages, the first parameter is the number of entries, the second the amount of seconds to live of each entry
CACHE_CHARACTERS = cachetools.TTLCache(1000, 30)
CACHE_GUILDS = cachetools.TTLCache(1000, 120)
CACHE_WORLDS = cachetools.TTLCache(100, 50)
CACHE_NEWS = cachetools.TTLCache(100, 1800)
CACHE_WORLD_LIST = cachetools.TTLCache(10, 120)


class NetworkError(Exception):
    pass


class NabChar(Character):
    """Adds extra attributes to the Character class."""
    __slots__ = ("id", "highscores", "owner_id")

    def __init__(self, name=None, world=None, vocation=None, level=0, sex=None, **kwargs):
        super().__init__(name, world, vocation, level, sex, **kwargs)
        self.id = 0
        self.owner_id = 0
        self.highscores = []

    @classmethod
    def from_online(cls, o_char: OnlineCharacter, sex=None, owner_id=0):
        """Creates a NabChar from an OnlineCharacter"""
        char =  cls(o_char.name, o_char.world, o_char.vocation, o_char.level, tibiapy.utils.try_enum(Sex, sex))
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


async def get_character(bot, name, tries=5) -> Optional[NabChar]:
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
        url = Character.get_url_tibiadata(name)
    except UnicodeEncodeError:
        return None
    # Fetch website
    try:
        character = CACHE_CHARACTERS[name.lower()]
    except KeyError:
        try:
            async with bot.session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                character = NabChar.from_tibiadata(content)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            await asyncio.sleep(config.network_retry_delay)
            return await get_character(bot, name, tries - 1)
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


async def bind_database_character(bot, character: NabChar):
    """Binds a Tibia.com character with a saved database character

    Compliments information found on the database and performs updating."""
    async with bot.pool.acquire() as conn:
        # Skills from highscores
        results = await conn.fetch("SELECT category, rank, value FROM highscores_entry WHERE name = $1",
                                   character.name)
        if len(results) > 0:
            character.highscores = results

        # Check if this user was recently renamed, and update old reference to this
        for old_name in character.former_names:
            char_id = await conn.fetchval('SELECT id FROM "character" WHERE name LIKE $1', old_name)
            if char_id:
                # TODO: Conflict handling is necessary now that name is a unique column
                row = await conn.fetchrow('UPDATE "character" SET name = $1 WHERE id = $2 RETURNING id, user_id',
                                          character.name, char_id)
                character.owner_id = row["user_id"]
                character.id = row["id"]
                log.info(f"get_character(): {old_name} renamed to {character.name}")
                bot.dispatch("character_rename", character, old_name)

        # Discord owner
        db_char = await conn.fetchrow("""SELECT id, user_id, name, user_id, vocation, world, guild, sex
                                        FROM "character"
                                        WHERE name LIKE $1""", character.name)
        if db_char is None:
            # Untracked character
            return

        character.owner_id = db_char["user_id"]
        character.id = db_char["id"]
        _vocation = character.vocation.value
        if db_char["vocation"] != _vocation:
            await conn.execute('UPDATE "character" SET vocation = $1 WHERE id = $2', _vocation, db_char["id"])
            log.info(f"get_character(): {character.name}'s vocation: {db_char['vocation']} -> {_vocation}")

        _sex = character.sex.value
        if db_char["sex"] != _sex:
            await conn.execute('UPDATE "character" SET sex = $1 WHERE id = $2', _sex, db_char["id"])
            log.info(f"get_character(): {character.name}'s sex: {db_char['sex']} -> {_sex}")

        if db_char["name"] != character.name:
            await conn.execute('UPDATE "character" SET name = $1 WHERE id = $2', character.name, db_char["id"])
            log.info(f"get_character: {db_char['name']} renamed to {character.name}")
            bot.dispatch("character_rename", character, db_char['name'])

        if db_char["world"] != character.world:
            await conn.execute('UPDATE "character" SET world = $1 WHERE id = $2', character.world, db_char["id"])
            log.info(f"get_character: {character.name}'s world updated {character.world} -> {db_char['world']}")
            bot.dispatch("character_transferred", character, db_char['world'])

        if db_char["guild"] != character.guild_name:
            await conn.execute('UPDATE "character" SET guild = $1 WHERE id = $2', character.guild_name, db_char["id"])
            log.info(f"get_character: {character.name}'s guild updated {db_char['guild']!r} -> {character.guild_name!r}")
            bot.dispatch("character_change", character.owner_id)
            bot.dispatch("character_guild_change", character, db_char['guild'])


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
        await asyncio.sleep(config.network_retry_delay)
        return await get_highscores(world, category, pagenum, profession, tries - 1)

    # Trimming content to reduce load
    try:
        start_index = content.index('<td style="width: 20%;" >Vocation</td>')
        end_index = content.index('<div style="float: left;"><b>&raquo; Pages:')
        content = content[start_index:end_index]
    except ValueError:
        await asyncio.sleep(config.network_retry_delay)
        return await get_highscores(world, category, pagenum, profession, tries - 1)

    if category == "loyalty":
        regex_deaths = r'<td>([^<]+)</TD><td><a href="https://www.tibia.com/community/\?subtopic=characters&name=[^"]+" >([^<]+)</a></td><td>([^<]+)</TD><td>[^<]+</TD><td style="text-align: right;" >([^<]+)</TD></TR>'
        pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
        matches = re.findall(pattern, content)
        score_list = []
        for m in matches:
            score_list.append({'rank': m[0], 'name': m[1], 'vocation': m[2], 'value': int(m[3].replace(',', ''))})
    else:
        regex_deaths = r'<td>([^<]+)</TD><td><a href="https://www.tibia.com/community/\?subtopic=characters&name=[^"]+" >([^<]+)</a></td><td>([^<]+)</TD><td style="text-align: right;" >([^<]+)</TD></TR>'
        pattern = re.compile(regex_deaths, re.MULTILINE + re.S)
        matches = re.findall(pattern, content)
        score_list = []
        for m in matches:
            score_list.append({'rank': m[0], 'name': m[1], 'vocation': m[2], 'value': int(m[3].replace(',', ''))})
    return score_list


async def get_highscores_tibiadata(world, category=None, vocation=None, tries=5):
    """Gets all the highscores entries of a world, category and vocation."""
    if vocation is None:
        vocation = "all"
    if category is None:
        category = "experience"
    url = f"https://api.tibiadata.com/v2/highscores/{world}/{category}/{vocation}.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                content = await resp.text(encoding='ISO-8859-1')
    except Exception:
        await asyncio.sleep(config.network_retry_delay)
        return await get_highscores_tibiadata(world, category, vocation, tries - 1)
    content_json = json.loads(content)
    try:
        if not isinstance(content_json["highscores"]["data"], list):
            return None
    except KeyError:
        return None
    entries = content_json["highscores"]["data"]
    for entry in entries:
        entry["vocation"] = entry["voc"]
        del entry["voc"]
    return entries


async def get_world(name, tries=5) -> Optional[World]:
    name = name.strip().title()
    if tries == 0:
        log.error("get_world: Couldn't fetch {0}, network error.".format(name))
        raise NetworkError()
        # Fetch website
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
    except aiohttp.ClientError:
        await asyncio.sleep(config.network_retry_delay)
        return await get_world(name, tries - 1)
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
    try:
        guild = CACHE_GUILDS[name.lower()]
        return guild
    except KeyError:
        pass

    if not title_case:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(guildstats_url) as resp:
                    content = await resp.text(encoding='ISO-8859-1')
        except Exception:
            await asyncio.sleep(config.network_retry_delay)
            return await get_guild(name, title_case, tries - 1)

        # Make sure we got a healthy fetch
        try:
            content.index('<div class="footer">')
        except ValueError:
            await asyncio.sleep(config.network_retry_delay)
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

    # Fetch website
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(Guild.get_url_tibiadata(name)) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                guild = Guild.from_tibiadata(content)
    except Exception:
        await asyncio.sleep(config.network_retry_delay)
        return await get_guild(name, title_case, tries - 1)

    if guild is None:
        if title_case:
            return await get_guild(name, False)
        else:
            return None
    CACHE_GUILDS[name.lower()] = guild
    return guild


async def get_recent_news(tries=5):
    if tries == 0:
        log.error("get_recent_news: network error.")
        raise NetworkError()
    try:
        url = f"https://api.tibiadata.com/v2/latestnews.json"
    except UnicodeEncodeError:
        return None
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
    except Exception:
        await asyncio.sleep(config.network_retry_delay)
        return await get_recent_news(tries - 1)

    content_json = json.loads(content)
    try:
        newslist = content_json["newslist"]
    except KeyError:
        return None
    for article in newslist["data"]:
        article["date"] = parse_tibiadata_time(article["date"]).date()
    CACHE_NEWS["recent"] = newslist["data"]
    return newslist["data"]


async def get_news_article(article_id: int, tries=5) -> Optional[Dict[str, Union[str, dt.date]]]:
    """Returns a news article with the specified id or None if it doesn't exist

    If there's a network error, NetworkError exception is raised"""
    if tries == 0:
        log.error("get_recent_news: network error.")
        raise NetworkError()
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
    except Exception:
        await asyncio.sleep(config.network_retry_delay)
        return await get_recent_news(tries - 1)

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


def get_house_id(name) -> Optional[int]:
    """Gets the house id of a house with a given name.

    Name is lowercase."""
    try:
        return wiki_db.execute("SELECT house_id FROM house WHERE name LIKE ?", (name,)).fetchone()["house_id"]
    except (AttributeError, KeyError):
        return None


async def get_house(house_id, world, tries=5) -> House:
    """Returns a dictionary containing a house's info, a list of possible matches or None.

    If world is specified, it will also find the current status of the house in that world."""
    if tries == 0:
        log.error(f"get_house: Couldn't fetch {house_id}, {world}, network error.")
        raise NetworkError()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(House.get_url_tibiadata(house_id, world)) as resp:
                content = await resp.text(encoding='ISO-8859-1')
                house = House.from_tibiadata(content)
    except aiohttp.ClientError:
        await asyncio.sleep(config.network_retry_delay)
        return await get_house(house_id, world, tries - 1)
    return house


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


def normalize_vocation(vocation) -> str:
    """Attempts to normalize a vocation string into a base vocation."""
    if vocation in PALADIN:
        return "paladin"
    if vocation in DRUID:
        return "druid"
    if vocation in SORCERER:
        return "sorcerer"
    if vocation in KNIGHT:
        return "knight"
    if vocation in NO_VOCATION:
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


async def get_world_list(tries=3) -> List[ListedWorld]:
    """Fetch the list of Tibia worlds from TibiaData"""
    if tries == 0:
        log.error("get_world_list(): Couldn't fetch TibiaData for the worlds list, network error.")
        raise NetworkError()

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
    except Exception:
        await asyncio.sleep(config.network_retry_delay)
        return await get_world_list(tries - 1)

    CACHE_WORLD_LIST[0] = worlds
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


def get_tibia_weekday() -> int:
    """Returns the current weekday according to the game.

    Since server save is at 10:00 CET, that's when a new day starts according to the game."""
    offset = get_tibia_time_zone() - get_local_timezone()
    # Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = dt.datetime.now() + dt.timedelta(hours=offset - 10)
    return tibia_time.weekday()


def get_rashid_city() -> Dict[str, Union[str, int]]:
    """Returns a dictionary with rashid's info

    Dictionary contains: the name of the week, city and x,y,z, positions."""
    offset = get_tibia_time_zone() - get_local_timezone()
    # Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = dt.datetime.now() + dt.timedelta(hours=offset - 10)
    c = wiki_db.cursor()
    c.execute("SELECT * FROM rashid_position WHERE day = ?", (tibia_time.weekday(),))
    info = c.fetchone()
    c.close()
    return info["city"]
