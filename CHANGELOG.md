# Changelog

## Unreleased Version 1.0.1
- Renamed characters are updated more effectively, preventing some cases of character duplication.


## Version 1.0.0 (2018-05-03)
- Now requires **Python 3.6** or higher.
- Now uses the "rewrite" version of `discord.py`, meaning there are tons of breaking changes, and there will be more
until v1.0.0 is released for `discord.py`
- Improved cogs organization, allowing to reload NabBot by modules
- Improved many commands to use pagination
- Added better support for multiple discord servers
- Added watchlist feature, to keep track of the online status of certain characters or guilds (also known as "Hunted list")
- Improved /whois appearance
- New commands: /ignore and /unignore, to make it easier to control where NabBot can answer to commands.
. Improved the way events work and are displayed
- Added event participants, to keep track of which characters are assisting and events, good for organizing team based events like Heart of Destruction.
- Various changes to /deaths, /levels and /timeline display
- Items and monsters now show animated gifs
- Items now show imbuements slots and materials show for which imbuement they are for
- Migrated many services from Tibia.com to TibiaData.com for better reliability.
- TibiaWiki database is now more recent and is now a [separate project](https://github.com/Galarzaa90/tibiawiki-sql)
- Added tons of new commands and rewrote many of them
- Added [documentation site](https://galarzaa90.github.io/NabBot/)
- And too many changes too list them here.

## Version 0.1.3 (2018-03-08)
- Removed site feature
- Adjustments to number positions for `/loot` detection
- Updated world list
- Fixed bug in encoding of spouse names
- Updated TibiaWiki database

## Version 0.1.2 (2017-06-09)
- Added Duna and Relembra to world list
- Added a database template for the loot database.
- Fixed bug with `/achiev` command not responding to unexistant achievements.

## Version 0.1.1 (2017-04-24)
- Added Honbra, Noctera and Vita to world list

## Version 0.1.0 (2017-04-16)
Initial release

### Features
- Tibia character lookup
- Item lookup
- Spell lookup
- Guild lookup
- Monster lookup
- Assigning Tibia characters to Discord Users
- Level up announcements
- Death announcements
- Tibia.com highscores tracking
- Loot screenshot analyzer
- Event creation


