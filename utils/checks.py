from discord.ext import commands

from config import owner_ids, mod_ids


def check_is_owner(message):
    return message.author.id in owner_ids


def is_owner():
    return commands.check(lambda ctx: check_is_owner(ctx.message))


def check_is_mod(message):
    return message.author.id in mod_ids or message.author.id in owner_ids


def is_mod():
    return commands.check(lambda ctx: check_is_mod(ctx.message))