import discord
import logging
from discord.ext import commands
import random
import asyncio
import urllib.request
import urllib
import time
import datetime
from datetime import timedelta
import sqlite3
import os
import platform

from login import *
from tibia import *

description = '''Mission: Destroy all humans.'''
bot = commands.Bot(command_prefix='/', description=description)
client = discord.Client()

########some global variables to give u cancer
#lastmessage stuff
lastmessage = None
lastmessagetime = datetime.datetime.now()
###a boolean to know if a goofing msg was the last thing we saw
isgoof = False
idlemessages = ["Galarzazzzzza is a nab, i know, i know, oh oh oh",
"Did you know 9 out of 10 giant spiders prefer nabchow?",
"Any allegations made about Nezune and corpses are nothing but slander!",
"All hail Michu, our cat overlord.",
"Beware of nomads, they are known to kill unsuspecting druids!"]

###admin id's for hax commands
admin_ids = ["162060569803751424","162070610556616705"]
###main channel where the bot chats for luls
##this is so we can keep track of idletime for this server only
##and do timed shit in here
mainserver = "Redd Alliance"
mainchannel = "general-chat"
mainchannel_idletime = timedelta(seconds=0)
goof_idletime = timedelta(seconds=300)
###the list of servers to check for with getOnline
tibiaservers = ["Fidera"]
###message list for announceLevel
levelmessages = ["Congratulations to **{0}** on reaching level {1}!",
"**{0}** is level {1} now, congrats!",
"**{0}** has reached level {1}, die and lose it, noob!",
"Well, look at **{0}** with his new fancy level {1}.",
"{1}, **{0}** is level {1}, watch out world...",
"**{0}** is level {1} now. Noice.",
"**{0}** has finally made it to level {1}, yay!"]
###message list for announceDeath (charName=0,deathTime=1,deathLevel=2,deathKiller=3,he/she=4,his/her=5,charName in full caps=6)
##deaths by monster
deathmessages_monster = ["RIP **{0}** ({2}), you lived like you died, inside {3}",
"**{0}** ({2}) was just eaten by {3}. Yum.",
"Silly **{0}** ({2}), I warned you not to play with {3}!",
"{3} killed {0} at level {2}, shame "+str(chr(0x0001f514))+" shame "+str(chr(0x0001f514))+" shame "+str(chr(0x0001f514)),
"**{0}** ({2}) is no more! {4} has ceased to be! {4}'s expired and gone to meet {5} maker! {4}'s a stiff! Bereft of life, {4} rests in peace! If {4} hadn't respawned {4}'d be pushing up the daisies! {5} metabolic processes are now history! {4}'s off the server! {4}'s kicked the bucket, {4}'s shuffled off {5} mortal coil, kissed {3}'s butt, run down the curtain and joined the bleeding choir invisible!! THIS IS AN EX-**{6}**",
"RIP **{0}** ({2}), we hardly knew you! (That {3} got to know you pretty well though "+str(chr(0x0001f609))+")"]
##deaths by player
deathmessages_player = ["**{0}** ({2}) got rekt! **{3}** ish pekay!",
"HALP **{3}** is going around killing innocent **{0}** ({2})!",
"Next time stay away from **{3}**, **{0}** ({2})"]
########

### Channels to look for users ###
## I don't want to change the other variable cause I don't want goof messages on the main channel yet
search_server = "Redd Alliance"
search_channel = "general-chat"


@bot.event
@asyncio.coroutine
def on_ready():
    bot.load_extension("tibia")
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    #start up async tasks
    asyncio.async(think())
    asyncio.async(getDeaths())
    asyncio.async(getOnline())
########a think function!
@asyncio.coroutine
def think():
    #i could do something like, check if the bots alive instead of just a "while true" but i dont see the point.
    while 1:
        #update idle time
        updateChannelIdleTime()
        
        #example function goof() will say some random shit after 30 secs of idle time
        #yield from goof()
        
        ##do any magic we want here
        #anything that needs to use a sleep() should probably be moved to its own coroutine though.
        
        
        #sleep for a bit and then loop back
        yield from asyncio.sleep(5)
########

