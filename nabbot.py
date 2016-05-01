from utils import *
from login import *
from config import *
from tibia import *

description = '''Mission: Destroy all humans.'''
bot = commands.Bot(command_prefix='/', description=description)
client = discord.Client()

@bot.event
@asyncio.coroutine
def on_ready():
    bot.load_extension("tibia")
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    #expose bot to ultis.py
    ##its either this or importing discord and commands in utils.py...
    utilsGetBot(bot)
    #start up think()
    yield from think()
    #######################################
    ###anything below this is dead code!###
    #######################################

    
########a think function!
@asyncio.coroutine
def think():
    #i could do something like, check if the bot's alive instead of just a "while true" but i dont see the point.
    lastServerOnlineCheck = datetime.now()
    lastPlayerDeathCheck = datetime.now()
    ####this is the global online list
    #dont look at it too closely or you'll go blind!
    #characters are added as servername_charactername and the list is updated periodically using getServerOnline()
    globalOnlineList = []
    while 1:
        #update idle time
        updateChannelIdleTime()
        #After some time (goof_delay) of silence, the bot will send a random message.
        #It won't say anything if the last message was by the bot.
        #if lastmessage != None and isgoof == False and mainchannel_idletime > goof_delay:
            #yield from goof()
        
        ##do any magic we want here
        
        #periodically check server online lists
        if datetime.now() - lastServerOnlineCheck > serveronline_delay and len(tibiaservers) > 0:
            ##pop last server in qeue, reinsert it at the beggining
            currentServer = tibiaservers.pop()
            tibiaservers.insert(0, currentServer)
            
            #get online list for this server
            currentServerOnline = getServerOnline(currentServer)
            
            if len(currentServerOnline) > 0:
                #open connection to users.db
                userdbconn = sqlite3.connect('users.db')
                userdb = userdbconn.cursor()
                
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
                    userdb.execute("SELECT charName, lastLevel FROM tibiaChars WHERE charName LIKE ?",(serverChar['name'],))
                    result = userdb.fetchone()
                    if result:
                        #if its a stalked character
                        lastLevel = result[1]
                        if not (currentServer+"_"+serverChar['name']) in globalOnlineList:
                            ##if the character wasnt in the globalOnlineList we add them
                            #(we insert them at the beggining of the list to avoid messing with the death checks order)
                            globalOnlineList.insert(0,(currentServer+"_"+serverChar['name']))
                            ##since this is the first time we see them online we flag their last death time
                            #to avoid backlogged death announces
                            userdb.execute("UPDATE tibiaChars SET lastDeathTime = ? WHERE charName LIKE ?",('',serverChar['name'],))
                            
                        ##else we check for levelup
                        elif lastLevel < serverChar['level']:
                            ##announce the level up
                            print("Announcing level up: "+serverChar['name'])
                            yield from announceLevel(serverChar['name'],serverChar['level'])

                        #finally we update their last level in the db
                        userdb.execute("UPDATE tibiaChars SET lastLevel = ? WHERE charName LIKE ?",(serverChar['level'],serverChar['name'],))
                
                #close users.db connection
                userdbconn.commit()
                userdbconn.close()
            
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
            currentCharDeaths = getPlayerDeaths(currentChar,True)
            
            if len(currentCharDeaths) > 0:
                #open connection to users.db
                userdbconn = sqlite3.connect('users.db')
                userdb = userdbconn.cursor()
                
                userdb.execute("SELECT charName, lastDeathTime FROM tibiaChars WHERE charName LIKE ?",(currentChar,))
                result = userdb.fetchone()
                if result:
                    lastDeath = currentCharDeaths[0]
                    dbLastDeathTime = result[1]
                    ##if the db lastDeathTime is an empty string it means this is the first time we're seeing them online
                    #so we just update it without announcing deaths
                    if dbLastDeathTime == '':
                        userdb.execute("UPDATE tibiaChars SET lastDeathTime = ? WHERE charName LIKE ?",(lastDeath['time'],currentChar,))
                    #else if the last death's time doesn't match the one in the db
                    elif dbLastDeathTime != lastDeath['time']:
                        #update the lastDeathTime for this char in the db
                        userdb.execute("UPDATE tibiaChars SET lastDeathTime = ? WHERE charName LIKE ?",(lastDeath['time'],currentChar,))
                        #and announce the death
                        print("Announcing death: "+currentChar)
                        yield from announceDeath(currentChar,lastDeath['time'],lastDeath['level'],lastDeath['killer'],lastDeath['byPlayer'])
                
                #close users.db connection
                userdbconn.commit()
                userdbconn.close()
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
    
    char = getPlayer(charName)
    #Failsafe in case getPlayer fails to retrieve player data
    if not char:
        print("Error in announceDeath, failed to getPlayer("+charName+")")
        return
    
    if not(char['world'] in tibiaservers):
        #Don't announce for players in non-tracked worlds
        return
    #Choose correct pronouns
    pronoun = ["he","his"] if char['pronoun'] == "He" else ["she","her"]

    channel = getChannelByServerAndName(mainserver,mainchannel)

    #Select a message
    message = weighedChoice(deathmessages_player) if deathByPlayer else weighedChoice(deathmessages_monster)
    #Format message with player data
    message = message.format(charName,deathTime,deathLevel,deathKiller,pronoun[0],pronoun[1])
    #Format extra stylization
    message = formatMessage(message)
    
    yield from bot.send_message(channel,message[:1].upper()+message[1:])
