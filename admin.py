import asyncio
import re

import discord
from discord.ext import commands

from config import lite_mode, welcome_pm
from utils import checks
from utils.database import *
from utils.tibia import tibia_worlds


class Admin:
    """Commands for server owners and admins"""
    def __init__(self, bot: discord.Client):
        self.bot = bot

    @commands.command(name="setworld", pass_context=True, no_pm=True)
    @checks.is_admin()
    @checks.is_not_lite()
    @asyncio.coroutine
    def set_world(self, ctx: commands.Context, *, world: str = None):
        """Sets this server's Tibia world.

        If no world is passed, it shows this server's current assigned world."""
        server_id = ctx.message.server.id
        if world is None:
            current_world = tracked_worlds.get(server_id, None)
            if current_world is None:
                yield from self.bot.say("This server has no tibia world assigned.")
            else:
                yield from self.bot.say("This server has **{0}** assigned.".format(current_world))
            return

        if world.lower() in ["clear", "none", "delete", "remove"]:
            yield from self.bot.say("Are you sure you want to delete this server's tracked world? `yes/no`")
            reply = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                         timeout=50.0)
            if reply is None:
                yield from self.bot.say("I guess you changed your mind...")
                return
            elif reply.content.lower() not in ["yes", "y"]:
                yield from self.bot.say("No changes were made then.")
                return
            c = userDatabase.cursor()
            try:
                c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'world'", (server_id,))
            finally:
                c.close()
                userDatabase.commit()
            yield from self.bot.say("This server's tracked world has been removed.")
            reload_worlds()
            return

        world = world.strip().capitalize()
        if world not in tibia_worlds:
            yield from self.bot.say("There's no world with that name.")
            return
        yield from self.bot.say("Are you sure you want to assign **{0}** to this server? "
                                "Previous worlds will be replaced.".format(world))
        reply = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                     timeout=50.0)
        if reply is None:
            yield from self.bot.say("I guess you changed your mind...")
            return
        elif reply.content.lower() not in ["yes", "y"]:
            yield from self.bot.say("No changes were made then.")
            return

        c = userDatabase.cursor()
        try:
            # Safer to just delete old entry and add new one
            c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'world'", (server_id,))
            c.execute("INSERT INTO server_properties(server_id, name, value) VALUES (?, 'world', ?)",
                      (server_id, world,))
            yield from self.bot.say("This server's world has been changed successfully.")
        finally:
            c.close()
            userDatabase.commit()
            reload_worlds()

    @commands.command(name="setwelcome", pass_context=True, no_pm=True)
    @checks.is_admin()
    @checks.is_not_lite()
    @asyncio.coroutine
    def set_welcome(self, ctx: commands.Context, *, message: str = None):
        """Changes the messages members get pmed when joining

        A part of the message is already fixed and cannot be changed, but the message can be extended

        Say "clear" to clear the current message.

        The following can be used to get dynamically replaced:
        {0.name} - The joining user's name
        {0.server.name} - The name of the server the user joined
        {0.server.owner.name} - The name of the owner of the server the member joined
        {0.server.owner.mention} - A mention to the owner of the server
        {1.user.name} - The name of the bot"""
        server_id = ctx.message.server.id
        if message is None:
            current_message = welcome_messages.get(server_id, None)
            if current_message is None:
                current_message = welcome_pm.format(ctx.message.author, self.bot)
                yield from self.bot.say("This server has no custom message, joining members get the default message:\n"
                                        "----------\n{0}".format(current_message))
            else:
                current_message = (welcome_pm + "\n" + current_message).format(ctx.message.author, self.bot)
                yield from self.bot.say("This server has the following welcome message:\n"
                                        "----------\n``The first two lines can't be changed``\n{0}"
                                        .format(current_message))
            return
        if message.lower() in ["clear", "none", "delete", "remove"]:
            yield from self.bot.say("Are you sure you want to delete this server's welcome message? `yes/no`\n"
                                    "The default welcome message will still be shown.")
            reply = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                         timeout=50.0)

            if reply is None:
                yield from self.bot.say("I guess you changed your mind...")
                return
            elif reply.content.lower() not in ["yes", "y"]:
                yield from self.bot.say("No changes were made then.")
                return
            c = userDatabase.cursor()
            try:
                c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'welcome'", (server_id,))
            finally:
                c.close()
                userDatabase.commit()
            yield from self.bot.say("This server's welcome message was removed.")
            reload_welcome_messages()
            return

        if len(message) > 1200:
            yield from self.bot.say("This message exceeds the character limit! ({0}/{1}".format(len(message), 1200))
            return
        try:
            complete_message = (welcome_pm+"\n"+message).format(ctx.message.author, self.bot)
        except Exception as e:
            yield from self.bot.say("There is something wrong with your message.\n```{0}```".format(e))
            return

        yield from self.bot.say("Are you sure you want this as your private welcome message?\n"
                                "----------\n``The first two lines can't be changed``\n{0}"
                                .format(complete_message))
        reply = yield from self.bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                     timeout=120.0)
        if reply is None:
            yield from self.bot.say("I guess you changed your mind...")
            return
        elif reply.content.lower() not in ["yes", "y"]:
            yield from self.bot.say("No changes were made then.")
            return

        c = userDatabase.cursor()
        try:
            # Safer to just delete old entry and add new one
            c.execute("DELETE FROM server_properties WHERE server_id = ? AND name = 'welcome'", (server_id,))
            c.execute("INSERT INTO server_properties(server_id, name, value) VALUES (?, 'welcome', ?)",
                      (server_id, message,))
            yield from self.bot.say("This server's welcome message has been changed successfully.")
        finally:
            c.close()
            userDatabase.commit()
            reload_welcome_messages()


def setup(bot):
    bot.add_cog(Admin(bot))
