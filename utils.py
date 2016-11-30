import asyncio
import discord
from discord.ext import commands
import logging
import random
import urllib.request
import re
import urllib
import sqlite3
import os
import time
from datetime import datetime, date
from calendar import timegm
import aiohttp

from messages import *
from config import *
import psutil

# Command list (populated automatically, used to check if a message is(n't) a command invocation)
command_list = []

# Global constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1
ERROR_NOTINDATABASE = 2

# Start logging
# Create logs folder
os.makedirs('logs/', exist_ok=True)
# discord.py log
discord_log = logging.getLogger('discord')
discord_log.setLevel(logging.INFO)
handler = logging.FileHandler(filename='logs/discord.log', encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_log.addHandler(handler)
# NabBot log
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
# Save log to file (info level)
fileHandler = logging.FileHandler(filename='logs/nabbot.log', encoding='utf-8', mode='a')
fileHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
fileHandler.setLevel(logging.INFO)
log.addHandler(fileHandler)
# Print output to console too (debug level)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
consoleHandler.setLevel(logging.DEBUG)
log.addHandler(consoleHandler)

# Database global connections
userDatabase = sqlite3.connect(USERDB)
tibiaDatabase = sqlite3.connect(TIBIADB)

DB_LASTVERSION = 6

# Tibia.com URLs:
url_character = "https://secure.tibia.com/community/?subtopic=characters&name="
url_guild = "https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName="
url_guild_online = "https://secure.tibia.com/community/?subtopic=guilds&page=view&onlyshowonline=1&"

def initDatabase():
    """Initializes and/or updates the database to the current version"""

    # Database file is automatically created with connect, now we have to check if it has tables
    print("Checking database version...")
    try:
        c = userDatabase.cursor()
        c.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type = 'table'")
        result = c.fetchone()
        # Database is empty
        if result is None or result["count"] == 0:
            c.execute("""CREATE TABLE discord_users (
                      id INTEGER NOT NULL,
                      weight INTEGER DEFAULT 5,
                      PRIMARY KEY(id)
                      )""")
            c.execute("""CREATE TABLE chars (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      name TEXT,
                      last_level INTEGER DEFAULT -1,
                      last_death_time TEXT
                      )""")
            c.execute("""CREATE TABLE char_levelups (
                      char_id INTEGER,
                      level INTEGER,
                      date INTEGER
                      )""")
        c.execute("SELECT tbl_name FROM sqlite_master WHERE type = 'table' AND name LIKE 'db_info'")
        result = c.fetchone()
        # If there's no version value, version 1 is assumed
        if result is None:
            c.execute("""CREATE TABLE db_info (
                      key TEXT,
                      value TEXT
                      )""")
            c.execute("INSERT INTO db_info(key,value) VALUES('version','1')")
            db_version = 1
            print("No version found, version 1 assumed")
        else:
            c.execute("SELECT value FROM db_info WHERE key LIKE 'version'")
            db_version = int(c.fetchone()["value"])
            print("Version {0}".format(db_version))
        if db_version == DB_LASTVERSION:
            print("Database is up to date.")
            return
        # Code to patch database changes
        if db_version == 1:
            # Added 'vocation' column to chars table, used to display vocations when /check'ing users among other things.
            # Changed how the last_level flagging system works a little, a character of unknown level is now flagged as level 0 instead of -1, negative levels are now used to flag of characters never seen online before.
            c.execute("ALTER TABLE chars ADD vocation TEXT")
            c.execute("UPDATE chars SET last_level = 0 WHERE last_level = -1")
            db_version += 1
        if db_version == 2:
            # Added 'events' table
            c.execute("""CREATE TABLE events (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      creator INTEGER,
                      name TEXT,
                      start INTEGER,
                      duration INTEGER,
                      active INTEGER DEFAULT 1
                      )""")
            db_version += 1
        if db_version == 3:
            # Added 'char_deaths' table
            # Added 'status column' to events (for event announces)
            c.execute("""CREATE TABLE char_deaths (
                      char_id INTEGER,
                      level INTEGER,
                      killer TEXT,
                      date INTEGER,
                      byplayer BOOLEAN
                      )""")
            c.execute("ALTER TABLE events ADD COLUMN status DEFAULT 4")
            db_version += 1
        if db_version == 4:
            # Added 'name' column to 'discord_users' table to save their names for external use
            c.execute("ALTER TABLE discord_users ADD name TEXT")
            db_version += 1
        if db_version == 5:
            # Added 'world' column to 'chars', renamed 'discord_users' to 'users', created table 'user_servers'
            c.execute("ALTER TABLE chars ADD world TEXT")
            c.execute("ALTER TABLE discord_users RENAME TO users")
            c.execute("""CREATE TABLE user_servers (
                      id INTEGER,
                      server INTEGER,
                      PRIMARY KEY(id)
                      );""")
            db_version += 1
        print("Updated database to version {0}".format(db_version))
        c.execute("UPDATE db_info SET value = ? WHERE key LIKE 'version'", (db_version,))

    finally:
        userDatabase.commit()


def dict_factory(cursor, row):
    """Makes values returned by cursor fetch functions return a dictionary instead of a tuple.

    To implement this, the connection's row_factory method must be replaced by this one."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

userDatabase.row_factory = dict_factory
tibiaDatabase.row_factory = dict_factory


def vocAbb(vocation) -> str:
    """Given a vocation name, it returns an abbreviated string """
    abbrev = {'None': 'N', 'Druid': 'D', 'Sorcerer': 'S', 'Paladin': 'P', 'Knight': 'K', 'Elder Druid': 'ED',
              'Master Sorcerer': 'MS', 'Royal Paladin': 'RP', 'Elite Knight': 'EK'}
    try:
        return abbrev[vocation]
    except KeyError:
        return 'N'


def getLogin():
    """When the bot is run without a login.py file, it prompts the user for login info"""
    if not os.path.isfile("login.py"):
        print("This seems to be the first time NabBot is ran (or login.py is missing)")
        print("To run your own instance of NabBot you need to create a new bot account to get a bot token")
        print("https://discordapp.com/developers/applications/me")
        print("Alternatively, you can use a regular discord account for your bot, although this is not recommended")
        print("Insert a bot token OR an e-mail address for a regular account to be used as a bot")
        login = input(">>")
        email = ""
        password = ""
        token = ""
        if "@" in login:
            email = login
            password = input("Enter password: >>")
        elif len(login) >= 50:
            token = login
        else:
            input("What you entered isn't a token or an e-mail. Restart NabBot to retry.")
            quit()
        f = open("login.py", "w+")
        f.write("#Token always has priority, if token is defined it will always attempt to login using a token\n")
        f.write("#Comment the token line or set it empty to use email login\n")
        f.write("token = '{0}'\nemail = '{1}'\npassword = '{2}'\n".format(token, email, password))
        f.close()
        print("Login data has been saved correctly. You can change this later by editing login.py")
        input("Press any key to start NabBot now...")
        quit()
    return __import__("login")


def formatMessage(message) -> str:
    """##handles stylization of messages, uppercasing \TEXT/, lowercasing /text\ and title casing /Text/"""
    upper = r'\\(.+?)/'
    upper = re.compile(upper, re.MULTILINE + re.S)
    lower = r'/(.+?)\\'
    lower = re.compile(lower, re.MULTILINE + re.S)
    title = r'/(.+?)/'
    title = re.compile(title, re.MULTILINE + re.S)
    skipproper = r'\^(.+?)\^(.+?)([a-zA-Z])'
    skipproper = re.compile(skipproper, re.MULTILINE + re.S)
    message = re.sub(upper, lambda m: m.group(1).upper(), message)
    message = re.sub(lower, lambda m: m.group(1).lower(), message)
    message = re.sub(title, lambda m: m.group(1).title(), message)
    message = re.sub(skipproper,
                     lambda m: m.group(2) + m.group(3) if m.group(3).istitle() else m.group(1) + m.group(2) + m.group(
                         3), message)
    return message


def weighedChoice(messages, condition1=False, condition2=False, condition3=False, condition4=False) -> str:
    """Makes weighed choices from message lists where [0] is a value representing the relative odds
    of picking a message and [1] is the message string"""

    # Find the max range by adding up the weigh of every message in the list
    # and purge out messages that dont fulfil the conditions
    range = 0
    _messages = []
    for message in messages:
        if len(message) == 6:
            if (not message[2] or condition1 in message[2]) and (not message[3] or condition2 in message[3]) and (
                not message[4] or condition3 in message[4]) and (not message[5] or condition4 in message[5]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        elif len(message) == 5:
            if (not message[2] or condition1 in message[2]) and (not message[3] or condition2 in message[3]) and (
                not message[4] or condition3 in message[4]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        elif len(message) == 4:
            if (not message[2] or condition1 in message[2]) and (not message[3] or condition2 in message[3]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        elif len(message) == 3:
            if (not message[2] or condition1 in message[2]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        else:
            range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
            _messages.append(message)
    # Choose a random number
    rangechoice = random.randint(0, range)
    # Iterate until we find the matching message
    rangepos = 0
    for message in _messages:
        if rangepos <= rangechoice < rangepos + (message[0] if not message[1] in lastmessages else message[0] / 10):
            currentChar = lastmessages.pop()
            lastmessages.insert(0, message[1])
            return message[1]
        rangepos = rangepos + (message[0] if not message[1] in lastmessages else message[0] / 10)
    # This shouldnt ever happen...
    print("Error in weighedChoice!")
    return _messages[0][1]


def getChannelByName(bot: discord.Client, channel_name: str, server_name=None) -> discord.Channel:
    """Finds a channel by name on all the channels visible by the bot.

    If server_name is specified, only channels in that server will be searched"""
    if server_name is None:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     bot.get_all_channels())
    else:
        server = getServerByName(bot, server_name)
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     server.channels)
    return channel


def getServerByName(bot: discord.Client, server_name: str) -> discord.Server:
    """Returns a server by its name"""
    server = discord.utils.find(lambda m: m.name == server_name, bot.servers)
    return server


def getMemberByName(bot: discord.Client, name: str, server=None) -> discord.Member:
    """Returns a member matching the name
    
    If no server_id is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    User functions remain the same, regardless of server"""
    if server is not None:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), server.members)
    else:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), bot.get_all_members())