########

########announceLevel
@asyncio.coroutine
def announceLevel(charName,charLevel):
    if int(charLevel) < announceTreshold:
        #Don't announce for low level players
        return
    
    char = getPlayer(charName)
    #Failsafe in case getPlayer fails to retrieve player data
    if not char:
        print("Error in announceLevel, failed to getPlayer("+charName+")")
        return
    #Choose correct pronouns
    pronoun = ["he","his"] if char['pronoun'] == "He" else ["she","her"]
        
    channel = getChannelByServerAndName(mainserver,mainchannel)
    
    #Select a message
    message = weighedChoice(levelmessages)
    #Format message with player data
    message = message.format(charName,charLevel,pronoun[0],pronoun[1])
    #Format extra stylization
    message = formatMessage(message)
    
    yield from bot.send_message(channel,message)
########

########update idle time, dunno if u wanna use a function for this, just seemed less ugly
def updateChannelIdleTime():
    global mainchannel_idletime
    mainchannel_idletime = datetime.now() - lastmessagetime
########

@asyncio.coroutine
def goof():
    global isgoof
    channel = getChannelByServerAndName(mainserver,mainchannel)
    yield from bot.send_message(channel,random.choice(idlemessages))
    ##this im kinda worried about, it seems to work but i'm not sure if it CANT fuck up
    #afaik, it shouldnt always be seeing its own msg instantly and if yield from means "dont wait for this to be done" then sometimes the isgoof should be set to true and then immediatly set back to false?
    #worked in all my tests though, so we'll see. worse case scenario it sometimes doesnt realize and goofs twice in a row
    
    ##in fact heres an ugly workaround: wait a few seconds before setting isgoof!
    #this holds back the whole think() function too but w/e :D
    yield from asyncio.sleep(2)
    isgoof = True

########custom on_message to handle hidden commands and lastmessage info
@asyncio.coroutine
def on_message(self, message):
    global lastmessage
    global lastmessagetime
    global isgoof
    #update last message
    if not message.channel.is_private:
        if lastmessage is not None and not lastmessage == message and message.channel.name == mainchannel and message.channel.server.name == mainserver and (not lastmessage.author.id == bot.user.id):
            lastmessage = message
            lastmessagetime = datetime.now()
            #if the message didnt come from the bot, set isgoof to false
            isgoof = False
    
    #do the default call to process_commands
    yield from self.process_commands(message)

#replacing default on_message from commands.Bot class
commands.Bot.on_message = on_message
########