########getDeaths
@asyncio.coroutine
def getDeaths():
    #the first run flag is here to avoid trolling a bunch of people when the bots been offline for a while
    firstRun = True
    while 1:
        userdbconn = sqlite3.connect('users.db')
        userdb = userdbconn.cursor()
        userdb.execute("SELECT charName, lastDeathTime FROM tibiaChars")
        result = userdb.fetchall()
        if(result is not None and len(result) > 0):
            for character in result:
                content = ""
                while content == "":
                    try:
                        page = urllib.request.urlopen('https://secure.tibia.com/community/?subtopic=characters&name='+urllib.parse.quote(character[0]))
                        content = page.read()
                    except Exception:
                        yield from asyncio.sleep(2)

                try:
                    content.decode().index("<b>Character Deaths</b>")
                except Exception:
                    continue
                startIndex = content.decode().index("<b>Character Deaths</b>")
                endIndex = content.decode().index("<B>Search Character</B>")
                content = content[startIndex:endIndex]

                regex_deaths = r'valign="top" >([^<]+)</td><td>(.+?)</td></tr>'
                pattern = re.compile(regex_deaths,re.MULTILINE+re.S)
                m = re.search(pattern,content.decode())
                if m:
                    deathTime = ""
                    deathLevel = ""
                    deathKiller = ""
                    deathByPlayer = False
                    regex_deathtime = r'(\w+).+?;(\d+).+?;(\d+).+?;(\d+):(\d+):(\d+)'
                    pattern = re.compile(regex_deathtime,re.MULTILINE+re.S)
                    m_deathtime = re.search(pattern,m.group(1))
                    
                    if m_deathtime:
                        deathTime = "{0} {1} {2} {3}:{4}:{5}".format(m_deathtime.group(1),m_deathtime.group(2),m_deathtime.group(3),m_deathtime.group(4),m_deathtime.group(5),m_deathtime.group(6))
                     
                    if m.group(2).find("Died") != -1:
                        regex_deathinfo_monster = r'Level (\d+) by ([^.]+)'
                        pattern = re.compile(regex_deathinfo_monster,re.MULTILINE+re.S)
                        m_deathinfo_monster = re.search(pattern,m.group(2))
                        if m_deathinfo_monster:
                            deathLevel = m_deathinfo_monster.group(1)
                            deathKiller = m_deathinfo_monster.group(2)
                    else:
                        regex_deathinfo_player = r'Level (\d+) by .+?name=([^"]+)'
                        pattern = re.compile(regex_deathinfo_player,re.MULTILINE+re.S)
                        m_deathinfo_player = re.search(pattern,m.group(2))
                        if m_deathinfo_player:
                            deathLevel = m_deathinfo_player.group(1)
                            deathKiller = m_deathinfo_player.group(2).replace('+',' ')
                            deathByPlayer = True
                    
                    if character[1] != deathTime:
                        userdb.execute("UPDATE tibiaChars SET lastDeathTime = ? WHERE charName = ?",(deathTime,character[0],))
                        if not firstRun:
                            yield from announceDeath(character[0],deathTime,deathLevel,deathKiller,deathByPlayer)
                        userdbconn.commit()
                yield from asyncio.sleep(2)
        userdbconn.close()
        firstRun = False
########

########announceDeath
@asyncio.coroutine
def announceDeath(charName,deathTime,deathLevel,deathKiller,deathByPlayer):
    global mainserver
    global mainchannel
    channel = getChannelByServerAndName(mainserver,mainchannel)
    char = getPlayer(charName)
    pronoun1 = "he"
    pronoun2 = "his"
    if char and char['pronoun'] == "she":
        pronoun1 = "she"
        pronoun1 = "her"
        
    message = ""
    if deathByPlayer:
        message = random.choice(deathmessages_player).format(charName,deathTime,deathLevel,deathKiller,pronoun1,pronoun2,charName.upper())
    else:
        message = random.choice(deathmessages_monster).format(charName,deathTime,deathLevel,deathKiller,pronoun1,pronoun2,charName.upper())
    yield from bot.send_message(channel,message[:1].upper()+message[1:])
########

