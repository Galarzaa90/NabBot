import functools
import re

import discord
from discord.ext import commands

from cogs.utils.context import NabCtx

TIBIA_CASH_PATTERN = re.compile(r'(\d*\.?\d*)k*$')


class InsensitiveMember(commands.IDConverter):
    """Converts to a :class:`discord.Member` or :class:`discord.User` object.

    This class replicates :class:`discord.ext.commands.MemberConverter`, but the lookup is case insensitive.

    Lookup order:
    1. By ID.
    2. By mention.
    3. By name (case insensitive)."""
    async def convert(self, ctx: NabCtx, argument):
        member = ctx.bot.get_member(argument, ctx.guild)
        if member is None:
            raise commands.BadArgument('Member "{}" not found.'.format(argument))
        return member


class ChannelOrMember(commands.Converter):
    """Converts to a TextChannel or Member object."""
    async def convert(self, ctx, argument):
        try:
            return await commands.TextChannelConverter().convert(ctx, argument)
        except commands.BadArgument:
            return await InsensitiveMember().convert(ctx, argument)


class InsensitiveRole(commands.IDConverter):
    """Convert to a :class:`discord.Role`. object.

    This class replicates :class:`discord.ext.commands.RoleConverter`, but the lookup is case insensitive.

    Lookup order:
    1. By ID.
    2. By mention.
    3. By name (case insensitive)."""

    async def convert(self, ctx, argument) -> discord.Role:
        argument = argument.replace("\"", "")
        guild = ctx.guild
        if not guild:
            raise commands.NoPrivateMessage()

        match = self._get_id_match(argument) or re.match(r'<@&([0-9]+)>$', argument)
        if match:
            result = guild.get_role(int(match.group(1)))
        else:
            result = discord.utils.find(lambda r: r.name.lower() == argument.lower(), guild.roles)
        if result is None:
            raise commands.BadArgument('Role "{}" not found.'.format(argument))
        return result


class BadTime(commands.BadArgument):
    pass


class BadStamina(commands.BadArgument):
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

        if self.seconds > (60*60*24*60):
            raise BadTime("That's a bit too far in the future... Try less than 60 days.")


stamina_pattern = re.compile(r"(\d{1,2}):(\d{1,2})")


@functools.total_ordering
class Stamina:
    def __init__(self, argument):
        match = stamina_pattern.match(argument)
        if not match:
            raise BadStamina("Invalid stamina format, expected: `hh:mm`")
        self.hours = int(match.group(1))
        self.minutes = int(match.group(2))
        if self.minutes >= 60:
            raise BadStamina("Invalid stamina, minutes can't be 60 or greater.")
        if self.hours > 42:
            raise BadStamina("Invalid stamina, can't have more than 42 hours.")

    @property
    def seconds(self):
        return ((self.hours*60) + self.minutes) * 60

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.seconds == other.seconds
        return False

    def __lt__(self, other):
        return self.seconds < other.seconds


class TibiaNumber(int):
    """Parses numbers allowing the use of 'k' as a thousand suffix.

    The output is an integer, so decimals will be truncated after multiplying.

    Examples:
        24k -> 24000
        1.2kk -> 1200000
        3435k -> 3435000
        1.4 -> 1
    """
    def __new__(cls, argument):
        try:
            return super().__new__(int, argument)
        except ValueError:
            argument = argument.replace(",", "").strip().lower()
            m = TIBIA_CASH_PATTERN.match(argument)
            if not m or not m.group(1):
                raise commands.BadArgument(f"`{argument}` is not a valid number.")
            num = float(m.group(1))
            k_count = argument.count("k")
            num *= pow(1000, k_count)
            return int(num)
