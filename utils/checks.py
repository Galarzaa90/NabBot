from discord.ext import commands

from utils.config import config
from utils.discord import is_lite_mode


# Checks
def is_owner():
    """Check if the author is the bot's owner"""
    async def predicate(ctx):
        return await is_owner_check(ctx)
    return commands.check(predicate)


def is_admin():
    """Checks if the author has administrator permission"""
    async def predicate(ctx):
        return await is_owner_check(ctx) or await check_guild_permissions(ctx, {'administrator': True})
    return commands.check(predicate)


def is_mod():
    """Checks if the author has manage channel permissions

    Mods are based on channel"""
    async def predicate(ctx):
        return await is_owner_check(ctx) or (await check_permissions(ctx, {'manage_channels': True}) and
                                             ctx.guild is not None)
    return commands.check(predicate)


def is_not_lite():
    """Checks if the bot is not running in lite mode"""
    def predicate(ctx):
        return not is_lite_mode(ctx)
    return commands.check(predicate)


# Check auxiliary functions
async def check_permissions(ctx, perms, *, check=all):
    if await ctx.bot.is_owner(ctx.author):
        return True

    permissions = ctx.channel.permissions_for(ctx.author)
    return check(getattr(permissions, name, None) == value for name, value in perms.items())


async def check_guild_permissions(ctx, perms, *, check=all):
    if await ctx.bot.is_owner(ctx.author):
        return True

    if ctx.guild is None:
        return False

    permissions = ctx.author.guild_permissions
    return check(getattr(permissions, name, None) == value for name, value in perms.items())


async def is_owner_check(ctx):
    return ctx.message.author.id in config.owner_ids or await ctx.bot.is_owner(ctx.author)
