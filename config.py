from utils import *

##This is the name of the server where the bot will work
###This bot doesn't support multiple servers yet
###mainchannel is where the Bot will do announcements, but he will reply to commands everywhere
###askchannel is a channel where the bot replies with full length messages (like on pms)
####Messages that are not commands are automatically deleted in askchannel
mainserver = "Redd Alliance/Bald Dwarfs"
mainchannel = "general-chat"
askchannel = "ask-nabbot"

##It's possible to fetch the database contents on a website to show more entries than what the bot can display
##If enabled, certain commands will link to the website
siteEnabled = True
baseUrl = "http://galarzaa.no-ip.org:7005/ReddAlliance/"
charactersPage = "characters.php"
deathsPage = "deaths.php"
levelsPage = "levels.php"

#Discord id for the users that can use admin commands
admin_ids = ["162060569803751424","162070610556616705","164253469912334350"]

#The list of servers to check for with getServerOnline
tibiaservers = ["Fidera","Secura"]

##Time since joining until the bot will ignore /im from an user. (See: /im in nabbot.py)
#Note that an user can simply rejoin the server to reset his join date, but that will trigger a log message.
timewindow_im_joining = timedelta(days=3)

###this is the global online list
##dont look at it too closely or you'll go blind!
##characters are added as servername_charactername and the list is updated periodically on think() using getServerOnline()
globalOnlineList = []

#level treshold for announces (level < announceLevel)
announceTreshold = 30

#delay inbetween server checks
serveronline_delay = timedelta(seconds=10)

#delay inbetween player death checks
playerdeath_delay = timedelta(seconds=5)

lastmessages = ["","","","","","","","","",""]
###message list for announceLevel ({charName}, {newLevel} , {pronoun1} (he/she), {pronoun2} (his/her), {pronoun3} (him/her))
##values are: relative chance(int), message(str), valid vocations(iterable or False to ignore), valid levels(iterable or False to ignore)
levelmessages = [[100,"Congratulations to **{charName}** on reaching level {newLevel}!"],
[100,"**{charName}** is level {newLevel} now, congrats!"],
[80,"**{charName}** has reached level {newLevel}, die and lose it, noob!"],
[100,"Well, look at **{charName}** with {pronoun2} new fancy level {newLevel}."],
[80,"**{charName}** is level {newLevel}, watch out world..."],
[100,"**{charName}** is level {newLevel} now. Noice."],
[100,"**{charName}** has finally made it to level {newLevel}, yay!"],
[80,"**{charName}** reached level {newLevel}! What a time to be alive..."+EMOJI[":_eyeroll:"]],
[70,"**{charName}** got level {newLevel}! So stronk now!"+EMOJI[":muscle:"]],
[30,"**{charName}** is level {newLevel}"+EMOJI[":cake:"]+"\r\n"+
    "I'm making a note here:"+EMOJI[":notes:"]+"\r\n"+
    "Huge success!"+EMOJI[":notes:"]+"\r\n"+
    "It's hard to overstate my"+EMOJI[":notes:"]+"\r\n"+
    "Satisfaction"+EMOJI[":_robot:"]],
[100,"**{charName}**, you reached level {newLevel}? Here, have a cookie "+EMOJI[":cookie:"]],
[80,"**{charName}** got level {newLevel}. I guess this justifies all those creatures {pronoun1} murdered."],
[90,"**{charName}** is level {newLevel}. Better than {pronoun1} was. Better, stronger, faster."],
[70,"Congrats **{charName}** on getting level {newLevel}! Maybe you can solo rats now?"],
[70,"**{charName}** is level {newLevel} now! And we all thought {pronoun1}'d never achieve anything in life."],
#EK Only
[50,"**{charName}** has reached level {newLevel}. Thats 9 more mana potions you can carry now!",["Knight","Elite Knight"],range(100,999)],
[200,"**{charName}** is level {newLevel}. Stick them with the pointy end! "+EMOJI[":_dagger:"],["Knight","Elite Knight"],range(100,999)],
[200,"**{charName}** is a fat level {newLevel} meatwall now. BLOCK FOR ME SENPAI.",["Knight","Elite Knight"],range(100,999)],
#RP Only
[50,"**{charName}** has reached level {newLevel}. But {pronoun1} still misses arrows...",["Paladin","Royal Paladin"],range(100,999)],
[150,"Congrats on level {newLevel}, **{charName}**. You can stop running around now.",["Paladin","Royal Paladin"],range(100,999)],
[150,"**{charName}** is level {newLevel}. Bullseye!"+EMOJI[":dart:"],["Paladin","Royal Paladin"],range(100,999)],
#MS Only
[50,"Level {newLevel},**{charName}**? Nice. Don't you wish you were a druid though?",["Sorcerer","Master Sorcerer"],range(100,999)],
[150,"**{charName}** is level {newLevel}. Watch out for {pronoun2} SDs!",["Sorcerer","Master Sorcerer"],range(100,999)],
[150,"**{charName}** is level {newLevel}. "+EMOJI[":fire:"]+EMOJI[":fire:"]+"BURN THEM ALL"+EMOJI[":fire:"]+EMOJI[":fire:"]+EMOJI[":fire:"],["Sorcerer","Master Sorcerer"],range(100,999)],
#ED Only
[50,"**{charName}** has reached level {newLevel}. Flower power!"+EMOJI[":blossom:"],["Druid","Elder Druid"],range(100,999)],
[150,"Congrats on level {newLevel}, **{charName}**. Sio plz.",["Druid","Elder Druid"],range(100,999)],
[150,"**{charName}** is level {newLevel}. "+EMOJI[":fire:"]+EMOJI[":fire:"]+"BURN THEM ALL... Or... Give them frostbite...?"+EMOJI[":_snowflake:"]+EMOJI[":_snowflake:"]+EMOJI[":_snowflake:"],["Druid","Elder Druid"],range(100,999)],
#Level specific
[20000,"**{charName}** is level {newLevel}! UMPs so good "+EMOJI[":wine_glass:"],["Druid","Elder Druid","Sorcerer","Master Sorcerer"],[130]],
[20000,"**{charName}** is now level {newLevel}. Don't forget to buy a Gearwheel Chain!"+EMOJI[":_necklace:"],False,[75]],
[30000,"**{charName}** is level {newLevel}! You can become a ninja now!"+EMOJI[":bust_in_silhouette:"],["Paladin","Royal Paladin"],[80]],
[20000,"Level {newLevel}, **{charName}**? You're finally important enough for me to notice!",False,[announceTreshold]],
[20000,"**{charName}** is now level {newLevel}! Time to go berserk! "+EMOJI[:anger:],["Knight","Elite Knight"],[35]],
[30000,"**{charName}** is level {newLevel}!!!!\r\n"+
    "Sweet, sweet triple digits!",False,[100]],
[20000,"**{charName}** is level {newLevel}!!!!\r\n"+
    "WOOO",False,[100,200,300,400]],
[20000,"**{charName}** is level {newLevel}!!!!\r\n"+
    "yaaaay milestone!",False,[100,200,300,400]],
[20000,"**{charName}** is level {newLevel}!!!!\r\n"+
    "holy crap!",False,[200,300,400]]]

