import asyncio
import os
import platform
import random
import re
import sys
import time
import traceback
from datetime import timedelta, datetime

import discord
import psutil
from discord.ext import commands

from config import *
from utils.database import init_database, userDatabase, reload_worlds
from utils.discord import get_member, send_log_message, get_region_string, get_channel_by_name, get_user_servers, \
    clean_string, get_role_list, get_member_by_name
from utils.general import command_list, join_list, get_uptime, TimeString, \
    single_line, is_numeric, getLogin
from utils.general import log
from utils.help_format import NabHelpFormat
from utils.messages import decode_emoji, deathmessages_player, deathmessages_monster, EMOJI, levelmessages, \
    weighedChoice, formatMessage
from utils.tibia import get_server_online, get_character, ERROR_NETWORK, ERROR_DOESNTEXIST, get_character_deaths, \
    get_voc_abb

description = '''Mission: Destroy all humans.'''
bot = commands.Bot(command_prefix=["/"], description=description, pm_help=True, formatter=NabHelpFormat())
# We remove the default help command so we can override it
bot.remove_command("help")


@bot.event
@asyncio.coroutine
def on_ready():
    bot.load_extension("tibia")
    bot.load_extension("mod")
    bot.load_extension("owner")
    bot.load_extension("admin")
    print('Logged in as')
    print(bot.user)
    print(bot.user.id)
    print('------')
    log.info('Bot is online and ready')

    # Populate command_list
    for command_name, command in bot.commands.items():
        command_list.append(command_name)

    # Notify reset author
    if len(sys.argv) > 1:
        user = get_member(bot, sys.argv[1])
        sys.argv[1] = 0
        if user is not None:
            yield from bot.send_message(user, "Restart complete")

    # Background tasks
    bot.loop.create_task(game_update())
    bot.loop.create_task(events_announce())
    bot.loop.create_task(scan_deaths())
    bot.loop.create_task(scan_online_chars())


@bot.event
@asyncio.coroutine
def on_command(command, ctx):
    """Called when a command is called. Used to log commands on a file."""
    if ctx.message.channel.is_private:
        destination = 'PM'
    else:
        destination = '#{0.channel.name} ({0.server.name})'.format(ctx.message)
    message_decoded = decode_emoji(ctx.message.content)
    log.info('Command by {0} in {1}: {2}'.format(ctx.message.author.display_name, destination, message_decoded))


@bot.event
@asyncio.coroutine
def on_command_error(error, ctx):
    if isinstance(error, commands.errors.CommandNotFound):
        return
    elif isinstance(error, commands.NoPrivateMessage):
        yield from bot.send_message(ctx.message.author, "This command cannot be used in private messages.")
    elif isinstance(error, commands.CommandInvokeError):
        print('In {0.command.qualified_name}:'.format(ctx), file=sys.stderr)
        traceback.print_tb(error.original.__traceback__)
        print('{0.__class__.__name__}: {0}'.format(error.original), file=sys.stderr)


@bot.event
@asyncio.coroutine
def on_message(message):
    """Called every time a message is sent on a visible channel.

    This is used to make commands case insensitive."""
    # Ignore if message is from any bot
    if message.author.bot:
        return

    split = message.content.split(" ", 1)
    if split[0][:1] == "/" and split[0].lower()[1:] in command_list:
        if len(split) > 1:
            message.content = split[0].lower()+" "+split[1]
        else:
            message.content = message.content.lower()
    if len(split) == 2:
        if message.author.id != bot.user.id and (not split[0].lower()[1:] in command_list or not split[0][:1] == "/")\
                and not message.channel.is_private and message.channel.name == ask_channel_name:
            yield from bot.delete_message(message)
            return
    else:
        # Delete messages in askchannel
        if message.author.id != bot.user.id \
                and (not message.content.lower()[1:] in command_list or not message.content[:1] == "/") \
                and not message.channel.is_private \
                and message.channel.name == ask_channel_name:
            yield from bot.delete_message(message)
            return
    yield from bot.process_commands(message)


@bot.event
@asyncio.coroutine
def on_server_join(server: discord.Server):
    log.info("Nab Bot added to server: {0.name} (ID: {0.id])".format(server))
    message = "Hello! I'm now in **{0.name}**. To see my available commands, type \help\n" \
              "I will reply to commands from any channel I can see, but if you create a channel called *{1}*, I will " \
              "give longer replies and more information there.\n" \
              "If you want a server log channel, create a channel called *{2}*, I will post logs in there. You might " \
              "want to make it private though."
    formatted_message = message.format(server, ask_channel_name, log_channel_name)
    yield from bot.send_message(server.owner, formatted_message)


@bot.event
@asyncio.coroutine
def on_member_join(member: discord.Member):
    """Called every time a member joins a server visible by the bot."""
    log.info("{0.display_name} (ID: {0.id}) joined {0.server.name}".format(member))
    if lite_mode:
        return
    message = "Welcome to **{0.server.name}**! I'm **{1.user.name}**, to learn more about my commands type `/help`\n" \
              "Start by telling me who is your Tibia character, say **/im *character_name*** so I can begin tracking " \
              "your level ups and deaths!"
    yield from bot.send_message(member, message.format(member, bot))
    yield from bot.send_message(member.server, "Look who just joined! Welcome {0.mention}!".format(member))
    yield from send_log_message(bot, member.server, "{0.mention} joined.".format(member))


@bot.event
@asyncio.coroutine
def on_member_remove(member):
    """Called when a member leaves or is kicked from a server."""
    log.info("{0.display_name} (ID:{0.id}) left or was kicked from {0.server.name}".format(member))
    yield from send_log_message(bot, member.server, "**{0.name}#{0.discriminator}** left or was kicked.".format(member))


@bot.event
@asyncio.coroutine
def on_member_ban(member):
    """Called when a member is banned from a server."""
    log.info("{0.display_name} (ID:{0.id}) was banned from {0.server.name}".format(member))
    yield from send_log_message(bot, member.server, "**{0.name}#{0.discriminator}** was banned.".format(member))


@bot.event
@asyncio.coroutine
def on_member_unban(server, user):
    """Called when a member is unbanned from a server"""
    log.info("{1.name} (ID:{1.id}) was unbanned from {0.name}".format(server, user))
    yield from send_log_message(bot, server, "**{0.name}#{0.discriminator}** was unbanned.".format(user))


@bot.event
@asyncio.coroutine
def on_message_delete(message):
    """Called every time a message is deleted."""
    if message.channel.name == ask_channel_name:
        return

    message_decoded = decode_emoji(message.content)
    log.info("A message by {0} was deleted. Message: '{1}'".format(message.author.display_name, message_decoded))
    for attachment in message.attachments:
        log.info(attachment)


