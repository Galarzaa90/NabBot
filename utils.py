import discord
import logging
from discord.ext import commands
import re
import math
import random
import asyncio
import urllib.request
import urllib
import sqlite3
import os
import platform
import time
from datetime import datetime,timedelta,date
from calendar import timegm
import sys
import aiohttp

#Emoji code
##Constants to define emoji codes to use in strings
EMOJI_COOKIE = str(chr(0x1F36A))
EMOJI_CAKE = str(chr(0x1F370))
EMOJI_MUSICNOTES = str(chr(0x1F3B6))
EMOJI_ROBOT = str(chr(0x1F916))
EMOJI_SKULL = str(chr(0x1F480))
EMOJI_WINK = str(chr(0x1F609))
EMOJI_BELL = str(chr(0x1F514))
EMOJI_EYEROLL = str(chr(0x1F644))
EMOJI_BICEPS = str(chr(0x1F4AA))
EMOJI_NECKLACE = str(chr(0x1F4FF))
EMOJI_WINEGLASS = str(chr(0x1F377))
EMOJI_FIRE = str(chr(0x1F525))
EMOJI_SNOWFLAKE = str(chr(0x2744))
EMOJI_BLOSSOM = str(chr(0x1F33C))
EMOJI_DAGGER = str(chr(0x1F5E1))
EMOJI_BULLSEYE = str(chr(0x1F3AF))

from config import *
bot = ""

#Global constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1

#Start logging
#Create logs folder
os.makedirs('logs/',exist_ok=True)
##discord.py log
discord_log = logging.getLogger('discord')
discord_log.setLevel(logging.INFO)
handler = logging.FileHandler(filename='logs/discord.log', encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_log.addHandler(handler)
##NabBot log
log = logging.getLogger(__name__ )
log.setLevel(logging.DEBUG)
###Save log to file (info level)
fileHandler = logging.FileHandler(filename='logs/nabbot.log', encoding='utf-8', mode='a') 
fileHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
fileHandler.setLevel(logging.INFO)
log.addHandler(fileHandler)
###Print output to console too (debug level)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
consoleHandler.setLevel(logging.DEBUG)
log.addHandler(consoleHandler)

#Database global connections
userDatabase = sqlite3.connect(USERDB)
tibiaDatabase = sqlite3.connect(TIBIADB)


def getLogin():
    if not os.path.isfile("login.py"):
        print("This seems to be the first time NabBot is ran (or login.py is missing)")
        print("To run your own instance of NabBot you need to create a new bot account to get a bot token")
        print("https://discordapp.com/developers/applications/me")
        print("Alternatively, you can use a regular discord account for your bot, althought this is not recommended")
        print("Insert a bot token OR an e-mail address for a regular account to be used as a bot")
        login = input(">>")
        email = "";
        password = ""
        token = ""
        if "@" in login:
            email = login
            password = input("Enter password: >>")
        elif len(login) >= 50:
            token = login
        else:
            input("What you entered isn't a token or an e-mail. Restart NabBot to retry.")
            quit()
        f = open("login.py","w+")
        f.write("#Token always has priority, if token is defined it will always attempt to login using a token\n")
        f.write("#Comment the token line or set it empty to use email login\n")
        f.write("token = '{0}'\nemail = '{1}'\npassword = '{2}'\n".format(token,email,password))
        f.close()
        print("Login data has been saved correctly. You can change this later by editing login.py")
        input("Press any key to start NabBot now...")
        quit()
    return __import__("login")

def utilsGetBot(_bot):
    global bot
    bot = _bot
    

########formatMessage
##handles stylization of messages, uppercasing \TEXT/, lowercasing /text\ and title casing /Text/
def formatMessage(message):
    upper = r'\\(.+?)/'
    upper = re.compile(upper,re.MULTILINE+re.S)
    lower = r'/(.+?)\\'
    lower = re.compile(lower,re.MULTILINE+re.S)
    title = r'/(.+?)/'
    title = re.compile(title,re.MULTILINE+re.S)
    skipproper = r'\^(.+?)\^(.+?)([a-zA-Z])'
    skipproper = re.compile(skipproper,re.MULTILINE+re.S)
    message = re.sub(upper,lambda m: m.group(1).upper(), message)
    message = re.sub(lower,lambda m: m.group(1).lower(), message)
    message = re.sub(title,lambda m: m.group(1).title(), message)
    message = re.sub(skipproper,lambda m: m.group(2)+m.group(3) if m.group(3).istitle() else m.group(1)+m.group(2)+m.group(3) , message)
    return message
########

########weighedChoice
##makes weighed choices from message lists where [0] is a value representing the relative odds of picking a message
###and [1] is the message string
def weighedChoice(messages,condition1=False,condition2=False):
    ##find the max range by adding up the weigh of every message in the list
    #and purge out messages that dont fulfil the conditions
    range = 0
    _messages = []
    for message in messages:
        if len(message) == 4:
            if (not message[2] or condition1 in message[2]) and (not message[3] or condition2 in message[3]):
                range = range+message[0]
                _messages.append(message)
        elif len(message) == 3:
            if (not message[2] or condition1 in message[2]):
                _messages.append(message)
        else:
            range = range+message[0]
            _messages.append(message)
    #choose a random number
    rangechoice = random.randint(0, range)
    #iterate until we find the matching message
    rangepos = 0
    for message in _messages:
        if rangechoice >= rangepos and rangechoice < rangepos+message[0]:
            return message[1]
        rangepos = rangepos+message[0]
    #this shouldnt ever happen...
    print("Error in weighedChoice!")
    return _messages[0][1]
########

########getChannelByServerAndName
##server_name can be left blank in which case all servers the bot is connected to will be searched
def getChannelByServerAndName(server_name : str, channel_name : str):
    if server_name == "":
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice, bot.get_all_channels())
    else:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice, getServerByName(server_name).channels)
    return channel

