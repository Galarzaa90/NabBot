# NabBot
Nab Bot is a discord bot that uses [Rapptz's discord.py](https://github.com/Rapptz/discord.py). It features commands related to the MMORPG [Tibia](http://www.tibia.com/news/?subtopic=latestnews).

##Requirements
* Python 3.4.2+
* discord.py
* Tested on Windows and Raspbian

#Installing and running
To install discord.py simply run the following on the command line:

```
pip install git+https://github.com/Rapptz/discord.py@async
```


To run the bot, execute the following command

```
python nabbot.py
```

##Current features

* **/check** *playername*: Returns information about a character.
* **/guild** *guildname*: Returns a list of the online players of a guild
* **/share** *level*/*playername*: Returns the level ranger for party experience share for the specified level or player.
* **/itemprice** *itemname*: Returns the highest NPC value of an item and the who buys it


<img src="https://cloud.githubusercontent.com/assets/12865379/14549417/86905512-0274-11e6-87f0-ccbab911c820.png">