@bot.command()
@asyncio.coroutine
def roll(dice : str):
    """Rolls a dice in NdN format."""
    try:
        rolls, limit = map(int, dice.split('d'))
    except Exception:
        yield from bot.say('Format has to be in NdN!')
        return

    result = ', '.join(str(random.randint(1, limit)) for r in range(rolls))
    yield from bot.say(result)

@bot.command(description='For when you wanna settle the score some other way')
@asyncio.coroutine
def choose(*choices : str):
    """Chooses between multiple choices."""
    yield from bot.say(random.choice(choices))
    
@bot.command(pass_context=True)
@asyncio.coroutine
def whois(ctx,*name : str):
    """Tells you the characters of a user"""
    name = " ".join(name).strip()
    #If @username is used
    if "<@" in name:
        id = name[2:-1]
        target = getUserById(id)
    #Username
    else:
        target = getUserByName(name)
    if (target is None):
        yield from bot.say("I don't see anyone with that name.")
        return
    if(target.id == bot.user.id):
        yield from bot.say("*Beep boop beep boop*. I'm just a bot!")
        return
        
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT charName, lastLevel FROM tibiaChars WHERE discordUser LIKE ? ORDER BY lastLevel DESC",(target.id,))
    chars = []
    for row in c:
        name = row[0]
        try:
            level = int(row[1])
        except ValueError:
            level = -1
        chars.append(name+((" (Lvl: "+str(level)+")") if level > 0 else ""))
    c.close()
    if(len(chars) <= 0):
        yield from bot.say("I don't know who that is...")
        return
        
    #TODO: Fix possesive if user ends with s
    yield from bot.say("**{0}**'s character{1}: {2}.".format(target.name,"s are" if len(chars) > 1 else " is", ", ".join(chars)))
    
    
##### Admin only commands #### 

