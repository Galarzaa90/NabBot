import datetime as dt
import logging
import os
import re
import time
from calendar import timegm
from logging.handlers import TimedRotatingFileHandler

from discord.ext import commands

# This is the global online list
# don't look at it too closely or you'll go blind!
# characters are added as servername_charactername
# The list is updated periodically on think() using get_server_online()
global_online_list = []

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
fileHandler = TimedRotatingFileHandler('logs/nabbot', when='midnight')
fileHandler.suffix = "%Y_%m_%d.log"
fileHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
fileHandler.setLevel(logging.INFO)
log.addHandler(fileHandler)
# Print output to console too (debug level)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
consoleHandler.setLevel(logging.DEBUG)
log.addHandler(consoleHandler)


def get_token():
    """When the bot is run without a login.py file, it prompts the user for login info"""
    if not os.path.isfile("token.txt"):
        print("This seems to be the first time NabBot is ran (or token.txt is missing)")
        print("To run your own instance of NabBot you need to create a new bot account to get a bot token")
        print("https://discordapp.com/developers/applications/me")
        print("Enter the token:")
        token = input(">>")
        if len(token) < 50:
            input("What you entered isn't a token. Restart NabBot to retry.")
            quit()
        f = open("token.txt", "w+")
        f.write(token)
        f.close()
        print("Token has been saved to token.txt, you can edit this file later to change it.")
        input("Press any key to start NabBot now...")
        return token
    else:
        with open("token.txt") as f:
            return f.read()


def get_time_diff(time_diff: dt.timedelta) -> str:
    """Returns a string showing the time difference of a timedelta"""
    if not isinstance(time_diff, dt.timedelta):
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


def get_n_weekday(year, month, weekday, n):
    """Returns the date where the nth weekday of a month occurred."""
    count = 0
    for i in range(1, 32):
        try:
            d = dt.date(year, month, i)
        except ValueError:
            break
        if d.isoweekday() == weekday:
            count += 1
        if count == n:
            return d
    return None


def get_brasilia_time_zone() -> int:
    """Returns Brasilia's timezone, considering their daylight saving time dates"""
    # Find date in Brasilia
    bt = dt.datetime.utcnow() - dt.timedelta(hours=3)
    brasilia_date = dt.date(bt.year, bt.month, bt.day)
    # DST starts on the third sunday of october and ends on the third sunday of february
    # It may be off by a couple hours
    dst_start = get_n_weekday(bt.year, 10, 7, 3)
    dst_end = get_n_weekday(bt.year, 2, 7, 3)
    if brasilia_date > dst_start or brasilia_date < dst_end:
        return -2
    return -3


def parse_uptime(start_time, long=False) -> str:
    """Returns a string with the time the bot has been running for.

    Start time is saved when this module is loaded, not when the bot actually logs in,
    so it is a couple seconds off."""
    now = dt.datetime.utcnow()
    delta = now - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    if days:
        fmt = '{d}d {h}h {m}m {s}s' if not long else '{d} days, {h} hours, {m} minutes, and {s} seconds.'
    else:
        fmt = '{h}h {m}m {s}s' if not long else '{h} hours, {m} minutes, and {s} seconds.'

    return fmt.format(d=days, h=hours, m=minutes, s=seconds)


def join_list(list, separator, endseparator) -> str:
    """Joins elements in a list with a separator between all elements and a different separator for the last element."""
    size = len(list)
    if size == 0:
        return ""
    if size == 1:
        return list[0]
    return separator.join(list[:size - 1]) + endseparator + str(list[size - 1])


def single_line(string: str) -> str:
    """Turns a multi-line string into a single

    Some platforms use CR and LF, others use only LF, so we first replace CR and LF together and then LF to avoid
    adding multiple spaces."""
    return string.replace("\r\n", " ").replace("\n", " ")


def is_numeric(s):
    """Checks if a string is numeric"""
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

        if self.seconds > (60*60*24*15):
            raise commands.BadArgument("That's a bit too far in the future... Try less than 15 days.")


if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
