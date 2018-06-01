# Changelog

## Version 1.2.0 (Unreleased)
- New `/help` style, with reaction pagination.
- New `/quote` command, shows a message's content given an id.
- New `/roleinfo` command, shows a role's detailed information.
- New `/userinfo` command, shows a user's detailed information.
- New `/ping` command, shows the bot's response times.
- Made some visual changes to `/serverinfo`
- Moved role related commands to new Roles cog.
- Many changes to command names and aliases:
    - `/item`: `checkprice` alias removed, `items` alias added.
    - `/monster`: `mon` alias removed.
    - `/spell`: `spells` alias added.
    - `/setworld`: `trackworld` alias added.
    - `/seteventchannel`: `seteventschannel` alias removed.
    - `/setleveldeathschannel`: `setlevelchannel`, `setdeathchannel`, `setleveldeathchannel` aliases removed.
    - `/server`: `server_info` alias removed.
    - `/guild`: `guildcheck` alias removed.
    - `/role`: Renamed to `/rolemembers`.
    - `/server`: Renamed to `/serverinfo`.

## Version 1.1.0 (2018-05-24)
- New command: `/leave`, to make the bot leave a discord server.
- New command: `/versions`, shows the current version and the version of dependencies.
- New command: `/searchworld`, to show filterable list of players online in a server.
- New subcommand: `/watched info` and `/watched infoguild` to show details about a watched list entry.
- `/monster` now shows monster's attributes and bestiary info.
- `/diagnose` was renamed to `/checkchannel`, permissions were updated.
- `/watched add` and `/watched addguild` now can take a reason as a parameter
- `/online` is no longer usable in PMs
- `/online` and `/searchteam` are hidden from `/help` when no world is tracked in the current server.
- Watched List now uses an embed, meaning the length is 3 times longer.
- Minor improvements to documentation site.
- Improvements to server-log to make them have a uniform style.
- Updated TibiaWiki database, fixed bug with potions price due to NPC Minzy.

## Version 1.0.1 (2018-05-07)
- Renamed characters are updated more effectively, preventing some cases of character duplication.
- `/watched` no longer asks for `Manage Roles` permissions.
- `/im` asks the user if he wants to add other visible characters if applicable, instead of just adding all.
- Changed format of server-log messages for `/im` and `/claim` to match the style of the rest of the messages.
- Fixed bug in `/namelock` command.
- Updated documentation.


## Version 1.0.0 (2018-05-03)
- Now requires **Python 3.6**.
- Now uses the "rewrite" version of `discord.py`, meaning there are tons of breaking changes, and there will be more until v1.0.0 is released for `discord.py`.
- Improved cogs organization, allowing to reload NabBot by modules.
- Improved many commands to use pagination.
- Added better support for multiple discord servers.
- Added watchlist feature, to keep track of the online status of certain characters or guilds (also known as "Hunted list").
- Improved `/whois` appearance.
- New commands: `/ignore` and `/unignore`, to make it easier to control where NabBot can answer to commands.
- Improved the way events work and are displayed.
- Added event participants, to keep track of which characters are assisting and events, good for organizing team based events like Heart of Destruction.
- Various changes to `/deaths`, `/levels` and `/timeline` display.
- Items and monsters now show animated gifs.
- Items now show imbuements slots and materials show for which imbuement they are for.
- Migrated many services from Tibia.com to TibiaData.com for better reliability.
- TibiaWiki database is now more recent and is now a [separate project](https://github.com/Galarzaa90/tibiawiki-sql)
- Added tons of new commands and rewrote many of them.
- Added [documentation site](https://galarzaa90.github.io/NabBot/)
- And too many changes too list them here.

## Version 0.1.3 (2018-03-08)
- Removed site feature.
- Adjustments to number positions for `/loot` detection.
- Updated world list.
- Fixed bug in encoding of spouse names.
- Updated TibiaWiki database.

## Version 0.1.2 (2017-06-09)
- Added Duna and Relembra to world list.
- Added a database template for the loot database.
- Fixed bug with `/achiev` command not responding to unexistant achievements.

## Version 0.1.1 (2017-04-24)
- Added Honbra, Noctera and Vita to world list.

## Version 0.1.0 (2017-04-16)
Initial release

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


