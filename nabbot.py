import discord
import logging
from discord.ext import commands
import random
import asyncio
import urllib.request
import urllib
import time

from datetime import *
import sqlite3
import os
import platform

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
                            userdb.execute("UPDATE tibiaChars SET lastDeathTime = ? WHERE charName = ?",('',serverChar['name'],))
                            
                        ##else we check for levelup
                        elif lastLevel < serverChar['level']:
                            ##announce the level up
                            print("Announcing level up: "+serverChar['name'])
                            yield from announceLevel(serverChar['name'],serverChar['level'])

                        #finally we update their last level in the db
                        userdb.execute("UPDATE tibiaChars SET lastLevel = ? WHERE charName = ?",(serverChar['level'],serverChar['name'],))
                
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
                        userdb.execute("UPDATE tibiaChars SET lastDeathTime = ? WHERE charName = ?",(lastDeath['time'],currentChar,))
                    #else if the last death's time doesn't match the one in the db
                    elif dbLastDeathTime != lastDeath['time']:
                        #update the lastDeathTime for this char in the db
                        userdb.execute("UPDATE tibiaChars SET lastDeathTime = ? WHERE charName = ?",(lastDeath['time'],currentChar,))
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

########formatMessage
def formatMessage(message):
    upper = r'\\(.+?)/'
    upper = re.compile(upper,re.MULTILINE+re.S)
    lower = r'/(.+?)\\'
    lower = re.compile(lower,re.MULTILINE+re.S)
    title = r'/(.+?)/'
    title = re.compile(title,re.MULTILINE+re.S)
    message = re.sub(upper,lambda m: m.group(1).upper(), message)
    message = re.sub(lower,lambda m: m.group(1).lower(), message)
    message = re.sub(title,lambda m: m.group(1).title(), message)
    return message
########

########weighedChoice
def weighedChoice(messages):
    #find the max range by adding up the weigh of every message in the list
    range = 0
    for message in messages:
        range = range+message[0]
    #choose a random number
    rangechoice = random.randint(0, range)
    #iterate until we find the matching message
    rangepos = 0
    for message in messages:
        if rangechoice >= rangepos and rangechoice < rangepos+message[0]:
            return message[1]
        rangepos = rangepos+message[0]
    #this shouldnt ever happen...
    print("Error in weighedChoice!")
    return messages[0][1]
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

########i cant use bot.say in think() because theres no context here for the bot to know what channel its supposed to respond to!
########so i made these two (now three!) funcs (the second is just if u dont wanna bother with specifying server name, but if ure in two channels with the same name itll pick one basically at random!)
def getChannelByServerAndName(server_name : str, channel_name : str):
    for server in bot.servers:
        if server.name == server_name or server_name == "":
            for channel in server.channels:
                if not channel.type == discord.ChannelType.voice and channel.name == channel_name:
                    return channel
    return None

def getChannelByName(channel_name : str):
    return getChannelByServerAndName("",channel_name)
    
def getServerByName(server_name : str):
    for server in bot.servers:
        if server.name == server_name:
            return server
    return None
########

########this gets an user by its name (it only checks our main server to avoid issues with duplicate usernames)
def getUserByName(userName):
    global search_server
    server = getServerByName(search_server)
    if server is None:
        return None
    for user in server.members:
        if user.name.lower() == userName.lower():
            return user
    
    return None
########

########this gets an user by its id
def getUserById(userId):
    global search_server
    server = getServerByName(search_server)
    if server is None:
        return None
    for user in server.members:
        if user.id == userId:
            return user
    
    return None
