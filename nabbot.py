from utils import *
from config import *
from tibia import *

description = '''Mission: Destroy all humans.'''
bot = commands.Bot(command_prefix=["/"], description=description, pm_help=True)

@bot.event
@asyncio.coroutine
def on_ready():
    bot.load_extension("tibia")
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    log.info('Bot is online and ready')
    #expose bot to ultis.py
    ##its either this or importing discord and commands in utils.py...
    utilsGetBot(bot)
    #populate command_list
    for command_name, command in bot.commands.items():
        command_list.append(command_name)
    #Notify reset author
    if len(sys.argv) > 1:
        user = getUserById(sys.argv[1])
        sys.argv[1] == 0
        if user is not None:
            yield from bot.send_message(user,"Restart complete")
    #start up think()
    yield from think()
    #######################################
    ###anything below this is dead code!###
    #######################################


@bot.event
@asyncio.coroutine
def on_command(command, ctx):
    if ctx.message.channel.is_private:
        destination = 'PM'
    else:
        destination = '#{0.channel.name} ({0.server.name})'.format(ctx.message)
    message_decoded = decode_emoji(ctx.message.content)
    log.info('Command by {0} in {1}: {2}'.format(ctx.message.author.name, destination,message_decoded))

@bot.event
@asyncio.coroutine
def on_message(message):
    #This is a workaround to make commands case insensitive
    split = message.content.split(" ",1)
    if len(split) == 2:
        message.content = split[0].lower()+" "+split[1]
        if message.author.id != bot.user.id and (not split[0].lower()[1:] in command_list or not split[0][:1] == "/") and not message.channel.is_private and message.channel.name == askchannel:
            yield from bot.delete_message(message)
            return
    else:
        message.content = message.content.lower()
        if message.author.id != bot.user.id and (not message.content.lower()[1:] in command_list or not message.content[:1] == "/") and not message.channel.is_private and message.channel.name == askchannel:
            yield from bot.delete_message(message)
            return
    yield from bot.process_commands(message)

@bot.event
@asyncio.coroutine
def on_member_join(member):
    message = "Welcome {0.mention}! Please tell us about yourself, who is your Tibia character?\r\nSay /im *charactername* and I'll begin tracking it for you!"
    log.info("New member joined: {0.name} (ID: {0.id})".format(member))
    ##Starting a private message with new members allows us to keep track of them even after they leave our visible servers.
    yield from bot.start_private_message(member)
    yield from bot.send_message(member.server,message.format(member))
    
@bot.event
@asyncio.coroutine
def on_member_remove(member):
    log.info("A member left discord: {0.name} (ID: {0.id})".format(member))

@bot.event
@asyncio.coroutine
def on_message_delete(message):
    message_decoded = decode_emoji(message.content)
    log.info("A message by {0} was deleted. Message: '{1}'".format(message.author.name,message_decoded))
    for attachment in message.attachments:
        log.info(attachment)

@bot.event
@asyncio.coroutine
def on_message_edit(older_message,message):
    older_message_decoded = decode_emoji(older_message.content)
    log.info("{0} has edited the message: '{1}'".format(older_message.author.name,older_message_decoded))
    for attachment in older_message.attachments:
        log.info(attachment)

    message_decoded = decode_emoji(message.content)
    log.info("New message: '{0}'".format(message_decoded))
    for attachment in message.attachments:
        log.info(attachment)