########getOnline
@asyncio.coroutine
def getOnline():
    #the first run flag is here to avoid congratulating a bunch of people when the bots been offline for a while
    firstRun = True
    while 1:
        for server in tibiaservers:
            userdbconn = sqlite3.connect('users.db')
            userdb = userdbconn.cursor()
            
            content = ""
            while content == "":
                try:
                    page = urllib.request.urlopen('https://secure.tibia.com/community/?subtopic=worlds&world='+server)
                    content = page.read()
                except Exception:
                    yield from asyncio.sleep(2)
            
            try:
                content.decode().index("Vocation&#160;&#160;")
            except Exception:
                continue
            
            startIndex = content.decode().index('Vocation&#160;&#160;')
            endIndex = content.decode().index('Search Character')
            content = content[startIndex:endIndex]
            
            
            regex_members = r'<a href="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)" >.+?</a></td><td style="width:10%;" >(.+?)</td>'
            pattern = re.compile(regex_members,re.MULTILINE+re.S)

            m = re.findall(pattern,content.decode())
            online_list = [];
            #Check if list is empty
            if m:
                #Building dictionary list from online players
                for (name, level) in m:
                    name = urllib.parse.unquote_plus(name)
                    online_list.append({'name' : name.title(), 'level' : int(level)})
                
                for character in online_list:
                    userdb.execute("SELECT charName, lastLevel FROM tibiaChars WHERE charName LIKE ?",(character['name'],))
                    result = userdb.fetchone()
                    if(result is not None):
                        if result[1] != character['level']:
                            userdb.execute("UPDATE tibiaChars SET lastLevel = ? WHERE charName = ?",(character['level'],character['name'],))
                            if not firstRun and result[1] != -1:
                                yield from announceLevel(result[0],character['level'])
            userdbconn.commit()
            userdbconn.close()
            #wait 5 seconds in between server searches, we could probably reduce this to 2 seconds or something, i just didnt wanna spam
            yield from asyncio.sleep(5)
        firstRun = False
########

########announceLevel
@asyncio.coroutine
def announceLevel(charName,charLevel):
    global mainserver
    global mainchannel
    channel = getChannelByServerAndName(mainserver,mainchannel)
    yield from bot.send_message(channel,random.choice(levelmessages).format(charName,str(charLevel)))
########

########update idle time, dunno if u wanna use a function for this, just seemed less ugly
def updateChannelIdleTime():
    global mainchannel_idletime
    mainchannel_idletime = datetime.datetime.now() - lastmessagetime
########

@asyncio.coroutine
def goof():
    global mainserver
    global mainchannel
    global mainchannel_idletime
    global lastmessage
    global isgoof
    #After some time (goof_idletime) of silence, the bot will send a random message.
    #It won't say anything if the last message was by the bot.
    if lastmessage != None and isgoof == False and mainchannel_idletime > goof_idletime:# and (not lastmessage.author.id == bot.user.id): #<< dont need this anymore
        channel = getChannelByServerAndName(mainserver,mainchannel)
        yield from bot.send_message(channel,random.choice(idlemessages))
        ##this im kinda worried about, it seems to work but i'm not sure if it CANT fuck up
        #afaik, it shouldnt always be seeing its own msg instantly and if yield from means "dont wait for this to be done" then sometimes the isgoof should be set to true and then immediatly set back to false?
        #worked in all my tests though, so we'll see. worse case scenario it sometimes doesnt realize and goofs twice in a row
        ##in fact heres an ugly workaround: wait a few seconds before setting isgoof!
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
    global mainserver
    global mainchannel
    global isgoof
    #update last message
    if not message.channel.is_private:
        if not lastmessage == message and message.channel.name == mainchannel and message.channel.server.name == mainserver:
            lastmessage = message
            lastmessagetime = datetime.datetime.now()
            #always sets isgoof to false, if the message came from us, and we were goofing, it will be set to true right after anyway
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
        
    args = " ".join(args).strip().split(",")
    if(len(args) < 2):
        yield from bot.say('Valid arguments for /stalk are **add**, **remove**, **weight**, **addchar**, **removechar**.')
        return
       
    operation = args[0].strip()
    name = args[1].strip()
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