######## Stalk command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def stalk(ctx,*args: str):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
        
    args = " ".join(args).split(",")
    args[:] = [arg.strip() for arg in args]

    if(len(args) < 2 and not args[0] == "purge"):
        yield from bot.say('Valid arguments for /stalk are **add**, **remove**, **weight**, **addchar**, **addacc**, **removechar**, **purge**.')
        return
       
    operation = args[0]
    name = None if operation == "purge" else args[1]
    target = None if operation == "purge" else getUserByName(name)
       
    #If the user is not on the server
    if target is None and not operation == "purge":
        yield from bot.say('User **@'+name.title()+'** not found in server **'+mainserver+'**.')
        return
        
    userdbconn = sqlite3.connect('users.db')
    userdb = userdbconn.cursor()
    
    ##/stalk add,-username-
    if operation == "add":
        userdb.execute("SELECT id FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        #If user is not in database
        if(result is None):
            userdb.execute("INSERT INTO discordUsers VALUES(?,?)",(int(target.id),5,))
            yield from bot.say('Added **@'+target.name+'** to discordUsers, his discord userID is **'+target.id+'**.\r\n'+
        'His importance weight has been set to the default **5**, please use **/stalk weight, -userName-, -weight-** to set it.\r\n'+
        'Use **/stalk addchar, -userName-, -charName-** to add Tibia characters to this user.')
        else:
            yield from bot.say('User **@'+target.name+'** is already in users db.')
    ##/stalk remove,-username-
    elif operation == "remove":
        userdb.execute("SELECT id FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            userdb.execute("SELECT charName FROM tibiaChars WHERE discordUser LIKE ?",(int(target.id),))
            results2 = userdb.fetchall()
            if(results2 is not None):
                for result in results2:
                    charName = result[0]
                    yield from bot.say('Removed **'+charName+'** from tibiaChars.')
            userdb.execute("DELETE FROM tibiaChars WHERE discordUser LIKE ?",(int(target.id),))
            userdb.execute("DELETE FROM discordUsers WHERE id LIKE ?",(int(target.id),))
            yield from bot.say('Removed **@'+target.name+'** from discordUsers.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.')
            
    ##/stalk weight, -discordUser-, -newWeight-
    elif operation == "weight":
        userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            #Nezune: hahaha this if is fucking cancer but oh well it works
            ##Nezune: ^^^^^I like how u tagged this comment as "shit nezune says" just in case it made you look bad
            if len(args) < 3 or not args[2].isdigit() or (args[2].isdigit() and (int(args[2]) > 5 or int(args[2]) < 1)):
                yield from bot.say('Usage for **weight** is **/stalk weight, -discordUser-, -newWeight-**.\r\n'+
            'Valid weights are 1 through 5.')
            else:
                newWeight = int(args[2])
                userdb.execute("UPDATE discordUsers SET weight = ? WHERE id LIKE ?",(newWeight,int(target.id),))
                yield from bot.say('**@'+target.name+'**\'s weight has been set to **'+str(newWeight)+'**.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.\r\n'+
        'Use **/stalk add, -discordUser-** to add this user.')
    ##
    ##/stalk addchar,-discordUser,-charName-
    elif operation == "addchar":
        userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            if len(args) < 3:
                yield from bot.say('Usage for **addchar** is **/stalk addchar, -discordUser-, -charName-**.')
            else:
                charName = str(args[2])
                char = getPlayer(charName)
                if char:
                    #Check if the char was renamed
                    if char['name'].lower() != charName.lower():
                        yield from bot.say('Tibia character **'+charName+'** was renamed to **'+char['name']+'**. The new name will be used.')
                    #Update the charName either way, for case consistency
                    charName = char['name']
                    userdb.execute("SELECT discordUser, charName FROM tibiaChars WHERE charName LIKE ?",(charName,))
                    result = userdb.fetchone()
                    if(result is None):
                        #IMPORTANT, the char['level'] isn't used to avoid congratulating newly added players
                        ##if they're currently online and have leveled up since their last login
                        ##this is because getPlayer uses the character page level which isn't updated until logout
                        ##tibiaChar's lastLevel is set to -1 instead
                        userdb.execute("INSERT INTO tibiaChars VALUES(?,?,?,?)",(int(target.id),charName,-1,None,))
                        yield from bot.say('**'+charName+'** has been added to **@'+target.name+'**\'s Tibia character list.\r\n'+
                    'Use **/stalk removechar, -discordUser-, -charName-** to remove Tibia chars from an user.')
                    else:
                        charOwner = getUserById(result[0])
                        if charOwner is not None:
                            yield from bot.say('Tibia character **'+charName+'** is already assigned to user **@'+charOwner.name+'**.')
                        else:
                            #the old char owner doesnt exist any more for some reason, so just assign it to this new user
                            userdb.execute("UPDATE tibiaChars SET discordUser = ? WHERE charName LIKE ?",(int(target.id),charName,))
                            yield from bot.say('**'+charName+'** has been added to **@'+target.name+'**\'s Tibia character list.\r\n'+
                        '**Warning:** this character was previously assigned to a missing discordUser, a database purge is recommended!')
                else:
                    yield from bot.say('Tibia character **'+charName+'** doesn\'t exist.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.\r\n'+
            'Use **/stalk add, -discordUser-** to add this user.')
    ##
    ##/stalk addacc,-discordUser,-accCharName-
    elif operation == "addacc":
        userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            if len(args) < 3:
                yield from bot.say('Usage for **addacc** is **/stalk addacc, -discordUser-, -accCharName-**.')
            else:
                charName = str(args[2]).title()
                char = getPlayer(charName)
                if char:
                    #Check if the char was renamed
                    if char['name'].lower() != charName.lower():
                        yield from bot.say('Tibia character **'+charName+'** was renamed to **'+char['name']+'**. The new name will be used.')
                    #Update the charName either way, for case consistency
                    charName = char['name']
                    if len(char['chars']) == 1:
                        yield from bot.say('No other chars found in **'+charlistChar['name']+'**\'s character list.')
                    elif len(char['chars']) == 0:
                        char['chars'].append({'name' : char['name'], 'world' : char['world']})
                        yield from bot.say('Tibia character **'+charName+'** is hidden.')
                    for charlistChar in char['chars']:
                        userdb.execute("SELECT discordUser, charName FROM tibiaChars WHERE charName LIKE ?",(charlistChar['name'],))
                        result = userdb.fetchone()
                        if(result is None):
                            if (charlistChar['world'] != tibia_server):
                                yield from bot.say('Skipped **'+charlistChar['name']+'**, character not in '+tibia_server+'.')
                                continue
                            userdb.execute("INSERT INTO tibiaChars VALUES(?,?,?,?)",(int(target.id),charlistChar['name'],-1,None,))
                            yield from bot.say('**'+charlistChar['name']+'** has been added to **@'+target.name+'**\'s Tibia character list.')
                        else:
                            charOwner = getUserById(result[0])
                            if charOwner is not None:
                                yield from bot.say('Tibia character **'+charlistChar['name']+'** is already assigned to user **@'+charOwner.name+'**.')
                            else:
                                #the old char owner doesnt exist any more for some reason, so just assign it to this new user
                                userdb.execute("UPDATE tibiaChars SET discordUser = ? WHERE charName LIKE ?",(int(target.id),charlistChar['name'],))
                                yield from bot.say('**'+charlistChar['name']+'** has been added to **@'+target.name+'**\'s Tibia character list.\r\n'+
                            '**Warning:** this character was previously assigned to a missing discordUser, a database purge is recommended!')
                else:
                    yield from bot.say('Tibia character **'+charName+'** doesn\'t exist.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.\r\n'+
            'Use **/stalk add, -discordUser-** to add this user.')
    ##
    ##/stalk removechar,-discordUser-,-charName-
    elif operation == "removechar":
        userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            if len(args) < 3:
                yield from bot.say('Usage for **removechar** is **/stalk removechar, -discordUser-, -charName-**.')
            else:
                charName = str(args[2]).title()
                userdb.execute("SELECT discordUser, charName FROM tibiaChars WHERE discordUser LIKE ? AND charName LIKE ?",(int(target.id),charName,))
                result = userdb.fetchone()
                if(result is not None):
                    userdb.execute("DELETE FROM tibiaChars WHERE discordUser LIKE ? AND charName LIKE ?",(int(target.id),charName,))
                    yield from bot.say('**'+charName+'** has been removed from **@'+target.name+'**\'s Tibia character list.')
                else:
                    yield from bot.say('**'+charName+'** is not in **@'+target.name+'**\'s Tibia character list.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.\r\n'+
        'Use **/stalk add, -discordUser-** to add this user.')
    ##
    ##/stalk purge
    elif operation == "purge":
        userdb.execute("SELECT id FROM discordUsers")
        results = userdb.fetchall()
        if(results is not None):
            #Iterate over users in discordUsers
            for result in results:
                discordUser = getUserById(result[0])
                discordUserId = result[0]
                userdb.execute("SELECT charName FROM tibiaChars WHERE discordUser LIKE ?",(discordUserId,))
                results2 = userdb.fetchall()
                if(results2 is not None and len(results2) > 0):
                    #Iterate over chars linked to this discord user
                    for result in results2:
                        charName = result[0]
                        if discordUser is None:
                            #If the discord user doesn't exist in our server any more we delete all tibia chars associated with it
                            userdb.execute("DELETE FROM tibiaChars WHERE discordUser LIKE ?",(discordUserId,))
                            yield from bot.say('Removed **'+charName+'** from tibiaChars. (Discord user **'+str(discordUserId)+'** no longer in server)')
                        else:
                            char = getPlayer(charName)
                            if char:
                                #If the char exists check if it was renamed
                                if char['name'].lower() != charName.lower():
                                    #Update to the new char name
                                    userdb.execute("UPDATE tibiaChars SET charName = ? WHERE charName LIKE ?",(char['name'],charName,))
                                    yield from bot.say('Tibia character **'+charName+'** was renamed to **'+char['name']+'**.')
                            else:
                                userdb.execute("DELETE FROM tibiaChars WHERE discordUser LIKE ?",(discordUserId,))
                                yield from bot.say('Removed **'+charName+'** from tibiaChars. (Character no longer exists)')
                    if discordUser is not None:
                        #Check again to see if any chars remain
                        userdb.execute("SELECT charName FROM tibiaChars WHERE discordUser LIKE ?",(discordUserId,))
                        results3 = userdb.fetchall()
                        if(results3 is None and len(results3) > 0):
                            #All chars were removed so we remove the discord user too
                            userdb.execute("DELETE FROM discordUsers WHERE id LIKE ?",(discordUserId,))
                            yield from bot.say('Removed discord user **'+discordUser.name+'** from discordUsers. (No chars remaining) (Id: **'+str(discordUserId)+'**)')
                    else:
                        #This discord user no longer exists in our server
                        userdb.execute("DELETE FROM discordUsers WHERE id LIKE ?",(discordUserId,))
                        yield from bot.say('Removed unknown discord user from discordUsers. (No longer in server) (Id: **'+str(discordUserId)+'**)')
                elif discordUser is not None:
                    #This discord user has no chars assigned so we remove it
                    userdb.execute("DELETE FROM discordUsers WHERE id LIKE ?",(discordUserId,))
                    yield from bot.say('Removed discord user **'+discordUser.name+'** from discordUsers. (No chars asigned) (Id: **'+str(discordUserId)+'**)')
                else:
                    #This discord user no longer exists in our server
                    userdb.execute("DELETE FROM discordUsers WHERE id LIKE ?",(discordUserId,))
                    yield from bot.say('Removed unknown discord user from discordUsers. (No longer in server) (Id: **'+str(discordUserId)+'**)')
    ##
    ####unknown operation
    else:
        yield from bot.say('Unknown operation for /stalk: **'+operation+'**')
    ####
    
    userdbconn.commit()
    userdbconn.close()
########

######## Heynab command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def heynab(ctx,*args: str):
    args = " ".join(args).strip().split(" ")
    
    userdbconn = sqlite3.connect('users.db')
    userdb = userdbconn.cursor()
    
    userName = ""
    while len(args) >= 2:
        #iterate until we find an user that matches or we run out of arguments
        userName = (userName+" "+args[0]).title().strip()
        print("trying: "+userName)
        args.remove(args[0])
        user = getUserByName(userName)
        #If the userName is not on the server
        if user is None:
            #check if its a stalked tibiaChar instead
            userdb.execute("SELECT discordUser FROM tibiaChars WHERE charName LIKE ?",(userName,))
            result = userdb.fetchone()
            if(result is not None):
                user = getUserById(result[0])
                if user is not None:
                    print("found user id "+str(user.id)+" ("+user.name+") from tibia char "+userName)
                else:
                    print("found user id "+str(result[0])+" from tibia char "+userName)
                print("message: "+(" ".join(args)))
                return
        else:
            #found a discord user
            print("found user id "+str(user.id)+" from discord user "+user.name)
            print("message: "+(" ".join(args)))
            return

    print("nobody found!")
########

######## Restart command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def restart(ctx):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    yield from bot.say('Restarting...')
    print("Closing NabBot")
    bot.logout()
    if(platform.system() == "Linux"):
        os.system("python3 restart.py")
    else:
        os.system("python restart.py")
    
    quit()
########

######## Shutdown command
@bot.command(pass_context=True,hidden=True)
@asyncio.coroutine
def shutdown(ctx):
    if not (ctx.message.channel.is_private and ctx.message.author.id in admin_ids):
        return
    yield from bot.say('Shutdown...')
    print("Closing NabBot")
    quit()
########


if __name__ == "__main__":
    #Start logging
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(filename='nabbot.log', encoding='utf-8', mode='a')
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    
    bot.run(username, password)
    print("Emergency restart!")
    if(platform.system() == "Linux"):
        os.system("python3 restart.py")
    else:
        os.system("python restart.py")
    quit()
