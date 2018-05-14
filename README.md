
# NabBot
Nab Bot is a discord bot that uses [Rapptz's discord.py](https://github.com/Rapptz/discord.py). It features commands related to the MMORPG [Tibia](http://www.tibia.com/news/?subtopic=latestnews).

![Python version](https://img.shields.io/badge/python-3.6-yellow.svg)
[![Build Status](https://travis-ci.org/Galarzaa90/NabBot.svg)](https://travis-ci.org/Galarzaa90/NabBot)
[![GitHub release](https://img.shields.io/github/release/Galarzaa90/NabBot.svg)](https://github.com/Galarzaa90/NabBot/releases)

## Requirements
* Python 3.6.1 with modules:
    * psutil
    * pillow (Python Imaging Library)
    * BeautifulSoup
    * pyYAML
* discord.py **rewrite branch**

## Installing and running
To install NabBot's dependencies, open the command line from NabBot's root folder and use:

```bat
python -m pip install -U -r requirements.txt
```

Create a bot token on Discord

```
https://discordapp.com/developers/applications/me
```

Allow the bot to join your server

```
https://discordapp.com/developers/docs/topics/oauth2#bots
```

Define the bots permissions for your server.  
As of 04/May/2018, Nab Bot needs the following permissions: 257232

```
https://discordapi.com/permissions.html
https://discordapp.com/developers/docs/topics/oauth2#adding-bots-to-guilds
```

Finally, execute the following command to run the bot:

```
python nabbot.py
```

For more detailed instructions, read the [install guide](https://galarzaa90.github.io/NabBot/install/).

## Current features
* Characters and guilds lookup
* Linking characters to discord users
* Level up and deaths announcements
* Event management, create timed events with announcements
* Keeps track of registered character's deaths and level ups as a log.
* Watched list, add characters or guilds to check their online status all the time
* Information commands, based on TibiaWiki articles. Items, monsters, NPCs, houses and more.

## Documentation
See https://galarzaa90.github.io/NabBot/

## Support
Visit our support server

[![Support Server](https://discordapp.com/api/guilds/441991938200305674/embed.png)](https://discord.gg/NmDvhpY)

## Donate
If you like Nab Bot, you can donate to this project. Nab Bot and the developers will appreciate it :)


[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donate_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=B33DCPZ9D3GMJ)