def getMember(bot: discord.Client, id, server=None) -> discord.Member:
    """Returns a member matching the id

    If no server_id is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    User functions remain the same, regardless of server"""
    if server is not None:
        return discord.utils.get(server.members, id=str(id))
    else:
        return discord.utils.get(bot.get_all_members(), id=str(id))


def getTimeDiff(time) -> str:
    """Returns a string showing the time difference of a timedelta"""
    if not isinstance(time, timedelta):
        return None
    hours = time.seconds // 3600
    minutes = (time.seconds // 60) % 60
    if time.days > 1:
        return "{0} days".format(time.days)
    if time.days == 1:
        return "1 day"
    if hours > 1:
        return "{0} hours".format(hours)
    if hours == 1:
        return "1 hour"
    if minutes > 1:
        return "{0} minutes".format(minutes)
    else:
        return "moments"


def getLocalTimezone() -> int:
    """Returns the server's local time zone"""
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    return (timegm(t) - timegm(u)) / 60 / 60


def getTibiaTimeZone() -> int:
    """Returns Germany's timezone, considering their daylight saving time dates"""
    # Find date in Germany
    gt = datetime.utcnow() + timedelta(hours=1)
    germany_date = date(gt.year, gt.month, gt.day)
    dst_start = date(gt.year, 3, (31 - (int(((5 * gt.year) / 4) + 4) % int(7))))
    dst_end = date(gt.year, 10, (31 - (int(((5 * gt.year) / 4) + 1) % int(7))))
    if dst_start < germany_date < dst_end:
        return 2
    return 1


def getBrasiliaTimeZone() -> int:
    """Returns Brasilia's timezone, considering their daylight saving time dates"""
    # Find date in Brasilia
    bt = datetime.utcnow() - timedelta(hours=3)
    brasilia_date = date(bt.year, bt.month, bt.day)
    # These are the dates for the 2016/2017 time change, they vary yearly but ¯\0/¯, good enough
    dst_start = date(bt.year, 10, 16)
    dst_end = date(bt.year + 1, 2, 21)
    if dst_start < brasilia_date < dst_end:
        return -2
    return -3


start_time = datetime.utcnow()


def getUptime() -> str:
    """Returns a string with the time the bot has been running for.

    Start time is saved when this module is loaded, not when the bot actually logs in,
    so it is a couple seconds off."""
    now = datetime.utcnow()
    delta = now - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    if days:
        fmt = '{d}d {h}h {m}m {s}s'
    else:
        fmt = '{h}h {m}m {s}s'

    return fmt.format(d=days, h=hours, m=minutes, s=seconds)


def joinList(list, separator, endseparator) -> str:
    """Joins elements in a list with a separator between all elements and a different separator for the last element."""
    size = len(list)
    if size == 0:
        return ""
    if size == 1:
        return list[0]
    return separator.join(list[:size - 1]) + endseparator + str(list[size - 1])


def getAboutContent() -> discord.Embed:
    """Returns a formatted string with general information about the bot.
    
    Used in /about and /whois Nab Bot"""
    user_count = 0
    char_count = 0
    deaths_count = 0
    levels_count = 0
    if not lite_mode:
        c = userDatabase.cursor()
        try:
            c.execute("SELECT COUNT(*) as count FROM users")
            result = c.fetchone()
            if result is not None:
                user_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM chars")
            result = c.fetchone()
            if result is not None:
                char_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_deaths")
            result = c.fetchone()
            if result is not None:
                deaths_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_levelups")
            result = c.fetchone()
            if result is not None:
                levels_count = result["count"]
        finally:
            c.close()

    embed = discord.Embed(description="*Beep boop beep boop*. I'm just a bot!")
    embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                     icon_url="https://assets-cdn.github.com/favicon.ico")
    embed.add_field(name="Authors", value="@Galarzaa#8515, @Nezune#2269")
    embed.add_field(name="Platform", value="Python " + EMOJI[":snake:"])
    embed.add_field(name="Created", value="March 30th 2016")
    embed.add_field(name="Uptime", value=getUptime())
    memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
    if not lite_mode:
        embed.add_field(name="Tracked users", value="{0:,}".format(user_count))
        embed.add_field(name="Tracked chars", value="{0:,}".format(char_count))
        embed.add_field(name="Tracked deaths", value="{0:,}".format(deaths_count))
        embed.add_field(name="Tracked level ups", value="{0:,}".format(levels_count))

    embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
    return embed