@bot.event
@asyncio.coroutine
def on_message_edit(older_message, message):
    """Called every time a message is edited."""

    if older_message.author.id == bot.user.id:
        return

    older_message_decoded = decode_emoji(older_message.content)
    log.info("{0} has edited the message: '{1}'".format(older_message.author.display_name, older_message_decoded))
    for attachment in older_message.attachments:
        log.info(attachment)

    message_decoded = decode_emoji(message.content)
    log.info("New message: '{0}'".format(message_decoded))
    for attachment in message.attachments:
        log.info(attachment)


@bot.event
@asyncio.coroutine
def on_member_update(before: discord.Member, after: discord.Member):
    if before.nick != after.nick:
        reply = "{1.mention}: Changed his nickname from **{0.nick}** to **{1.nick}**".format(before, after)
        yield from send_log_message(bot, after.server, reply)
    elif before.name != after.name:
        reply = "{1.mention}: Changed his name from **{0.name}** to **{1.name}**".format(before, after)
        yield from send_log_message(bot, after.server, reply)
    return


@bot.event
@asyncio.coroutine
def on_server_update(before: discord.Server, after: discord.Server):
    if before.name != after.name:
        reply = "Server name changed from **{0.name}** to **{1.name}**".format(before, after)
        yield from send_log_message(bot, after, reply)
    elif before.region != after.region:
        reply = "Server region changed from {0} to {1}".format(get_region_string(before.region),
                                                               get_region_string(after.region))
        yield from send_log_message(bot, after, reply)


@asyncio.coroutine
def events_announce():
    if lite_mode:
        return
    yield from bot.wait_until_ready()
    while not bot.is_closed:
        """Announces when an event is close to starting."""
        first_announcement = 60*30
        second_announcement = 60*15
        third_announcement = 60*5
        c = userDatabase.cursor()
        try:
            channel = get_channel_by_name(bot, main_channel, server_id=main_server)
            # Current time
            date = time.time()
            # Find incoming events

            # First announcement
            c.execute("SELECT creator, start, name, id "
                      "FROM events "
                      "WHERE start < ? AND start > ? AND active = 1 AND status > 3 "
                      "ORDER by start ASC", (date+first_announcement+60, date+first_announcement,))
            results = c.fetchall()
            if len(results) > 0:
                for row in results:
                    author = "unknown" if get_member(bot, row["creator"]) is None else get_member(bot, row["creator"]).display_name
                    name = row["name"]
                    event_id = row["id"]
                    time_diff = timedelta(seconds=row["start"]-date)
                    days, hours, minutes = time_diff.days, time_diff.seconds//3600, (time_diff.seconds//60)%60
                    if days:
                        start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                    elif hours:
                        start = '{0} hours and {1} minutes'.format(hours, minutes)
                    else:
                        start = '{0} minutes'.format(minutes)

                    message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}.".format(name, author, start, event_id)
                    c.execute("UPDATE events SET status = 3 WHERE id = ?", (event_id,))
                    log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name, author, start, event_id))
                    yield from bot.send_message(channel, message)
                    # Send PM to subscribers:
                    c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (event_id,))
                    subscribers = c.fetchall()
                    if len(subscribers) > 0:
                        for subscriber in subscribers:
                            user = get_member(bot, subscriber["user_id"])
                            if user is None:
                                continue
                            yield from bot.send_message(user, message)
            # Second announcement
            c.execute("SELECT creator, start, name, id "
                      "FROM events "
                      "WHERE start < ? AND start > ? AND active = 1 AND status > 2 "
                      "ORDER by start ASC", (date+second_announcement+60, date+second_announcement,))
            results = c.fetchall()
            if len(results) > 0:
                for row in results:
                    author = "unknown" if get_member(bot, row["creator"]) is None else get_member(bot, row["creator"]).display_name
                    name = row["name"]
                    event_id = row["id"]
                    time_diff = timedelta(seconds=row["start"]-date)
                    days, hours, minutes = time_diff.days, time_diff.seconds//3600, (time_diff.seconds//60) % 60
                    if days:
                        start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                    elif hours:
                        start = '{0} hours and {1} minutes'.format(hours, minutes)
                    else:
                        start = '{0} minutes'.format(minutes)

                    message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}.".format(name, author, start, event_id)
                    c.execute("UPDATE events SET status = 2 WHERE id = ?", (event_id,))
                    log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name, author, start, event_id))
                    yield from bot.send_message(channel, message)
                    # Send PM to subscribers:
                    c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (event_id,))
                    subscribers = c.fetchall()
                    if len(subscribers) > 0:
                        for subscriber in subscribers:
                            user = get_member(bot, subscriber["user_id"])
                            if user is None:
                                continue
                            yield from bot.send_message(user, message)
            # Third announcement
            c.execute("SELECT creator, start, name, id "
                      "FROM events "
                      "WHERE start < ? AND start > ? AND active = 1 AND status > 1 "
                      "ORDER by start ASC", (date+third_announcement+60, date+third_announcement,))
            results = c.fetchall()
            if len(results) > 0:
                for row in results:
                    author = "unknown" if get_member(bot, row["creator"]) is None else get_member(bot, row["creator"]).display_name
                    name = row["name"]
                    event_id = row["id"]
                    time_diff = timedelta(seconds=row["start"]-date)
                    days, hours, minutes = time_diff.days, time_diff.seconds//3600, (time_diff.seconds//60) % 60
                    if days:
                        start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                    elif hours:
                        start = '{0} hours and {1} minutes'.format(hours, minutes)
                    else:
                        start = '{0} minutes'.format(minutes)

                    message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}!".format(name, author, start, event_id)
                    c.execute("UPDATE events SET status = 1 WHERE id = ?", (event_id,))
                    log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name, author, start, event_id))
                    yield from bot.send_message(channel, message)
                    # Send PM to subscribers:
                    c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (event_id,))
                    subscribers = c.fetchall()
                    if len(subscribers) > 0:
                        for subscriber in subscribers:
                            user = get_member(bot, subscriber["user_id"])
                            if user is None:
                                continue
                            yield from bot.send_message(user, message)
            # Last announcement
            c.execute("SELECT creator, start, name, id "
                      "FROM events "
                      "WHERE start < ? AND start > ? AND active = 1 AND status > 0 "
                      "ORDER by start ASC", (date+60,date,))
            results = c.fetchall()
            if len(results) > 0:
                for row in results:
                    author = "unknown" if get_member(bot, row["creator"]) is None else get_member(bot, row["creator"]).display_name
                    name = row["name"]
                    event_id = row["id"]
                    time_diff = timedelta(seconds=row["start"]-date)
                    days, hours, minutes = time_diff.days, time_diff.seconds//3600, (time_diff.seconds//60) % 60
                    if days:
                        start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                    elif hours:
                        start = '{0} hours and {1} minutes'.format(hours, minutes)
                    else:
                        start = '{0} minutes'.format(minutes)

                    message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting right now!".format(name, author, start, event_id)
                    c.execute("UPDATE events SET status = 0 WHERE id = ?", (event_id,))
                    log.info("Announcing event: {0} (by @{1},ID:{3}) - Starting ({2})".format(name, author, start, event_id))
                    yield from bot.send_message(channel, message)
                    # Send PM to subscribers:
                    c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (event_id,))
                    subscribers = c.fetchall()
                    if len(subscribers) > 0:
                        for subscriber in subscribers:
                            user = get_member(bot, subscriber["user_id"])
                            if user is None:
                                continue
                            yield from bot.send_message(user, message)
        except AttributeError:
            pass
        finally:
            userDatabase.commit()
            c.close()
        yield from asyncio.sleep(20)


