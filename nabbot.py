import asyncio
import traceback

from discord.ext import commands
import discord
import sys
import platform

from utils import *
from utils_tibia import *

description = '''Mission: Destroy all humans.'''
bot = commands.Bot(command_prefix=["/"], description=description, pm_help=True)


@bot.event
@asyncio.coroutine
def on_ready():
    bot.load_extension("tibia")
    bot.load_extension("mod")
    bot.load_extension("owner")
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

    yield from think()
    # Anything below this won't be executed in this definition.


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
    if len(split) == 2:
        message.content = split[0].lower()+" "+split[1]
        if message.author.id != bot.user.id and (not split[0].lower()[1:] in command_list or not split[0][:1] == "/")\
                and not message.channel.is_private and message.channel.name == askchannel:
            yield from bot.delete_message(message)
            return
    else:
        message.content = message.content.lower()
        # Delete messages in askchannel
        if message.author.id != bot.user.id \
                and (not message.content.lower()[1:] in command_list or not message.content[:1] == "/") \
                and not message.channel.is_private \
                and message.channel.name == askchannel:
            yield from bot.delete_message(message)
            return
    yield from bot.process_commands(message)


@bot.event
@asyncio.coroutine
def on_member_join(member):
    """Called every time a member joins a server visible by the bot."""
    log.info("{0.display_name} (ID: {0.id}) joined {0.server.name}".format(member))
    if lite_mode:
        return
    message = "Welcome {0.mention}! Please tell us about yourself, who is your Tibia character?\r\n" \
              "Say /im *charactername* and I'll begin tracking it for you!"
    yield from bot.send_message(member.server, message.format(member))


@bot.event
@asyncio.coroutine
def on_member_remove(member):
    """Called when a member leaves or is kicked from a server."""
    log.info("{0.display_name} (ID:{0.id}) left or was kicked from {0.server.name}".format(member))


@bot.event
@asyncio.coroutine
def on_member_ban(member):
    """Called when a member is banned from a server."""
    log.info("{0.display_name} (ID:{0.id}) was banned from {0.server.name}".format(member))


@bot.event
@asyncio.coroutine
def on_member_unban(server, user):
    """Called when a member is unbanned from a server"""
    log.info("{1.name} (ID:{1.id}) was unbanned from {0.name}".format(server, user))


@bot.event
@asyncio.coroutine
def on_message_delete(message):
    """Called every time a message is deleted."""
    if message.channel.name == askchannel:
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


