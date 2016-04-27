from config import *
import builtins
from datetime import *
import time
bot = ""
def utilsGetBot(_bot):
    global bot
    bot = _bot

########print
##custom print function replacement for logging
def print(output):
    builtins.print(output)
    outputfile = open('console.txt', 'a')
    outputfile.write(output+"\r\n")
    outputfile.close()
########

########formatMessage
##handles stylization of messages, uppercasing \TEXT/, lowercasing /text\ and title casing /Text/
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
###the user must be present in the main discord channel
def getUserById(userId):
    server = getServerByName(search_server)
    if server is None:
        return None
    for user in server.members:
        if user.id == str(userId):
            return user
    
    return None
########