@asyncio.coroutine
def scan_deaths():
    #################################################
    #             Nezune's cave                     #
    # Do not touch anything, enter at your own risk #
    #################################################
    if lite_mode:
        return
    yield from bot.wait_until_ready()
    while not bot.is_closed:
        yield from asyncio.sleep(death_scan_interval)
        if len(global_online_list) == 0:
            continue
        # Pop last char in queue, reinsert it at the beginning
        current_char = global_online_list.pop()
        global_online_list.insert(0, current_char)

        # Get rid of server name
        current_char = current_char.split("_", 1)[1]
        # Check for new death
        yield from check_death(current_char)



@asyncio.coroutine
def scan_online_chars():
    #################################################
    #             Nezune's cave                     #
    # Do not touch anything, enter at your own risk #
    #################################################
    if lite_mode:
        return
    yield from bot.wait_until_ready()
    while not bot.is_closed:
        yield from asyncio.sleep(online_scan_interval)
        if len(tibia_servers) == 0:
            continue
        # Pop last server in queue, reinsert it at the beginning
        current_server = tibia_servers.pop()
        tibia_servers.insert(0, current_server)

        # Get online list for this server
        current_server_online = yield from get_server_online(current_server)

        if len(current_server_online) > 0:
            # Open connection to users.db
            c = userDatabase.cursor()

            # Remove chars that are no longer online from the globalOnlineList
            offline_list = []
            for char in global_online_list:
                if char.split("_", 1)[0] == current_server:
                    offline = True
                    for server_char in current_server_online:
                        if server_char['name'] == char.split("_", 1)[1]:
                            offline = False
                            break
                    if offline:
                        offline_list.append(char)
            for now_offline_char in offline_list:
                global_online_list.remove(now_offline_char)
                # Check for deaths and level ups when removing from online list
                now_offline_char = yield from get_character(now_offline_char.split("_", 1)[1])
                if not (now_offline_char == ERROR_NETWORK or now_offline_char == ERROR_DOESNTEXIST):
                    c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?", (now_offline_char['name'],))
                    result = c.fetchone()
                    if result:
                        last_level = result["last_level"]
                        c.execute(
                            "UPDATE chars SET last_level = ? WHERE name LIKE ?",
                            (now_offline_char['level'], now_offline_char['name'],)
                        )
                        if now_offline_char['level'] > last_level > 0:
                            # Saving level up date in database
                            c.execute(
                                "INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",
                                (result["id"], now_offline_char['level'], time.time(),)
                            )
                            # Announce the level up
                            yield from announce_level(now_offline_char, now_offline_char['level'])
                    yield from check_death(now_offline_char['name'])

            # Add new online chars and announce level differences
            for server_char in current_server_online:
                c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?", (server_char['name'],))
                result = c.fetchone()
                if result:
                    # If its a stalked character
                    last_level = result["last_level"]
                    # We update their last level in the db
                    c.execute(
                        "UPDATE chars SET last_level = ? WHERE name LIKE ?",
                        (server_char['level'], server_char['name'],)
                    )

                    if not (current_server + "_" + server_char['name']) in global_online_list:
                        # If the character wasn't in the globalOnlineList we add them
                        # (We insert them at the beginning of the list to avoid messing with the death checks order)
                        global_online_list.insert(0, (current_server + "_" + server_char['name']))
                        # Since this is the first time we see them online we flag their last death time
                        # to avoid backlogged death announces
                        c.execute(
                            "UPDATE chars SET last_death_time = ? WHERE name LIKE ?",
                            (None, server_char['name'],)
                        )
                        yield from check_death(server_char['name'])

                    # Else we check for levelup
                    elif server_char['level'] > last_level > 0:
                        # Saving level up date in database
                        c.execute(
                            "INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",
                            (result["id"], server_char['level'], time.time(),)
                        )
                        # Announce the level up
                        char = yield from get_character(server_char['name'])
                        yield from announce_level(char, server_char['level'])

            # Close cursor and commit changes
            userDatabase.commit()
            c.close()


@asyncio.coroutine
def check_death(character):
    """Gets death list for a character (from database)

    Only the first death is needed"""
    character_deaths = yield from get_character_deaths(character, True)

    if (type(character_deaths) is list) and len(character_deaths) > 0:
        c = userDatabase.cursor()

        c.execute("SELECT name, last_death_time, id FROM chars WHERE name LIKE ?", (character,))
        result = c.fetchone()
        if result:
            last_death = character_deaths[0]
            db_last_death_time = result["last_death_time"]
            # If the db lastDeathTime is None it means this is the first time we're seeing them online
            # so we just update it without announcing deaths
            if db_last_death_time is None:
                c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?", (last_death['time'], character,))
            # Else if the last death's time doesn't match the one in the db
            elif db_last_death_time != last_death['time']:
                # Update the lastDeathTime for this char in the db
                c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?", (last_death['time'], character,))
                # Saving death info in database
                c.execute(
                    "INSERT INTO char_deaths (char_id,level,killer,byplayer,date) VALUES(?,?,?,?,?)",
                    (result["id"], int(last_death['level']), last_death['killer'], last_death['byPlayer'], time.time(),)
                )
                # Announce the death
                yield from announce_death(character, last_death['time'], last_death['level'], last_death['killer'], last_death['byPlayer'])

        # Close cursor and commit changes
        userDatabase.commit()
        c.close()


