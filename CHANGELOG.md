# Changelog
## Version 1.6.0 (2018-08-27)
- New command: `/rashid`.
- `/time` no longer displays Mexico and Brazil's timezones.
- Custom timezones can be added on a per-server basis using `/time add`. See `/time` subcommands for more info.
- Now requires module `pytz`.
- `/watched` can now be used by Server Moderators instead of Administrators only.
- Fixed a bug with the global online list not having its levels updated.
- Fixed a bug with invalid characters when using `/whois`.
- Fixed a bug with `/whois` visibility.
    - You're no longer able to see the characters of people you can't see in discord when using on PM.
    - When using on server channels, you can only see characters of people in that server. 

## Version 1.5.1 (2018-08-07)
- Various `/event` subcommands were showing the member's nicknames from other servers
- Cleaner bad argument errors for commands in the General cog.
- Fixed bug with highscores not getting saved
- Fixed issue with `/house` being case sensitive with world names.
- Added caching for external requests, to reduce load on external services.
- Updated TibiaWiki database to the state of August 7th 2018.

## Version 1.5.0 (2018-07-31)
- Small changes to `/userinfo`
- Fixed bug in `/monster` with creatures without a bestiary class defined.
- Added loading message to `/im`.
- Bot owner can now use `/serverinfo` to see other server's info.
- `/servers` now has pagination and sorting.
- NabBot now responds to a mention with its command prefixes.
- New `/emojiinfo` command
- Created new cog `Info`, moved information commands from `General`
- Level up and death messages now use lambdas for filtering.
- Server settings can now be changed with `Manage Server` permissions instead of `Administrator` permission.
- NabBot's initial message is now sent on a server channel instead of PMing the owner.  

