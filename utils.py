import discord
from discord.ext import commands
import logging
import random
import re
import sqlite3
import os
import time
from datetime import datetime, date
from calendar import timegm

from messages import *
from config import *
import psutil

# Command list (populated automatically, used to check if a message is(n't) a command invocation)
command_list = []

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

DB_LASTVERSION = 7

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
            # Added 'vocation' column to chars table, to display vocations when /check'ing users among other things.
            # Changed how the last_level flagging system works a little, a character of unknown level is now flagged as
            # level 0 instead of -1, negative levels are now used to flag of characters never seen online before.
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
        if db_version == 6:
            # Added 'description', 'server' column to 'events', created table 'events_subscribers'
            c.execute("ALTER TABLE events ADD description TEXT AFTER name")
            c.execute("ALTER TABLE events ADD server INTEGER AFTER creator")
            c.execute("""CREATE TABLE event_subscribers (
                      event_id INTEGER,
                      user_id INTEGER
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


def get_channel_by_name(bot: discord.Client, channel_name: str, server_name: str=None) -> discord.Channel:
    """Finds a channel by name on all the channels visible by the bot.

    If server_name is specified, only channels in that server will be searched"""
    if server_name is None:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     bot.get_all_channels())
    else:
        server = get_server_by_name(bot, server_name)
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     server.channels)
    return channel


def get_server_by_name(bot: discord.Client, server_name: str) -> discord.Server:
    """Returns a server by its name"""
    server = discord.utils.find(lambda m: m.name == server_name, bot.servers)
    return server


def get_member_by_name(bot: discord.Client, name: str, server: discord.Server=None) -> discord.Member:
    """Returns a member matching the name
    
    If no server is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    User functions remain the same, regardless of server"""
    if server is not None:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), server.members)
    else:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), bot.get_all_members())


def get_member(bot: discord.Client, user_id, server: discord.Server=None) -> discord.Member:
    """Returns a member matching the id

    If no server_id is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    User functions remain the same, regardless of server"""
    if server is not None:
        return server.get_member(str(user_id))
    else:
        return discord.utils.get(bot.get_all_members(), id=str(user_id))


def get_time_diff(time_diff: timedelta) -> str:
    """Returns a string showing the time difference of a timedelta"""
    if not isinstance(time_diff, timedelta):
        return None
    hours = time_diff.seconds // 3600
    minutes = (time_diff.seconds // 60) % 60
    if time_diff.days > 1:
        return "{0} days".format(time_diff.days)
    if time_diff.days == 1:
        return "1 day"
    if hours > 1:
        return "{0} hours".format(hours)
    if hours == 1:
        return "1 hour"
    if minutes > 1:
        return "{0} minutes".format(minutes)
    else:
        return "moments"


def get_local_timezone() -> int:
    """Returns the server's local time zone"""
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    return (timegm(t) - timegm(u)) / 60 / 60


def get_brasilia_time_zone() -> int:
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


def get_uptime() -> str:
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


def join_list(list, separator, endseparator) -> str:
    """Joins elements in a list with a separator between all elements and a different separator for the last element."""
    size = len(list)
    if size == 0:
        return ""
    if size == 1:
        return list[0]
    return separator.join(list[:size - 1]) + endseparator + str(list[size - 1])


def get_about_content() -> discord.Embed:
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
    embed.add_field(name="Uptime", value=get_uptime())
    memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
    if not lite_mode:
        embed.add_field(name="Tracked users", value="{0:,}".format(user_count))
        embed.add_field(name="Tracked chars", value="{0:,}".format(char_count))
        embed.add_field(name="Tracked deaths", value="{0:,}".format(deaths_count))
        embed.add_field(name="Tracked level ups", value="{0:,}".format(levels_count))

    embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
    return embed


def get_role_list(server: discord.Server):
    """Lists all role within the discord server and returns to caller."""
    roles = []
    for role in server.roles:
        # Ignore @everyone and NabBot
        if role.name not in ["@everyone", "Nab Bot"]:
            roles.append(role)

    return roles


def get_user_color(user: discord.User, server: discord.Server) -> discord.Colour:
    """Gets the user's color based on the highest role with a color"""
    # If it's a PM, server will be none
    if server is None:
        return discord.Colour.default()
    member = server.get_member(user.id)  # type: discord.Member
    if member is not None:
        return member.colour
    return discord.Colour.default()


def get_region_string(region: discord.ServerRegion) -> str:
    """Returns a formatted string for a given ServerRegion"""
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
    return regions.get(str(region), str(region))


def single_line(string: str) -> str:
    """Turns a multi-line string into a single

    Some platforms use CR and LF, others use only LF, so we first replace CR and LF together and then LF to avoid
    adding multiple spaces."""
    return string.replace("\r\n", " ").replace("\n", " ")


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


class TimeString:
    def __init__(self, argument):
        compiled = re.compile(r"(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?")
        self.original = argument
        match = compiled.match(argument)
        if match is None or not match.group(0):
            raise commands.BadArgument("That's not a valid time, try something like this: 1d7h or 4h20m")

        self.seconds = 0
        days = match.group('days')
        if days is not None:
            self.seconds += int(days) * 86400
        hours = match.group('hours')
        if hours is not None:
            self.seconds += int(hours) * 3600
        minutes = match.group('minutes')
        if minutes is not None:
            self.seconds += int(minutes) * 60
        seconds = match.group('seconds')
        if seconds is not None:
            self.seconds += int(seconds)

        if self.seconds < 0:
            raise commands.BadArgument("I can't go back in time.")

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
