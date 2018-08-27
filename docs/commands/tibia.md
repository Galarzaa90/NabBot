# Tibia commands

Commands related to Tibia, gathered from information present in Tibia.com

!!! info
    Parameters are enclosed with `< >`.   
    Optional parameters are enclosed in brackets `[]`.

## blessings
**Usage:** `blessings <level>`  
**Other aliases:** `bless`

Calculates the price of blessings at a specific level.

For players over level 100, it will also display the cost of the Blessing of the Inquisition.

??? Summary "Examples"
    **/bless 90**  
    ![image](../assets/images/commands/bless_1.png)  
    **/bless 140**  
    ![image](../assets/images/commands/bless_2.png)

----

## deaths
**Syntax:** `deaths [player]`  
**Other aliases:** `deathlist`

Shows a character's recent deaths.

If this discord server is tracking a tibia world, it will show deaths registered to the character.
Additionally, if no name is provided, all recent deaths will be shown.

??? Summary "Examples"
    **/deaths Xzilla**  
    ![image](../assets/images/commands/deaths_1.png)  
    **/deaths**  
    ![image](../assets/images/commands/deaths_2.png)

----

### deaths monster
**Syntax:** `deaths monster <name>`  
**Other aliases:** `deaths mob`, `deaths killer`

Shows the latest deaths caused by a specific monster.

??? Summary "Example"
    **/deaths mob Lloyd**  
    ![image](../assets/images/commands/deaths_mob.png)

----

### deaths user
**Syntax:** `death user <name>`

Shows recent deaths by all characters registered to a user.

??? Summary "Example"
    **/deaths user Nezune**  
    ![image](../assets/images/commands/deaths_stats.png)

----

### deaths stats
**Syntax:** `death stats [week/month]`

Shows death statistics.

Shows the total number of deaths, the characters and users with more deaths, and the most common killers.

To see a shorter period, use `week` or `month` as a parameter.

??? Summary "Example"
    **/deaths stats**  
    ![image](../assets/images/commands/deaths_stats.png)

----

## guild
**Syntax:** `guild <name>`  
**Other aliases:** `checkguild`

Show's the number of members the guild has and a list of their users.
It also shows whether the guild has a guildhall or not, and their funding date.

??? summary "Examples"
    **/guild Redd Alliance**  
    ![image](../assets/images/commands/guild.png)

----

### guild info
**Syntax:** `guild info <name>`  
**Other aliases:** `guild stats`

Shows basic information and stats about a guild.
        
It shows their description, homepage, guildhall, number of members and more.

??? summary "Examples"
    **/guild info Bald Dwarfs**  
    ![image](../assets/images/commands/guildinfo.png)

----

### guild members
**Syntax:** `guild members <name>`  
**Other aliases:** `guild list`

Shows a list of all guild members.

Online members have an icon next to their name.


??? summary "Examples"
    **/guild members Redd Alliance**  
    ![image](../assets/images/commands/guildmembers.png)

----

## highscores
**Syntax**: `highscores [world,category[,vocation]]`

Shows the entries in the highscores.
If the server is already tracking a world, there's no need to specify a world.
Available categories are: experience, magic, shielding, distance, sword, club, axe, fist and fishing.
Available vocations are: all, paladin, druid, sorcerer, knight.

??? summary "Examples"
    **/highscores**  
    ![image](../assets/images/commands/highscores1.png)  
    **/highscores shielding**  
    ![image](../assets/images/commands/highscores2.png)  
    **/highscores antica,magic,paladin**  
    ![image](../assets/images/commands/highscores3.png)

----

## house
**Syntax:** `house <name>[,world]`  
**Other aliases:** `guildhall`

Shows info for a house or guildhall.

By default, it shows the current status of a house for the current tracked world (if any).
If used on private messages, no world is looked up unless specified.

To specify a world, add the world at the end separated with a comma.

??? Summary "Examples"
    **/house darashia 8, flat 03**  
    ![image](../assets/images/commands/house_1.png)  
    **/house caveman shelter,calmera**  
    ![image](../assets/images/commands/house_2.png)

----

## levels
**Syntax:** `levels [player]`  
**Other aliases:** `levelups`

