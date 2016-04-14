import discord
from discord.ext import commands
import asyncio
import urllib.request
import urllib
import re
import math
import random
import sqlite3

def getGuildOnline(guildname):
    #Fetch webpage
    page = urllib.request.urlopen('https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName='+urllib.parse.quote(guildname)+'&onlyshowonline=1')
    content = page.read()
    #Check if guild exists (in a really lazy way)
    try:
        content.decode().index("Information")
    except Exception:
        return 'NE'
    #Trimming content string to reduce load
    startIndex = content.decode().index("<td>Status</td>")
    endIndex = content.decode().index("name=\"Show All\"")
    content = content[startIndex:endIndex]

    #Regex pattern to fetch information
    regex_members = r'<TD>(.+?)</TD>\s</td><TD><A HREF="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)">.+?</A> *\(*(.*?)\)*</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>'
    pattern = re.compile(regex_members,re.MULTILINE+re.S)

    m = re.findall(pattern,content.decode())
    member_list = [];
    #Check if list is empty
    if m:
        #Building dictionary list from members
        for (rank, name, title, vocation, level, joined) in m:
            rank = '' if (rank == '&#160;') else rank
            name = urllib.parse.unquote_plus(name)
            joined = joined.replace('&#160;','-')
            member_list.append({'rank' : rank, 'name' : name, 'title' : title,
            'vocation' : vocation, 'level' : level, 'joined' : joined})
        return member_list
    
    return 'NO'

def getPlayer(name):
    char = {'guild' : ''}
    #Fetch website
    page = urllib.request.urlopen('https://secure.tibia.com/community/?subtopic=characters&name='+urllib.parse.quote(name))
    content = page.read()
    #Check if guild exists (in a really lazy way)
    try:
        content.decode().index("Vocation:")
    except Exception:
        return
    #Trimming content to reduce load
    startIndex = content.decode().index("BoxContent")
    endIndex = content.decode().index("<B>Search Character</B>")
    content = content[startIndex:endIndex]

    #TODO: Is there a way to reduce this part?
    #Name
    m = re.search(r'Name:</td><td>([^<]+)\s',content.decode())
    if m:
        char['name'] = m.group(1).strip()

    #Vocation
    m = re.search(r'Vocation:</td><td>([^<]+)',content.decode())
    if m:
        char['vocation'] = m.group(1)

    #Level
    m = re.search(r'Level:</td><td>(\d+)',content.decode())
    if m:
        char['level'] = int(m.group(1))

    #World
    m = re.search(r'World:</td><td>([^<]+)',content.decode())
    if m:
        char['world'] = m.group(1)

    #Residence (City)        
    m = re.search(r'Residence:</td><td>([^<]+)',content.decode())
    if m:
        char['residence'] = m.group(1)

    #Sex, only stores pronoun
    m = re.search(r'Sex:</td><td>([^<]+)',content.decode())
    if m:
        if m.group(1) == 'male':
            char['pronoun'] = 'He'
        else:
            char['pronoun'] = 'She'
            
    #Guild rank
    m = re.search(r'membership:</td><td>([^<]+)\sof the',content.decode())
    if m:
        char['rank'] = m.group(1)
        #Guild membership
        m = re.search(r'GuildName=.*?([^"]+).+',content.decode())
        if m:
            char['guild'] = urllib.parse.unquote_plus(m.group(1))
        
    return char

def getItem(name):
    #Reading item database
    c = sqlite3.connect('Database.db').cursor()
    #Search query
    c.execute("SELECT title, vendor_value FROM Items WHERE name LIKE ?",(name,))
    result = c.fetchone()
    #Checking if item exists
    if(result is not None):
        #Turning result tuple into dictionary
        item = dict(zip(['name','value'],result))
        #If value is greater than 0, we search npcs that buy it
        if(item['value'] and item['value'] > 0):
            c.execute("SELECT Items.title, value, NPCs.title, city"+
            " FROM Items, SellItems, NPCs WHERE Items.name LIKE ?"+
            " AND SellItems.itemid = Items.id AND NPCs.id = vendorid"+
            " ORDER BY value DESC LIMIT 1",(name,))
            result = c.fetchone()
            #This shouldn't be neccesary...
            #Note: Items that are not sellable to NPCs take the value from the buyprice
            #So if the item's value is greater than 0, it might still have no npc key
            if(result is not None):
                item = dict(zip(['name','value','npc','city'],result))
        #Only used for the cases where the value doesn't exist, fuck that noise
        if(not item['value']):
            item['value'] = 0
        return item
    return