@asyncio.coroutine
def announce_death(char_name, death_time, death_level, death_killer, death_by_player):
    if int(death_level) < announceTreshold:
        # Don't announce for low level players
        return

    log.info("Announcing death: {0}({1}) | {2}".format(char_name, death_level, death_killer))
    char = yield from get_character(char_name)
    # Failsafe in case getPlayer fails to retrieve player data
    if type(char) is not dict:
        log.warning("Error in announceDeath, failed to getPlayer(" + char_name + ")")
        return

    if not(char['world'] in tibia_servers):
        # Don't announce for players in non-tracked worlds
        return
    # Choose correct pronouns
    pronoun = ["he", "his", "him"] if char['gender'] == "male" else ["she", "her", "her"]

    channel = get_channel_by_name(bot, main_channel, server_id=main_server)
    # Find killer article (a/an)
    death_killer_article = ""
    if not death_by_player:
        death_killer_article = death_killer.split(" ", 1)
        if death_killer_article[0] in ["a", "an"] and len(death_killer_article) > 1:
            death_killer = death_killer_article[1]
            death_killer_article = death_killer_article[0]+" "
        else:
            death_killer_article = ""
    # Select a message
    message = weighedChoice(deathmessages_player, char['vocation'], int(death_level)) if death_by_player else weighedChoice(deathmessages_monster, char['vocation'], int(death_level), death_killer)
    # Format message with death information
    deathInfo = {'charName': char_name, 'deathTime': death_time, 'deathLevel': death_level, 'deathKiller': death_killer,
                 'deathKillerArticle': death_killer_article, 'pronoun1': pronoun[0], 'pronoun2': pronoun[1],
                 'pronoun3': pronoun[2]}
    message = message.format(**deathInfo)
    # Format extra stylization
    message = formatMessage(message)
    message = EMOJI[":skull_crossbones:"] + " " + message

    yield from bot.send_message(channel, message[:1].upper()+message[1:])


@asyncio.coroutine
def announce_level(char, new_level):
    # Don't announce low level players
    if int(new_level) < announceTreshold:
        return
    if type(char) is not dict:
        log.error("Error in announceLevel, invalid character passed")
        return
    log.info("Announcing level up: {0} ({1})".format(char["name"], new_level))

    # Get pronouns based on gender
    pronoun = ["he", "his", "him"] if char['gender'] == "male" else ["she", "her", "her"]

    channel = get_channel_by_name(bot, main_channel, server_id=main_server)

    # Select a message
    message = weighedChoice(levelmessages, char['vocation'], int(new_level))
    # Format message with level information
    level_info = {'charName': char["name"], 'newLevel': new_level, 'pronoun1': pronoun[0], 'pronoun2': pronoun[1],
                 'pronoun3': pronoun[2]}
    message = message.format(**level_info)
    # Format extra stylization
    message = formatMessage(message)
    message = EMOJI[":star2:"]+" "+message

    yield from bot.send_message(channel, message)


# Bot commands
@bot.command(pass_context=True)
@asyncio.coroutine
def help(ctx, *commands: str):
    """Shows this message."""
    _mentions_transforms = {
        '@everyone': '@\u200beveryone',
        '@here': '@\u200bhere'
    }
    _mention_pattern = re.compile('|'.join(_mentions_transforms.keys()))

    bot = ctx.bot
    destination = ctx.message.channel if ctx.message.channel.name == ask_channel_name else ctx.message.author

    def repl(obj):
        return _mentions_transforms.get(obj.group(0), '')

    # help by itself just lists our own commands.
    if len(commands) == 0:
        pages = bot.formatter.format_help_for(ctx, bot)
    elif len(commands) == 1:
        # try to see if it is a cog name
        name = _mention_pattern.sub(repl, commands[0])
        command = None
        if name in bot.cogs:
            command = bot.cogs[name]
        else:
            command = bot.commands.get(name)
            if command is None:
                yield from bot.send_message(destination, bot.command_not_found.format(name))
                return

        pages = bot.formatter.format_help_for(ctx, command)
    else:
        name = _mention_pattern.sub(repl, commands[0])
        command = bot.commands.get(name)
        if command is None:
            yield from bot.send_message(destination, bot.command_not_found.format(name))
            return

        for key in commands[1:]:
            try:
                key = _mention_pattern.sub(repl, key)
                command = command.commands.get(key)
                if command is None:
                    yield from bot.send_message(destination, bot.command_not_found.format(key))
                    return
            except AttributeError:
                yield from bot.send_message(destination, bot.command_has_no_subcommands.format(command, key))
                return

        pages = bot.formatter.format_help_for(ctx, command)

    for page in pages:
        yield from bot.send_message(destination, page)


@bot.command(pass_context=True, description='For when you wanna settle the score some other way')
@asyncio.coroutine
def choose(ctx, *choices: str):
    if choices is None:
        return
    """Chooses between multiple choices."""
    user = ctx.message.author
    yield from bot.say('Alright, **@{0}**, I choose: "{1}"'.format(user.display_name, random.choice(choices)))


@bot.command(pass_context=True, aliases=["i'm", "iam"], hidden=lite_mode)
@asyncio.coroutine
def im(ctx, *, char_name: str):
    """Lets you add your first tibia character(s) for the bot to track.

    If you need to add any more characters or made a mistake, please message an admin."""

    if lite_mode:
        return

    # This is equivalent to someone using /stalk addacc on themselves.
    # To avoid abuse it will only work on users who have joined recently and have no characters added to their account.

    user = ctx.message.author
    try:
        c = userDatabase.cursor()
        mod_list = owner_ids+mod_ids
        admins_message = join_list(["**" + get_member(bot, admin, ctx.message.server).mention + "**" for admin in mod_list], ", ", " or ")
        servers_message = join_list(["**" + server + "**" for server in tibia_servers], ", ", " or ")
        not_allowed_message = ("I'm sorry, {0.mention}, this command is reserved for new users, if you need any help "
                              "adding characters to your account please message {1}.").format(user, admins_message)

        # Check that this user doesn't exist or has no chars added to it yet.
        c.execute("SELECT id from users WHERE id = ?", (user.id,))
        result = c.fetchone()
        if result is not None:
            c.execute("SELECT name,user_id FROM chars WHERE user_id LIKE ?", (user.id,))
            result = c.fetchone()
            if result is not None:
                yield from bot.say(not_allowed_message)
                return
        else:
            # Add the user if it doesn't exist
            c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))

        char = yield from get_character(char_name)
        if type(char) is not dict:
            if char == ERROR_NETWORK:
                yield from bot.say("I couldn't fetch the character, please try again.")
            elif char == ERROR_DOESNTEXIST:
                yield from bot.say("That character doesn't exists.")
            return
        chars = char['chars']
        # If the char is hidden,we still add the searched character
        if len(chars) == 0:
            chars = [char]
        skipped = []
        updated = []
        added = []
        for char in chars:
            if char['world'] not in tibia_servers:
                skipped.append(char)
                continue
            c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?", (char['name'],))
            result = c.fetchone()
            if result is not None:
                owner = get_member(bot, result["user_id"])
                if owner is None:
                    updated.append({'name': char['name'], 'world': char['world'], 'prevowner': result["user_id"],
                                    'guild': char.get("guild", "No guild")})
                    continue
                else:
                    reply = "Sorry but a character in that account was already claimed by **{0.mention}**.\n" \
                            "Maybe you made a mistake? Message {1} if you need any help!"
                    yield from bot.say(reply.format(owner, admins_message))
                    return
            char = yield from get_character(char['name'])
            char["guild"] = char.get("guild", "No guild")
            added.append(char)
        if len(skipped) == len(chars):
            reply = "Sorry, I couldn't find any characters in that account from the servers I track ({1}).\n" \
                    "Maybe you made a mistake? Message {1} if you need help!"
            yield from bot.say(reply.format(servers_message, admins_message))
            return
        for char in updated:
            c.execute("UPDATE chars SET user_id = ? WHERE name LIKE ?", (user.id, char['name']))
            log.info("Character {0} was reasigned to {1.display_name} (ID: {1.id}) from /im. (Previous owner (ID: {2}) was not found)".format(char['name'], user, char['prevowner']))
        for char in added:
            c.execute(
                "INSERT INTO chars (name,last_level,vocation,user_id, world) VALUES (?,?,?,?,?)",
                (char['name'], char['level']*-1, char['vocation'], user.id, char["world"])
            )
            log.info("Character {0} was assigned to {1.display_name} (ID: {1.id}) from /im.".format(char['name'], user))

        reply = "Thanks {0.mention}! I have added the following character(s) to your account: {1}\n" \
                "From now on I will track level ups and deaths for you, if you need to add any more characters " \
                "please message {2}"
        added_chars = join_list(["**" + char['name'] + "**" for char in added + updated], ", ", " and ")
        yield from bot.say(reply.format(user, added_chars, admins_message))

        log_entry = "{0.mention} registered the following characters:\n\t".format(ctx.message.author)
        log_entry += "\n\t".join(["{name} - {level} {vocation} - **{guild}**".format(**char) for char in added+updated])
        yield from send_log_message(bot, ctx.message.server, log_entry)
        return
    finally:
        c.close()
        userDatabase.commit()


