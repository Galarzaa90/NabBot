import datetime as dt
import io
import logging
import os
import re
import time
from calendar import timegm
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, List, Union, Tuple

import discord
from PIL import Image
from discord.ext import commands

from .config import config

# This is the global online list
# don't look at it too closely or you'll go blind!
# characters are added as servername_charactername
# The list is updated periodically on think() using get_server_online()
online_characters = {}

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
    """Turns mentions into plain text.

    Works exactly like :func:`Message.clean_content`, except this can be used on any string.

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


def get_local_timezone() -> int:
    """Returns the server's local time zone

    :return: The UTC offset of the host's timezone.
    """
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    return (timegm(t) - timegm(u)) / 60 / 60


def most_frequent_color(image: Union[Image.Image, bytes]) -> Tuple[int, int, int]:
    """Gets the most frequent color in an image

    The most frequent color is the color that is found the most times in the image. Ties are handled arbitrarily.

    :param image: The image to check, can be either an Image object or the byte content.
    :return: A tuple with the RGB components of the most frequent color in the image."""
    if not isinstance(image, Image.Image):
        image = Image.open(io.BytesIO(bytearray(image)))
    w, h = image.size
    image = image.convert("RGBA")
    pixels = image.getcolors(w * h)
    most_frequent_pixel = sorted(pixels, key=lambda p: p[0], reverse=True)
    for count, (r, g, b, a) in most_frequent_pixel:
        if a < 125 or (r < 15 and g < 15 and b < 15) or (r > 254 and g > 254 and b > 254):
            continue
        return r, g, b


def average_color(image: Union[Image.Image, bytes]) -> Tuple[int, int, int]:
    """Gets the average image's color.

    The average color is the average value of each color component (RGB).

    :param image: The image to check, can be either an Image object or the byte content.
    :return: A tuple with the RGB components of the average color in the image."""
    if not isinstance(image, Image.Image):
        image = Image.open(io.BytesIO(bytearray(image)))
    image = image.convert("RGBA")
    pixels = image.getdata()

    rs = []
    gs = []
    bs = []
    for r, g, b, a in pixels:
        # Skip transparent pixels
        if a == 0:
            continue
        rs.append(r)
        gs.append(g)
        bs.append(b)
    return int(sum(rs) / len(rs)), int(sum(gs) / len(gs)), int(sum(bs) / len(bs))


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


def get_user_avatar(user: Union[discord.User, discord.Member]) -> str:
    """Gets the user's avatar url

    If they don't have an avatar set, the default avatar is returned.
x
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


async def safe_delete_message(message: discord.Message) -> bool:
    """Attempts to delete a message, failing silently if the bot couldn't delete it.

    This is used as a shortcut to attempt to delete a message when failure is not critical.
    The bot may fail to delete a message by another user if the bot lacks `Manage Messages` permission.
    It might also fail if the message no longer exist.

    Note that an exception will still be raised if something other than a message is passed.

    :return: If the message was deleted or not."""
    try:
        await message.delete()
        return True
    except (discord.Forbidden, discord.NotFound):
        return False


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


