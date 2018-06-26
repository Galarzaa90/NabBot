import datetime as dt
import logging
import os
import re
import time
from calendar import timegm
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, List

import discord
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

CONTENT_LIMIT = 2000
DESCRIPTION_LIMIT = 2048
FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
FIELD_AMOUNT = 25
EMBED_LIMIT = 6000


def clean_string(ctx: commands.Context, string: str) -> str:
    """Turns mentions into plain text

    For message object, there's already a property that does this :method:`discord.Message.clean_content`

    :param ctx: The invocation context
    :param string: The string to clean.
    :return: The clean string.
    """
    def repl_channel(match):
        channel_id = match.group(0).replace("<", "").replace("#", "").replace(">", "")
        channel = ctx.guild.get_channel(int(channel_id))
        return "#deleted_channel" if channel is None else "#"+channel.name

    def repl_role(match):
        role_id = match.group(0).replace("<", "").replace("@", "").replace("&", "").replace(">", "")
        role = get_role(ctx.guild, int(role_id))
        return "@deleted_role" if role is None else "@"+role.name

    def repl_user(match):
        user_id = match.group(0).replace("<", "").replace("@", "").replace("!", "").replace(">", "")
        user = ctx.guild.get_member(int(user_id))
        return "@deleted_user" if user is None else "@" + user.display_name
    # Find channel mentions:
    string = re.sub(r"<#\d+>", repl_channel, string)
    # Find role mentions
    string = re.sub(r"<@&\d+>", repl_role, string)
    # Find user mentions
    string = re.sub(r"<@!\d+>", repl_user, string)
    string = re.sub(r"<@\d+>", repl_user, string)
    # Clean @everyone and @here
    return string.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")


def get_region_string(region: discord.VoiceRegion) -> str:
    """Returns a formatted string for a given :class:`VoiceRegion`

    :param region: The voice region to convert.
    :return: The string representing the region."""
    regions = {"us-west": "🇺🇸US West",
               "us-east": "🇺🇸US East",
               "us-central": "🇺🇸US Central",
               "us-south": "🇺🇸US South",
               "eu-west": "🇪🇺West Europe",
               "eu-central": "🇪🇺Central Europe",
               "singapore": "🇸🇬Singapore",
               "london": "🇬🇧London",
               "sydney": "🇦🇺Sydney",
               "amsterdam": "🇳🇱Amsterdam",
               "frankfurt": "🇩🇪Frankfurt",
               "brazil": "🇧🇷Brazil",
               "japan": "🇯🇵Japan",
               "hongkong": "🇭🇰Hong Kong",
               "russia": "🇷🇺Russia",
               "vip-us-east": "🇺🇸US East (VIP)",
               "vip-us-west": "🇺🇸US West (VIP)",
               "vip-amsterdam": "🇳🇱Amsterdam (VIP)",
               }
    return regions.get(str(region), str(region))


def get_brasilia_time_zone() -> int:
    """Returns Brasilia's timezone, considering their daylight saving time dates

    :return: The UTC offset of Brasilia's timezone.
    """
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


def get_local_timezone() -> int:
    """Returns the server's local time zone

    :return: The UTC offset of the host's timezone.
    """
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    return (timegm(t) - timegm(u)) / 60 / 60


def get_n_weekday(year: int, month: int, weekday: int, n: int) -> Optional[dt.date]:
    """Returns the date where the nth weekday of a month occurred.

    :param year: The year to check
    :param month: The month to check
    :param weekday: The day of the week to look for (Monday = 1)
    :param n: The nth day to look for
    :return: The date where the request occurred.
    """
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


def get_role(guild: discord.Guild, role_id: int = None, role_name: str = None) -> Optional[discord.Role]:
    """Returns a role matching the id in a server.

    :param guild: The guild where the role should be looked in.
    :param role_id: The id of the role to look for.
    :param role_name: The name of the role to look for.
    :return: The found role or None.
    :raise ValueError: If guild is None or both role_id and role_name are specified.
    """
    if guild is None:
        raise ValueError("guild is None")
    if role_id is None and role_name is None:
        raise ValueError("Either role_id or role_name must be specified")
    for role in guild.roles:
        if role.id == role_id or (role_name is not None and role.name.lower() == role_name.lower()):
            return role
    return None


def get_time_diff(time_diff: dt.timedelta) -> Optional[str]:
    """Returns a string showing the time difference of a timedelta

    :param time_diff: The time difference object
    :return: A string representation of the time difference."""
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


def get_user_avatar(user: discord.user.BaseUser) -> str:
    """Gets the user's avatar url

    If they don't have an avatar set, the default avatar is returned.

    :param user: The user to get the avatar of
    :return: The avatar's url."""
    return user.avatar_url if user.avatar_url is not None else user.default_avatar_url


def is_numeric(s: str) -> bool:
    """Checks if a string is numeric.

    :param s: The string to check.
    :return: True if the value is numeric
    """
    try:
        int(s)
        return True
    except ValueError:
        return False


def join_list(_list: List, separator: str, end_separator: str) -> str:
    """Joins elements in a list, using a different sepaator for the last item.

    :param _list: The list to join.
    :param separator: The string that will separate the items.
    :param end_separator: The separator that will be used for the last item.
    :return: A string containing all list elements.
    """
    size = len(_list)
    if size == 0:
        return ""
    if size == 1:
        return _list[0]
    return separator.join(_list[:size - 1]) + end_separator + str(_list[size - 1])


def parse_uptime(start_time, long=False) -> str:
    """Returns a string with the time the bot has been running for.

    :param start_time: The time where the bot started.
    :param long: Whether to use long notation or not.
    :return: A string representing the total running time."""
    now = dt.datetime.utcnow()
    delta = now - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    if days:
        fmt = '{d}d {h}h {m}m {s}s' if not long else '{d} days, {h} hours, {m} minutes, and {s} seconds'
    else:
        fmt = '{h}h {m}m {s}s' if not long else '{h} hours, {m} minutes, and {s} seconds'

    return fmt.format(d=days, h=hours, m=minutes, s=seconds)


def single_line(string: str) -> str:
    """Turns a multi-line string into a single.

    Some platforms use CR and LF, others use only LF, so we first replace CR and LF together and then LF to avoid
    adding multiple spaces.

    :param string: The string to convert.
    :return: The converted string.
    """
    return string.replace("\r\n", " ").replace("\n", " ")
class BadTime(commands.BadArgument):
    pass


class TimeString:
    def __init__(self, argument):
        compiled = re.compile(r"(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?")
        self.original = argument
        match = compiled.match(argument)
        if match is None or not match.group(0):
            raise BadTime("That's not a valid time, try something like this: 1d7h or 4h20m")

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
            raise BadTime("I can't go back in time.")

        if self.seconds > (60*60*24*30):
            raise BadTime("That's a bit too far in the future... Try less than 30 days.")