@bot.command(hidden=lite_mode)
@asyncio.coroutine
def online():
    """Tells you which users are online on Tibia

    This list gets updated based on Tibia.com online list, so it takes a couple minutes
    to be updated."""
    if lite_mode:
        return
    discord_online_chars = []
    c = userDatabase.cursor()
    try:
        for char in global_online_list:
            char = char.split("_", 1)[1]
            c.execute("SELECT name, user_id, vocation, last_level FROM chars WHERE name LIKE ?", (char,))
            result = c.fetchone()
            if result:
                # This will always be true unless a char is removed from chars in between globalOnlineList updates
                discord_online_chars.append({"name": result["name"], "id": result["user_id"],
                                             "vocation": result["vocation"], "level": result["last_level"]})
        if len(discord_online_chars) == 0:
            yield from bot.say("There is no one online from Discord.")
        else:
            reply = "The following discord users are online:"
            for char in discord_online_chars:
                user = get_member(bot, char['id'])

                char['vocation'] = get_voc_abb(char['vocation'])

                # discordName = user.display_name if (user is not None) else "unknown"
                if user is not None:
                    discord_name = user.display_name
                    reply += "\n\t{0} (Lvl {1} {2}, **@{3}**)".format(char['name'], abs(char['level']), char['vocation'], discord_name)
            yield from bot.say(reply)
    finally:
        c.close()


@bot.command()
@asyncio.coroutine
def about():
    """Shows information about the bot"""
    user_count = 0
    char_count = 0
    deaths_count = 0
    levels_count = 0
    if not lite_mode:
        c = userDatabase.cursor()
        try:
            c.execute("SELECT COUNT(*) as count FROM users")
            result = c.fetchone()
            if result is not None:
                user_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM chars")
            result = c.fetchone()
            if result is not None:
                char_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_deaths")
            result = c.fetchone()
            if result is not None:
                deaths_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_levelups")
            result = c.fetchone()
            if result is not None:
                levels_count = result["count"]
        finally:
            c.close()

    embed = discord.Embed(description="*Beep boop beep boop*. I'm just a bot!")
    embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                     icon_url="https://assets-cdn.github.com/favicon.ico")
    embed.add_field(name="Authors", value="@Galarzaa#8515, @Nezune#2269")
    embed.add_field(name="Platform", value="Python " + EMOJI[":snake:"])
    embed.add_field(name="Created", value="March 30th 2016")
    embed.add_field(name="Uptime", value=get_uptime())
    memory_usage = psutil.Process().memory_full_info().uss / 1024 ** 2
    if not lite_mode:
        embed.add_field(name="Tracked users", value="{0:,}".format(user_count))
        embed.add_field(name="Tracked chars", value="{0:,}".format(char_count))
        embed.add_field(name="Tracked deaths", value="{0:,}".format(deaths_count))
        embed.add_field(name="Tracked level ups", value="{0:,}".format(levels_count))

    embed.add_field(name='Memory Usage', value='{:.2f} MiB'.format(memory_usage))
    yield from bot.say(embed=embed)


@bot.group(pass_context=True, aliases=["event"], hidden=lite_mode, invoke_without_command=True)
@asyncio.coroutine
def events(ctx):
    """Shows a list of current active events"""
    time_threshold = 60 * 30
    now = time.time()
    if lite_mode:
        return
    c = userDatabase.cursor()
    try:
        # If this is used on a PM, show events for all shared servers
        if ctx.message.channel.is_private:
            servers = get_user_servers(bot, ctx.message.author.id)
        else:
            servers = [ctx.message.server]
        servers_ids = [s.id for s in servers]
        placeholders = ", ".join("?" for s in servers)
        embed = discord.Embed(description="For more info about an event, use `/event info (id)`"
                                          "\nTo receive notifications for an event, use `/event sub (id)`")
        c.execute("SELECT creator, start, name, id, server FROM events "
                  "WHERE start < {0} AND start > {1} AND active = 1 AND server IN ({2}) "
                  "ORDER by start ASC".format(now, now - time_threshold, placeholders), tuple(servers_ids))
        recent_events = c.fetchall()
        c.execute("SELECT creator, start, name, id, server FROM events "
                  "WHERE start > {0} AND active = 1 AND server IN ({1})"
                  "ORDER BY start ASC".format(now, placeholders), tuple(servers_ids))
        upcoming_events = c.fetchall()
        if len(recent_events) + len(upcoming_events) == 0:
            yield from bot.say("There are no upcoming events.")
            return
        # Recent events
        if recent_events:
            name = "Recent events"
            value = ""
            for event in recent_events:
                author = get_member(bot, event["creator"])
                event["author"] = "unknown" if author is None else author.display_name
                time_diff = timedelta(seconds=now - event["start"])
                minutes = round((time_diff.seconds/60) % 60)
                event["start_str"] = "Started {0} minutes ago".format(minutes)
                value += "\n**{name}** (by **@{author}**,*ID:{id}*) - {start_str}".format(**event)
            embed.add_field(name=name, value=value, inline=False)
        # Upcoming events
        if upcoming_events:
            name = "Upcoming events"
            value = ""
            for event in upcoming_events:
                author = get_member(bot, event["creator"])
                event["author"] = "unknown" if author is None else author.display_name
                time_diff = timedelta(seconds=event["start"]-now)
                days, hours, minutes = time_diff.days, time_diff.seconds // 3600, (time_diff.seconds // 60) % 60
                if days:
                    event["start_str"] = 'In {0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                elif hours:
                    event["start_str"] = 'In {0} hours and {1} minutes'.format(hours, minutes)
                elif minutes > 0:
                    event["start_str"] = 'In {0} minutes'.format(minutes)
                else:
                    event["start_str"] = 'Starting now!'
                value += "\n**{name}** (by **@{author}**,*ID:{id}*) - {start_str}".format(**event)
            embed.add_field(name=name, value=value, inline=False)
        yield from bot.say(embed=embed)
    finally:
        c.close()


