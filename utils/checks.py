from discord.ext import commands

from config import owner_ids, mod_ids


# Checks if the user is the owner of the bot
# Bot owner can pass any checks
def is_owner():
    def predicate(ctx):
        author = ctx.message.author
        return author.id in owner_ids
    return commands.check(predicate)


def is_mod():
    def predicate(ctx):
        author = ctx.message.author
        return author.id in mod_ids or author.id in owner_ids
    return commands.check(predicate)


# Checks if the user is a server admin
def is_admin():
    def predicate(ctx):
        channel = ctx.message.channel
        author = ctx.message.author
        if channel.is_private:
            return False
        return channel.permissions_for(author).manage_server or author.id in owner_ids
    return commands.check(predicate)
