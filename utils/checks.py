import discord
from discord.ext import commands

from config import owner_ids, mod_ids, main_server, lite_servers
from utils.discord import get_user_admin_guilds, is_private


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
    return len(get_user_admin_guilds(ctx.bot, author.id)) > 0 or is_owner_check(ctx)


# Checks if the user is a server admin
def is_admin():
    def predicate(ctx):
        return is_admin_check(ctx) or is_owner_check(ctx)
    return commands.check(predicate)


# Checks if the user belongs to main_server and channel is in main_server
def is_main_server():
    def predicate(ctx):
        if ctx.message.author.id in owner_ids:
            return True
        member = discord.utils.get(ctx.bot.get_all_members(), guild__id=main_server)
        if member is None:
            return False
        if not is_private(ctx.message.channel) and not ctx.message.guild.id == main_server:
            return False
        return True
    return commands.check(predicate)


# Checks if the bot is not ruining in lite mode
def is_not_lite():
    def predicate(ctx):
        return ctx.guild.id not in lite_servers
    return commands.check(predicate)