@events.command(pass_context=True, name="info", aliases=["show", "details"])
@asyncio.coroutine
def event_info(ctx, event_id: int):
    """Displays an event's info"""
    c = userDatabase.cursor()
    try:
        # If this is used on a PM, show events for all shared servers
        if ctx.message.channel.is_private:
            servers = get_user_servers(bot, ctx.message.author.id)
        else:
            servers = [ctx.message.server]
        servers_ids = [s.id for s in servers]
        placeholders = ", ".join("?" for s in servers)

        c.execute("SELECT * FROM events "
                  "WHERE id = {0} AND active = 1 and server IN ({1})".format(event_id, placeholders), tuple(servers_ids))
        event = c.fetchone()
        if not event:
            yield from bot.say("There's no event with that id.")
            return
        start = datetime.utcfromtimestamp(event["start"])
        embed = discord.Embed(title=event["name"], description=event["description"], timestamp=start)
        author = get_member(bot, event["creator"])
        footer = "Start time"
        footer_icon = ""
        if author is not None:
            footer = "Created by "+author.display_name+" | Start time"
            footer_icon = author.avatar_url if author.avatar_url else author.default_avatar_url
        embed.set_footer(text=footer, icon_url=footer_icon)
        yield from bot.say(embed=embed)
    finally:
        c.close()


@events.command(name="add", pass_context=True)
@asyncio.coroutine
def event_add(ctx, starts_in: TimeString, *, params):
    """Adds an event

    The syntax is:
    /event starts_in name
    /event starts_in name,description

    starts_in means in how much time the event will start since the moment of creation
    The time can be set using units such as 'd' for days, 'h' for hours, 'm' for minutes and 'd' for seconds.
    Examples: 1d20h5m, 1d30m, 1h40m, 40m
    """
    now = time.time()
    creator = ctx.message.author.id
    start = now+starts_in.seconds
    params = params.split(",", 1)
    name = single_line(clean_string(ctx, params[0]))
    event_description = ""
    if len(params) > 1:
        event_description = clean_string(ctx, params[1])

    c = userDatabase.cursor()
    try:
        c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
        result = c.fetchall()
        if len(result) > 1 and creator not in owner_ids+mod_ids:
            yield from bot.say("You can only have two running events simultaneously. Delete or edit an active event")
            return

        servers = get_user_servers(bot, creator)
        # If message is via PM, but user only shares one server, we just consider that server
        if ctx.message.channel.is_private and len(servers) == 1:
            server = servers[0]
        # Not a private message, so we just take current server
        elif not ctx.message.channel.is_private:
            server = ctx.message.server
        # PM and user shares multiple servers, we must ask him for which server is the event
        else:
            yield from bot.say("For which server is this event? Choose one (number only)" +
                               "\n\t0: *Cancel*\n\t" +
                               "\n\t".join(["{0}: **{1.name}**".format(i+1, j) for i, j in enumerate(servers)]))
            reply = yield from bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                    timeout=50.0)
            if reply is None:
                yield from bot.say("Nothing? Forget it then.")
                return
            elif is_numeric(reply.content):
                answer = int(reply.content)
                if answer == 0:
                    yield from bot.say("Changed your mind? Typical human.")
                    return
                try:
                    server = servers[answer-1]
                except IndexError:
                    yield from bot.say("That wasn't in the choices, you ruined it. Start from the beginning.")
                    return
            else:
                yield from bot.say("That's not a valid answer, try the command again.")
                return

        c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                  (creator, server.id, start, name, event_description))
        event_id = c.lastrowid
        reply = "Event registered successfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*"
        yield from bot.say(reply.format(name, starts_in.original, event_id))
    finally:
        userDatabase.commit()
        c.close()


@event_add.error
@asyncio.coroutine
def event_add_error(error, ctx):
    if isinstance(error, commands.BadArgument):
        yield from bot.say(str(error))


@events.command(name="editname", pass_context=True)
@asyncio.coroutine
def event_edit_name(ctx, event_id: int, *, new_name):
    """Changes an event's name

    Only the creator of the event or mods can edit an event's name
    Only upcoming events can be edited"""
    c = userDatabase.cursor()
    now = time.time()
    new_name = single_line(clean_string(ctx, new_name))
    try:
        c.execute("SELECT creator FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
        event = c.fetchone()
        if not event:
            yield from bot.say("There are no active events with that ID.")
            return
        if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids+owner_ids:
            yield from bot.say("You can only edit your own events.")
            return
        yield from bot.say("Do you want to change the name of **{0}**? `(yes/no)`".format(event["name"]))
        answer = yield from bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel, timeout=30.0)
        if answer is None:
            yield from bot.say("I will take your silence as a no...")
        elif answer.content.lower() in ["yes", "y"]:
            c.execute("UPDATE events SET name = ? WHERE id = ?", (new_name, event_id,))
            yield from bot.say("Your event was renamed successfully to **{0}**.".format(new_name))
        else:
            yield from bot.say("Ok, nevermind.")
    finally:
        userDatabase.commit()
        c.close()


@events.command(name="editdesc", aliases=["editdescription"], pass_context=True)
@asyncio.coroutine
def event_edit_description(ctx, event_id: int, *, new_description):
    """Changes an event's description

    Only the creator of the event or mods can edit an event's description
    Only upcoming events can be edited"""
    c = userDatabase.cursor()
    now = time.time()
    new_description = clean_string(ctx, new_description)
    try:
        c.execute("SELECT creator FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
        event = c.fetchone()
        if not event:
            yield from bot.say("There are no active events with that ID.")
            return
        if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids+owner_ids:
            yield from bot.say("You can only edit your own events.")
            return
        yield from bot.say("Do you want to change the description of **{0}**? `(yes/no)`")
        answer = yield from bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel, timeout=30.0)
        if answer is None:
            yield from bot.say("I will take your silence as a no...")
        elif answer.content.lower() in ["yes", "y"]:
            c.execute("UPDATE events SET description = ? WHERE id = ?", (new_description, event_id,))
            yield from bot.say("Your event's description was changed successfully to **{0}**.".format(new_description))
        else:
            yield from bot.say("Ok, nevermind.")

    finally:
        userDatabase.commit()
        c.close()