Shows a character's or everyone's recent level ups.
       
If a character is specified, it displays a list of its recent level ups.
If no character is specified, it will show the recent level ups of all registered characters in the server.

This only works for characters registered in the bots database, which are the characters owned
by the users of this discord server.

??? Summary "Examples"
    **/levels**  
    ![image](../assets/images/commands/levels_1.png)  
    **/levels Dre amz**  
    ![image](../assets/images/commands/levels_2.png)

----

### levels user
**Syntax:** `levels user <name>`  

Shows a user's recent level ups on their registered characters.

??? Summary "Examples"
    **/levels user Nezune**  
    ![image](../assets/images/commands/levels_user.png)

----

## news
**Syntax:** `news [id]`

Shows the latest news articles from Tibia.com.

If no id is supplied, a list of recent articles is shown, otherwise, a snippet of the article is shown.

??? Summary "Examples"
    **/news**    
    ![image](../assets/images/commands/news_1.png)  
    **/news 4400**  
    ![image](../assets/images/commands/news_2.png)

----

## searchworld
**Syntax:** `searchworld <name>[,world]` or `searchworld <level>[,world]` or `searchworld <min>,<max>[,world]`  
**Other aliases:** `whereworld`, `findworld`

Searches for online characters that meet the criteria.

There are 3 ways to use this command:

- Find a character in share range with another character. (`searchworld <name>`)
- Find a character in share range with a certain level. (`searchworld <level>`)
- Find a character in a level range. (`searchworld <min>,<max>`)

By default, the tracked world is searched, unless specified at the end of the parameters

You can add the world where you want to look in by adding a comma, followed by the name of the world.  
Example: `searchworld Cachero,Calmera`

??? Summary "Examples"
    **/searchworld Galarzaa Fidera**  
    ![image](../assets/images/commands/searchworld_1.png)  
    **/searchworld Nezune,Calmera**  
    ![image](../assets/images/commands/searchworld_2.png)  
    **/searchworld 600,700**  
    ![image](../assets/images/commands/searchworld_3.png)  
    **/searchworld 70**  
    ![image](../assets/images/commands/searchworld_4.png)

----

## share
**Syntax:** `share <level>` or `share <character>` or `share <char1, char2, ...>`  
**Other aliases:** `expshare`, `party`

Shows the sharing range for that level or character or list of characters.

This command can be used in three ways:

1. Find the share range of a certain level. (`share <level>`)
2. Find the share range of a character. (`share <name>`)
3. Find the joint share range of a group of characters. (`share <name1, name2...>`)

??? summary "Examples"
    **/share 300**  
    ![image](../assets/images/commands/share_1.png)  
    **/share Galarzaa Fidera**  
    ![image](../assets/images/commands/share_2.png)  
    **/share Galarzaa Fidera, Nezune, Xzilla**  
    ![image](../assets/images/commands/share_3.png)  
    **/share Galarzaa Fidera, Topheroo**  
    ![image](../assets/images/commands/share_4.png)

----

## stamina
**Syntax:** `stamina <current stamina>`

Tells you the time you have to wait to restore stamina.

To use it, you must provide your current stamina, in this format: `hh:mm`.
The bot will show the time needed to reach full stamina if you were to start sleeping now.

The footer text shows the time in your timezone where your stamina would be full.

??? Summary "Examples"
    **/stamina 39:00**  
    ![image](../assets/images/commands/stamina_1.png)  
    **/stamina 28:32**  
    ![image](../assets/images/commands/stamina_2.png)

----

## stats
**Syntax:** `stats <level>,<vocation` or `stats <character>`

Calculates character stats based on vocation and level.
        
Shows hitpoints, mana, capacity, total experience and experience to next level.

This command can be used in two ways:

1. To calculate the stats for a certain level and vocation. (`stats <level>,<vocation>`)
2. To calculate the stats of a character. (`stats <character>`)

??? Summary "Examples"
    **/stats 543,elder druid**  
    ![image](../assets/images/commands/stats_1.png)  
    **/stats Galarzaa Fidera**  
    ![image](../assets/images/commands/stats_2.png)

