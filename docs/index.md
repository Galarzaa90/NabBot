# NabBot [![Build Status](https://travis-ci.org/Galarzaa90/NabBot.svg?branch=rewrite)](https://travis-ci.org/Galarzaa90/NabBot)
 Nab Bot is a discord bot that uses [Rapptz's discord.py](https://github.com/Rapptz/discord.py). 
It features commands related to the MMORPG [Tibia](http://www.tibia.com/abouttibia/?subtopic=whatistibia).

## Features
* Characters and guilds lookup
* Linking characters to discord users
* Level up and deaths announcements
* Event management, create timed events with announcements
* Keeps track of registered character's deaths and level ups as a log.
* Watched list, add characters or guilds to check their online status all the time
* Information commands, based on TibiaWiki articles. Items, monsters, NPCs, houses and more.

!!! error "Note"
     This is not a cavebot, this bot does not interact with the client in any way, NabBot is a messaging bot. We're not interested in developing cavebots, do not contact us for such reasons.

## Requirements
* Python 3.6+
* [discord.py (rewrite branch)](https://github.com/Rapptz/discord.py/tree/rewrite)
* psutil
* pillow
* BeautifulSoup
* pyYAML
* Any operating system
 
## Installing and running
1. Install the required python modules
    ```bat
    python -m pip install -U git+https://github.com/Rapptz/discord.py@rewrite
    python -m pip install pillow psutil beautifulsoup4 pyYAML
    ```
1. [Create a bot token on Discord](https://discordapp.com/developers/applications/me)
1. Start the bot by running the file `nabbot.py`, you will be prompted for a token. Insert the generated token.
1. The console should show your bot is online now.
1. Allow the bot to join your server.
1. NabBot should now be online on your server now.

!!! info
    For more details, check the [Install Guide](install.md)


## Support
Visit our support server

[![Support Server](https://discordapp.com/api/guilds/441991938200305674/embed.png)](https://discord.gg/NmDvhpY)
 
 
## Donate
If you like Nab Bot, you can donate to this project. Nab Bot and the developers will appreciate it :)


[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donate_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=B33DCPZ9D3GMJ)
