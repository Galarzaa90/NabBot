from utils import *

@asyncio.coroutine
def getPlayerDeaths(player, singleDeath = False):
    url = "https://secure.tibia.com/community/?subtopic=characters&name="+urllib.parse.quote(player)
    content = ""
    deathList = []
    content = ""
    retry = 0
    while content == "" and retry < 5:
        try:
            page = yield from aiohttp.get(url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            retry+=1

    if content == "":
        log.error("Error in getPlayerDeaths("+player+")")
        return ERROR_NETWORK

    #Check if player exists (in a really lazy way)
    try:
        content.index("Vocation:")
    except Exception:
        return ERROR_DOESNTEXIST

    try:
        content.index("<b>Character Deaths</b>")
    except Exception:
        return deathList
    startIndex = content.index("<b>Character Deaths</b>")
    endIndex = content.index("<B>Search Character</B>")
    content = content[startIndex:endIndex]

    regex_deaths = r'valign="top" >([^<]+)</td><td>(.+?)</td></tr>'
    pattern = re.compile(regex_deaths,re.MULTILINE+re.S)
    matches = re.findall(pattern,content)

    for m in matches:
        deathTime = ""
        deathLevel = ""
        deathKiller = ""
        deathByPlayer = False
        regex_deathtime = r'(\w+).+?;(\d+).+?;(\d+).+?;(\d+):(\d+):(\d+).+?;(\w+)'
        pattern = re.compile(regex_deathtime,re.MULTILINE+re.S)
        m_deathtime = re.search(pattern,m[0])

        if m_deathtime:
            deathTime = "{0} {1} {2} {3}:{4}:{5} {6}".format(m_deathtime.group(1),m_deathtime.group(2),m_deathtime.group(3),m_deathtime.group(4),m_deathtime.group(5),m_deathtime.group(6),m_deathtime.group(7))

        if m[1].find("Died") != -1:
            regex_deathinfo_monster = r'Level (\d+) by ([^.]+)'
            pattern = re.compile(regex_deathinfo_monster,re.MULTILINE+re.S)
            m_deathinfo_monster = re.search(pattern,m[1])
            if m_deathinfo_monster:
                deathLevel = m_deathinfo_monster.group(1)
                deathKiller = m_deathinfo_monster.group(2)
        else:
            regex_deathinfo_player = r'Level (\d+) by .+?name=([^"]+)'
            pattern = re.compile(regex_deathinfo_player,re.MULTILINE+re.S)
            m_deathinfo_player = re.search(pattern,m[1])
            if m_deathinfo_player:
                deathLevel = m_deathinfo_player.group(1)
                deathKiller = urllib.parse.unquote_plus(m_deathinfo_player.group(2))
                deathByPlayer = True

        deathList.append({'time': deathTime, 'level' : deathLevel, 'killer' : deathKiller, 'byPlayer' : deathByPlayer})
        if(singleDeath):
            break
    return deathList

@asyncio.coroutine
def getServerOnline(server):
    url = 'https://secure.tibia.com/community/?subtopic=worlds&world='+server
    onlineList = []
    content = ""
    retry = 0
    while content == "" and retry < 5:
        try:
            page = yield from aiohttp.get(url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            retry+=1

    if content == "":
        log.error("Error in getServerOnline("+server+")")
        return onlineList

    try:
        content.index("Vocation&#160;&#160;")
    except Exception:
        return onlineList

    startIndex = content.index('Vocation&#160;&#160;')
    endIndex = content.index('Search Character')
    content = content[startIndex:endIndex]


    regex_members = r'<a href="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)" >.+?</a></td><td style="width:10%;" >(.+?)</td>'
    pattern = re.compile(regex_members,re.MULTILINE+re.S)

    m = re.findall(pattern,content)
    #Check if list is empty
    if m:
        #Building dictionary list from online players
        for (name, level) in m:
            name = urllib.parse.unquote_plus(name)
            onlineList.append({'name' : name, 'level' : int(level)})
    return onlineList

@asyncio.coroutine
def getGuildOnline(guildname,titlecase=True):
    gstats_url = 'http://guildstats.eu/guild?guild='+urllib.parse.quote(guildname)
    tibia_url = 'https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName='+urllib.parse.quote(guildname)+'&onlyshowonline=1'
    #Fix casing using guildstats.eu if needed
    ##Sorry guildstats.eu :D
    if not titlecase:
        content = ""
        retry = 0
        while content == "" and retry < 5:
            try:
                page = yield from aiohttp.get(gstats_url)
                content = yield from page.text(encoding='ISO-8859-1')
            except Exception:
                retry+=1
        if content == "":
            log.error("Error in getGuildOnline("+guildname+"), while fixing casing with guildstats.eu")
            return ERROR_NETWORK
        #Check if guild exists (in a really lazy way)
        try:
            content.index("General info")
        except Exception:
            return ERROR_DOESNTEXIST
        startIndex = content.index("General info")
        endIndex = content.index("Recruitment")
        content = content[startIndex:endIndex]
        m = re.search(r'<a href="set=(.+?)"',content)
        if m:
            guildname = urllib.parse.unquote_plus(m.group(1))
    else:
        guildname = guildname.title()
    #Fetch webpage
    content = ""
    retry = 0
    while content == "" and retry < 5:
        try:
            page = yield from aiohttp.get(tibia_url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            retry+=1

    if content == "":
        log.error("Error in getGuildOnline("+guildname+")")
        return ERROR_NETWORK
    #Check if guild exists (in a really lazy way)
    try:
        content.index("Information")
    except Exception:
        if titlecase:
            ret = yield from getGuildOnline(guildname,False)
            return ret
        else:
            return ERROR_DOESNTEXIST
    #Trimming content string to reduce load
    startIndex = content.index("<td>Status</td>")
    endIndex = content.index("name=\"Show All\"")
    content = content[startIndex:endIndex]

    #Regex pattern to fetch information
    regex_members = r'<TD>(.+?)</TD>\s</td><TD><A HREF="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)">.+?</A> *\(*(.*?)\)*</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>'
    pattern = re.compile(regex_members,re.MULTILINE+re.S)

    m = re.findall(pattern,content)
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
    return member_list,guildname

@asyncio.coroutine
def getPlayer(name):
    #Fetch website
    url = "https://secure.tibia.com/community/?subtopic=characters&name="+urllib.parse.quote(name)
    content = ""
    retry = 0
    while content == "" and retry < 5:
        try:
            page = yield from aiohttp.get(url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            retry+=1

    if content == "":
        log.error("Error in getPlayer("+name+")")
        return ERROR_NETWORK
    #Check if player exists (in a really lazy way)
    try:
        content.index("Vocation:")
    except Exception:
        return ERROR_DOESNTEXIST

    #Trimming content to reduce load
    startIndex = content.index("BoxContent")
    endIndex = content.index("<B>Search Character</B>")
    content = content[startIndex:endIndex]

    char = {'guild' : ''}

    #TODO: Is there a way to reduce this part?
    #Name
    m = re.search(r'Name:</td><td>([^<,]+)',content)
    if m:
        char['name'] = m.group(1).strip()

    #Deleted
    m = re.search(r', will be deleted at ([^<]+)',content)
    if m:
        char['deleted'] = True

    #Vocation
    m = re.search(r'Vocation:</td><td>([^<]+)',content)
    if m:
        char['vocation'] = m.group(1)

    #Level
    m = re.search(r'Level:</td><td>(\d+)',content)
    if m:
        char['level'] = int(m.group(1))

    #World
    m = re.search(r'World:</td><td>([^<]+)',content)
    if m:
        char['world'] = m.group(1)

    #Residence (City)
    m = re.search(r'Residence:</td><td>([^<]+)',content)
    if m:
        char['residence'] = m.group(1)

    #Sex, only stores pronoun
    m = re.search(r'Sex:</td><td>([^<]+)',content)
    if m:
        if m.group(1) == 'male':
            char['gender'] = 'male'
        else:
            char['gender'] = 'female'

    #Guild rank
    m = re.search(r'membership:</td><td>([^<]+)\sof the',content)
    if m:
        char['rank'] = m.group(1)
        #Guild membership
        m = re.search(r'GuildName=.*?([^"]+).+',content)
        if m:
            char['guild'] = urllib.parse.unquote_plus(m.group(1))

    #Other chars
    ##note that an empty char list means the character is hidden
    ##otherwise you'd have at least the same char in the list
    char['chars'] = []
    try:
        #See if there is a character list
        startIndex = content.index("<B>Characters</B>")
        content = content[startIndex:]

        #Find characters
        regex_chars = r'<TD WIDTH=10%><NOBR>([^<]+)[^?]+.+?VALUE=\"([^\"]+)'
        pattern = re.compile(regex_chars,re.MULTILINE+re.S)
        m = re.findall(pattern,content)

        if m:
            for (world,name) in m:
                name = urllib.parse.unquote_plus(name)
                char['chars'].append({'name' : name, 'world' : world})
    except Exception:
        pass

    return char

def getItem(name):
    #Reading item database
    c = tibiaDatabase.cursor()
    #Search query
    c.execute("SELECT title, vendor_value FROM Items WHERE name LIKE ?",(name,))
    result = c.fetchone()
    try:
        #Checking if item exists
        if(result is not None):
            #Turning result tuple into dictionary
            item = dict(zip(['name','value'],result))
            #Checking NPCs that buy the item
            c.execute("SELECT NPCs.title, city FROM Items, SellItems, NPCs WHERE Items.name LIKE ? AND SELLItems.itemid = Items.id AND NPCs.id = vendorid AND vendor_value = value",(name,))
            npcs = []
            for row in c:
                name = row[0]
                city = row[1].title()
                #Replacing cities for special npcs
                if(name == 'Alesar' or name == 'Yaman'):
                    city = 'Green Djinn\'s Fortress'
                elif(name == 'Nah\'Bob' or name == 'Haroun'):
                    city = 'Blue Djinn\'s Fortress'
                elif(name == 'Rashid'):
                    city = [
                        "Svargrond",
                        "Liberty Bay",
                        "Port Hope",
                        "Ankrahmun",
                        "Darashia",
                        "Edron",
                        "Carlin"][date.today().weekday()]
                elif(name == 'Yasir'):
                    city = 'his boat'
                npcs.append({"name" : name, "city": city})
            item['npcs'] = npcs
            return item
    finally:
        c.close()
    return

def getLocalTime(tibiaTime):
    #Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    #UTC Offset
    local_utc_offset = ((timegm(t) - timegm(u))/60/60)

    #Convert time string to time object
    #Removing timezone cause CEST and CET are not supported
    t = datetime.strptime(tibiaTime[:-4].strip(), "%b %d %Y %H:%M:%S")
    #Extracting timezone
    tz = tibiaTime[-4:].strip()

    #Getting the offset
    if(tz == "CET"):
        utc_offset = 1
    elif(tz == "CEST"):
        utc_offset = 2
    else:
        return None
    #Add/substract hours to get the real time
    return t + timedelta(hours=(local_utc_offset - utc_offset))

def getTimeDiff(time):
    if not isinstance(time, timedelta):
        return None
    hours = time.seconds//3600
    minutes = (time.seconds//60)%60
    if time.days > 1:
        return "{0} days ago".format(time.days)
    if time.days == 1:
        return "1 day ago"
    if hours > 1:
        return "{0} hours ago".format(hours)
    if hours == 1:
        return "1 hour ago"
    if minutes > 15:
        return "{0} minutes ago".format(minutes)
    else:
        return "moments ago"

def getStats(level, vocation):
    try:
        level = int(level)
    except ValueError:
        return "bad level"
    if level <= 0:
        return "low level"
    elif level > 2000:
        return "high level"

    vocation = vocation.lower()
    if vocation in ["knight","k","elite knight","kina","kinight","ek","eliteknight"]:
        hp = 5*(3*level - 2*8 + 29)
        mp = 5*level + 50
        cap = 5*(5*level - 5*8 + 94)
        vocation = "knight"
    elif vocation in ["paladin","royal paladin","rp","pally","royal pally","p"]:
        hp = 5*(2*level - 8 + 29)
        mp = 5*(3*level - 2*8) + 50
        cap = 10*(2*level - 8 + 39)
        vocation = "paladin"
    elif vocation in ["mage","druid","elder druid","elder","ed","d","sorc","sorcerer","master sorcerer","ms","s"]:
        hp = 5*(level+29)
        mp = 5*(6*level - 5*8) + 50
        cap = 10*(level + 39)
        vocation = "mage"
    elif vocation in ["no vocation","no voc","novoc","nv","n v","none","no","n","noob","noobie","rook","rookie"]:
        vocation = "no vocation"
    else:
        return "bad vocation"

    if level < 8 or vocation == "no vocation":
        hp = 5*(level+29)
        mp = 5*level + 50
        cap = 10*(level + 39)

    return {"vocation" : vocation, "hp" : hp, "mp" : mp, "cap" : cap}

####################### Commands #######################

class Tibia():
    """Tibia related commands"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True,aliases=['player','checkplayer','char'])
    @asyncio.coroutine
    def check(self,ctx,*name : str):
        """Tells you information about a character"""
        name = " ".join(name)
        char = yield from getPlayer(name)
        if(char == ERROR_NETWORK):
            yield from self.bot.say("I... can you repeat that?")
            return
        if(char == ERROR_DOESNTEXIST):
            yield from self.bot.say("That character doesn't exist.")
            return
        pronoun = "He"
        if(char['gender'] == "female"):
            pronoun = "She"
        replyF = "**{1}** is a level {2} __{3}__. {0} resides in __{4}__ in the world __{5}__.{6}"
        guildF = "\n{0} is __{1}__ of the **{2}**."
        if(char['guild']):
            guild = guildF.format(pronoun,char['rank'],char['guild'])
        else:
            guild = ""
        reply = replyF.format(pronoun,char['name'],char['level'],char['vocation'],char['residence'],char['world'],guild)
        yield from self.bot.say(reply)

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
            char = yield from getPlayer(name)
            if type(char) is dict:
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
        guildname = " ".join(guildname)
        onlinelist,guildname = yield from getGuildOnline(guildname)
        if onlinelist == ERROR_DOESNTEXIST:
            yield from self.bot.say("The guild "+urllib.parse.unquote_plus(guildname)+" doesn't exist.")
            return
        if onlinelist == ERROR_NETWORK:
            yield from self.bot.say("Can you repeat that?")
        if len(onlinelist) < 1:
            yield from self.bot.say("Nobody is online on "+urllib.parse.unquote_plus(guildname)+".")
            return

        result = ('There '
                    + ('are' if (len(onlinelist) > 1) else 'is')+' '+str(len(onlinelist))+' player'
                    + ('s' if (len(onlinelist) > 1) else '')+' online in **'+guildname+'**:')
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


    @commands.command(aliases=['checkprice','item'])
    @asyncio.coroutine
    def itemprice(self,*itemname : str):
        """Checks an item's highest NPC price"""
        itemname = " ".join(itemname).strip()
        item = getItem(itemname)
        if(item is not None):
            #Check if item has npcs that buy the item
            if('npcs' in item and len(item['npcs']) > 0):
                reply = "**{0}** can be sold for {1:,} gold coins to:".format(item['name'],item['value'])
                for npc in item['npcs']:
                    reply += "\n\t**{0}** in *{1}*".format(npc['name'],npc['city'])
                yield from self.bot.say(reply)
            else:
                yield from self.bot.say('**'+item['name']+'** can\'t be sold to NPCs.')
        else:
            yield from self.bot.say("I couldn't find an item with that name.")

    @commands.command()
    @asyncio.coroutine
    def deaths(self,*name : str):
        """Shows a player's recent deaths"""
        name = " ".join(name).strip()
        deaths = yield from getPlayerDeaths(name)
        if(deaths == ERROR_DOESNTEXIST):
            yield from self.bot.say("That character doesn't exists!")
            return
        if(deaths == ERROR_NETWORK):
            yield from self.bot.say("Sorry, try it again, I'll do it right this time.")
            return
        if(len(deaths) == 0):
            yield from self.bot.say(name.title()+" hasn't died recently.")
            return

        reply = name.title()+" recent deaths:"
        for death in deaths:
            diff = getTimeDiff(datetime.now() - getLocalTime(death['time']))
            died = "Killed" if death['byPlayer'] else "Died"
            reply += "\n\t{0} at level **{1}** by {2} - *{3}*".format(died,death['level'],death['killer'],diff)

        yield from self.bot.say(reply)

    @commands.command(aliases=['levelups'])
    @asyncio.coroutine
    def levels(self,*name : str):
        """Shows a player's recent level ups or global leveups if no player is specified

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        name = " ".join(name)
        c = userDatabase.cursor()
        try:
            if(not name):
                c.execute("SELECT level, date, name, user_id FROM char_levelups, chars WHERE char_id = id ORDER BY date DESC LIMIT 15")
                result = c.fetchall()
                if len(result) < 1:
                    yield from self.bot.say("No one has leveled up recently")
                    return
                now = time.time()
                reply = "Latest level ups:"
                for levelup in result:
                    timediff = timedelta(seconds=now-levelup[1])
                    user = getUserById(levelup[3])
                    username = "unkown"
                    if(user):
                        username = user.name
                    reply += "\n\tLevel **{0}** - {2} (**@{3}**) - *{1}*".format(levelup[0],getTimeDiff(timediff),levelup[2],username)
                yield from self.bot.say(reply)
                return
            #Checking if character exists in db and get id while we're at it
            c.execute("SELECT id, name FROM chars WHERE name LIKE ?",(name,))
            result = c.fetchone()
            if(result is None):
                yield from self.bot.say("I don't have a character with that name registered.")
                return
            #Getting correct capitalization
            name = result[1]
            id = result[0]
            #Limit to 15 entries, could also be limited by time
            c.execute("SELECT level, date FROM char_levelups WHERE char_id = ? ORDER BY date DESC LIMIT 15",(id,))
            result = c.fetchall()
            #Checking number of level ups
            if len(result) < 1:
                yield from self.bot.say("**{0}** hasn't leveled up recently".format(name))
                return
            now = time.time()
            reply = "**{0}** latest level ups:".format(name)
            for levelup in result:
                timediff = timedelta(seconds=now-levelup[1])
                reply += "\n\tLevel **{0}** - *{1}*".format(levelup[0],getTimeDiff(timediff))
            yield from self.bot.say(reply)
        finally:
            c.close()

    @commands.command()
    @asyncio.coroutine
    def stats(self,*params: str):
        """Calculates the stats for a certain level and vocation, or a certain player"""
        paramsError = "You're doing it wrong! Do it like this: ``/stats player`` or ``/stats level,vocation`` or ``/stats vocation,level``"
        params = " ".join(params).split(",")
        char = None
        if(len(params) == 1):
            _digits = re.compile('\d')
            if _digits.search(params[0]) is not None:
                yield from self.bot.say(paramsError)
                return
            else:
                char = yield from getPlayer(params[0])
                if char == ERROR_NETWORK:
                    yield from self.bot.say("Sorry, can you try it again?")
                    return
                if char == ERROR_DOESNTEXIST:
                    yield from self.bot.say("Player **{0}** doesn't exist!".format(params[0]))
                    return
                level = int(char['level'])
                vocation = char['vocation']
        elif(len(params) == 2):
            try:
                level = int(params[0])
                vocation = params[1]
            except ValueError:
                try:
                    level = int(params[1])
                    vocation = params[0]
                except ValueError:
                    yield from self.bot.say(paramsError)
                    return
        else:
            yield from self.bot.say(paramsError)
            return
        stats = getStats(level,vocation)
        if(stats == "low level"):
            yield from self.bot.say("Not even *you* can go down so low!")
        elif(stats == "high level"):
            yield from self.bot.say("Why do you care? You will __**never**__ reach this level "+str(chr(0x1f644)))
        elif(stats == "bad vocation"):
            yield from self.bot.say("I don't know what vocation that is...")
        elif(stats == "bad level"):
            yield from self.bot.say("Level needs to be a number!")
        elif isinstance(stats, dict):
            if(stats["vocation"] == "no vocation"):
                stats["vocation"] = "with no vocation"
            if char:
                pronoun = "he" if char['gender'] == "male" else "she"
                yield from self.bot.say("**{5}** is a level **{0}** {1}, {6} has:\n\t**{2:,}** HP\n\t**{3:,}** MP\n\t**{4:,}** Capacity".format(level,char["vocation"].lower(),stats["hp"],stats["mp"],stats["cap"],char['name'],pronoun))
            else:
                yield from self.bot.say("A level **{0}** {1} has:\n\t**{2:,}** HP\n\t**{3:,}** MP\n\t**{4:,}** Capacity".format(level,stats["vocation"],stats["hp"],stats["mp"],stats["cap"]))
        else:
            yield from self.bot.say("Are you sure that is correct?")

    @commands.command(aliases=['bless'])
    @asyncio.coroutine
    def blessings(self,level : int):
        """Calculates the price of blessings at a specific level"""
        if (level < 1):
            yield from self.bot.say("Very funny...")
            return
        price = 200 * (level - 20)
        if level <= 30: price = 2000
        if level >= 120: price = 20000
        inquisition = ""
        if(level >= 100):
            inquisition = "\nBlessing of the Inquisition costs **{0:,}** gold coins.".format(int(price*5*1.1))
        yield from self.bot.say(
                "At that level, you will pay **{0:,}** gold coins per blessing for a total of **{1:,}** gold coins.{2}"
                .format(price,price*5,inquisition))



def setup(bot):
    bot.add_cog(Tibia(bot))