@asyncio.coroutine
def announceEvents():
    firstAnnouncement = 60*30
    secondAnnouncement = 60*15
    thirdAnnouncement = 60*5
    c = userDatabase.cursor()
    channel = getChannelByServerAndName(mainserver,mainchannel)
    try:
        #Current time
        date = time.time()
        #Find incoming events
        ##First announcement
        c.execute("SELECT creator, start, name, id FROM events WHERE start < ? AND start > ? AND active = 1 AND status > 3 ORDER by start ASC",(date+firstAnnouncement+60,date+firstAnnouncement,))
        results = c.fetchall()
        if len(results) > 0:
            for row in results:
                author = "unknown" if getUserById(row[0]) is None else getUserById(row[0]).name
                name = row[2]
                id = row[3]
                timediff = timedelta(seconds=row[1]-date)
                days,hours,minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60)%60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days,hours,minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours,minutes)
                else:
                    start = '{0} minutes'.format(minutes)
                
                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}.".format(name,author,start,id)
                c.execute("UPDATE events SET status = 3 WHERE id = ?",(id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name,author,start,id))
                yield from bot.send_message(channel,message)
        ##Second announcement
        c.execute("SELECT creator, start, name, id FROM events WHERE start < ? AND start > ? AND active = 1 AND status > 2 ORDER by start ASC",(date+secondAnnouncement+60,date+secondAnnouncement,))
        results = c.fetchall()
        if len(results) > 0:
            for row in results:
                author = "unknown" if getUserById(row[0]) is None else getUserById(row[0]).name
                name = row[2]
                id = row[3]
                timediff = timedelta(seconds=row[1]-date)
                days,hours,minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60)%60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days,hours,minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours,minutes)
                else:
                    start = '{0} minutes'.format(minutes)
                
                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}.".format(name,author,start,id)
                c.execute("UPDATE events SET status = 2 WHERE id = ?",(id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name,author,start,id))
                yield from bot.send_message(channel,message)
        ##Third announcement
        c.execute("SELECT creator, start, name, id FROM events WHERE start < ? AND start > ? AND active = 1 AND status > 1 ORDER by start ASC",(date+thirdAnnouncement+60,date+thirdAnnouncement,))
        results = c.fetchall()
        if len(results) > 0:
            for row in results:
                author = "unknown" if getUserById(row[0]) is None else getUserById(row[0]).name
                name = row[2]
                id = row[3]
                timediff = timedelta(seconds=row[1]-date)
                days,hours,minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60)%60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days,hours,minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours,minutes)
                else:
                    start = '{0} minutes'.format(minutes)
                
                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting in {2}!".format(name,author,start,id)
                c.execute("UPDATE events SET status = 1 WHERE id = ?",(id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - In {2}".format(name,author,start,id))
                yield from bot.send_message(channel,message)
        ##Last announcement
        c.execute("SELECT creator, start, name, id FROM events WHERE start < ? AND start > ? AND active = 1 AND status > 0 ORDER by start ASC",(date+60,date,))
        results = c.fetchall()
        if len(results) > 0:
            for row in results:
                author = "unknown" if getUserById(row[0]) is None else getUserById(row[0]).name
                name = row[2]
                id = row[3]
                timediff = timedelta(seconds=row[1]-date)
                days,hours,minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60)%60
                if days:
                    start = '{0} days, {1} hours and {2} minutes'.format(days,hours,minutes)
                elif hours:
                    start = '{0} hours and {1} minutes'.format(hours,minutes)
                else:
                    start = '{0} minutes'.format(minutes)
                
                message = "**{0}** (by **@{1}**,*ID:{3}*) - Is starting right now!".format(name,author,start,id)
                c.execute("UPDATE events SET status = 0 WHERE id = ?",(id,))
                log.info("Announcing event: {0} (by @{1},ID:{3}) - Starting ({2})".format(name,author,start,id))
                yield from bot.send_message(channel,message)
    finally:
        userDatabase.commit()
        c.close()

########a think function!
@asyncio.coroutine
def think():
    #################################################
    #             Nezune's cave                     #
    # Do not touch anything, enter at your own risk #
    #################################################
    lastServerOnlineCheck = datetime.now()
    lastPlayerDeathCheck = datetime.now()
    global globalOnlineList
    while 1:
        #announce incoming events
        yield from announceEvents()
        
        #periodically check server online lists
        if datetime.now() - lastServerOnlineCheck > serveronline_delay and len(tibiaservers) > 0:
            ##pop last server in qeue, reinsert it at the beggining
            currentServer = tibiaservers.pop()
            tibiaservers.insert(0, currentServer)

            #get online list for this server
            currentServerOnline = yield from getServerOnline(currentServer)

            if len(currentServerOnline) > 0:
                #open connection to users.db
                c = userDatabase.cursor()

                ##remove chars that are no longer online from the globalOnlineList
                offlineList = []
                for char in globalOnlineList:
                    if char.split("_",1)[0] == currentServer:
                        offline = True
                        for serverChar in currentServerOnline:
                            if serverChar['name'] == char.split("_",1)[1]:
                                offline = False
                                break
                        if offline:
                            offlineList.append(char)
                for nowOfflineChar in offlineList:
                    globalOnlineList.remove(nowOfflineChar)

                #add new online chars and announce level differences
                for serverChar in currentServerOnline:
                    c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?",(serverChar['name'],))
                    result = c.fetchone()
                    if result:
                        #if its a stalked character
                        lastLevel = result[1]
                        #we update their last level in the db
                        c.execute("UPDATE chars SET last_level = ? WHERE name LIKE ?",(serverChar['level'],serverChar['name'],))
                        
                        if not (currentServer+"_"+serverChar['name']) in globalOnlineList:
                            ##if the character wasnt in the globalOnlineList we add them
                            #(we insert them at the beggining of the list to avoid messing with the death checks order)
                            globalOnlineList.insert(0,(currentServer+"_"+serverChar['name']))
                            ##since this is the first time we see them online we flag their last death time
                            #to avoid backlogged death announces
                            c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?",(None,serverChar['name'],))

                        ##else we check for levelup
                        elif lastLevel < serverChar['level'] and lastLevel > 0:
                            #Saving level up date in database
                            c.execute("INSERT INTO char_levelups (char_id,level,date) VALUES(?,?,?)",(result[2],serverChar['level'],time.time(),))
                            ##announce the level up
                            yield from announceLevel(serverChar['name'],serverChar['level'])

                #Close cursor and commit changes
                userDatabase.commit()
                c.close()

            #update last server check time
            lastServerOnlineCheck = datetime.now()

        #periodically check for deaths
        if datetime.now() - lastPlayerDeathCheck > playerdeath_delay and len(globalOnlineList) > 0:
            ##pop last char in qeue, reinsert it at the beggining
            currentChar = globalOnlineList.pop()
            globalOnlineList.insert(0, currentChar)

            #get rid of server name
            currentChar = currentChar.split("_",1)[1]
            #get death list for this char
            #we only need the last death
            currentCharDeaths = yield from getPlayerDeaths(currentChar,True)

            if (type(currentCharDeaths) is list) and len(currentCharDeaths) > 0:
                c = userDatabase.cursor()

                c.execute("SELECT name, last_death_time, id FROM chars WHERE name LIKE ?",(currentChar,))
                result = c.fetchone()
                if result:
                    lastDeath = currentCharDeaths[0]
                    dbLastDeathTime = result[1]
                    ##if the db lastDeathTime is None it means this is the first time we're seeing them online
                    #so we just update it without announcing deaths
                    if dbLastDeathTime is None:
                        c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?",(lastDeath['time'],currentChar,))
                    #else if the last death's time doesn't match the one in the db
                    elif dbLastDeathTime != lastDeath['time']:
                        #update the lastDeathTime for this char in the db
                        c.execute("UPDATE chars SET last_death_time = ? WHERE name LIKE ?",(lastDeath['time'],currentChar,))
                        #Saving death info in database
                        c.execute("INSERT INTO char_deaths (char_id,level,killer,byplayer,date) VALUES(?,?,?,?,?)",(result[2],int(lastDeath['level']),lastDeath['killer'],lastDeath['byPlayer'],time.time(),))
                        #and announce the death
                        yield from announceDeath(currentChar,lastDeath['time'],lastDeath['level'],lastDeath['killer'],lastDeath['byPlayer'])

                #Close cursor and commit changes
                userDatabase.commit()
                c.close()
            #update last death check time
            lastPlayerDeathCheck = datetime.now()

        #sleep for a bit and then loop back
        yield from asyncio.sleep(1)
########

########announceDeath
@asyncio.coroutine
def announceDeath(charName,deathTime,deathLevel,deathKiller,deathByPlayer):
    if int(deathLevel) < announceTreshold:
        #Don't announce for low level players
        return
        
    log.info("Announcing death: {0}({1}) | {2}".format(charName,deathLevel,deathKiller))
    char = yield from getPlayer(charName)
    #Failsafe in case getPlayer fails to retrieve player data
    if type(char) is not dict:
        log.warning("Error in announceDeath, failed to getPlayer("+charName+")")
        return

    if not(char['world'] in tibiaservers):
        #Don't announce for players in non-tracked worlds
        return
    #Choose correct pronouns
    pronoun = ["he","his","him"] if char['gender'] == "male" else ["she","her","her"]

    channel = getChannelByServerAndName(mainserver,mainchannel)
    #Find killer article (a/an)
    deathKillerArticle = ""
    if not deathByPlayer:
        deathKillerArticle = deathKiller.split(" ",1)
        if deathKillerArticle[0] in ["a","an"] and len(deathKillerArticle) > 1:
            deathKiller = deathKillerArticle[1]
            deathKillerArticle = deathKillerArticle[0]+" "
        else:
            deathKillerArticle = ""
    #Select a message
    message = weighedChoice(deathmessages_player,char['vocation'],int(deathLevel)) if deathByPlayer else weighedChoice(deathmessages_monster,char['vocation'],int(deathLevel),deathKiller)
    #Format message with death information
    deathInfo = {'charName' : charName, 'deathTime' : deathTime, 'deathLevel' : deathLevel, 'deathKiller' : deathKiller, 'deathKillerArticle' : deathKillerArticle, 'pronoun1' : pronoun[0], 'pronoun2' : pronoun[1], 'pronoun3' : pronoun[2]}
    message = message.format(**deathInfo)
    #Format extra stylization
    message = formatMessage(message)
    
    yield from bot.send_message(channel,message[:1].upper()+message[1:])
########

########announceLevel
@asyncio.coroutine
def announceLevel(charName,newLevel):
    if int(newLevel) < announceTreshold:
        #Don't announce low level players
        return
    log.info("Announcing level up: {0} ({1})".format(charName,newLevel))
    char = yield from getPlayer(charName)
    #Failsafe in case getPlayer fails to retrieve player data
    if type(char) is not dict:
        log.error("Error in announceLevel, failed to getPlayer("+charName+")")
        return
    #Choose correct pronouns
    pronoun = ["he","his","him"] if char['gender'] == "male" else ["she","her","her"]
    
    channel = getChannelByServerAndName(mainserver,mainchannel)

    #Select a message
    message = weighedChoice(levelmessages,char['vocation'],int(newLevel))
    #Format message with level information
    levelInfo = {'charName' : charName, 'newLevel' : newLevel, 'pronoun1' : pronoun[0], 'pronoun2' : pronoun[1], 'pronoun3' : pronoun[2]}
    message = message.format(**levelInfo)
    #Format extra stylization
    message = formatMessage(message)

    yield from bot.send_message(channel,message)
########

###### Bot commands
@bot.command(aliases=["dice"])
@asyncio.coroutine
def roll(dice : str):
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
def choose(ctx,*choices : str):
    """Chooses between multiple choices."""
    user = ctx.message.author
    yield from bot.say('Alright, **@{0}**, I choose: "{1}"'.format(user.name,random.choice(choices)))

@bot.command(pass_context=True,aliases=["i'm","iam"],no_pm=True)
@asyncio.coroutine
def im(ctx,*charname : str):
    """Lets you add your first tibia character(s) for the bot to track.

    If you need to add any more characters or made a mistake, please message an admin."""
    
    ##This is equivalent to someone using /stalk addacc on themselves.
    #To avoid abuse it will only work on users who have joined recently and have no characters added to their account.
    #This command can't work on private messages, since we need a member instead of an user to be able to check the joining date.

    charname = " ".join(charname).strip()
    user = ctx.message.author
    try:
        c = userDatabase.cursor()
        admins_message = joinList(["**@"+getUserById(admin).name+"**" for admin in admin_ids],", "," or ")
        servers_message = joinList(["**"+server+"**" for server in tibiaservers],", "," or ")
        notallowed_message = ("I'm sorry, {0.mention}, this command is reserved for new users, if you need any help adding characters to your account please message "+admins_message+".").format(user)
        
        ##Check if the user has joined recently
        if datetime.now() - user.joined_at > timewindow_im_joining:
            yield from bot.say(notallowed_message)
            return
        ##Check that this user doesn't exist or has no chars added to it yet.
        c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
        result = c.fetchone()
        if(result is not None):
            c.execute("SELECT name,user_id FROM chars WHERE user_id LIKE ?",(user.id,))
            result = c.fetchone();
            if(result is not None):
                yield from bot.say(notallowed_message)
                return
        else:
            #Add the user if it doesn't exist
            c.execute("INSERT INTO discord_users(id,name) VALUES (?,?)",(user.id,user.name,))
        
        char = yield from getPlayer(charname)
        if(type(char) is not dict):
            if char == ERROR_NETWORK:
                yield from bot.say("I couldn't fetch the character, please try again.")
            elif char == ERROR_DOESNTEXIST:
                yield from bot.say("That character doesn't exists.")
            return
        chars = char['chars']
        #If the char is hidden,we still add the searched character
        if(len(chars) == 0):
            chars = [char]
        skipped = []
        updated = []
        added = []
        for char in chars:
            if(char['world'] not in tibiaservers):
                skipped.append(char)
                continue
            c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?",(char['name'],))
            result = c.fetchone();
            if(result is not None):
                if getUserById(result[1]) is None:
                    updated.append({'name' : char['name'], 'world' : char['world'], 'prevowner' : result[1]})
                    continue
                else:
                    yield from bot.say("I'm sorry but a character in that account was already claimed by **@{0}**.".format(getUserById(result[1]).name)+"\r\n"+
                        "Have you made a mistake? Message "+admins_message+" if you need any help!")
                    return
            char = yield from getPlayer(char['name'])
            added.append(char)
        if len(skipped) == len(chars):
            yield from bot.say("I'm sorry, I couldn't find any characters in that account from the worlds I track ("+servers_message+")\r\n"+
                        "Have you made a mistake? Message "+admins_message+" if you need any help!")
            return
        for char in updated:
            c.execute("UPDATE chars SET user_id = ? WHERE name LIKE ?",(user.id,char['name']))
            log.info("Character {0} was reasigned to {1.name} (ID: {1.id}) from /im. (Previous owner (ID: {2}) was not found)".format(char['name'],user,char['prevowner']))
        for char in added:
            c.execute("INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",(char['name'],char['level']*-1,char['vocation'],user.id))
            log.info("Character {0} was asigned to {1.name} (ID: {1.id}) from /im.".format(char['name'],user))

        yield from bot.say(("Thanks {0.mention}! I have added the following character(s) to your account: "+", ".join("**"+char['name']+"**" for char in added)+", ".join("**"+char['name']+"**" for char in updated)+".\r\nFrom now on I will track level advances and deaths for you, if you need to add any more characters please message "+admins_message+".").format(user))
        return
    finally:
        c.close()
        userDatabase.commit()


@bot.command()
@asyncio.coroutine
def online():
    """Tells you which users are online on Tibia

    This list gets updated based on Tibia.com online list, so it takes a couple minutes
    to be updated."""
    discordOnlineChars = []
    c = userDatabase.cursor()
    try:
        for char in globalOnlineList:
            char = char.split("_",1)[1]
            c.execute("SELECT name, user_id, vocation, last_level FROM chars WHERE name LIKE ?",(char,))
            result = c.fetchone()
            if result:
                #this will always be true unless a char is removed from chars inbetween globalOnlineList updates
                discordOnlineChars.append({"name" : result[0], "id" : result[1], "vocation" : result[2], "level" : result[3]})
        if len(discordOnlineChars) == 0:
            yield from bot.say("There is no one online from Discord.")
        else:
            reply = "The following discord users are online:"
            for char in discordOnlineChars:
                user = getUserById(char['id'])

                char['vocation'] = vocAbb(char['vocation'])
                #discordName = user.name if (user is not None) else "unknown"
                if user is not None:
                    discordName = user.name
                    reply += "\n\t{0} (Lvl {1} {2}, **@{3}**)".format(char['name'],abs(char['level']),char['vocation'],discordName)
            yield from bot.say(reply)
    finally:
        c.close()
                
@bot.command()
@asyncio.coroutine
def about():
    """Shows information about the bot"""
    yield from bot.say(getAboutContent())
    
@bot.command(pass_context=True,aliases=["event","checkevents","checkevent"])
@asyncio.coroutine
def events(ctx,*args : str):
    """Shows a list of current active events
    
    The following subcommands are only available through PMs or askchannel
    To add an event, use:
    /events add [startTime] [eventName]
    e.g. /events add 1h20m Pits of Inferno Quest
    
    To edit an event, use:
    /events editname [id] [newName]
    /events edittime [id] [newTime]
    e.g. /events editname 4 PoI Quest
    e.g. /events edittime 4 5h
    
    To delete an event, use:
    /events delete [id]"""
    #Time the event will be shown in the event list
    timeThreshold = 60*30
    c = userDatabase.cursor()
    try:
        #Current time
        date = time.time()
        if not args:
            reply = ""
            #Recent events
            c.execute("SELECT creator, start, name, id FROM events WHERE start < ? AND start > ? AND active = 1 ORDER by start ASC",(date,date-timeThreshold,))
            results = c.fetchall()
            if len(results) > 0:
                reply += "Recent events:"
                for row in results:
                    author = "unknown" if getUserById(row[0]) is None else getUserById(row[0]).name
                    name = row[2]
                    id = row[3]
                    timediff = timedelta(seconds=date-row[1])
                    minutes = (timediff.seconds//60)%60
                    start = 'Started {0} minutes ago'.format(minutes)                    
                    reply += "\n\t**{0}** (by **@{1}**,*ID:{3}*) - {2}".format(name,author,start,id)
            #Upcoming events
            c.execute("SELECT creator, start, name, id FROM events WHERE start > ? AND active = 1 ORDER BY start ASC",(date,))
            results = c.fetchall()
            if len(results) > 0:
                if(reply):
                    reply += "\n"
                reply += "Upcoming events:"
                for row in results:
                    author = "unknown" if getUserById(row[0]) is None else getUserById(row[0]).name
                    name = row[2]
                    id = row[3]
                    timediff = timedelta(seconds=row[1]-date)
                    days,hours,minutes = timediff.days, timediff.seconds//3600, (timediff.seconds//60)%60
                    if days:
                        start = 'In {0} days, {1} hours and {2} minutes'.format(days,hours,minutes)
                    elif hours:
                        start = 'In {0} hours and {1} minutes'.format(hours,minutes)
                    elif minutes > 0:
                        start = 'In {0} minutes'.format(minutes)
                    else:
                        start = 'Starting now!'
                    
                    reply += "\n\t**{0}** (by **@{1}**,*ID:{3}*) - {2}".format(name,author,start,id)
            if reply:
                yield from bot.say(reply)
            else:
                yield from bot.say("There are no upcoming events.")
            return
        if not ctx.message.channel.is_private and not ctx.message.channel.name == askchannel:
            return
            
        if args[0] == "add":
            if len(args) < 3:
                yield from bot.say("Invalid arguments, the format is the following:\n`/events add [startTime] [eventName]`\ne.g. `/events add 1d15h Pits of Inferno`")
                return
            creator = ctx.message.author.id
            timeStr = args[1]
            name = " ".join(args[2:])
            
            m = re.search(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?',timeStr)
            if(not m.group(0)):
                yield from bot.say("Time must be in the following formats: *1d1h20m*, *6h*, *2h30m*, *30m*")
                return
            if(m.group(1)):
                date += int(m.group(1))*60*60*24
            if(m.group(2)):
                date += int(m.group(2))*60*60
            if(m.group(3)):
                date += int(m.group(3))*60
                
            c.execute("SELECT * FROM events WHERE creator = ? AND active = 1 AND start > ?",(creator,date,))
            result= c.fetchall()
            if len(result) > 1 and creator not in admin_ids:
                yield from bot.say("You can only have two running events at a time. Delete or edit your active event.")
                return
            c.execute("INSERT INTO events (creator,start,name) VALUES(?,?,?)",(creator,date,name,))
            id = c.lastrowid
            yield from bot.say("Event registered succesfully.\n\t**{0}** in *{1}*.\n*To edit this event use ID {2}*".format(name,timeStr,id))
            
        if args[0] == "editname":
            if len(args) < 3:
                yield from bot.say("Invalid arguments, the format is the following:\n`/events editname [id] [newName]`\ne.g. `/events editname 4 PoI Quest`")
                return
            creator = ctx.message.author.id
            id = int(args[1])
            name = " ".join(args[2:])
            c.execute("SELECT creator FROM events WHERE id = ? AND active = 1 AND start > ?",(id,date,))
            result = c.fetchone()
            if not result:
                yield from bot.say("There are no active events with that ID.")
                return
            if result[0] != int(creator):
                yield from bot.say("You can only edit your own events.")
                return
            c.execute("UPDATE events SET name = ? WHERE id = ?",(name,id,))
            
            yield from bot.say("Your events name was changed succesfully.")
            
        if args[0] == "edittime":
            if len(args) != 3:
                yield from bot.say("Invalid arguments, the format is the following:\n`/events edittime [id] [newStart]`\ne.g. `/events edittime 4 5h`")
                return
            creator = ctx.message.author.id
            id = int(args[1])
            timeStr = args[2]
            c.execute("SELECT creator FROM events WHERE id = ? AND active = 1 AND start > ?",(id,date,))
            result = c.fetchone()
            if not result:
                yield from bot.say("There are no active events with that ID.")
                return
            if result[0] != int(creator) and creator not in admin_ids:
                yield from bot.say("You can only edit your own events.")
                return
                
            m = re.search(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?',timeStr)
            if(not m.group(0)):
                yield from bot.say("Time must be in the following formats: *1d1h20m*, *6h*, *2h30m*, *30m*")
                return
            if(m.group(1)):
                date += int(m.group(1))*60*60*24
            if(m.group(2)):
                date += int(m.group(2))*60*60
            if(m.group(3)):
                date += int(m.group(3))*60
            
            c.execute("UPDATE events SET start = ? WHERE id = ?",(date,id,))
            yield from bot.say("Your events start time was changed succesfully.")
            
        if args[0] == "delete":
            if len(args) != 2:
                yield from bot.say("Invalid arguments, the format is the following:\n`/events delete [id]`")
                return
            
            creator = ctx.message.author.id
            id = int(args[1])
            
            c.execute("SELECT creator FROM events WHERE id = ? AND active = 1 AND start > ?",(id,date,))
            result = c.fetchone()
            if not result:
                yield from bot.say("There are no active events with that ID.")
                return
            if result[0] != int(creator) and creator not in admin_ids:
                yield from bot.say("You can only delete your own events.")
                
            c.execute("UPDATE events SET active = 0 WHERE id = ?",(id,))
            yield from bot.say("Your event was deleted succesfully.")
        
    finally:
        userDatabase.commit()
        c.close()
        
##### Admin only commands ####

######## Makesay command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def makesay(ctx,*args: str):
    if not ctx.message.author.id in admin_ids:
        return
    if ctx.message.channel.is_private:
        channel = getChannelByServerAndName(mainserver,mainchannel)
        yield from bot.send_message(channel," ".join(args))
    else:
        yield from bot.delete_message(ctx.message)
        yield from bot.send_message(ctx.message.channel," ".join(args))

@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def stalk(ctx, subcommand, *args : str):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    params = (" ".join(args)).split(",")
    try:
        c = userDatabase.cursor()
        ###Add user
        if(subcommand == "add"):
            if len(params) != 1:
                yield from bot.say("The correct syntax is: /stalk add username")
                return
            user = getUserByName(params[0])
            if(user is None):
                yield from bot.say("I don't see any user named **{0}**".format(params[0]))
                return
            c.execute("SELECT id from discord_users WHERE id LIKE ?",(user.id,))
            if(c.fetchone() is not None):
                yield from bot.say("**@{0}** is already registered.".format(user.name))
                return
            c.execute("INSERT INTO discord_users(id,name) VALUES (?,?)",(user.id,user.name,))
            yield from bot.say("**@{0}** was registered succesfully.".format(user.name))

        ###Add char & Add account common operations
        if(subcommand == "addchar" or subcommand == "addacc"):
            if len(params) != 2:
               yield from bot.say("The correct syntax is: /stalk {0} username,character".format(subcommand))
               return
            user = getUserByName(params[0])
            char = yield from getPlayer(params[1])
            if(user is None):
                yield from bot.say("I don't see any user named **{0}**".format(params[0]))
                return
            if(type(char) is not dict):
                if char == ERROR_NETWORK:
                    yield from bot.say("I couldn't fetch the character, please try again.")
                elif char == ERROR_DOESNTEXIST:
                    yield from bot.say("That character doesn't exists.")
                return
            ###Add char
            if(subcommand == "addchar"):
                c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?",(char['name'],))
                result = c.fetchone();
                if(result is not None):
                    if(char['name'] != params[1]):
                        c.execute("UPDATE chars SET name = ? WHERE id LIKE ?",(user['name'],result[1],))
                        yield from bot.say("This character's name was changed from **{0}** to **{1}**".format(params[1],char['name']))
                    #Registered to a different user
                    if(result[1] != user.id):
                        username = "unknown" if getUserById(result[1]) is None else getUserById(result[1]).name
                        yield from bot.say("This character is already registered to **@{0}**".format(username))
                        return
                    #Registered to current user
                    yield from bot.say("This character is already registered to this user.")
                    return
                c.execute("INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",(char['name'],char['level']*-1,char['vocation'],user.id))
                c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
                result = c.fetchone()
                if(result is None):
                    c.execute("INSERT INTO discord_users(id,name) VALUES (?,?)",(user.id,user.name,))
                    yield from bot.say("**@{0}** was registered succesfully.".format(user.name))
                yield from bot.say("**{0}** was registered succesfully to this user.".format(char['name']))
                return
            ###Add account
            if(subcommand == "addacc"):
                chars = char['chars']
                #If the char is hidden,we still add the searched character
                if(len(chars) == 0):
                    yield from bot.say("Character is hidden.")
                    chars = [char]
                for char in chars:
                    if(char['world'] not in tibiaservers):
                        yield from bot.say("**{0}** skipped, character not in server list.".format(char['name']))
                        continue
                    char = yield from getPlayer(char['name'])
                    c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?",(char['name'],))
                    result = c.fetchone();
                    if(result is not None):
                        if(result[1] != user.id):
                            username = "unknown" if getUserById(result[1]) is None else getUserById(result[1]).name
                            yield from bot.say("**{0}** is already registered to **@{1}**".format(char['name'],username))
                            continue
                        yield from bot.say("**{0}** is already registered to this user.".format(char['name']))
                        continue
                    c.execute("INSERT INTO chars (name,last_level,vocation,user_id) VALUES (?,?,?,?)",(char['name'],char['level']*-1,char['vocation'],user.id))
                    yield from bot.say("**{0}** was registered succesfully to this user.".format(char['name']))
                c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
                result = c.fetchone()
                if(result is None):
                    c.execute("INSERT INTO discord_users(id,name) VALUES (?,?)",(user.id,user.name,))
                    yield from bot.say("**@{0}** was registered succesfully.".format(user.name))
                    return

        ###Remove char
        if(subcommand == "removechar"):
            if len(params) != 1:
                yield from bot.say("The correct syntax is: /stalk {0} character".format(subcommand))
                return
            char = params[0]
            #This could be used to remove deleted chars so we don't need to check anything
            #Except if the char exists...
            c.execute("SELECT name, user_id FROM chars WHERE name LIKE ?",(char,))
            result = c.fetchone()
            if(result is None):
                yield from bot.say("There's no character with that name registered.")
                return
            username = "unknown" if getUserById(result[1]) is None else getUserById(result[1]).name
            c.execute("DELETE FROM chars WHERE name LIKE ?",(result[0],))
            yield from bot.say("**{0}** was removed succesfully from **@{1}**.".format(result[0],username))
            return
        ###Remove user
        if(subcommand == "remove"):
            if len(params) != 1:
                yield from bot.say("The correct syntax is: /stalk {0} user".format(subcommand))
                return
            user = getUserByName(params[0])
            if(user is None):
                yield from bot.say("I don't see any user named **{0}**\nI recommend using purge to remove former users.".format(params[0]))
                return
            c.execute("SELECT id from discord_users WHERE id = ?",(user.id,))
            if(c.fetchone() is None):
                yield from bot.say("**@{0}** wasn't registered.".format(user.name))
                return
            c.execute("DELETE FROM discord_users WHERE id = ?",(user.id,))
            yield from bot.say("**@{0}** was removed succesfully.".format(user.name))
            c.execute("SELECT name FROM chars WHERE user_id = ?",(user.id,))
            result = c.fetchall()
            if len(result) >= 1:
                chars = ["**"+i[0]+"**" for i in result]
                reply = "The following chars were registered to that user, remove them or use purge to clean up:\n\t"
                reply += "\n\t".join(chars)
                yield from bot.say(reply)
            return
        ###Purge
        if(subcommand == "purge"):
            c.execute("SELECT id FROM discord_users")
            result = c.fetchall()
            if result is None:
                yield from bot.say("There are no users registered.")
                return
            delete_users = list()
            yield from bot.say("Initiating purge...")
            #Deleting users no longer in server
            for row in result:
                user = getUserById(row[0])
                if(user is None):
                    delete_users.append((row[0],))
            if len(delete_users) > 0:
                c.executemany("DELETE FROM discord_users WHERE id = ?",delete_users)
                yield from bot.say("{0} user(s) no longer in the server were removed.".format(c.rowcount))
            #Deleting chars with non-existant user
            c.execute("SELECT name FROM chars WHERE user_id NOT IN (SELECT id FROM discord_users)")
            result = c.fetchall()
            if len(result) >= 1:
                chars = ["**"+i[0]+"**" for i in result]
                reply = "{0} char(s) were assigned to a non-existant user and were deleted:\n\t".format(len(result))
                reply += "\n\t".join(chars)
                yield from bot.say(reply)
                c.execute("DELETE FROM chars WHERE user_id NOT IN (SELECT id FROM discord_users)")
            #Removing deleted chars
            c.execute("SELECT name,last_level,vocation FROM chars")
            result = c.fetchall()
            if(result is None):
                return
            delete_chars = list()
            rename_chars = list()
            #revoc_chars = list()
            for name,last_level,vocation in result:
                char = yield from getPlayer(name)
                if char == ERROR_NETWORK:
                    yield from bot.say("Couldn't fetch **{0}**, skipping...".format(name))
                    continue
                #Char was deleted
                if char == ERROR_DOESNTEXIST:
                    delete_chars.append((name,))
                    yield from bot.say("**{0}** doesn't exists, deleting...".format(name))
                    continue
                #Char was renamed
                if char['name'] != name:
                    rename_chars.append((char['name'],name,))
                    yield from bot.say("**{0}** was renamed to **{1}**, updating...".format(name,char['name']))
                ##Char vocation changed
                #if char['vocation'] != vocation:
                #    revoc_chars.append((char['vocation'],name,))
                #    yield from bot.say("**{0}**'s vocation was set to **{1}** from **{2}**, updating...".format(name,char['vocation'],vocation))
            #No need to check if user exists cause those were removed already
            if len(delete_chars) > 0:
                c.executemany("DELETE FROM chars WHERE name LIKE ?",delete_chars)
                yield from bot.say("{0} char(s) were removed.".format(c.rowcount))
            #if len(revoc_chars) > 0:
            #    c.executemany("UPDATE chars SET vocation = ? WHERE name LIKE ?",revoc_chars)
            #    yield from bot.say("{0} char(s)' vocations were updated.".format(c.rowcount))
            if len(rename_chars) > 0:
                c.executemany("UPDATE chars SET name = ? WHERE name LIKE ?",rename_chars)
                yield from bot.say("{0} char(s) were renamed.".format(c.rowcount))
            #Remove users with no chars
            c.execute("SELECT id FROM discord_users WHERE id NOT IN (SELECT user_id FROM chars)")
            result = c.fetchall()
            if len(result) >= 1:
                c.execute("DELETE FROM discord_users WHERE id NOT IN (SELECT user_id FROM chars)")
                yield from bot.say("{0} user(s) with no characters were removed.".format(c.rowcount))
            c.execute("DELETE FROM char_levelups WHERE char_id NOT IN (SELECT id FROM chars)")
            c.execute("DELETE FROM char_deaths WHERE char_id NOT IN (SELECT id FROM chars)")
            if c.rowcount > 0:
                yield from bot.say("{0} level up registries from removed characters were deleted.".format(c.rowcount))
            yield from bot.say("Purge done.")
            return
        ##Check
        if(subcommand == "check"):
            #Fetch a list of users with chars only:
            c.execute("SELECT user_id FROM chars GROUP BY user_id")
            result = c.fetchall()
            if len(result) <= 0:
                yield from bot.say("There are no registered characters.")
                return
            users = [str(i[0]) for i in result]
            members = getServerByName(mainserver).members
            empty_members = list()
            for member in members:
                if member.id == bot.user.id:
                    continue
                if member.id not in users:
                    empty_members.append("**@"+member.name+"**")
            if len(empty_members) == 0:
                yield from bot.say("There are no unregistered users or users without characters.")
                return
            yield from bot.say("The following users are not registered or have no chars registered to them:\n\t{0}".format("\n\t".join(empty_members)))
        ##Checknames
        if(subcommand == "refreshnames"):
            c.execute("SELECT id FROM discord_users")
            result = c.fetchall()
            if len(result) <= 0:
                yield from bot.say("There are no registered users.")
                return
            update_users = list()
            for user in result:
                update_users.append(("unknown" if getUserById(user[0]) is None else getUserById(user[0]).name,user[0]))
            c.executemany("UPDATE discord_users SET name = ? WHERE id LIKE ?",update_users)
            yield from bot.say("Usernames updated succesfully.")
    finally:
        c.close()
        userDatabase.commit()

@stalk.error
@asyncio.coroutine
def stalk_error(error,ctx):
    if type(error) is commands.MissingRequiredArgument:
        yield from bot.say("""```Valid subcommands are:
        /stalk add user
        /stalk addchar user,char
        /stalk addacc user,char
        /stalk remove user
        /stalk removechar char
        /stalk purge
        /stalk check
        /stalk refreshnames```""")


######## Restart command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def restart(ctx):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    yield from bot.say('Restarting...')
    bot.logout()
    log.warning("Closing NabBot")
    if(platform.system() == "Linux"):
        os.system("python3 restart.py {0}".format(ctx.message.author.id))
    else:
        os.system("python restart.py {0}".format(ctx.message.author.id))

    quit()
########

######## Shutdown command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def shutdown(ctx):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    yield from bot.say('Shutdown...')
    bot.logout()
    log.warning("Closing NabBot")
    quit()
########


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
        if(token):
            bot.run(token)
        elif(email and password):
            bot.run(login.email,login.password)
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
    if(platform.system() == "Linux"):
        os.system("python3 restart.py")
    else:
        os.system("python restart.py")
    quit()
