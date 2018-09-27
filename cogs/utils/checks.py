from discord.ext import commands
from discord.ext.commands import MissingPermissions

from . import config
from .context import NabCtx


class CannotEmbed(commands.CheckFailure):
    pass


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
    """Checks if the author has manage guild permissions"""
    async def predicate(ctx):
        return await is_owner_check(ctx) or (await check_guild_permissions(ctx, {'manage_guild': True}) and
                                             ctx.guild is not None)
    return commands.check(predicate)


def is_mod_somewhere():
    """Checks if the author has manage guild permissions in any guild"""
    async def predicate(ctx):
        ret = await is_owner_check(ctx)
        if ret:
            return True
        if ctx.guild is not None:
            return await check_guild_permissions(ctx, {'manage_guild': True})
        for guild in ctx.bot.get_user_guilds(ctx.author.id):
            member = guild.get_member(ctx.author.id)
            permissions = member.guild_permissions
            if permissions.administrator or permissions.manage_guild:
                return True
        return False
    return commands.check(predicate)


def is_channel_mod():
    """Checks if the author has manage channel permissions"""
    async def predicate(ctx):
        return await is_owner_check(ctx) or (await check_permissions(ctx, {'manage_channels': True}) and
                                             ctx.guild is not None)
    return commands.check(predicate)


def is_channel_mod_somewhere():
    """Checks if the author has manage guild permissions in any guild"""
    async def predicate(ctx):
        ret = await is_owner_check(ctx)
        if ret:
            return True
        if ctx.guild is not None:
            return await check_guild_permissions(ctx, {'manage_channels': True})
        for guild in ctx.bot.get_user_guilds(ctx.author.id):
            member = guild.get_member(ctx.author.id)
            permissions = member.guild_permissions
            if permissions.administrator or permissions.manage_channels:
                return True
        return False
    return commands.check(predicate)


def is_tracking_world():
    """Checks if the current server is tracking a tibia world

    This check implies that the command can only be used in server channels
    """
    def predicate(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command cannot be used in private messages.")
        return ctx.guild.id in ctx.bot.tracked_worlds
    return commands.check(predicate)


def is_in_tracking_world():
    """Checks if any of the shared servers track a world

    If used in a server's channel, only that server is considered
    If used on a private message, all servers are considered

    Similar to is_tracking_world but allows PM usage.
    This check may be slow and shouldn't be used much"""
    def predicate(ctx):
        if ctx.guild is not None:
            return ctx.guild.id in ctx.bot.tracked_worlds
        return len(ctx.bot.get_user_worlds(ctx.author.id)) > 0

    return commands.check(predicate)


def can_embed():
    def predicate(ctx: NabCtx):
        if not ctx.bot_permissions.embed_links:
            raise CannotEmbed()
        return True
    return commands.check(predicate)


def is_not_lite():
    """Checks if the bot is not running in lite mode"""
    def predicate(ctx: NabCtx):
        return not ctx.is_lite
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
    return ctx.author.id in config.owner_ids or await ctx.bot.is_owner(ctx.author)


def has_guild_permissions(**perms):
    def predicate(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command cannot be used in private messages.")

        permissions = ctx.author.guild_permissions

        missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

        if not missing:
            return True

        raise MissingPermissions(missing)

    return commands.check(predicate)
