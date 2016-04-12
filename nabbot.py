import discord
import math
from discord.ext import commands
import random
import asyncio
import urllib.request
import urllib
import re
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
#a boolean to know if a goofing msg was the last thing we saw
isgoof = False
idlemessages = ["Galarzazzzzza is a nab, i know, i know, oh oh oh",
"Did you know 9 out of 10 giant spiders prefer nabchow?",
"Any allegations made about Nezune and corpses are nothing but slander!",
"All hail Michu, our cat overlord.",
"Beware of nomads, they are known to kill unsuspecting druids!"]

#admin id's for hax commands
admin_ids = ["162060569803751424","162070610556616705"]
#main channel where the bot chats for luls
#this is so we can keep track of idletime for this server only
#and do timed shit in here
mainserver = "Nab Bot"
mainchannel = "general"
mainchannel_idletime = timedelta(seconds=0)
goof_idletime = timedelta(seconds=300)
########

@bot.event
@asyncio.coroutine
def on_ready():
    bot.load_extension("tibia")
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    #call think() when everything's ready
    yield from think()


########a think function!
@asyncio.coroutine
def think():
    #i could do something like, check if the bots alive instead of just a "while true" but i dont see the point.
    while 1:
        #update idle time
        updateChannelIdleTime()
        
        #example function goof() will say some random shit after 30 secs of idle time
        yield from goof()
        
        #do any magic we want here
        #(this is a good spot to have a function that periodically crawls online lists and checks for levelups etc)
        
        
        #sleep for a bit and then loop back
        yield from asyncio.sleep(5)
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
        #this im kinda worried about, it seems to work but i'm not sure if it CANT fuck up
        #afaik, it shouldnt always be seeing its own msg instantly and if yield from means "dont wait for this to be done" then sometimes the isgoof should be set to true and then immediatly set back to false?
        #worked in all my tests though, so we'll see. worse case scenario it sometimes doesnt realize and goofs twice in a row
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
########

########this gets an user by its name (it only checks our main server to avoid issues with duplicate usernames)
def getUserByName(userName):
    global mainserver
    server = getServerByName(mainserver)
    for user in server.members:
        if user.name.lower() == userName.lower():
            return user
    
    return None
########

########this gets an user by its id
def getUserById(userId):
    global mainserver
    server = getServerByName(mainserver)
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
    
    #here you can add any commands u want hidden or whatever. use message.content and message.author.id
    if message.content.startswith("/"):
        commandEnd = message.content.find(" ")
        command = ""
        if commandEnd > -1:
            command = message.content[1:commandEnd]
        else:
            command = message.content[1:]
        #This commands only work via PM by Admins
        if message.channel.is_private and message.author.id in admin_ids:
            if command == "stalk":
                yield from stalk(message.channel,message.content[len(command)+2:].strip().split(","))
            if command == "restart":
                yield from restart(message.channel)
            if command == "shutdown":
                yield from shutdown(message.channel)
    
    #do the default call to process_commands
    yield from self.process_commands(message)

#replacing default on_message from commands.Bot class
commands.Bot.on_message = on_message
########

######## Restart command
def restart(channel):
    yield from bot.send_message(channel,'Restarting...')
    print("Closing NabBot")
    if(platform.system() == "Linux"):
        os.system("python3 restart.py")
    else:
        os.system("python restart.py")
    
    quit()
########

######## Shutdown command
def shutdown(channel):
    yield from bot.send_message(channel,'Shutdown...')
    print("Closing NabBot")
    quit()
########

