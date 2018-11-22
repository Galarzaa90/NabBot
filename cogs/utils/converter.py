import re

import discord
from discord.ext.commands import BadArgument, IDConverter, NoPrivateMessage


class InsensitiveRole(IDConverter):
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
            raise NoPrivateMessage()

        match = self._get_id_match(argument) or re.match(r'<@&([0-9]+)>$', argument)
        if match:
            result = guild.get_role(int(match.group(1)))
        else:
            result = discord.utils.find(lambda r: r.name.lower() == argument.lower(), guild.roles)
        if result is None:
            raise BadArgument('Role "{}" not found.'.format(argument))
        return result