class Tibia():
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True,aliases=['player','checkplayer','char'])
    @asyncio.coroutine
    def check(self,ctx,*name : str):
        """Tells you information about a character"""
        name = " ".join(name)
        char = getPlayer(name)
        if char:
            yield from self.bot.say('**'+char['name']+'** is a level '+str(char['level'])+
            ' __'+char['vocation']+'__. '+char['pronoun']+' resides in __'+
            char['residence']+'__, in the world __'+ char['world']+'__.\n'+
            ((char['pronoun']+' is a '+char['rank']+' of the **'+char['guild']+'**.') if (char['guild']) else ''))
        else:
            yield from self.bot.say('That character doesn\'t exist.')

    @commands.command(pass_context=True,aliases=['expshare','party'])
    @asyncio.coroutine
    def share(self,ctx,*param : str):
        """Shows the sharing range for that level or character"""
        level = 0
        name = ''
        #Check if param is numeric
        try:
            level = int(param[0])
        #If it's not numeric, then it must be a char's name
        except ValueError:
            name = " ".join(param)
            char = getPlayer(name)
            if char:
                level = int(char['level']);
                name = char['name'];
            else:
                yield from self.bot.say('There is no character with that name.');
                return
        if(level <= 0):
            replies = ["Invalid level.", "I don't think that's a valid level.",
            "You're doing it wrong!", "Nope, you can't share with anyone.",
            "You probably need a couple more levels"]
            yield from self.bot.say(random.choice(replies))
            return
        low = int(math.ceil(level*2.0/3.0))
        high = int(math.floor(level*3.0/2.0))
        if(name == ''):
            yield from self.bot.say('A level '+str(level)+' can share experience with levels **'+str(low)+
        '** to **'+str(high)+'**.')
        else:
            yield from self.bot.say('**'+name+'** ('+str(level)+') can share experience with levels **'+str(low)+
        '** to **'+str(high)+'**.')
            
        

    @commands.command(pass_context=True,aliases=['guildcheck'])
    @asyncio.coroutine
    def guild(self,ctx,*guildname : str):
        """Checks who is online in a guild"""
        guildname = " ".join(guildname).title()
        onlinelist = getGuildOnline(guildname)
        if onlinelist == 'NE':
            yield from self.bot.say('The guild '+urllib.parse.unquote_plus(guildname)+' doesn\'t exist.')
        elif onlinelist == 'NO':
            yield from self.bot.say('Nobody is online on '+urllib.parse.unquote_plus(guildname)+'.')
        else:
            result = ('There '+
            ('are' if (len(onlinelist) > 1) else 'is')+' '+str(len(onlinelist))+' player'+
            ('s' if (len(onlinelist) > 1) else '')+' online in **'+guildname+'**:')
            for member in onlinelist:
                result += '\n'  
                if(member['rank'] != ''):
                    result += '__'+member['rank']+'__\n'
                result += '\t'+member['name']
                result += (' (*'+member['title']+'*)' if (member['title'] != '') else '')
                result += ' -- '+member['level']+' '
                vocAbb = {'None' : 'N', 'Druid' : 'D', 'Sorcerer' : 'S', 'Paladin' : 'P', 'Knight' : 'K',
                'Elder Druid' : 'ED', 'Master Sorcerer' : 'MS', 'Royal Paladin' : 'RP', 'Elite Knight' : 'EK'}
                try:
                    result += vocAbb[member['vocation']]
                except KeyError:
                    result += 'N'            
                
            yield from self.bot.say(result)
            
    @commands.command(pass_context=True,aliases=['checkprice','item'])
    @asyncio.coroutine
    def itemprice(self,ctx,*itemname : str):
        """Checks an item's NPC price"""
        itemname = " ".join(itemname).strip()
        item = getItem(itemname)
        if(item is not None):   
            #Check if item is sellable to NPC
            if('npc' in item):
                city = item['city'].title()
                #If it's a djinn, show the race instead of city
                if(item['npc'] == 'Alesar' or item['npc'] == 'Yaman'):
                    city = 'Green Djinn'
                elif(item['npc'] == 'Nah\'Bob' or item['npc'] == 'Haroun'):
                    city = 'Blue Djinn'
                #TODO: Replace Rashid's "varies" with today's city
                #TODO: If Yasir's is the top seller, also display the alternate seller
                yield from self.bot.say('**'+item['name']+'** can be sold to **'
                +item['npc']+'** ('+city+') for **'+('{0:,}'.format(item['value']))+'** gold coins.')
            else:
                yield from self.bot.say('**'+item['name']+'** can\'t be sold to NPCs.')
        else:
            yield from self.bot.say("I couldn't find an item with that name.")

def setup(bot):
    bot.add_cog(Tibia(bot))