########hidden stalk function! we will use this to make links between people and give them importance weights etc
@asyncio.coroutine
def stalk(channel,args : str):
    if len(args) >= 2:
        operation = args[0].strip()
        args.remove(args[0])
        stalkeename = args[0].strip()
        args.remove(args[0])
        stalkee = getUserByName(stalkeename)
        if stalkee is not None:
            userdbconn = sqlite3.connect('users.db')
            userdb = userdbconn.cursor()
            
            ####/stalk add, -userName-
            if operation == "add":
                userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(stalkee.id),))
                result = userdb.fetchone()
                if(result is None):
                    userdb.execute("INSERT INTO discordUsers VALUES(?,?)",(int(stalkee.id),5,))
                    yield from bot.send_message(channel,'Added **@'+stalkee.name+'** to userList, his discord userID is **'+stalkee.id+'**.\r\n'+
                'His importance weight has been set to the default **5**, please use **/stalk weight, -userName-, -weight-** to set it.\r\n'+
                'Use **/stalk addchar, -userName-, -char-** to add Tibia characters to this user.')
                else:
                    yield from bot.send_message(channel,'User **@'+stalkee.name+'** is already in users db.')
            ####
            
            ####/stalk remove, -userName-
            elif operation == "remove":
                #there should probably be either a confirmation or a backup for this but w/e
                userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(stalkee.id),))
                result = userdb.fetchone()
                if(result is not None):
                    userdb.execute("DELETE FROM discordUsers WHERE id = ?",(int(stalkee.id),))
                    yield from bot.send_message(channel,'Removed **@'+stalkee.name+'** from userList.')
                else:
                    yield from bot.send_message(channel,'User **@'+stalkee.name+'** not found in users db.')
            ####
            
            ####/stalk weight, -userName-, -newWeight-
            elif operation == "weight":
                userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(stalkee.id),))
                result = userdb.fetchone()
                if(result is not None):
                    #hahaha this if is fucking cancer but oh well it works
                    if len(args) == 0 or not args[0].isdigit() or (args[0].isdigit() and (int(args[0]) > 5 or int(args[0]) < 1)):
                        yield from bot.send_message(channel,'Usage for **weight** is **/stalk weight, -userName-, -newWeight-**.\r\n'+
                    'Valid weights are 1 through 5.')
                    else:
                        newWeight = int(args[0])
                        userdb.execute("UPDATE discordUsers SET weight = ? WHERE id = ?",(newWeight,int(stalkee.id),))
                        yield from bot.send_message(channel,'**@'+stalkee.name+'**\'s weight has been set to **'+str(newWeight)+'**.')
                else:
                    yield from bot.send_message(channel,'User **@'+stalkee.name+'** not found in users db.\r\n'+
                'Use **/stalk add, -userName-** to add this user.')
            ####
            
            ####/stalk addchar, -userName-, -char-
            elif operation == "addchar":
                userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(stalkee.id),))
                result = userdb.fetchone()
                if(result is not None):
                    if len(args) == 0:
                        yield from bot.send_message(channel,'Usage for **addchar** is **/stalk addchar, -userName-, -char-**.')
                    else:
                        charName = str(args[0]).title()
                        userdb.execute("SELECT discordUser, charName FROM tibiaChars WHERE charName LIKE ?",(charName,))
                        result = userdb.fetchone()
                        if(result is None):
                            userdb.execute("INSERT INTO tibiaChars VALUES(?,?)",(int(stalkee.id),charName,))
                            yield from bot.send_message(channel,'**'+charName+'** has been added to **@'+stalkee.name+'**\'s Tibia character list.\r\n'+
                        'Use **/stalk removechar, -userName-, -char-** to remove Tibia chars from an user.')
                        else:
                            charOwner = getUserById(str(result[0]))
                            if charOwner is not None:
                                yield from bot.send_message(channel,'Tibia character **'+charName+'** is already assigned to user **@'+charOwner.name+'**.')
                            else:
                                #the old char owner doesnt exist any more for some reason, so just assign it to this new user
                                userdb.execute("UPDATE tibiaChars SET discordUser = ? WHERE charName = ?",(int(stalkee.id),charName,))
                                yield from bot.send_message(channel,'**'+charName+'** has been added to **@'+stalkee.name+'**\'s Tibia character list.\r\n'+
                            'Use **/stalk removechar, -userName-, -char-** to remove Tibia chars from an user.')
                else:
                    yield from bot.send_message(channel,'User **@'+stalkee.name+'** not found in users db.\r\n'+
                'Use **/stalk add, -userName-** to add this user.')
            ####
            
            ####/stalk removechar, -userName-, -char-
            elif operation == "removechar":
                userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(stalkee.id),))
                result = userdb.fetchone()
                if(result is not None):
                    if len(args) == 0:
                        yield from bot.send_message(channel,'Usage for **removechar** is **/stalk removechar, -userName-, -char-**.')
                    else:
                        charName = str(args[0]).title()
                        userdb.execute("SELECT discordUser, charName FROM tibiaChars WHERE discordUser LIKE ? AND charName LIKE ?",(int(stalkee.id),charName,))
                        result = userdb.fetchone()
                        if(result is not None):
                            userdb.execute("DELETE FROM tibiaChars WHERE discordUser LIKE ? AND charName LIKE ?",(int(stalkee.id),charName,))
                            yield from bot.send_message(channel,'**'+charName+'** has been removed from **@'+stalkee.name+'**\'s Tibia character list.')
                        else:
                            yield from bot.send_message(channel,'**'+charName+'** is not in **@'+stalkee.name+'**\'s Tibia character list.')
                else:
                    yield from bot.send_message(channel,'User **@'+stalkee.name+'** not found in users db.\r\n'+
                'Use **/stalk add, -userName-** to add this user.')
            ####
            
            ####unknown operation
            else:
                yield from bot.send_message(channel,'Unknown operation for /stalk: **'+operation+'**')
            ####
            
            userdbconn.commit()
            userdb.execute("SELECT id, weight FROM discordUsers WHERE id LIKE ?",(int(stalkee.id),))
            result = userdb.fetchone()
            if(result is not None):
                userinfo = dict(zip(['id','weight'],result))
                print('id = '+str(userinfo['id']))
                print('weight = '+str(userinfo['weight']))
                
            userdb.execute("SELECT discordUser, charName FROM tibiaChars WHERE discordUser LIKE ?",(int(stalkee.id),))
            result = userdb.fetchone()
            if(result is not None):
                userinfo = dict(zip(['discordUser','charName'],result))
                print('discordUser = '+str(userinfo['discordUser']))
                print('charName = '+str(userinfo['charName']))
            userdbconn.close()
        else:
            yield from bot.send_message(channel,'User **@'+stalkeename.title()+'** not found in server **'+mainserver+'**.')
    else:
        yield from bot.send_message(channel,'Valid arguments for /stalk are **add**, **remove**, **weight**, **addchar**, **removechar**.')
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


bot.run(username, password)