----

## timeline
**Syntax:** `timeline [character]`  
**Other aliases:** `story`

Shows a character's recent level ups and deaths. :flame: :fire:

If no character is provided, the timeline of all registered characters in the server will be shown.

Characters must be registered in order to see their timelines.

- 🌟 Indicates level ups
- 💀 Indicates deaths

??? Summary "Examples"
    **/timeline**  
    ![image](../assets/images/commands/timeline_1.png)  
    **/timeline Fila Bro**  
    ![image](../assets/images/commands/timeline_2.png)

----

### timeline user
**Syntax:** `timeline user <name>`

Shows a users's recent level ups and deaths on their characters.

??? Summary "Examples"
    **/timeline user Pepyto 🍌**  
    ![image](../assets/images/commands/timeline_user.png)

----

## time
**Other aliases:** `serversave`

Displays Tibia server's time and time until server save.

Server moderators can manage displayed timezones using the subcommands.

??? Summary "Examples" 
    **/time**  
    ![image](../assets/images/commands/time.png)

----

### time add
**Syntax:** `time add <timezone>`

Adds a new timezone to display.

You can look by city, country or region.  
Once the timezone is found, you can set the name you want to show on the `time` command.

Only Server Moderators can use this command.

??? Summary "Examples" 
    **/time add berlin**  
    ![image](../assets/images/commands/time_add.png)

----

### time list
Shows a list of all the currently added timezones.

Only Server Moderators can use this command.

??? Summary "Examples" 
    **/time list**  
    ![image](../assets/images/commands/time_list.png)

----

### time remove
**Syntax:** `time remove <timezone>`  
**Other aliases:** `time delete`

Removes a timezone from the list.

Only Server Moderators can use this command.

----

## whois
**Syntax:** `whois <character/user>`  
**Other aliases:** `check`, `char`, `character`

Shows a character's or a discord user's information.

If the parameter matches a discord user, it displays a list of the characters linked to that user.
If the parameter matches a character, it will display the character's info

If the character found is registered to a discord user, it will show the owner of the character.

Users can be looked through their username, user#discriminator or their user id.

Additionally, if the character is in the highscores, their ranking will be shown.

??? summary "Examples"
    **/whois Galarzaa Fidera**  
    ![image](../assets/images/commands/whois_1.png)  
    In this case, it matched *Galarzaa Fidera* to a character, and that character is registered to user @Galarzaa  
    **/whois Galarzaa**  
    ![image](../assets/images/commands/whois_2.png)  
    In this case, Galarzaa matches the discord user @Galarzaa, so a list of his registered characters is displayed.  
    However, it also matches the character *Galarzaa* which may not be necessarily related to the user.  
    **/whois Bichæo**  
    ![image](../assets/images/commands/whois_3.png)  
    In this case, the name only matches a user, and since no character was matched, their highest level registered character is shown.  
    **/whois 115042985778872322**
    ![image](../assets/images/commands/whois_4.png)      
    In this case, a user id was provided, and it searched for the user with that id.

----

## world
**Syntax:** `world <name>`

Shows basic information about a Tibia world.
        
Shows information like PvP type, online count, server location, vocation distribution, and more.

??? Summary "Examples"
    **/world Fidera**    
    ![image](../assets/images/commands/world_1.png)  
    **/world Ferobra**  
    ![image](../assets/images/commands/world_2.png)
 
----

## worlds
**Syntax:** `worlds [query]`

Shows a list of worlds.

You can pass a list of parameters separated by commas to change the sorting or filter worlds.

- `online` to sort by online count.
- `descending` to reverse the order.
- `europe`, `south america` or `north america` to filter by location.
- `optional pvp`, `open pvp`, `retro open pvp`, `hardcore pvp` or `retro hardcore pvp` to filter by pvp type.

??? Summary "Examples"
    **/worlds**  
    ![image](../assets/images/commands/worlds_1.png)  
    **/worlds northamerica,online,descending**  
    ![image](../assets/images/commands/worlds_2.png)  
    **/worlds southamerica,openpvp,online,descending**  
    ![image](../assets/images/commands/worlds_3.png)    