@events.command(name="edittime", aliases=["editstart"], pass_context=True)
@asyncio.coroutine
def event_edit_time(ctx, event_id: int, starts_in: TimeString):
    """Changes an event's time

    Only the creator of the event or mods can edit an event's time
    Only upcoming events can be edited"""
    c = userDatabase.cursor()
    now = time.time()
    try:
        c.execute("SELECT creator, name FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
        event = c.fetchone()
        if not event:
            yield from bot.say("There are no active events with that ID.")
            return
        if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids+owner_ids:
            yield from bot.say("You can only edit your own events.")
            return
        yield from bot.say("Do you want to change the start time of '**{0}**'? `(yes/no)`".format(event["name"]))
        answer = yield from bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel, timeout=30.0)
        if answer is None:
            yield from bot.say("I will take your silence as a no...")
        elif answer.content.lower() in ["yes", "y"]:
            c.execute("UPDATE events SET start = ? WHERE id = ?", (now+starts_in.seconds, event_id,))
            yield from bot.say(
                "Your event's start time was changed successfully to **{0}**.".format(starts_in.original))
        else:
            yield from bot.say("Ok, nevermind.")
    finally:
        userDatabase.commit()
        c.close()


@events.command(name="delete", aliases=["remove"], pass_context=True)
@asyncio.coroutine
def event_remove(ctx, event_id: int):
    """Deletes an event

    Only the creator of the event or mods can delete an event
    Only upcoming events can be edited"""
    c = userDatabase.cursor()
    now = time.time()
    try:
        c.execute("SELECT creator,name FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now,))
        event = c.fetchone()
        if not event:
            yield from bot.say("There are no active events with that ID.")
            return
        if event["creator"] != int(ctx.message.author.id) and ctx.message.author.id not in mod_ids+owner_ids:
            yield from bot.say("You can only delete your own events.")
            return
        yield from bot.say("Do you want to delete the event '**{0}**'? `(yes/no)`".format(event["name"]))
        answer = yield from bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel, timeout=30.0)
        if answer is None:
            yield from bot.say("I will take your silence as a no...")
        elif answer.content.lower() in ["yes", "y"]:
            c.execute("UPDATE events SET active = 0 WHERE id = ?", (event_id,))
            yield from bot.say("Your event was deleted successfully.")
        else:
            yield from bot.say("Ok, nevermind.")
    finally:
        userDatabase.commit()
        c.close()


@events.command(pass_context=True, name="make", aliases=["creator", "maker"])
@asyncio.coroutine
def event_make(ctx):
    """Creates an event guiding you step by step

    Instead of using confusing parameters, commas and spaces, this commands has the bot ask you step by step."""
    author = ctx.message.author
    creator = author.id
    now = time.time()
    c = userDatabase.cursor()
    try:
        c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
        event = c.fetchall()
        if len(event) > 1 and creator not in owner_ids + mod_ids:
            return
        yield from bot.say("Let's create an event. What would you like the name to be?")

        name = yield from bot.wait_for_message(author=author, channel=ctx.message.channel, timeout=50.0)
        if name is None:
            yield from bot.say("...You took to long. Try the command again.")
            return
        name = single_line(name.clean_content)

        yield from bot.say("Alright, what description would you like the event to have? `(no/none = no description)`")
        event_description = yield from bot.wait_for_message(author=author, channel=ctx.message.channel, timeout=50.0)
        if event_description is None:
            yield from bot.say("...You took too long. Try the command again.")
            return
        elif event_description.content.lower().strip() in ["no", "none"]:
            yield from bot.say("No description then? Alright, now tell me the start time of the event from now.")
            event_description = ""
        else:
            event_description = event_description.clean_content
            yield from bot.say("Alright, now tell me the start time of the event from now.")

        starts_in = yield from bot.wait_for_message(author=author, channel=ctx.message.channel, timeout=50.0)
        if starts_in is None:
            yield from bot.say("...You took too long. Try the command again.")
            return
        try:
            starts_in = TimeString(starts_in.content)
        except commands.BadArgument:
            yield from bot.say("Invalid time. Try  the command again. `Time examples: 1h2m, 2d30m, 40m, 5h`")
            return

        servers = get_user_servers(bot, creator)
        # If message is via PM, but user only shares one server, we just consider that server
        if ctx.message.channel.is_private and len(servers) == 1:
            server = servers[0]
        # Not a private message, so we just take current server
        elif not ctx.message.channel.is_private:
            server = ctx.message.server
        # PM and user shares multiple servers, we must ask him for which server is the event
        else:
            yield from bot.say("One more question...for which server is this event? Choose one (number only)" +
                               "\n\t0: *Cancel*\n\t" +
                               "\n\t".join(["{0}: **{1.name}**".format(i+1, j) for i, j in enumerate(servers)]))
            reply = yield from bot.wait_for_message(author=ctx.message.author, channel=ctx.message.channel,
                                                    timeout=50.0)
            if reply is None:
                yield from bot.say("Nothing? Forget it then.")
                return
            elif is_numeric(reply.content):
                answer = int(reply.content)
                if answer == 0:
                    yield from bot.say("Changed your mind? Typical human.")
                    return
                try:
                    server = servers[answer-1]
                except IndexError:
                    yield from bot.say("That wasn't in the choices, you ruined it. Start from the beginning.")
                    return
            else:
                yield from bot.say("That's not a valid answer, try the command again.")
                return

        now = time.time()
        c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                  (creator, server.id, now+starts_in.seconds, name, event_description))
        event_id = c.lastrowid
        reply = "Event registered successfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*"
        yield from bot.say(reply.format(name, starts_in.original, event_id))
    finally:
        userDatabase.commit()
        c.close()