def getListRoles(server):
    """Lists all role within the discord server and returns to caller."""

    roles = []

    for role in server.roles:
        # Ignore @everyone and NabBot
        if role.name not in ["@everyone", "Nab Bot"]:
            roles.append(role)

    return roles


def getUserColor(user: discord.User, server: discord.Server) -> discord.Colour:
    """Gets the user's color based on the highest role with a color"""
    # If it's a PM, server will be none
    if server is None:
        return discord.Colour.default()
    member = server.get_member(user.id)  # type: discord.Member
    if member is not None:
        return member.colour
    return discord.Colour.default()


def getRegionString(region: discord.ServerRegion) -> str:
    regions = {"us-west": EMOJI[":flag_us:"]+"US West",
               "us-east": EMOJI[":flag_us:"]+"US East",
               "us-central": EMOJI[":flag_us:"]+"US Central",
               "us-south": EMOJI[":flag_us:"]+"US South",
               "eu-west": EMOJI[":flag_eu:"]+"West Europe",
               "eu-central": EMOJI[":flag_eu:"]+"Central Europe",
               "singapore": EMOJI[":flag_sg:"]+"Singapore",
               "london": EMOJI[":flag_gb:"]+"London",
               "sydney": EMOJI[":flag_au:"]+"Sydney",
               "amsterdam": EMOJI[":flag_nl:"]+"Amsterdam",
               "frankfurt": EMOJI[":flag_de:"]+"Frankfurt",
               "brazil": EMOJI[":flag_br:"]+"Brazil"
               }
    return regions.get(str(region),str(region))



