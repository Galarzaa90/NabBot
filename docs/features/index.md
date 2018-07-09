# Features Overview
Apart of the traditional discord bot features like commands, NabBot has a couple other useful features for server management.

NabBot is able to check and retrieve most information available in Tibia.com, like character information, guilds, online list and houses.
Aditionally, it uses a database generated from TibiaWiki content, to show information about monsters, items and more.

To see a full list commands check the [commands section](../commands).

## Character tracking
One of the initial features of NabBot was the ability to link discord users and tibia characters together.

A user can indicate which characters are theirs by using the [im command](../commands/tracking.md#im).
Once they have registered their characters, they are able to see them using the [whois command](../commands/tibia.md#whois).

This allows you to have a correlation between discord users and tibia characters.

## Level and death announcements
Al tracked characters are constantly being scanned by the bot, checking for level differences or new deaths.

Once a new level or a death is found, they are announced on the designated channel.
Additionally, entries are saved so they can be checked later, creating a history for the character.
