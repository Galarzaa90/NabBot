from utils import *

##This is the name of the server where the bot will work
###This bot doesn't support multiple servers yet
mainserver = "Redd Alliance/Bald Dwarfs"
mainchannel = "general-chat"

#Discord id for the users that can use admin commands
admin_ids = ["162060569803751424","162070610556616705"]

#The list of servers to check for with getServerOnline
tibiaservers = ["Fidera","Secura"]

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

###message list for announceLevel (charName=0,newLevel=1,he/she=2,his/her=3)
levelmessages = [[100,"Congratulations to **{0}** on reaching level {1}!"],
[100,"**{0}** is level {1} now, congrats!"],
[80,"**{0}** has reached level {1}, die and lose it, noob!"],
[100,"Well, look at **{0}** with {3} new fancy level {1}."],
[80,"**{0}** is level {1}, watch out world..."],
[100,"**{0}** is level {1} now. Noice."],
[100,"**{0}** has finally made it to level {1}, yay!"],
[80,"**{0}** reached level {1}! What a time to be alive..."+EMOJI_EYEROLL],
[70,"**{0}** got level {1}! So stronk now!"+EMOJI_BICEPS],
[60,"**{0}** is level {1}"+EMOJI_CAKE+"\r\n"+
    "I'm making a note here:"+EMOJI_MUSICNOTES+"\r\n"+
    "Huge success!"+EMOJI_MUSICNOTES+"\r\n"+
    "It's hard to overstate my"+EMOJI_MUSICNOTES+"\r\n"+
    "Satisfaction"+EMOJI_ROBOT],
[100,"**{0}**, you reached level {1}? Here, have a cookie "+EMOJI_COOKIE],
[80,"**{0}** got level {1}. I guess this justifies all those creatures {2} murdered."],
[90,"**{0}** is level {1}. Better than {2} was. Better, stronger, faster."],
[70,"Congrats **{0}** on getting level {1}! Maybe you can solo rats now?"],
[70,"**{0}** is level {1} now! And we all thought {2}'d never achieve anything in life."],
###EK Only
[50,"**{0}** has reached level {1}. Thats 9 more mana potions you can carry now!",["Knight","Elite Knight"],range(100,999)],
[200,"**{0}** is level {1}. Stick them with the pointy end! "+EMOJI_DAGGER,["Knight","Elite Knight"],range(100,999)],
[200,"**{0}** is a fat level {1} meatwall now. BLOCK FOR ME SENPAI.",["Knight","Elite Knight"],range(100,999)],
###RP Only
[50,"**{0}** has reached level {1}. But he still misses arrows...",["Paladin","Royal Paladin"],range(100,999)],
[150,"Congrats on level {1}, **{0}**. You can stop running around now.",["Paladin","Royal Paladin"],range(100,999)],
[150,"**{0}** is level {1}. Bullseye!"+EMOJI_BULLSEYE,["Paladin","Royal Paladin"],range(100,999)],
###MS Only
[50,"Level {1},**{0}**? Nice. Don't you wish you were a druid though?",["Sorcerer","Master Sorcerer"],range(100,999)],
[150,"**{0}** is level {1}. Watch out for {3} SDs!",["Sorcerer","Master Sorcerer"],range(100,999)],
[150,"**{0}** is level {1}. "+EMOJI_FIRE+EMOJI_FIRE+"BURN THEM ALL"+EMOJI_FIRE+EMOJI_FIRE+EMOJI_FIRE,["Sorcerer","Master Sorcerer"],range(100,999)],
###ED Only
[50,"**{0}** has reached level {1}. Flower power!"+EMOJI_BLOSSOM,["Druid","Elder Druid"],range(100,999)],
[150,"Congrats on level {1}, **{0}**. Sio plz.",["Druid","Elder Druid"],range(100,999)],
[150,"**{0}** is level {1}. "+EMOJI_FIRE+EMOJI_FIRE+"BURN THEM ALL... Or... Give them frostbite...?"+EMOJI_SNOWFLAKE+EMOJI_SNOWFLAKE+EMOJI_SNOWFLAKE,["Druid","Elder Druid"],range(100,999)],
###Level specific
[2000,"**{0}** is level {1}! UMPs so good "+EMOJI_WINEGLASS,["Druid","Elder Druid","Sorcerer","Master Sorcerer"],[130]],
[2000,"**{0}** is now level {1}. Don't forget to buy a Gearwheel Chain!"+EMOJI_NECKLACE,False,[75]],
[2000,"Level {1}, **{0}**? You're finally important enough for me to notice!",False,[announceTreshold]],
[3000,"**{0}** is level {1}!!!!\r\n"+
    "Sweet, sweet triple digits!",False,[100]],
[2000,"**{0}** is level {1}!!!!\r\n"+
    "WOOO ",False,[100,200,300,400]]]

###message list for announceDeath (charName=0,deathTime=1,deathLevel=2,deathKiller=3,deathKillerArticle=4,he/she=5,his/her=6)
##additionally, words surrounded by \WORD/ are uppercased, /word\ are lowercased, /Word/ are title cased
##              words surrounded by ^WORD^ are ignored if the next letter found is uppercase (useful for dealing with proper nouns)
##deaths by monster

deathmessages_monster = [[100,"RIP **{0}** ({2}), you died the way you lived- inside {4}**{3}**."],
[100,"**{0}** ({2}) was just eaten by {4}**{3}**. Yum."],
[100,"Silly **{0}** ({2}), I warned you not to play with {4}**{3}**!"],
[100,"{4}**{3}** killed **{0}** at level {2}. Shame "+EMOJI_BELL+" shame "+EMOJI_BELL+" shame "+EMOJI_BELL],
[50,"**{0}** ({2}) is no more! /{5}/ has ceased to be! /{5}/'s expired and gone to meet {6} maker! /{5}/'s a stiff! Bereft of life, {5} rests in peace! If {5} hadn't respawned {5}'d be pushing up the daisies! /{6}/ metabolic processes are now history! /{5}/'s off the server! /{5}/'s kicked the bucket, {5}'s shuffled off {6} mortal coil, kissed {4}**{3}**'s butt, run down the curtain and joined the bleeding choir invisible!! THIS IS AN EX-**\{0}/**."],
[100,"RIP **{0}** ({2}), we hardly knew you! (^That ^**{3}** got to know you pretty well though "+EMOJI_WINK+")"],
[80,"A priest, {4}**{3}** and **{0}** ({2}) walk into a bar. "+EMOJI_SKULL+"ONLY ONE WALKS OUT."+EMOJI_SKULL],
[90,"RIP **{0}** ({2}), you were strong. ^The ^**{3}** was stronger."]]
##deaths by player
deathmessages_player = [[100,"**{0}** ({2}) got rekt! **{3}** ish pekay!"],
[100,"HALP **{3}** is going around killing innocent **{0}** ({2})!"],
[100,"Next time stay away from **{3}**, **{0}** ({2})."]]
########


##Databases filenames
USERDB = "users.db"
TIBIADB = "Database.db"