## Version 1.4.0 (2018-07-24)
- `/loot` has been rewritten:
    - Loot database remade from scratch with images extracted directly from the client, all images should now be pixel perfect matches to those taken from in-game screenshots
    - Priority values for items were removed so database can be updated directly (no longer requires template database)
    - Quality checks removed, now expects pixel perfect images (compressed images or screenshots taken using the software renderer won't be scanned at all).
    - Number scan updated to properly handle stacks higher than three digits (mostly to be able to scan images taken from the stash, also recognizes the letter K in stack numbers)
    - Now properly scans slots even if a few pixels at the bottom were cut off or blocked by the window border.
    - Massive performance improvements.
- Minimum announce level is now configurable per server (`/settings minlevel`).
- Event channel is now disabled by default.
- New configurable emoji: `loading_emoji`
    - By default ⏳ is used.
- Removed restart scripts as they were outdated, very platform specific and bad practice.
- Improved world scanning speed to not be heavily affected by the number of tracked worlds.
- New `/sql` command, executes a sql query and shows the results, only for the bot owner.
- New `/wikistats` command, shows you information about the TibiaWiki database used.
- `/removechar` now only lets you remove chars from users that are only in servers you are an admin in.
- Fixed bug in `/event make` showing failure icon on success.
- Fixed bug in `/addchar`, it was not working at all.
- Fixed bug in `/world` when query included spaces.
- Fixed bug in `/monster` failing if it was missing some bestiary data.
- Fixed bug in `/event addplayer` failing when the character was not registered.
- Fixed error when using `/share` with no parameters.
- Fixed bug in commands that offer you choices not working in commands channel.
- Fixed bug in `/choose` when the command was used with no parameters.
- `/stamina` now considers the 10 minutes you have to be logged off to start regenerating stamina.
- Removed `/restart` command as it was really system specific and not an universal solution, along with the autorestarting launchers.
- Command error now contains a link to the support server.

## Version 1.3.2 (2018-07-15)
- Monster's occurence was being displayed incorrectly.
- Updated database to show better update information.

## Version 1.3.1 (2018-07-14)
- Fixed some typos in config_template.yml
- Added suggested emojis for charms, occurrence and bestiary difficulty.

## Version 1.3.0 (2018-07-12)
- Emoji changes are now displayed on server-log.
- Main emojis can be customized now, allowing custom discord emojis
    - Vocation emojis.
    - Elemental resistance emojis in `/monster`.
    - Discord presence emojis in `/serverinfo`.
    - Checkbox and cross emojis to show boolean flags.
    - Level up and deaths emojis.
    - And more
- Added joinable role feature, called groups:
    - To create a group: `/group add <name>` (requires `Manage Roles` permission)
    - To join/leave a group: `/group <name`
    - To see available groups: `/group list`
    - To delete a group: `/group remove <name>`
- Added automatic roles
    - Roles are assigned based on the guilds of registered characters.
    - See `help autorole` for more information on commands.
- Increased /loot scanning speed.
- Simultaneous loot scans are now user-wide, not global. Each user can only have one image scanned at a time.
- Welcome message can now be fully customized, including the welcome message channel. Available under `/settings`
- Welcome messages are no longer enabled by default.
- New `/imbuement` command, shows basic information about an imbuement and if prices are provided, it calculates costs.
- New `/permissions` command, shows the permissions for a member in a channel.
- New `/cleanup` command, cleans bot messages and command invocations in the current channel.
- New `/roll` command, rolls a die and shows the results.
- New `/botinfo` command, shows advanced information about the bot.
- New `/worlds` command, shows a list of worlds with their location, pvptype and online population, with filtering options.
- `/about` now shows less advanced information, and more general information.
- `/version` now checks if the required minimum commit version of discord.py is being used.
- `/monster` now shows occurrence, kills required and charm points given.
- `/monster`, `/house`, `/spell`, `/npc`, `/item`, `/imbuement`, `/achievement`
- Fixed `/checkchannel` ignoring channel parameter.
- Fixed `/quote` failing when quoting users no longer in server.
- Tibia.com news announcement are now disabled by default, must be enabled per server.
- Command name and aliases changes:
    - `/debug`: renamed to `/eval`.
    - `/help`: Alias `/commands` added.
    - `/setwelcome`: Removed.
    - `/purge`: Removed.

## Version 1.2.3 (2018-06-19)
- Fixed a bug with `/whois` when a user was not found.

## Version 1.2.2 (2018-06-19)
- `/unregistered` no longer displays discord bots.
- Fixed display bug in `/settings askchannel`.
- Improved `/event make`, no longer aborts on failure, lets the user retry and cleans up messages after.
- Improved `/event` subcommands in general, they leave less messages behind.
- Fixed checks for `/watched` subcommands.
- Removed orphaned `utils/emoji.py`
- Minor improvements to `/debug` (now handles multiple lines), added `/eval`as alias.
- Documentation improvements.

## Version 1.2.1 (2018-06-14)
- Updated mentions of `/setworld` and similar to `/settings world`.
- If the server owner has PMs disabled when the bot joins, the bot will send the initial message in the server.

## Version 1.2.0 (2018-06-14)
- New `/help` style, with reaction pagination.
- New `/quote` command, shows a message's content given an id.
- New `/roleinfo` command, shows a role's detailed information.
- New `/userinfo` command, shows a user's detailed information.
- New `/ping` command, shows the bot's response times.
- New `/bestiary` command, shows the bestiary classes or creatures that belong to a class.
- Command prefix is now configurable per server
- Mention prefix command is now always enabled (e.g. `@NabBot help`)
- Improvements to the watched list task
- Made some visual changes to `/serverinfo`
- Moved role related commands to new Roles cog.
- `/roles` now sorts results by position and shows members with the role.
- New command: `/settings`, to change all server specific settings:
    - `/setworld` moved to `/settings world`.
    - `/setleveldeathschannel` moved to `/settings levelschannel`.
    - `/seteventschannel` moved to `/settings eventschannel`
    - News channel is now configured separately from Events channel: `/settings newschannel`
    - Command channel (ask-nabbot) is now configurable.
    - Tibia news announcements and Events announcements can be disabled entirely.
- Many changes to command names and aliases:
    - `/item`: `checkprice` alias removed.
    - `/monster`: `mon` alias removed.
    - `/spell`: `spells` alias added.
    - `/server`: `server_info` alias removed.
    - `/guild`: `guildcheck` alias removed.
    - `/role`: Renamed to `/rolemembers`.
    - `/server`: Renamed to `/serverinfo`.
    - `/deaths`: `death` alias removed.
    - `/house`: `houses`, `gh` aliases removed.
    - `/levels`: `lvl`, `level` and `lvls` aliases removed.
    - `/time`: `ss` alias removed.
    - `/whois`: `player`, `checkplayer` aliases removed
    - `/npc`: `npcs` alias removed.
    - `/key`: `keys` alias removed.
    - `/spell`: `spell` alias removed.
    - `admins_message`: renamed to `adminsmessage`, removed all aliases, added `notifyadmins`
    - Many more aliases changes

## Version 1.1.1 (2018-06-12)
- Added missing items from the Feyrist area to the loot database
- Fixed an issue causing /loot update to only work the second time it was called

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
- Added [documentation site](https://nabdev.github.io/NabBot/)
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