###message list for announceDeath ({charName},{deathTime},{deathLevel},{deathKiller},{deathKillerArticle},{pronoun1} (he/she),{pronoun2} (his/her),{pronoun3} (him/her))
##additionally, words surrounded by \WORD/ are uppercased, /word\ are lowercased, /Word/ are title cased
##              words surrounded by ^WORD^ are ignored if the next letter found is uppercase (useful for dealing with proper nouns)
##values are: relative chance(int), message(str)   (conditions aren't being used yet (see: weighedChoice in utils.py))
##values are: relative chance(int), message(str), valid vocations(iterable or False to ignore), valid levels(iterable or False to ignore),valid killers(iterable or False to ignore, only for monster deaths)

#deaths by monster
deathmessages_monster = [
[100,"RIP **{charName}** ({deathLevel}), you died the way you lived- inside {deathKillerArticle}**{deathKiller}**."],
[100,"**{charName}** ({deathLevel}) was just eaten by {deathKillerArticle}**{deathKiller}**. Yum."],#TODO, get a list of human monsters to filter out of this. should also add some form of negation to conditions, or maybe just turn them into lambda function checks? idk im too drunk to do that right now -Nezune (see i signed this one, no need to worry Galarza!)
[100,"Silly **{charName}** ({deathLevel}), I warned you not to play with {deathKillerArticle}**{deathKiller}**!"],
[100,"{deathKillerArticle}**{deathKiller}** killed **{charName}** at level {deathLevel}. Shame "+EMOJI[":bell:"]+" shame "+EMOJI[":bell:"]+" shame "+EMOJI[":bell:"]],
[30,"**{charName}** ({deathLevel}) is no more! /{pronoun1}/ has ceased to be! /{pronoun1}/'s expired and gone to meet {pronoun2} maker! /{pronoun1}/'s a stiff! Bereft of life, {pronoun1} rests in peace! If {pronoun1} hadn't respawned {pronoun1}'d be pushing up the daisies! /{pronoun2}/ metabolic processes are now history! /{pronoun1}/'s off the server! /{pronoun1}/'s kicked the bucket, {pronoun1}'s shuffled off {pronoun2} mortal coil, kissed {deathKillerArticle}**{deathKiller}**'s butt, run down the curtain and joined the bleeding choir invisible!! THIS IS AN EX-**\{charName}/**."],
[100,"RIP **{charName}** ({deathLevel}), we hardly knew you! (^That ^**{deathKiller}** got to know you pretty well though "+EMOJI[":wink:"]+")"],
[80,"A priest, {deathKillerArticle}**{deathKiller}** and **{charName}** ({deathLevel}) walk into a bar. "+EMOJI[":skull:"]+"ONLY ONE WALKS OUT."+EMOJI[":skull:"]],
[90,"RIP **{charName}** ({deathLevel}), you were strong. ^The ^**{deathKiller}** was stronger."],
[80,"Oh, there goes **{charName}** ({deathLevel}), killed by {deathKillerArticle}**{deathKiller}**. So young, so full of life. /{pronoun1}/ will be miss... oh nevermind, {pronoun1} respawned already."],
[60,"Oh look! **{charName}** ({deathLevel}) died by {deathKillerArticle}**{deathKiller}**! What a surprise..."+EMOJI[":_eyeroll:"]],
[100,"**{charName}** ({deathLevel}) was killed by {deathKillerArticle}**{deathKiller}**, but we all saw that coming."],
[70,"That's what you get **{charName}** ({deathLevel}), for messing with ^that ^**{deathKiller}**!"],
[100,"Oh no! **{charName}** died at level {deathLevel}. Well, it's okay, just blame lag, I'm sure ^the^ **{deathKiller}** had nothing to do with it."],
[100,"**{charName}** ({deathLevel}) + **{deathKiller}** = dedd."],
[100,"**{charName}** ({deathLevel}) got killed by a **{deathKiller}**. Another one bites the dust!"],
[100,"**{charName}** ({deathLevel}) just kicked the bucket. And by kicked the bucket I mean a **{deathKiller}** beat the crap out of {pronoun3}."],
[100,"Alas, poor **{charName}** ({deathLevel}), I knew {pronoun3} Horatio; a fellow of infinite jest, of most excellent fancy; {pronoun1} hath borne me on {pronoun2} back a thousand times; and now, {pronoun1} got rekt by {deathKillerArticle}**{deathKiller}**."],
[70,"To be or not to be "+EMOJI[":skull:"]+", that is the-- Well I guess **{charName}** ({deathLevel}) made his choice, or ^that ^**{deathKiller}** chose for him..."],
[500,"**{charName}** ({deathLevel}) just died to {deathKillerArticle}**{deathKiller}**, why did nobody sio {pronoun3}!?",["Knight","Elite Knight"]],
[500,"Poor **{charName}** ({deathLevel}) has died. Killed by {deathKillerArticle}**{deathKiller}**. I bet it was your blockers fault though, eh **{charName}**?",["Druid","Elder Druid","Sorcerer","Master Sorcerer"]],
[500,"**{charName}** ({deathLevel}) tried running away from {deathKillerArticle}**{deathKiller}**. /{pronoun1}/ didn't run fast enough...",["Paladin","Royal Paladin"]],
[500,"What happened to **{charName}** ({deathLevel})!? Talk about sudden death! I guess ^that ^**{deathKiller}** was too much for {pronoun3}...",["Sorcerer","Master Sorcerer"]],
[500,"**{charName}** ({deathLevel}) was killed by {deathKillerArticle}**{deathKiller}**. I guess {pronoun1} couldn't sio {pronoun3}self.",["Druid","Elder Druid"]],
[20000,"**{charName}** ({deathLevel}) got killed by ***{deathKiller}***. How spooky is that! "+EMOJI[":ghost:"],False,False,["something evil"]],
[20000,"**{charName}** ({deathLevel}) died from **{deathKiller}**. Yeah, no shit.",False,False,["death"]],
[20000,"They did warn you **{charName}** ({deathLevel}), you *did* burn "+EMOJI[":fire:"]+EMOJI[":dragon_face:"]+".",False,False,["dragon","dragon lord"]],
[20000,"Asian chicks are no joke **{charName}** ({deathLevel}) "+EMOJI[":hocho:"]+EMOJI[":broken_heart:"]+".",False,False,["midnight asura","dawnfire asura"]]]
#deaths by player
deathmessages_player = [[100,"**{charName}** ({deathLevel}) got rekt! **{deathKiller}** ish pekay!"],
[100,"HALP **{deathKiller}** is going around killing innocent **{charName}** ({deathLevel})!"],
[100,"Next time stay away from **{deathKiller}**, **{charName}** ({deathLevel})."]]

########


##Databases filenames
USERDB = "users.db"
TIBIADB = "Database.db"

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")