########getChannelByName
##alias for getChannelByServerAndName("",channel_name)
##main server is given priority, next all visible servers are searched.
def getChannelByName(channel_name : str):
    channel = getChannelByServerAndName(mainserver,channel_name)
    if channel is None:
        return getChannelByServerAndName("",channel_name)
    return channel
    
########getServerByName
def getServerByName(server_name : str):
    server = discord.utils.find(lambda m: m.name == server_name, bot.servers)
    return server
########

########getUserByName
##this gets a discord user by its name
##currently, duplicate usernames will return the first user found(!)
##priority is given to users in the main server, next all visible channels are searched and finally private channels.
def getUserByName(userName):
    user = None
    _mainserver = getServerByName(mainserver)
    if _mainserver is not None:
        user = discord.utils.find(lambda m: m.name.lower() == userName.lower(), _mainserver.members)
    if user is None:
        user = discord.utils.find(lambda m: m.name.lower() == userName.lower(), bot.get_all_members())
    if user is None:
        user = discord.utils.find(lambda m: m.user.name.lower() == userName.lower(), bot.private_channels)
    return user
########

########getUserById
##this gets a discord user by its id
def getUserById(userId):
    user = discord.utils.find(lambda m: m.id == str(userId), bot.get_all_members())
    if user is None:
        user = discord.utils.find(lambda m: m.user.id == str(userId), bot.private_channels)
    return user
########

#Returns your local time zone
def getLocalTimezone():
    #Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    #UTC Offset
    return ((timegm(t) - timegm(u))/60/60)
    
##Returns Germany's timezone, considering their daylight saving time dates
def getTibiaTimeZone():
    #Find date in Germany
    gt = datetime.utcnow()+timedelta(hours=1)
    germany_date = date(gt.year,gt.month,gt.day)
    dst_start = date(gt.year,3,(31 - (int(((5 * gt.year) / 4) + 4) % int(7))))
    dst_end = date(gt.year,10,(31 - (int(((5 * gt.year) / 4) + 1) % int(7))))
    if dst_start < germany_date < dst_end:
        return 2
    return 1