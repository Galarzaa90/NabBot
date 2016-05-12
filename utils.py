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

from config import *
bot = ""

#Global constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1


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

########getChannelByServerAndName
##server_name can be left blank in which case all servers the bot is connected to will be searched
def getChannelByServerAndName(server_name : str, channel_name : str):
    for server in bot.servers:
        if server.name == server_name or server_name == "":
            for channel in server.channels:
                if not channel.type == discord.ChannelType.voice and channel.name == channel_name:
                    return channel
    return None

########getChannelByName
##alias for getChannelByServerAndName("",channel_name)
def getChannelByName(channel_name : str):
    return getChannelByServerAndName("",channel_name)
    
########getServerByName
def getServerByName(server_name : str):
    for server in bot.servers:
        if server.name == server_name:
            return server
    return None
########

########getUserByName
##this gets a discord user by its name
###the user must be present in the main discord channel
###currently, duplicate usernames will return the first user found(!)
def getUserByName(userName):
    server = getServerByName(search_server)
    if server is None:
        return None
    for user in server.members:
        if user.name.lower() == userName.lower():
            return user
    
    return None
########

########getUserById
##this gets a discord user by its id
def getUserById(userId):
    for server in bot.servers:
        for user in server.members:
            if user.id == str(userId):
                return user
    return None
########