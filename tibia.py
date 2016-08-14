from utils import *

@asyncio.coroutine
def getPlayerDeaths(name, singleDeath = False, tries = 5):
    url = "https://secure.tibia.com/community/?subtopic=characters&name="+urllib.parse.quote(name)
    content = ""
    deathList = []
    
    #Fetch website
    try:
        page = yield from aiohttp.get(url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if(tries == 0):
            log.error("getPlayerDeaths: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayerDeaths(name,singleDeath,tries)
            return ret

    if content == "":
        log.error("getPlayerDeaths: Couldn't fetch {0}, network error.".format(name))
        return ERROR_NETWORK
        
    #Trimming content to reduce load
    try:
        startIndex = content.index('<div class="BoxContent"')
        endIndex = content.index("<B>Search Character</B>")
        content = content[startIndex:endIndex]
    except ValueError:
        #Website fetch was incomplete, due to a network error
        if(tries == 0):
            log.error("getPlayerDeaths: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayerDeaths(name,singleDeath,tries)
            return ret
            
    #Check if player exists
    if "Name:</td><td>" not in content:
        return ERROR_DOESNTEXIST
        
    #Check if player has recent deaths, return empty list if not
    if "<b>Character Deaths</b>" not in content:
        return deathList
        
    #Trimming content again once we've checked char exists and has deaths
    startIndex = content.index("<b>Character Deaths</b>")
    content = content[startIndex:]

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
def getServerOnline(server,tries = 5):
    url = 'https://secure.tibia.com/community/?subtopic=worlds&world='+server
    onlineList = []
    content = ""
    
    #Fetch website
    try:
        page = yield from aiohttp.get(url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if(tries == 0):
            log.error("getServerOnline: Couldn't fetch {0}, network error.".format(server))
            #This should return ERROR_NETWORK, but requires error handling where this function is used
            return onlineList
        else:
            tries -= 1
            ret = yield from getServerOnline(server,tries)
            return ret
            
    while content == "" and retry < 5:
        try:
            page = yield from aiohttp.get(url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            retry+=1

    #Trimming content to reduce load
    try:
        startIndex = content.index('<div class="BoxContent"')
        endIndex = content.index('<div id="ThemeboxesColumn" >')
        content = content[startIndex:endIndex]
    except ValueError:
        #Website fetch was incomplete due to a network error
        if(tries == 0):
            log.error("getServerOnline: Couldn't fetch {0}, network error.".format(server))
            #This should return ERROR_NETWORK, but requires error handling where this function is used
            return onlineList
        else:
            tries -= 1
            ret = yield from getServerOnline(server,tries)
            return ret


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
def getGuildOnline(guildname,titlecase=True,tries=5):
    gstats_url = 'http://guildstats.eu/guild?guild='+urllib.parse.quote(guildname)
    #Fix casing using guildstats.eu if needed
    ##Sorry guildstats.eu :D
    if not titlecase:
        #Fetch website
        try:
            page = yield from aiohttp.get(gstats_url)
            content = yield from page.text(encoding='ISO-8859-1')
        except Exception:
            if(tries == 0):
                log.error("getGuildOnline: Couldn't fetch {0} from guildstats.eu, network error.".format(guildname))
                return ERROR_NETWORK,guildname
            else:
                tries -= 1
                ret = yield from getGuildOnline(guildname,titlecase,tries)
                return ret

        #Make sure we got a healthy fetch
        try:
            content.index('<div class="footer">')
        except ValueError:
            #Website fetch was incomplete, due to a network error
            if(tries == 0):
                log.error("getGuildOnline: Couldn't fetch {0} from guildstats.eu, network error.".format(guildname))
                return ERROR_NETWORK,guildname
            else:
                tries -= 1
                ret = yield from getGuildOnline(guildname,titlecase,tries)
                return ret

        #Check if the guild doesn't exist
        if "<div>Sorry!" in content:
            return ERROR_DOESNTEXIST,guildname
        
        
        #Failsafe in case guildstats.eu changes their websites format
        try:
            content.index("General info")
            content.index("Recruitment")
        except Exception:
            log.error("getGuildOnline: -IMPORTANT- guildstats.eu seems to have changed their websites format.")
            return ERROR_NETWORK,guildname

        startIndex = content.index("General info")
        endIndex = content.index("Recruitment")
        content = content[startIndex:endIndex]
        m = re.search(r'<a href="set=(.+?)"',content)
        if m:
            guildname = urllib.parse.unquote_plus(m.group(1))
    else:
        guildname = guildname.title()

    tibia_url = 'https://secure.tibia.com/community/?subtopic=guilds&page=view&GuildName='+urllib.parse.quote(guildname)+'&onlyshowonline=1'
    #Fetch website
    try:
        page = yield from aiohttp.get(tibia_url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if(tries == 0):
            log.error("getGuildOnline: Couldn't fetch {0}, network error.".format(guildname))
            return ERROR_NETWORK,guildname
        else:
            tries -= 1
            ret = yield from getGuildOnline(guildname,titlecase,tries)
            return ret

    #Trimming content to reduce load and making sure we got a healthy fetch
    try:
        startIndex = content.index('<div class="BoxContent"')
        endIndex = content.index('<div id="ThemeboxesColumn" >')
        content = content[startIndex:endIndex]
    except ValueError:
        #Website fetch was incomplete, due to a network error
        if(tries == 0):
            log.error("getGuildOnline: Couldn't fetch {0}, network error.".format(guildname))
            return ERROR_NETWORK,guildname
        else:
            tries -= 1
            ret = yield from getGuildOnline(guildname,titlecase,tries)
            return ret

    #Check if the guild doesn't exist
    ##Note: for some reason, when the bot fetches an unexistant guild it gets an error saying "An internal error has occurred. Please try again later!"
    ##instead of the "A guild by that name was not found." error, thats why we're just searching for the "Error" title.
    if '<div class="Text" >Error</div>' in content:
        if titlecase:
            ret = yield from getGuildOnline(guildname,False)
            return ret
        else:
            return ERROR_DOESNTEXIST,guildname

    #Regex pattern to fetch information
    regex_members = r'<TR BGCOLOR=#[\dABCDEF]+><TD>(.+?)</TD>\s</td><TD><A HREF="https://secure.tibia.com/community/\?subtopic=characters&name=(.+?)">.+?</A> *\(*(.*?)\)*</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>\s<TD>(.+?)</TD>'
    pattern = re.compile(regex_members,re.MULTILINE+re.S)

    m = re.findall(pattern,content)
    member_list = []
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
def getPlayer(name, tries = 5):
    url = "https://secure.tibia.com/community/?subtopic=characters&name="+urllib.parse.quote(name)
    content = ""
    char = dict()
    
    #Fetch website
    try:
        page = yield from aiohttp.get(url)
        content = yield from page.text(encoding='ISO-8859-1')
    except Exception:
        if(tries == 0):
            log.error("getPlayer: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayer(name,tries)
            return ret

    #Trimming content to reduce load
    try:
        startIndex = content.index('<div class="BoxContent"')
        endIndex = content.index("<B>Search Character</B>")
        content = content[startIndex:endIndex]
    except ValueError:
        #Website fetch was incomplete, due to a network error
        if(tries == 0):
            log.error("getPlayer: Couldn't fetch {0}, network error.".format(name))
            return ERROR_NETWORK
        else:
            tries -= 1
            ret = yield from getPlayer(name,tries)
            return ret
    #Check if player exists
    if "Name:</td><td>" not in content:
        return ERROR_DOESNTEXIST        

    
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
    ##Use database levels if possible, since those are updated even if the char hasnt logged out
    c = userDatabase.cursor()
    c.execute("SELECT name, last_level, id FROM chars WHERE name LIKE ?",(char['name'],))
    result = c.fetchone()
    if result:
        char['level'] = abs(result[1])
    else:
        m = re.search(r'Level:</td><td>(\d+)',content)
        if m:
            char['level'] = int(m.group(1))
    c.close()

    #World
    m = re.search(r'World:</td><td>([^<]+)',content)
    if m:
        char['world'] = m.group(1)

    #Residence (City)
    m = re.search(r'Residence:</td><td>([^<]+)',content)
    if m:
        char['residence'] = m.group(1)
        
    #Residence (City)
    m = re.search(r'Married to:</td><td>?.+name=([^"]+)',content)
    if m:
        char['married'] = urllib.parse.unquote_plus(m.group(1))

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


    #update name and vocation in chars database if necessary
    c = userDatabase.cursor()
    c.execute("SELECT vocation FROM chars WHERE name LIKE ?",(name,))
    result = c.fetchone()
    if result:
        if result[0] != char['vocation']:
            c.execute("UPDATE chars SET vocation = ? WHERE name LIKE ?",(char['vocation'],name,))
            log.info("{0}'s vocation was set to {1} from {2} during getPlayer()".format(char['name'],char['vocation'],result[0]))
        #if name != char['name']:
        #    c.execute("UPDATE chars SET name = ? WHERE name LIKE ?",(char['name'],name,))
        #    yield from bot.say("**{0}** was renamed to **{1}**, updating...".format(name,char['name']))

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
    
def getRashidCity():
    offset = getTibiaTimeZone() - getLocalTimezone()
    #Server save is at 10am, so in tibia a new day starts at that hour
    tibia_time = datetime.now()+timedelta(hours=offset-10)
    return ["Svargrond",
            "Liberty Bay",
            "Port Hope",
            "Ankrahmun",
            "Darashia",
            "Edron",
            "Carlin"][tibia_time.weekday()]

def getItemByName(name):
    c = tibiaDatabase.cursor()
    c.execute("SELECT id FROM Items WHERE title LIKE ?",(name,))
    result = c.fetchone()
    try:
        if(result is not None):
            item = dict(zip(['id'],result))
            return item
    finally:
        c.close()
    return

def getItemById(id):
    c = tibiaDatabase.cursor()
    c.execute("SELECT title FROM Items WHERE id LIKE ?",(id,))
    result = c.fetchone()
    try:
        if(result is not None):
            item = dict(zip(['name'],result))
            return item
    finally:
        c.close()
    return

def getLoot(id):
    c = tibiaDatabase.cursor()
    c.execute("SELECT itemid FROM CreatureDrops WHERE creatureid LIKE ?",(id,))
    result = c.fetchone()
    try:
        if(result is not None):
            c.execute("SELECT itemid, percentage, min, max FROM CreatureDrops WHERE creatureid LIKE ?"+
            " ORDER BY percentage DESC",(id,))
            result = c.fetchall()
            if(result is not None):
                return result
    finally:
        c.close()
    return

def getMonster(name):
    #Reading monster database
    c = tibiaDatabase.cursor()
    c.execute("SELECT title, id, health, experience, maxdamage, physical, holy, death, fire, energy, ice, earth, drown, lifedrain, senseinvis, abilities, armor, image FROM Creatures WHERE name LIKE ?",(name,))
    result = c.fetchone()
    try:
        #Checking if monster exists
        if(result is not None):
            #Turning result tuple into dictionary
            monster = dict(zip(['name','id','hp','exp','maxdmg','elem_physical','elem_holy','elem_death','elem_fire','elem_energy','elem_ice','elem_earth','elem_drown','elem_lifedrain','senseinvis','abilities','arm','image'],result))
            if monster['hp'] is None or monster['hp'] < 1:
                monster['hp'] = 1
            if monster['exp'] is None or monster['exp'] < 1:
                monster['exp'] = 1
            return monster
    finally:
        c.close()
    return

def getItem(itemname):
    #Reading item database
    c = tibiaDatabase.cursor()

    #Search query
    c.execute("SELECT title, look_text FROM Items WHERE name LIKE ?",(itemname,))
    result = c.fetchone()
    try:
        #Checking if item exists
        if(result is not None):
            #Turning result tuple into dictionary
            item = dict(zip(['name','look_text'],result))

            #Checking NPCs that buy the item
            c.execute("SELECT NPCs.title, city, value"+
            " FROM Items, SellItems, NPCs WHERE Items.name LIKE ?"+
            " AND SellItems.itemid = Items.id AND NPCs.id = vendorid"+
            " ORDER BY value DESC",(itemname,))
            npcs = []
            value_sell = None
            for row in c:
                name = row[0]
                city = row[1].title()
                if value_sell is None:
                    value_sell = row[2]
                elif row[2] != value_sell:
                    break
                #Replacing cities for special npcs
                if(name == 'Alesar' or name == 'Yaman'):
                    city = 'Green Djinn\'s Fortress'
                elif(name == 'Nah\'Bob' or name == 'Haroun'):
                    city = 'Blue Djinn\'s Fortress'
                elif(name == 'Rashid'):
                    city = getRashidCity()
                elif(name == 'Yasir'):
                    city = 'his boat'
                npcs.append({"name" : name, "city": city})
            item['npcs_sold'] = npcs
            item['value_sell'] = value_sell

            #Checking NPCs that sell the item
            c.execute("SELECT NPCs.title, city, value"+
            " FROM Items, BuyItems, NPCs WHERE Items.name LIKE ?"+
            " AND BuyItems.itemid = Items.id AND NPCs.id = vendorid"+
            " ORDER BY value ASC",(itemname,))
            npcs = []
            value_buy = None
            for row in c:
                name = row[0]
                city = row[1].title()
                if value_buy is None:
                    value_buy = row[2]
                elif row[2] != value_buy:
                    break
                #Replacing cities for special npcs
                if(name == 'Alesar' or name == 'Yaman'):
                    city = 'Green Djinn\'s Fortress'
                elif(name == 'Nah\'Bob' or name == 'Haroun'):
                    city = 'Blue Djinn\'s Fortress'
                elif(name == 'Rashid'):
                    offset = getTibiaTimeZone() - getLocalTimezone()
                    #Server save is at 10am, so in tibia a new day starts at that hour
                    tibia_time = datetime.now()+timedelta(hours=offset-10)
                    city = [
                        "Svargrond",
                        "Liberty Bay",
                        "Port Hope",
                        "Ankrahmun",
                        "Darashia",
                        "Edron",
                        "Carlin"][tibia_time.weekday()]
                elif(name == 'Yasir'):
                    city = 'his boat'
                npcs.append({"name" : name, "city": city})
            item['npcs_bought'] = npcs
            item['value_buy'] = value_buy



            return item
    finally:
        c.close()
    return

#Gets a time object from a time string from tibia.cmo
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

def getStats(level, vocation):
    try:
        level = int(level)
    except ValueError:
        return "bad level"
    if level <= 0:
        return "low level"
    elif level > 2000:
        return "high level"

    vocation = vocation.lower().lstrip().rstrip()
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

def getCharString(char):
    if(char == ERROR_NETWORK or char == ERROR_DOESNTEXIST):
        return char
    pronoun = "He"
    if(char['gender'] == "female"):
        pronoun = "She"
    replyF = "**{1}** is a level {2} __{3}__. {0} resides in __{4}__ in the world __{5}__.{6}{7}"
    guildF = "\n{0} is __{1}__ of the **{2}**."
    marriedF = "\n{0} is married to **{1}**."
    guild = ""
    married = ""
    if(char.get('guild',None)):
        guild = guildF.format(pronoun,char['rank'],char['guild'])
    if(char.get('married',None)):
        married = marriedF.format(pronoun,char['married'])
    
    reply = replyF.format(pronoun,char['name'],char['level'],char['vocation'],char['residence'],char['world'],guild,married)
    return reply

def getMonsterString(monster,short=True):
    reply =monster['name']+"\r\n```"
    reply+="HP:"+str(monster['hp'])+"   Exp:"+str(monster['exp'])+"\r\n"
    reply+="HP/Exp Ratio: "+"{0:.2f}".format(monster['exp']/monster['hp']).zfill(4)
    reply+="\r\n```"
    reply+="```"
    loot = getLoot(monster['id'])
    weak = []
    resist = []
    for index, value in monster.items():
        if index[:5] == "elem_":
            weak.append([index[5:].title(),monster[index]]) if (monster[index] > 100) else resist.append([index[5:].title(),monster[index]]) if (monster[index] < 100) else False
    if len(weak) >= 1:
        reply+='Weak to:'+"\r\n"
        for element in sorted(weak, key=lambda elem: elem[1]):
            reply+="	 +"+str(element[1]-100)+"%  "+element[0]+"\r\n"
    if len(resist) >= 1:
        reply+='Resistant to:'+"\r\n"
        for element in sorted(resist, key=lambda elem: elem[1]):
            reply+="	"+((" -"+str(100-element[1])+"% ") if 100-element[1] < 100 else "Immune")+" "+element[0]+"\r\n"
    reply+="\r\n```"
    reply+="```"
    reply+=("Can" if monster['senseinvis'] else "Can't")+" sense invisibility"+"\r\n"
    reply+="\r\n```"
    if not short:
        reply+="```"
        reply+="\r\nLoot:\r\n"
        if loot is not None:
            for item in loot:
                item = dict(zip(['itemid','percentage','min','max'],item))
                reply+=("??.??%" if item['percentage'] is None else "Always" if item['percentage'] >= 100 else ("{0:.2f}".format(item['percentage']).zfill(5)+"%"))+"  "+getItemById(item['itemid'])['name']+(" ("+str(item['min'])+"-"+str(item['max'])+")" if item['max'] > 1 else "")+"\r\n"
        else:
            reply+="Doesn't drop anything"
        reply+="\r\n```"
        reply+="```"
        reply+="Max damage:"+str(monster["maxdmg"]) if monster["maxdmg"] is not None else "???"+"\r\n"
        reply+="\r\n```"
        reply+="```"
        if monster['abilities'] is not None:
            reply+="Abilities:\r\n"
            reply+=monster['abilities']
        reply+="\r\n```"
    else:
        reply += '*I also PM\'d you this monster\'s full information with loot and abilities.*'
    return reply

def getItemString(item,short=True):
    reply = ""
    if('look_text' in item):
        reply = item['look_text']

    if('npcs_bought' in item and len(item['npcs_bought']) > 0):
        reply += "\n\n**{0}** can be bought for {1:,} gold coins from:".format(item['name'],item['value_buy'])
        count = 0
        for npc in item['npcs_bought']:
            if count < 3 or not short:
                reply += "\n\t**{0}** in *{1}*".format(npc['name'],npc['city'])
            count+=1
        if count >= 3 and short:
            reply += "\n\t*And **{0}** others.*".format(count-3)
    else:
        reply += '\n\n**'+item['name']+'** can\'t be bought from NPCs.'

    if('npcs_sold' in item and len(item['npcs_sold']) > 0):
        reply += "\n\n**{0}** can be sold for {1:,} gold coins to:".format(item['name'],item['value_sell'])
        count = 0
        for npc in item['npcs_sold']:
            if count < 3 or not short:
                reply += "\n\t**{0}** in *{1}*".format(npc['name'],npc['city'])
            count+=1
        if count >= 3 and short:
            reply += "\n\t*And **{0}** others.*".format(count-3)
    else:
        reply += '\n\n**'+item['name']+'** can\'t be sold to NPCs.'

    if (len(item['npcs_bought']) > 3 or len(item['npcs_sold']) > 3) and short:
        reply += '\n\n*The list of NPCs was too long, so I PM\'d you an extended version.*'
    return reply

def getSpell(name):
    c = tibiaDatabase.cursor()
    try:
        c.execute("""SELECT id, name, words, levelrequired, promotion, premium, goldcost, manacost,
                  knight, paladin, sorcerer, druid FROM Spells WHERE words LIKE ? OR name LIKE ?""",(name+"%",name,))
        result = c.fetchone()
        if(result is None):
            return None
        id = result[0]
        spell = {"name" : result[1],
                 "words" : result[2],
                 "level" : result[3],
                 "promotion" : True if result[4] == 1 else False,
                 "premium" : True if result[5] == 1 else False,
                 "price" : result[6],
                 "mana" : result[7],
                 "knight" : True if result[8] == 1 else False,
                 "paladin" : True if result[9] == 1 else False,
                 "sorcerer" : True if result[10] == 1 else False,
                 "druid" : True if result[11] == 1 else False,
                 "npcs" : list()}
        c.execute("""SELECT NPCs.title, NPCs.city, SpellNPCs.knight, SpellNPCs.paladin,
                  SpellNPCs.sorcerer, SpellNPCs.druid FROM NPCs, SpellNPCs WHERE
                  SpellNPCs.spellid = ? AND SpellNPCs.npcid = NPCs.id""",(id,))
        result = c.fetchall()
        #This should always be true
        if(result is not None):
            for (name,city,knight, paladin, sorcerer, druid) in result:
                seller = {"name" : name,
                          "city" : city.title(),
                          "knight" : True if knight == 1 else False,
                          "paladin" : True if paladin == 1 else False,
                          "sorcerer" : True if sorcerer == 1 else False,
                          "druid" : True if druid == 1 else False}
                spell["npcs"].append(seller)
        return spell

    finally:
        c.close()
####################### Commands #######################

class Tibia():
    """Tibia related commands"""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['check','player','checkplayer','char','character'])
    @asyncio.coroutine
    def whois(self,*name : str):
        """Tells you the characters of a user or the owner of a character and/or information of a tibia character

        Note that the bot has no way to know the characters of a member that just joined.
        The bot has to be taught about the character's of an user."""
        name = " ".join(name).strip()
        user = getUserByName(name)
        c = userDatabase.cursor()
        try:
            #Checking if the param used is the name of a character in the database
            c.execute("SELECT name, user_id FROM chars WHERE name LIKE ?",(name,))
            char = yield from getPlayer(name)
            charString = getCharString(char)
            result = c.fetchone()
            if (user is None):
                #If it's not a discord user, it might be a known tibia character
                if (result is not None):
                    user = getUserById(result[1])
                    #Check if the user exists just in case
                    if(user is not None):
                        if char == ERROR_NETWORK:
                            charString = "I couldn't fetch that character's info, though. Maybe try again?"
                        if char == ERROR_DOESNTEXIST:
                            charString = "But the character no longer exists."
                        charString = "**{0}** is a character of **@{1.name}**.\n".format(result[0],user)+charString
                        yield from self.bot.say(charString)
                        return
                #It wasn't a discord user nor a known tibia character
                if char == ERROR_NETWORK:
                    charString = "I... can you repeat that?"
                if char == ERROR_DOESNTEXIST:
                    charString = "I don't see any user or character with that name."
                yield from self.bot.say(charString)
                return
            if(user.id == self.bot.user.id):
                yield from self.bot.say(getAboutContent())
                return
            c.execute("SELECT name, last_level, vocation FROM chars WHERE user_id = ? ORDER BY abs(last_level) DESC",(user.id,))
            chars = []
            for name, level, vocation in c:
                try:
                    level = int(level)
                except ValueError:
                    level = 0

                vocation = vocAbb(vocation)
                chars.append("{0} (Lvl {1} {2})".format(name,abs(level) if level != 0 else "",vocation))
            if(len(chars) <= 0):
                yield from self.bot.say("I don't know who **@{0.name}** is...".format(user))
                if char == ERROR_NETWORK:
                    yield from self.bot.say("I also failed to do a character search for some reason "+EMOJI[":astonished:"])
                    return
                if char == ERROR_DOESNTEXIST:
                    yield from self.bot.say("And I don't see any character with that name.")
                    return

                c.execute("SELECT name,user_id FROM chars WHERE name LIKE ?",(name,))
                result = c.fetchone();
                if(result is not None):
                    user2 = getUserById(result[1])
                    if(user2 is not None):
                        charString = "But **{0}** is a character of **@{1.name}**.\n".format(char['name'],user2)+charString
                        yield from self.bot.say(charString)
                        return
                yield from self.bot.say(charString)
                return
            #TODO: Fix possesive if user ends with s
            yield from self.bot.say("@**{0.name}**'s character{1}: {2}.".format(user,"s are" if len(chars) > 1 else " is", joinList(chars,", "," and ")))
            if char == ERROR_NETWORK:
                yield from self.bot.say("But I failed to do a character search for some reason "+EMOJI[":astonished:"])
                return
            if char == ERROR_DOESNTEXIST:
                return
            yield from self.bot.say("The character "+charString)
            return
        finally:
            c.close()

    @commands.command(aliases=['expshare','party'])
    @asyncio.coroutine
    def share(self,*param : str):
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
        low = int(math.floor(level*2.0/3.0))
        high = int(math.floor(level*3.0/2.0))
        if(name == ''):
            yield from self.bot.say('A level '+str(level)+' can share experience with levels **'+str(low)+
        '** to **'+str(high)+'**.')
        else:
            yield from self.bot.say('**'+name+'** ('+str(level)+') can share experience with levels **'+str(low)+
        '** to **'+str(high)+'**.')



    @commands.command(aliases=['guildcheck'])
    @asyncio.coroutine
    def guild(self,*guildname : str):
        """Checks who is online in a guild"""
        guildname = " ".join(guildname)
        onlinelist,guildname = yield from getGuildOnline(guildname)
        if onlinelist == ERROR_DOESNTEXIST:
            yield from self.bot.say("The guild "+urllib.parse.unquote_plus(guildname)+" doesn't exist.")
            return
        if onlinelist == ERROR_NETWORK:
            yield from self.bot.say("Can you repeat that?")
            return
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
            result += vocAbb(member['vocation'])
        yield from self.bot.say(result)


    @commands.command(pass_context=True,aliases=['checkprice','item'])
    @asyncio.coroutine
    def itemprice(self,ctx,*itemname : str):
        """Checks an item's highest NPC price"""
        itemname = " ".join(itemname).strip()
        item = getItem(itemname)
        if(item is not None):
            if ctx.message.channel.is_private or ctx.message.channel.name == askchannel:
                yield from self.bot.say(getItemString(item,False))
            else:
                yield from self.bot.say(getItemString(item))
                if len(item['npcs_bought']) > 3 or len(item['npcs_sold']) > 3:
                    if ctx.message.author is not None:
                        yield from self.bot.send_message(ctx.message.author,getItemString(item,False))
        else:
            yield from self.bot.say("I couldn't find an item with that name.")
            
            


    @commands.command(pass_context=True,aliases=['mon','mob','creature'])
    @asyncio.coroutine
    def monster(self,ctx,*monstername : str):
        """Gives information about a monster"""
        monstername = " ".join(monstername).strip()
        if monstername.lower() == "nab bot":
            yield from self.bot.say(random.choice(["**Nab Bot** is too strong for you to hunt!","Sure, you kill *one* child and suddenly you're a monster!","I'M NOT A MONSTER"]))
            return
        monster = getMonster(monstername)
        if(monster is not None):
            filename = monster['name']+".gif"
            while os.path.isfile(filename):
                filename="_"+filename
            with open(filename, "w+b") as f:
                f.write(bytearray(monster['image']))
                f.close()

            if ctx.message.channel.is_private or ctx.message.channel.name == askchannel:
                with open(filename, "r+b") as f:
                    yield from self.bot.send_file(ctx.message.channel,f)
                    f.close()
                yield from self.bot.say(getMonsterString(monster,False))
            else:
                with open(filename, "r+b") as f:
                    yield from self.bot.send_file(ctx.message.channel,f)
                    f.close()
                yield from self.bot.say(getMonsterString(monster))
                if ctx.message.author is not None:
                    with open(filename, "r+b") as f:
                        yield from self.bot.send_file(ctx.message.author,f)
                        f.close()
                    yield from self.bot.send_message(ctx.message.author,getMonsterString(monster,False))
            os.remove(filename)
        else:
            yield from self.bot.say("I couldn't find a monster with that name.")


    @commands.command(aliases=['deathlist','death'])
    @asyncio.coroutine
    def deaths(self,*name : str):
        """Shows a player's recent deaths or global deaths if no player is specified"""
        name = " ".join(name).strip()
        if(not name):
            c = userDatabase.cursor()
            try:
                c.execute("SELECT level, date, name, user_id, byplayer, killer FROM char_deaths, chars WHERE char_id = id ORDER BY date DESC LIMIT 15")
                result = c.fetchall()
                if len(result) < 1:
                    yield from self.bot.say("No one has died recently")
                    return
                now = time.time()
                reply = "Latest deaths:"
                for level, date, name, user_id, byplayer, killer in result:
                    timediff = timedelta(seconds=now-date)
                    died = "Killed" if byplayer else "Died"
                    user = getUserById(user_id)
                    username = "unkown"
                    if(user):
                        username = user.name
                    reply += "\n\t{4} (**@{5}**) - {0} at level **{1}** by {2} - *{3} ago*".format(died,level,killer,getTimeDiff(timediff),name,username)
                yield from self.bot.say(reply)
                return
            finally:
                c.close()
        if name.lower() == "nab bot":
            yield from self.bot.say("**Nab Bot** never dies.")
            return
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
        tooMany = False
        if(len(deaths) > 15):
            tooMany = True
            deaths = deaths[:15]
        
        reply = name.title()+" recent deaths:"
        
        for death in deaths:
            diff = getTimeDiff(datetime.now() - getLocalTime(death['time']))
            died = "Killed" if death['byPlayer'] else "Died"
            reply += "\n\t{0} at level **{1}** by {2} - *{3} ago*".format(died,death['level'],death['killer'],diff)
        if(tooMany):
            reply += "\n*This person dies too much, I can't show you all the deaths!*"

        yield from self.bot.say(reply)

    @commands.command(pass_context=True,aliases=['levelups','lvl','level','lvls'])
    @asyncio.coroutine
    def levels(self,ctx,*name : str):
        """Shows a player's recent level ups or global leveups if no player is specified

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        name = " ".join(name)
        c = userDatabase.cursor()
        limit = 10
        if ctx.message.channel.is_private or ctx.message.channel.name == askchannel:
            limit = 20
        try:
            if(not name):
                c.execute("SELECT level, date, name, user_id FROM char_levelups, chars WHERE char_id = id AND level >= ? ORDER BY date DESC LIMIT ?",(announceTreshold,limit,))
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
                    reply += "\n\tLevel **{0}** - {2} (**@{3}**) - *{1} ago*".format(levelup[0],getTimeDiff(timediff),levelup[2],username)
                if(siteEnabled):
                    reply += "\nSee more levels check: <{0}{1}>".format(baseUrl,levelsPage)
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
            c.execute("SELECT level, date FROM char_levelups WHERE char_id = ? ORDER BY date DESC LIMIT ?",(id,limit,))
            result = c.fetchall()
            #Checking number of level ups
            if len(result) < 1:
                yield from self.bot.say("I haven't seen **{0}** level up.".format(name))
                return
            now = time.time()
            reply = "**{0}** latest level ups:".format(name)
            for levelup in result:
                timediff = timedelta(seconds=now-levelup[1])
                reply += "\n\tLevel **{0}** - *{1} ago*".format(levelup[0],getTimeDiff(timediff))
                
            reply += "\nSee more levels at: <{0}{1}?name={2}>".format(baseUrl,charactersPage,urllib.parse.quote(name))
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

    @commands.command()
    @asyncio.coroutine
    def spell(self,*name : str):
        """Tells you information about a certain spell."""
        name = " ".join(name)
        spell = getSpell(name)
        if spell is None:
            yield from self.bot.say("I don't know any spell with that name or words.")
            return
        mana = spell["mana"]
        if mana < 0:
            mana = "variable"
        words = spell["words"]
        if "exani hur" in words:
            words = "exani hur up/down"
        vocs = list()
        if(spell['knight']): vocs.append("knights")
        if(spell['paladin']): vocs.append("paladins")
        if(spell['druid']): vocs.append("druids")
        if(spell['sorcerer']): vocs.append("sorcerers")
        voc = joinList(vocs,", "," and ")
        reply = "**{0}** (*{1}*) is a {2}spell for level **{3}** and up. It uses **{4}** mana."
        reply = reply.format(spell["name"],words,"premium " if spell["premium"] else "",
                            spell["level"],mana)
        reply += " It can be used by {0}.".format(voc)
        if(spell["price"] == 0):
            reply += "\nIt can be obtained for free."
        else:
            reply += "\nIt can be bought for {0:,} gold coins.".format(spell["price"])
        #Todo: Show which NPCs sell the spell
        """if(len(spell['npcs']) > 0):
            for npc in spell['npcs']:
                vocs = list()
                if(npc['knight']): vocs.append("knights")
                if(npc['paladin']): vocs.append("paladins")
                if(npc['druid']): vocs.append("druids")
                if(npc['sorcerer']): vocs.append("sorcerers")
                voc = ", ".join(vocs)
                print("{0} ({1}) - {2}".format(npc['name'],npc['city'],voc))"""
        yield from self.bot.say(reply)

    @commands.command(aliases=['serversave'])
    @asyncio.coroutine
    def time(self):
        """Displays tibia server's time and time until server save"""
        offset = getTibiaTimeZone() - getLocalTimezone()
        tibia_time = datetime.now()+timedelta(hours=offset)
        server_save = tibia_time
        if(tibia_time.hour >= 10):
            server_save+= timedelta(days=1)
        server_save = server_save.replace(hour=10,minute=0,second=0,microsecond=0)
        time_until_ss = server_save - tibia_time
        hours, remainder = divmod(int(time_until_ss.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        timestr = tibia_time.strftime("%H:%M")
        server_save_str = '{h} hours and {m} minutes'.format(h=hours, m=minutes)

        yield from self.bot.say("It's currently **{0}** in Tibia's servers.\nServer save is in {1}.\nRashid is in **{2}** today".format(timestr,server_save_str,getRashidCity()))


def setup(bot):
    bot.add_cog(Tibia(bot))
    
if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")