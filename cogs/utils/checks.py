from discord.ext import commands

from . import config, context, errors


# region Checks (Valid as decorators)

def owner_only():
    """Command can only be executed by the bot owner."""
    async def predicate(ctx):
        return await is_owner(ctx)
    return commands.check(predicate)


def server_admin_only():
    """Command can only be executed by a server administrator."""
    async def predicate(ctx):
        return await check_guild_permissions(ctx, {'administrator': True}) or await is_owner(ctx)
    return commands.check(predicate)


def server_mod_only():
    """Command can only be used by users with manage guild permissions."""
    async def predicate(ctx):
        return await check_guild_permissions(ctx, {'manage_guild': True}) or await is_owner(ctx)
    return commands.check(predicate)


def server_mod_somewhere():
    """Command can only be used by users with manage guild permissions in any guild."""
    async def predicate(ctx):
        ret = await is_owner(ctx)
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


def channel_mod_only():
    """Command can only be used by users with manage channel permissions."""
    async def predicate(ctx):
        return await is_owner(ctx) or (await check_permissions(ctx, {'manage_channels': True}) and
                                       ctx.guild is not None)
    return commands.check(predicate)


def channel_mod_somewhere():
    """Command can only be used by users with manage channel permissions in any guild."""
    async def predicate(ctx):
        ret = await is_owner(ctx)
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


def tracking_world_only():
    """Command can only be used if the current server is tracking a world.

    This check implies that the command can only be used in server channels
    """
    def predicate(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command cannot be used in private messages.")
        if not ctx.bot.tracked_worlds.get(ctx.guild.id):
            raise errors.NotTracking("This server is not tracking any worlds.")
        return True
    return commands.check(predicate)


def tracking_world_somewhere():
    """Command can only be used if the user is in any server tracking a world.

    If used in a server's channel, only that server is considered
    If used on a private message, all servers are considered

    Similar to tracking_world_only but allows PM usage.
    This check may be slow and shouldn't be used much"""
    def predicate(ctx):
        if ctx.guild is not None and not ctx.bot.tracked_worlds.get(ctx.guild.id):
            raise errors.NotTracking("This server is not tracking any worlds.")
        if not len(ctx.bot.get_user_worlds(ctx.author.id)) > 0:
            raise errors.NotTracking("You're not in any server tracking a world.")
        return True

    return commands.check(predicate)


def can_embed():
    """Command requires embed links permissions to display it's contents."""
    def predicate(ctx: context.NabCtx):
        if not ctx.bot_permissions.embed_links:
            raise errors.CannotEmbed()
        return True
    return commands.check(predicate)


def not_lite_only():
    """Command cannot be used in lite servers."""
    def predicate(ctx: context.NabCtx):
        return not ctx.is_lite
    return commands.check(predicate)


def has_permissions(*, check=all, **perms):
    """Command can only be used if both the user and bot have the permissions."""
    async def pred(ctx):
        return await check_permissions(ctx, perms, check=check)
    return commands.check(pred)


def has_guild_permissions(**perms):
    """Command can only be used if the user has the provided guild permissions."""
    def predicate(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command cannot be used in private messages.")

        permissions = ctx.author.guild_permissions

        missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

        if not missing:
            return True

        raise commands.MissingPermissions(missing)

    return commands.check(predicate)
# endregion


# region Auxiliary functions (Not valid decorators)
async def check_permissions(ctx, perms, *, check=all):
    """Checks if the user has the specified permissions in the current channel."""
    if await ctx.bot.is_owner(ctx.author):
        return True

    permissions = ctx.channel.permissions_for(ctx.author)
    return check(getattr(permissions, name, None) == value for name, value in perms.items())


async def check_guild_permissions(ctx, perms, *, check=all):
    """Checks if the user has the specified permissions in the current guild."""
    if not ctx.guild:
        raise commands.NoPrivateMessage("This command cannot be used in private messages.")

    if await ctx.bot.is_owner(ctx.author):
        return True

    permissions = ctx.author.guild_permissions
    return check(getattr(permissions, name, None) == value for name, value in perms.items())


async def is_owner(ctx):
    """Checks if the user is an owner."""
    return ctx.author.id in config.owner_ids or await ctx.bot.is_owner(ctx.author)
# endregion
