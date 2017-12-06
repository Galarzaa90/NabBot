from discord.ext import commands

from config import owner_ids, mod_ids
from utils.discord import is_lite_mode


# Checks if the user is the owner of the bot
# Bot owner can pass any checks


def is_owner_check(ctx):
    return ctx.message.author.id in owner_ids


def is_owner():
    return commands.check(is_owner_check)


def is_mod_check(ctx):
    return ctx.message.author.id in mod_ids


def is_mod():
    def predicate(ctx):
        return is_owner_check(ctx) or is_mod_check(ctx) or is_admin_check(ctx)
    return commands.check(predicate)


def is_admin_check(ctx):
    author = ctx.message.author
    return len(ctx.bot.get_user_admin_guilds(author.id)) > 0 or is_owner_check(ctx)


# Checks if the user is a server admin
def is_admin():
    def predicate(ctx):
        return is_admin_check(ctx) or is_owner_check(ctx)
    return commands.check(predicate)


# Checks if the bot is not ruining in lite mode
def is_not_lite():
    def predicate(ctx):
        return not is_lite_mode(ctx)
    return commands.check(predicate)