########

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
    target = getUserByName(name)
    if (target is None):
        yield from bot.say("I don't see anyone with that name.")
        return
    if(target.id == bot.user.id):
        yield from bot.say("*Beep boop beep boop*. I'm just a bot!")
        return
        
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT charName FROM tibiaChars WHERE discordUser = ? ORDER BY lastLevel DESC",(target.id,))
    chars = []
    for row in c:
        chars.append(row[0])
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

    
    if(len(args) < 2):
        yield from bot.say('Valid arguments for /stalk are **add**, **remove**, **weight**, **addchar**, **removechar**.')
        return
       
    operation = args[0]
    name = args[1]
    target = getUserByName(name)
       
    #If the user is not on the server
    if target is None:
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
            yield from bot.say('Added **@'+target.name+'** to userList, his discord userID is **'+target.id+'**.\r\n'+
        'His importance weight has been set to the default **5**, please use **/stalk weight, -userName-, -weight-** to set it.\r\n'+
        'Use **/stalk addchar, -userName-, -char-** to add Tibia characters to this user.')
        else:
            yield from bot.say('User **@'+target.name+'** is already in users db.')
    ##/stalk remove,-username-
    elif operation == "remove":
        userdb.execute("SELECT id FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            userdb.execute("DELETE FROM discordUsers WHERE id = ?",(int(target.id),))
            yield from bot.say('Removed **@'+target.name+'** from userList.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.')
            
    ####/stalk weight, -userName-, -newWeight-
    elif operation == "weight":
        userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            #Nezune: hahaha this if is fucking cancer but oh well it works
            if len(args) < 3 or not args[2].isdigit() or (args[2].isdigit() and (int(args[2]) > 5 or int(args[2]) < 1)):
                yield from bot.say('Usage for **weight** is **/stalk weight, -userName-, -newWeight-**.\r\n'+
            'Valid weights are 1 through 5.')
            else:
                newWeight = int(args[2])
                userdb.execute("UPDATE discordUsers SET weight = ? WHERE id = ?",(newWeight,int(target.id),))
                yield from bot.say('**@'+target.name+'**\'s weight has been set to **'+str(newWeight)+'**.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.\r\n'+
        'Use **/stalk add, -userName-** to add this user.')
    ####
    
    ##/stalk addchar,-username,-char-
    elif operation == "addchar":
        userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            if len(args) < 3:
                yield from bot.say('Usage for **addchar** is **/stalk addchar, -userName-, -char-**.')
            else:
                charName = str(args[2]).title()
                userdb.execute("SELECT discordUser, charName FROM tibiaChars WHERE charName LIKE ?",(charName,))
                result = userdb.fetchone()
                if(result is None):
                    userdb.execute("INSERT INTO tibiaChars VALUES(?,?,?,?)",(int(target.id),charName,-1,None,))
                    yield from bot.say('**'+charName+'** has been added to **@'+target.name+'**\'s Tibia character list.\r\n'+
                'Use **/stalk removechar, -userName-, -char-** to remove Tibia chars from an user.')
                else:
                    charOwner = getUserById(str(result[0]))
                    if charOwner is not None:
                        yield from bot.say('Tibia character **'+charName+'** is already assigned to user **@'+charOwner.name+'**.')
                    else:
                        #the old char owner doesnt exist any more for some reason, so just assign it to this new user
                        userdb.execute("UPDATE tibiaChars SET discordUser = ? WHERE charName = ?",(int(target.id),charName,))
                        yield from bot.say('**'+charName+'** has been added to **@'+target.name+'**\'s Tibia character list.\r\n'+
                    'Use **/stalk removechar, -userName-, -char-** to remove Tibia chars from an user.')
        else:
            yield from bot.say('User **@'+target.name+'** not found in users db.\r\n'+
            'Use **/stalk add, -userName-** to add this user.')
            
    ##/stalk removechar,-username-,-char-
    elif operation == "removechar":
        userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(target.id),))
        result = userdb.fetchone()
        if(result is not None):
            if len(args) < 3:
                yield from bot.say('Usage for **removechar** is **/stalk removechar, -userName-, -char-**.')
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
        'Use **/stalk add, -userName-** to add this user.')
        
    ####unknown operation
    else:
        yield from bot.say('Unknown operation for /stalk: **'+operation+'**')
    ####
    
    userdbconn.commit()
    userdbconn.close()
        
        
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