@asyncio.coroutine
def getPlayerDeaths(name, single_death=False, tries=5):
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
def getServerOnline(server, tries=5):
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
            ret = yield from getServerOnline(server, tries)
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
def getGuildOnline(guildname, titlecase=True, tries=5):
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
            ret = yield from getGuildOnline(guildname, False)
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
def getPlayer(name, tries=5):
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
            ret = yield from getPlayer(name, tries)
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


def getRashidCity() -> str:
    """Returns the city Rashid is currently in."""
    offset = getTibiaTimeZone() - getLocalTimezone()
    # Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = datetime.now() + timedelta(hours=offset - 10)
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
    c.execute("SELECT * FROM Items WHERE name LIKE ?", (itemname,))
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
    local_utc_offset = ((timegm(t) - timegm(u)) / 60 / 60)

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
        hp = 5 * (3 * level - 2 * 8 + 29)
        mp = 5 * level + 50
        cap = 5 * (5 * level - 5 * 8 + 94)
        vocation = "knight"
    elif vocation in ["paladin", "royal paladin", "rp", "pally", "royal pally", "p"]:
        hp = 5 * (2 * level - 8 + 29)
        mp = 5 * (3 * level - 2 * 8) + 50
        cap = 10 * (2 * level - 8 + 39)
        vocation = "paladin"
    elif vocation in ["mage", "druid", "elder druid", "elder", "ed", "d", "sorc", "sorcerer", "master sorcerer", "ms",
                      "s"]:
        hp = 5 * (level + 29)
        mp = 5 * (6 * level - 5 * 8) + 50
        cap = 10 * (level + 39)
        vocation = "mage"
    elif vocation in ["no vocation", "no voc", "novoc", "nv", "n v", "none", "no", "n", "noob", "noobie", "rook",
                      "rookie"]:
        vocation = "no vocation"
    else:
        return "bad vocation"

    if level < 8 or vocation == "no vocation":
        hp = 5 * (level + 29)
        mp = 5 * level + 50
        cap = 10 * (level + 39)

    return {"vocation": vocation, "hp": hp, "mp": mp, "cap": cap}


def getShareRange(level: int):
    """Returns the share range for a specific level

    The returned value is a list with the lower limit and the upper limit in that order."""
    return int(round(level * 2 / 3, 0)), int(round(level * 3 / 2, 0))

# TODO: Improve formatting to match /monster and /item
def getSpell(name):
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

# Check decorators for commands

def check_is_owner(message):
    return message.author.id in owner_ids


def is_owner():
    return commands.check(lambda ctx: check_is_owner(ctx.message))


def check_is_mod(message):
    return message.author.id in mod_ids or message.author.id in owner_ids


def is_mod():
    return commands.check(lambda ctx: check_is_mod(ctx.message))


def check_is_pm(message):
    return message.channel.is_private


def is_pm():
    return commands.check(lambda ctx: check_is_pm(ctx.message))


def is_numeric(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
