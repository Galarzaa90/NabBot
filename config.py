from utils import *

########some global variables to give u cancer
###main channel where the bot chats for luls
##this is so we can keep track of idletime for this server only
##and do timed shit in here
mainserver = "Redd Alliance/Bald Dwarfs"
mainchannel = "general-chat"
mainchannel_idletime = timedelta(seconds=0)
###lastmessage stuff
lastmessage = None
lastmessagetime = datetime.now()
###goof() globals
#a boolean to know if a goofing msg was the last thing we saw
isgoof = False
#delay inbetween goofing
goof_delay = timedelta(seconds=300)
#list of idle messages for the goof() command
idlemessages = ["Galarzazzzzza is a nab, i know, i know, oh oh oh",
"Did you know 9 out of 10 giant spiders prefer nabchow?",
"Any allegations made about Nezune and corpses are nothing but slander!",
"All hail Michu, our cat overlord.",
"Beware of nomads, they are known to kill unsuspecting druids!"]

#admin id's for hax commands
admin_ids = ["162060569803751424","162070610556616705"]

###Main Tibia Server
#tibia_server = "Fidera"
#^^^^just use the servers list!!!

#the list of servers to check for with getServerOnline
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
[80,"**{0}** reached level {1}! What a time to be alive..."+str(chr(0x1f644))],
[70,"**{0}** got level {1}! So stronk now!"]]

###message list for announceDeath (charName=0,deathTime=1,deathLevel=2,deathKiller=3,deathKillerArticle=4,he/she=5,his/her=6)
##additionally, words surrounded by \WORD/ are uppercased, /word\ are lowercased, /Word/ are title cased
##              words surrounded by ^WORD^ are ignored if the next letter found is uppercase (useful for dealing with proper nouns)
##deaths by monster

deathmessages_monster = [[100,"RIP **{0}** ({2}), you died the way you lived- inside {4}**{3}**."],
[100,"**{0}** ({2}) was just eaten by {4}**{3}**. Yum."],
[100,"Silly **{0}** ({2}), I warned you not to play with {4}**{3}**!"],
[100,"{4}**{3}** killed **{0}** at level {2}. Shame "+str(chr(0x0001f514))+" shame "+str(chr(0x0001f514))+" shame "+str(chr(0x0001f514))],
[50,"**{0}** ({2}) is no more! /{5}/ has ceased to be! /{5}/'s expired and gone to meet {6} maker! /{5}/'s a stiff! Bereft of life, {5} rests in peace! If {5} hadn't respawned {5}'d be pushing up the daisies! /{6}/ metabolic processes are now history! /{5}/'s off the server! /{5}/'s kicked the bucket, {5}'s shuffled off {6} mortal coil, kissed {4}**{3}**'s butt, run down the curtain and joined the bleeding choir invisible!! THIS IS AN EX-**\{0}/**."],
[100,"RIP **{0}** ({2}), we hardly knew you! (^That ^**{3}** got to know you pretty well though "+str(chr(0x0001f609))+")"],
[80,"A priest, {4}**{3}** and **{0}** ({2}) walk into a bar. "+str(chr(0x0001f480))+"ONLY ONE GETS OUT."+str(chr(0x0001f480))],
[90,"RIP **{0}** ({2}), you were strong. ^The ^**{3}** was stronger."]]
##deaths by player
deathmessages_player = [[100,"**{0}** ({2}) got rekt! **{3}** ish pekay!"],
[100,"HALP **{3}** is going around killing innocent **{0}** ({2})!"],
[100,"Next time stay away from **{3}**, **{0}** ({2})."]]
########

### Channels to look for users ###
## I don't want to change the other variable cause I don't want goof messages on the main channel yet
mainserver = "Redd Alliance/Bald Dwarfs"
search_channel = "general-chat"