@asyncio.coroutine
def announceEvents():
    if lite_mode:
        return
    """Announces when an event is close to starting."""
    firstAnnouncement = 60*30
    secondAnnouncement = 60*15
    thirdAnnouncement = 60*5
    c = userDatabase.cursor()
    try:
        channel = get_channel_by_name(bot, mainchannel, mainserver)
        # Current time
        date = time.time()
        # Find incoming events

        # First announcement
        c.execute("SELECT creator, start, name, id "
                  "FROM events "
                  "WHERE start < ? AND start > ? AND active = 1 AND status > 3 "
                  "ORDER by start ASC", (date+firstAnnouncement+60, date+firstAnnouncement,))
        results = c.fetchall()
        if len(results) > 0:
            for row in results:
                author = "unknown" if get_member(bot, row["creator"]) is None else get_member(bot, row["creator"]).display_name
                name = row["name"]
                id = row["id"]
                timediff = timedelta(seconds=row["start"]-date)
                days, hours, minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60)%60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours, minutes)
                else:
                    start = '{0} minutes'.format(minutes)

                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}.".format(name, author, start, id)
                c.execute("UPDATE events SET status = 3 WHERE id = ?", (id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name, author, start, id))
                yield from bot.send_message(channel, message)
                # Send PM to subscribers:
                c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (id,))
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
                  "ORDER by start ASC", (date+secondAnnouncement+60, date+secondAnnouncement,))
        results = c.fetchall()
        if len(results) > 0:
            for row in results:
                author = "unknown" if get_member(bot, row["creator"]) is None else get_member(bot, row["creator"]).display_name
                name = row["name"]
                id = row["id"]
                timediff = timedelta(seconds=row["start"]-date)
                days, hours, minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60) % 60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours, minutes)
                else:
                    start = '{0} minutes'.format(minutes)

                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}.".format(name, author, start, id)
                c.execute("UPDATE events SET status = 2 WHERE id = ?", (id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name, author, start, id))
                yield from bot.send_message(channel, message)
                # Send PM to subscribers:
                c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (id,))
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
                  "ORDER by start ASC", (date+thirdAnnouncement+60, date+thirdAnnouncement,))
        results = c.fetchall()
        if len(results) > 0:
            for row in results:
                author = "unknown" if get_member(bot, row["creator"]) is None else get_member(bot, row["creator"]).display_name
                name = row["name"]
                id = row["id"]
                timediff = timedelta(seconds=row["start"]-date)
                days, hours, minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60) % 60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours, minutes)
                else:
                    start = '{0} minutes'.format(minutes)

                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}!".format(name, author, start, id)
                c.execute("UPDATE events SET status = 1 WHERE id = ?", (id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name, author, start, id))
                yield from bot.send_message(channel, message)
                # Send PM to subscribers:
                c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (id,))
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
                id = row["id"]
                timediff = timedelta(seconds=row["start"]-date)
                days, hours, minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60) % 60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days, hours, minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours, minutes)
                else:
                    start = '{0} minutes'.format(minutes)

                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting right now!".format(name, author, start, id)
                c.execute("UPDATE events SET status = 0 WHERE id = ?", (id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - Starting ({2})".format(name, author, start, id))
                yield from bot.send_message(channel, message)
                # Send PM to subscribers:
                c.execute("SELECT * FROM event_subscribers WHERE event_id = ?", (id,))
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


@asyncio.coroutine
def think():
    if lite_mode:
        return
    #################################################
    #             Nezune's cave                     #
    # Do not touch anything, enter at your own risk #
    #################################################
    lastServerOnlineCheck = datetime.now()
    lastPlayerDeathCheck = datetime.now()
    global globalOnlineList
    while 1:
        # Announce incoming events
        yield from announceEvents()

        # Periodically check server online lists
        if datetime.now() - lastServerOnlineCheck > serveronline_delay and len(tibiaservers) > 0:
            # Pop last server in queue, reinsert it at the beginning
            currentServer = tibiaservers.pop()
            tibiaservers.insert(0, currentServer)

            # Get online list for this server
            currentServerOnline = yield from get_server_online(currentServer)

            if len(currentServerOnline) > 0:
                # Open connection to users.db
                c = userDatabase.cursor()

                # Remove chars that are no longer online from the globalOnlineList
                offlineList = []
                for char in globalOnlineList:
                    if char.split("_", 1)[0] == currentServer:
                        offline = True
                        for serverChar in currentServerOnline:
                            if serverChar['name'] == char.split("_", 1)[1]:
                                offline = False
                                break
                        if offline:
                            offlineList.append(char)
                for nowOfflineChar in offlineList:
                    globalOnlineList.remove(nowOfflineChar)
                    # Check for deaths and level ups when removing from online list
                    nowOfflineChar = yield from get_character(nowOfflineChar.split("_", 1)[1])
                    if not(nowOfflineChar == ERROR_NETWORK or nowOfflineChar == ERROR_DOESNTEXIST):
                        c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?", (nowOfflineChar['name'],))
                        result = c.fetchone()
                        if result:
                            lastLevel = result["last_level"]
                            c.execute(
                                "UPDATE chars SET last_level = ? WHERE name LIKE ?",
                                (nowOfflineChar['level'], nowOfflineChar['name'],)
                            )
                            if nowOfflineChar['level'] > lastLevel > 0:
                                # Saving level up date in database
                                c.execute(
                                    "INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",
                                    (result["id"], nowOfflineChar['level'], time.time(),)
                                )
                                # Announce the level up
                                yield from announceLevel(nowOfflineChar, nowOfflineChar['level'])
                        yield from checkDeath(nowOfflineChar['name'])

                # Add new online chars and announce level differences
                for serverChar in currentServerOnline:
                    c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?", (serverChar['name'],))
                    result = c.fetchone()
                    if result:
                        # If its a stalked character
                        lastLevel = result["last_level"]
                        # We update their last level in the db
                        c.execute(
                            "UPDATE chars SET last_level = ? WHERE name LIKE ?",
                            (serverChar['level'], serverChar['name'],)
                        )

                        if not (currentServer+"_"+serverChar['name']) in globalOnlineList:
                            # If the character wasn't in the globalOnlineList we add them
                            # (We insert them at the beginning of the list to avoid messing with the death checks order)
                            globalOnlineList.insert(0, (currentServer+"_"+serverChar['name']))
                            # Since this is the first time we see them online we flag their last death time
                            # to avoid backlogged death announces
                            c.execute(
                                "UPDATE chars SET last_death_time = ? WHERE name LIKE ?",
                                (None, serverChar['name'],)
                            )
                            yield from checkDeath(serverChar['name'])

                        # Else we check for levelup
                        elif serverChar['level'] > lastLevel > 0:
                            # Saving level up date in database
                            c.execute(
                                "INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",
                                (result["id"], serverChar['level'], time.time(),)
                            )
                            # Announce the level up
                            char = yield from get_character(serverChar['name'])
                            yield from announceLevel(char, serverChar['level'])

                # Close cursor and commit changes
                userDatabase.commit()
                c.close()

            # Update last server check time
            lastServerOnlineCheck = datetime.now()

        # Periodically check for deaths
        if datetime.now() - lastPlayerDeathCheck > playerdeath_delay and len(globalOnlineList) > 0:
            # Pop last char in queue, reinsert it at the beginning
            currentChar = globalOnlineList.pop()
            globalOnlineList.insert(0, currentChar)

            # Get rid of server name
            currentChar = currentChar.split("_", 1)[1]
            # Check for new death
            yield from checkDeath(currentChar)

            # Update last death check time
            lastPlayerDeathCheck = datetime.now()

        # Sleep for a bit and then loop back
        yield from asyncio.sleep(1)


@asyncio.coroutine
def checkDeath(character):
    """Gets death list for a character (from database)

    Only the first death is needed"""
    characterDeaths = yield from get_character_deaths(character, True)

    if (type(characterDeaths) is list) and len(characterDeaths) > 0:
        c = userDatabase.cursor()

        c.execute("SELECT name, last_death_time, id FROM chars WHERE name LIKE ?", (character,))
        result = c.fetchone()
        if result:
            lastDeath = characterDeaths[0]
            dbLastDeathTime = result["last_death_time"]
            # If the db lastDeathTime is None it means this is the first time we're seeing them online
            # so we just update it without announcing deaths
            if dbLastDeathTime is None:
                c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?", (lastDeath['time'], character,))
            # Else if the last death's time doesn't match the one in the db
            elif dbLastDeathTime != lastDeath['time']:
                # Update the lastDeathTime for this char in the db
                c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?", (lastDeath['time'], character,))
                # Saving death info in database
                c.execute(
                    "INSERT INTO char_deaths (char_id,level,killer,byplayer,date) VALUES(?,?,?,?,?)",
                    (result["id"], int(lastDeath['level']), lastDeath['killer'], lastDeath['byPlayer'], time.time(),)
                )
                # Announce the death
                yield from announceDeath(character, lastDeath['time'], lastDeath['level'], lastDeath['killer'], lastDeath['byPlayer'])

        # Close cursor and commit changes
        userDatabase.commit()
        c.close()


@asyncio.coroutine
def announceDeath(charName, deathTime, deathLevel, deathKiller, deathByPlayer):
    if int(deathLevel) < announceTreshold:
        # Don't announce for low level players
        return

    log.info("Announcing death: {0}({1}) | {2}".format(charName, deathLevel, deathKiller))
    char = yield from get_character(charName)
    # Failsafe in case getPlayer fails to retrieve player data
    if type(char) is not dict:
        log.warning("Error in announceDeath, failed to getPlayer("+charName+")")
        return

    if not(char['world'] in tibiaservers):
        # Don't announce for players in non-tracked worlds
        return
    # Choose correct pronouns
    pronoun = ["he", "his", "him"] if char['gender'] == "male" else ["she", "her", "her"]

    channel = get_channel_by_name(bot, mainchannel, mainserver)
    # Find killer article (a/an)
    deathKillerArticle = ""
    if not deathByPlayer:
        deathKillerArticle = deathKiller.split(" ", 1)
        if deathKillerArticle[0] in ["a", "an"] and len(deathKillerArticle) > 1:
            deathKiller = deathKillerArticle[1]
            deathKillerArticle = deathKillerArticle[0]+" "
        else:
            deathKillerArticle = ""
    # Select a message
    message = weighedChoice(deathmessages_player, char['vocation'], int(deathLevel)) if deathByPlayer else weighedChoice(deathmessages_monster, char['vocation'], int(deathLevel), deathKiller)
    # Format message with death information
    deathInfo = {'charName': charName, 'deathTime': deathTime, 'deathLevel': deathLevel, 'deathKiller': deathKiller,
                 'deathKillerArticle': deathKillerArticle, 'pronoun1': pronoun[0], 'pronoun2': pronoun[1],
                 'pronoun3': pronoun[2]}
    message = message.format(**deathInfo)
    # Format extra stylization
    message = formatMessage(message)
    message = EMOJI[":skull_crossbones:"] + " " + message

    yield from bot.send_message(channel,message[:1].upper()+message[1:])


@asyncio.coroutine
def announceLevel(char, newLevel):
    # Don't announce low level players
    if int(newLevel) < announceTreshold:
        return
    if type(char) is not dict:
        log.error("Error in announceLevel, invalid character passed")
        return
    log.info("Announcing level up: {0} ({1})".format(char["name"], newLevel))

    # Get pronouns based on gender
    pronoun = ["he", "his", "him"] if char['gender'] == "male" else ["she", "her", "her"]

    channel = get_channel_by_name(bot, mainchannel, mainserver)

    # Select a message
    message = weighedChoice(levelmessages, char['vocation'], int(newLevel))
    # Format message with level information
    levelInfo = {'charName': char["name"], 'newLevel': newLevel, 'pronoun1': pronoun[0], 'pronoun2': pronoun[1],
                 'pronoun3': pronoun[2]}
    message = message.format(**levelInfo)
    # Format extra stylization
    message = formatMessage(message)
    message = EMOJI[":star2:"]+" "+message

    yield from bot.send_message(channel, message)


# Bot commands
@bot.command(aliases=["dice"])
@asyncio.coroutine
def roll(dice: str):
    """Rolls a dice in TdN format.

    Rolls a N-sides dice T times.
    Example:
    /roll 3d6 - Rolls a 6 sided dice 3 times"""
    try:
        rolls, limit = map(int, dice.split('d'))
    except Exception:
        yield from bot.say('Format has to be in NdN!')
        return

    result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
    yield from bot.say(result)


@bot.command(pass_context=True,description='For when you wanna settle the score some other way')
@asyncio.coroutine
def choose(ctx, *choices: str):
    """Chooses between multiple choices."""
    user = ctx.message.author
    yield from bot.say('Alright, **@{0}**, I choose: "{1}"'.format(user.display_name, random.choice(choices)))


@bot.command(pass_context=True, aliases=["i'm", "iam"], no_pm=True, hidden=lite_mode)
@asyncio.coroutine
def im(ctx, *charname: str):
    """Lets you add your first tibia character(s) for the bot to track.

    If you need to add any more characters or made a mistake, please message an admin."""

    if lite_mode:
        return

    # This is equivalent to someone using /stalk addacc on themselves.
    # To avoid abuse it will only work on users who have joined recently and have no characters added to their account.
    # This command can't work on private messages, since we need a member instead of an user to be able to check the joining date.

    charname = " ".join(charname).strip()
    user = ctx.message.author
    try:
        c = userDatabase.cursor()
        mod_list = owner_ids + mod_ids
        admins_message = join_list(["**@" + get_member(bot, admin, ctx.message.server).display_name + "**" for admin in mod_list], ", ", " or ")
        servers_message = join_list(["**" + server + "**" for server in tibiaservers], ", ", " or ")
        notallowed_message = ("I'm sorry, {0.mention}, this command is reserved for new users, if you need any help adding characters to your account please message "+admins_message+".").format(user)

        # Check if the user has joined recently
        if datetime.now() - user.joined_at > timewindow_im_joining:
            yield from bot.say(notallowed_message)
            return
        # Check that this user doesn't exist or has no chars added to it yet.
        c.execute("SELECT id from users WHERE id = ?", (user.id,))
        result = c.fetchone()
        if result is not None:
            c.execute("SELECT name,user_id FROM chars WHERE user_id LIKE ?", (user.id,))
            result = c.fetchone()
            if result is not None:
                yield from bot.say(notallowed_message)
                return
        else:
            # Add the user if it doesn't exist
            c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
            c.execute("INSERT INTO user_servers(id,server) VALUES (?,?)", (user.id, ctx.message.server.id,))

        char = yield from get_character(charname)
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
            if char['world'] not in tibiaservers:
                skipped.append(char)
                continue
            c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?", (char['name'],))
            result = c.fetchone()
            if result is not None:
                if get_member(bot, result["user_id"]) is None:
                    updated.append({'name': char['name'], 'world': char['world'], 'prevowner': result["user_id"]})
                    continue
                else:
                    yield from bot.say("I'm sorry but a character in that account was already claimed by **@{0}**.".format(get_member(bot, result["user_id"]).display_name) + "\r\n" +
                        "Have you made a mistake? Message " + admins_message +" if you need any help!")
                    return
            char = yield from get_character(char['name'])
            added.append(char)
        if len(skipped) == len(chars):
            yield from bot.say("I'm sorry, I couldn't find any characters in that account from the worlds I track ("+servers_message+")\r\n"+
                        "Have you made a mistake? Message "+admins_message+" if you need any help!")
            return
        for char in updated:
            c.execute("UPDATE chars SET user_id = ? WHERE name LIKE ?", (user.id, char['name']))
            log.info("Character {0} was reasigned to {1.display_name} (ID: {1.id}) from /im. (Previous owner (ID: {2}) was not found)".format(char['name'], user, char['prevowner']))
        for char in added:
            c.execute(
                "INSERT INTO chars (name,last_level,vocation,user_id, world) VALUES (?,?,?,?,?)",
                (char['name'], char['level']*-1, char['vocation'], user.id, char["world"])
            )
            log.info("Character {0} was asigned to {1.display_name} (ID: {1.id}) from /im.".format(char['name'], user))

        yield from bot.say(("Thanks {0.mention}! I have added the following character(s) to your account: "+", ".join("**"+char['name']+"**" for char in added)+", ".join("**"+char['name']+"**" for char in updated)+".\r\nFrom now on I will track level advances and deaths for you, if you need to add any more characters please message "+admins_message+".").format(user))
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
    discordOnlineChars = []
    c = userDatabase.cursor()
    try:
        for char in globalOnlineList:
            char = char.split("_", 1)[1]
            c.execute("SELECT name, user_id, vocation, last_level FROM chars WHERE name LIKE ?", (char,))
            result = c.fetchone()
            if result:
                # This will always be true unless a char is removed from chars in between globalOnlineList updates
                discordOnlineChars.append({"name": result["name"], "id": result["user_id"],
                                           "vocation": result["vocation"], "level": result["last_level"]})
        if len(discordOnlineChars) == 0:
            yield from bot.say("There is no one online from Discord.")
        else:
            reply = "The following discord users are online:"
            for char in discordOnlineChars:
                user = get_member(bot, char['id'])

                char['vocation'] = get_voc_abb(char['vocation'])
                # discordName = user.display_name if (user is not None) else "unknown"
                if user is not None:
                    discordName = user.display_name
                    reply += "\n\t{0} (Lvl {1} {2}, **@{3}**)".format(char['name'], abs(char['level']), char['vocation'], discordName)
            yield from bot.say(reply)
    finally:
        c.close()


@bot.command()
@asyncio.coroutine
def about():
    """Shows information about the bot"""
    yield from bot.say(embed=get_about_content())


@bot.group(pass_context=True, aliases=["event"], hidden=lite_mode, invoke_without_command=True, no_pm=True)
@asyncio.coroutine
def events(ctx):
    """Shows a list of current active events"""
    time_threshold = 60 * 30
    now = time.time()
    if lite_mode:
        return
    c = userDatabase.cursor()
    try:
        embed = discord.Embed(description="For more info about an event, use ``/event info (id)``")
        c.execute("SELECT creator, start, name, id FROM events "
                  "WHERE start < ? AND start > ? AND active = 1 AND server = ?"
                  "ORDER by start ASC", (now, now - time_threshold, ctx.message.server.id))
        recent_events = c.fetchall()
        c.execute("SELECT creator, start, name, id FROM events "
                  "WHERE start > ? AND active = 1 ORDER BY start ASC", (now,))
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


@events.command(pass_context=True, name="info", aliases=["show", "details"], no_pm=True)
@asyncio.coroutine
def event_info(ctx, event_id: int):
    """Displays an event's info"""
    c = userDatabase.cursor()
    try:
        c.execute("SELECT * FROM events WHERE id = ? AND active = 1 and server = ?", (event_id, ctx.message.server.id))
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


@events.command(name="add", pass_context=True, no_pm=True)
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
    server = ctx.message.server.id
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
        c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                  (creator, server, start, name, event_description))
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


@events.command(name="editname", pass_context=True, no_pm=True)
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
        if event["creator"] != int(ctx.message.author.id) or ctx.message.author.id not in mod_ids+owner_ids:
            yield from bot.say("You can only edit your own events.")
            return
        yield from bot.say("Do you want to change the name of **{0}**? `(yes/no)`")
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


@events.command(name="editdesc", aliases=["editdescription"], pass_context=True, no_pm=True)
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
        if event["creator"] != int(ctx.message.author.id) or ctx.message.author.id not in mod_ids+owner_ids:
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


@events.command(name="edittime", aliases=["editstart"], pass_context=True, no_pm=True)
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
        if event["creator"] != int(ctx.message.author.id) or ctx.message.author.id not in mod_ids+owner_ids:
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


@events.command(name="delete", aliases=["remove"], pass_context=True, no_pm=True)
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
        if event["creator"] != int(ctx.message.author.id) or ctx.message.author.id not in mod_ids+owner_ids:
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


@events.command(pass_context=True, name="make", aliases=["creator", "maker"], no_pm=True)
@asyncio.coroutine
def event_make(ctx):
    """Creates an event guiding you step by step

    Instead of using confusing parameters, commas and spaces, this commands has the bot ask you step by step."""
    author = ctx.message.author
    creator = author.id
    server = ctx.message.server.id
    now = time.time()
    c = userDatabase.cursor()
    try:
        c.execute("SELECT creator FROM events WHERE creator = ? AND active = 1 AND start > ?", (creator, now,))
        event = c.fetchall()
        if len(event) > 1 and creator not in owner_ids + mod_ids:
            return
        yield from bot.say("Let's create an event. What would you like the name to be?")

        name = yield from bot.wait_for_message(author=author, channel=ctx.message.channel, timeout=30.0)
        if name is None:
            yield from bot.say("...You took to long. Try the command again.")
            return
        name = single_line(name.clean_content)

        yield from bot.say("Alright, what description would you like the event to have? `(no/none = no description)`")
        event_description = yield from bot.wait_for_message(author=author, channel=ctx.message.channel, timeout=30.0)
        if event_description is None:
            yield from bot.say("...You took too long. Try the command again.")
            return
        elif event_description.content.lower().strip() in ["no", "none"]:
            yield from bot.say("No description then? Alright, now tell me the start time of the event from now.")
            event_description = ""
        else:
            event_description = event_description.clean_content
            yield from bot.say("Alright, now tell me the start time of the event from now.")

        starts_in = yield from bot.wait_for_message(author=author, channel=ctx.message.channel, timeout=30.0)
        if starts_in is None:
            yield from bot.say("...You took too long. Try the command again.")
            return
        try:
            starts_in = TimeString(starts_in.content)
        except commands.BadArgument:
            yield from bot.say("Invalid time. Try  the command again. `Time examples: `1h2m, 2d30m, 40m, 5h`")
            return
        now = time.time()
        c.execute("INSERT INTO events (creator,server,start,name,description) VALUES(?,?,?,?,?)",
                  (creator, server, now+starts_in.seconds, name, event_description))
        event_id = c.lastrowid
        reply = "Event registered successfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*"
        yield from bot.say(reply.format(name, starts_in.original, event_id))
    finally:
        userDatabase.commit()
        c.close()


@events.command(pass_context=True, name="subscribe", aliases=["sub"])
@asyncio.coroutine
def event_subscribe(ctx, event_id: int):
    c = userDatabase.cursor()
    author = ctx.message.author
    now = time.time()
    try:
        c.execute("SELECT * FROM events WHERE id = ? AND active = 1 AND start > ?", (event_id, now))
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
            yield from bot.say("Alright then...")
    finally:
        c.close()
        userDatabase.commit()


@event_add.error
@asyncio.coroutine
def event_error(error, ctx):
    print("event_error", error)
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
    """Shows all role names within the Discord server, or all roles for a single member"""
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


if __name__ == "__main__":
    initDatabase()

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