@events.command(pass_context=True, name="subscribe", aliases=["sub"])
@asyncio.coroutine
def event_subscribe(ctx, event_id: int):
    """Subscribe to receive a PM when an event is happening."""
    c = userDatabase.cursor()
    author = ctx.message.author
    now = time.time()
    try:
        # If this is used on a PM, show events for all shared servers
        if ctx.message.channel.is_private:
            servers = get_user_servers(bot, ctx.message.author.id)
        else:
            servers = [ctx.message.server]
        servers_ids = [s.id for s in servers]
        placeholders = ", ".join("?" for s in servers)
        c.execute("SELECT * FROM events "
                  "WHERE id = {0} AND active = 1 AND start > {1} AND server IN ({2})".format(event_id, now, placeholders)
                  , tuple(servers_ids))
        event = c.fetchone()
        if event is None:
            yield from bot.say("There are no active events with that id.")
            return

        c.execute("SELECT * FROM event_subscribers WHERE event_id = ? AND user_id = ?", (event_id, author.id))
        subscription = c.fetchone()
        if subscription is not None:
            yield from bot.say("You're already subscribed to this event.")
            return
        yield from bot.say("Do you want to subscribe to **{0}**? `(yes/no)`".format(event["name"]))
        reply = yield from bot.wait_for_message(author=author, channel=ctx.message.channel, timeout=30.0)
        if reply is None:
            yield from bot.say("No answer? Nevermind then.")
        elif reply.content in ["yes", "y"]:
            c.execute("INSERT INTO event_subscribers (event_id, user_id) VALUES(?,?)", (event_id, author.id))
            yield from bot.say("You have subscribed successfully to this event. I'll let you know when it's happening.")
        else:
            yield from bot.say("No? Alright then...")
    finally:
        c.close()
        userDatabase.commit()


@event_add.error
@asyncio.coroutine
def event_error(error, ctx):
    if isinstance(error, commands.BadArgument):
        yield from bot.say(str(error))
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        yield from bot.say("You're missing a required argument. `Type /help {0}`".format(ctx.invoked_subcommand))


@event_edit_name.error
@event_edit_description.error
@event_edit_time.error
@event_remove.error
@event_subscribe.error
@asyncio.coroutine
def event_error(error, ctx):
    if isinstance(error, commands.BadArgument):
        yield from bot.say("Invalid arguments used. `Type /help {0}`".format(ctx.invoked_subcommand))
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        yield from bot.say("You're missing a required argument. `Type /help {0}`".format(ctx.invoked_subcommand))


@bot.command(pass_context=True, no_pm=True, name="server", aliases=["serverinfo", "server_info"])
@asyncio.coroutine
def info_server(ctx):
    """Shows the server's information."""
    embed = discord.Embed()
    _server = ctx.message.server  # type: discord.Server
    embed.set_thumbnail(url=_server.icon_url)
    embed.description = _server.name
    # Check if owner has a nickname
    if _server.owner.name == _server.owner.display_name:
        owner = "{0.name}#{0.discriminator}".format(_server.owner)
    else:
        owner = "{0.display_name}\n({0.name}#{0.discriminator})".format(_server.owner)
    embed.add_field(name="Owner", value=owner)
    embed.add_field(name="Created", value=_server.created_at.strftime("%d/%m/%y"))
    embed.add_field(name="Server Region", value=get_region_string(_server.region))

    # Channels
    text_channels = 0
    for channel in _server.channels:
        if channel.type == discord.ChannelType.text:
            text_channels += 1
    voice_channels = len(_server.channels) - text_channels
    embed.add_field(name="Text channels", value=text_channels)
    embed.add_field(name="Voice channels", value=voice_channels)
    embed.add_field(name="Members", value=_server.member_count)
    embed.add_field(name="Roles", value=len(_server.roles))
    embed.add_field(name="Emojis", value=len(_server.emojis))
    embed.add_field(name="Bot joined", value=_server.me.joined_at.strftime("%d/%m/%y"))
    yield from bot.say(embed=embed)


@bot.command(pass_context=True, no_pm=True)
@asyncio.coroutine
def roles(ctx, *userName:str):
    """Shows a list of roles or an user's roles"""
    userName = " ".join(userName).strip()
    msg = "These are the active roles for "

    if not userName:
        msg += "this server:\r\n"

        for role in get_role_list(ctx.message.server):
            msg += role.name + "\r\n"
    else:
        user = get_member_by_name(bot, userName)

        if user is None:
            msg = "I don't see any user named **" + userName + "**. \r\n"
            msg += "I can only check roles from an username registered on this server."
        else:
            msg += "**" + user.display_name + "**:\r\n"
            roles = []

            # Ignoring "default" roles
            for role in user.roles:
                if role.name not in ["@everyone", "Nab Bot"]:
                    roles.append(role.name)

            # There shouldn't be anyone without active roles, but since people can check for NabBot,
            # might as well show a specific message.
            if roles:
                for roleName in roles:
                    msg += roleName + "\r\n"
            else:
                msg = "There are no active roles for **" + user.display_name + "**."

    yield from bot.say(msg)
    return


@bot.command(pass_context=True, no_pm=True)
@asyncio.coroutine
def role(ctx, *roleName: str):
    """Shows member list within the specified role"""
    roleName = " ".join(roleName).strip()
    lowerRoleName = roleName.lower()
    roleDict = {}

    # Need to get all roles and check all members because there's
    # no API call like role.getMembers
    for role in get_role_list(ctx.message.server):
        if role.name.lower() == lowerRoleName:
            roleDict[role] = []

    if len(roleDict) > 0:
        # Check every member and add to dict for each role he is in
        # In this case, the dict will only have the specific role searched
        for member in ctx.message.server.members:
            for role in member.roles:
                if role in roleDict:
                    roleDict[role].append(member.display_name)
                    # Getting the name directly from server to respect case
                    roleName = role.name

        # Create return message
        msg = "These are the members from **" + roleName + "**:\r\n"

        for key, value in roleDict.items():
            if len(value) < 1:
                msg = "There are no members for this role yet."
            else:
                for memberName in roleDict[key]:
                    msg += "\t" + memberName + "\r\n"

        yield from bot.say(msg)
    else:
        yield from bot.say("I couldn't find a role with that name.")

    return


@asyncio.coroutine
def game_update():
    game_list = ["Half-Life 3", "Tibia on Steam", "DOTA 3", "Human Simulator 2017", "Russian Roulette",
                 "with my toy humans", "with fire"+EMOJI[":fire:"], "God", "innocent", "the part", "hard to get",
                 "with my human minions", "Singularity", "Portal 3", "Dank Souls"]
    yield from bot.wait_until_ready()
    while not bot.is_closed:
        yield from bot.change_presence(game=discord.Game(name=random.choice(game_list)))
        yield from asyncio.sleep(60*20)  # Change game every 20 minutes


if __name__ == "__main__":
    init_database()
    reload_worlds()

    print("Attempting login...")

    login = getLogin()
    try:
        token = login.token
    except NameError:
        token = ""

    try:
        email = login.email
        password = login.password
    except NameError:
        email = ""
        password = ""
    try:
        if token:
            bot.run(token)
        elif email and password:
            bot.run(login.email, login.password)
        else:
            print("No login data found. Edit or delete login.py and restart.")
            input("\nPress any key to continue...")
            quit()
    except discord.errors.LoginFailure:
        print("Incorrect login data. Edit or delete login.py and restart.")
        input("\nPress any key to continue...")
        quit()
    finally:
        bot.session.close()

    log.warning("Emergency restart!")
    if platform.system() == "Linux":
        os.system("python3 restart.py")
    else:
        os.system("python restart.py")
    quit()
