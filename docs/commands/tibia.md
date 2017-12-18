!!! note
    The information contained here refers to the `master` branch, it will be updated to `rewrite` documentation soon.

Command parameters are shown in italics, optional parameters are surrounded with `[ ]`

## /whois *playerName/discordUser*
*Other aliases: /check, /player, /checkplayer, /char, /character*

This commands has 2 functions:  

* It retrieves and displays info about a Tibia character
* It retrieves the list of characters linked to a discord user

If the parameter matches a discord user, it displays a list of the characters linked to that user.
If the parameter matches a character, it will display the character's info, such as level, vocation, guild, world, etc.

If the character found is registered to a discord user, it will show the owner of the character.

Discord users can be looked for through Usernames, User#Discriminator (i.e. `Galarzaa#8515`) or even user id.

Both cases can match simultaneously.

It also shows the character's corresponding highscore positions, however, this is only available for registered characters.

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
    
    In this case, the name only matches an user, and since no character was matched, their highest level registered character is shown.
    
    **/whois 115042985778872322**
    ![image](../assets/images/commands/whois_4.png)
    
    In this case, a user id was provided, and it searched for the user with that id.

---

## /guild *guildname*
*Other aliases: /guildcheck, /checkguild*

Show's the number of members a guild has, and a list of their online users.
It also shows whether the guild has a guildhall or not, and their founded date.

??? summary "Examples"

    **/guild Redd Alliance**  
    ![image](../assets/images/commands/guild.png)

---

## /guildmembers *guildname*
*Other aliases: /guildlist*

Shows a paginated list of all the members of a guild. If they are online, 🔹 is shown next to their name.

??? summary "Examples"
    
    **/guildmembers Redd Alliance**  
    ![image](../assets/images/commands/guildmembers.png)
    
---

## /guildinfo *guildname*
*Other aliases /guildstats*

Shows basic information about a guild, like their description, homepage, guildhall, number of members of members and more.

??? summary "Examples"
    
    **/guildmembers Bald Dwarfs**  
    ![image](../assets/images/commands/guildinfo.png)


## /share *level/player*
*Other aliases: /expshare, /party*

Shows the party experience share for a determined level. If a name is used as parameter, it retrieves the player's level and it uses that for the calculation.

Example:  
/share 300  
![image](https://cloud.githubusercontent.com/assets/12865379/25453759/042b2ee2-2a7f-11e7-8cdc-04677b62af42.png)

/share Galarzaa Fidera  
![image](https://cloud.githubusercontent.com/assets/12865379/25453790/19b6d982-2a7f-11e7-9180-dc8ecbee00e9.png)

---

## /itemprice *name*
*Other aliases: /checkprice, /item*

Shows the in-game look text of an item, a list of NPCs taht buy and/or sell it (only the best price is considered) and list of monsters that drop it with their approximate chance percentages. The embedded message's sidebar color shows if a major loot NPC buys it can be noticed at quick glance. Yellow for Rashid, Blue and Green for Djinns, and Purple for gems. When listing Rashid, it will show the city Rashid's currently in.

The answer given may be shortened to avoid spam in chats. For longer replies, the command must be used in the ask channel or via private message.

Example:  
/item dragon scale mail  
![image](https://cloud.githubusercontent.com/assets/12865379/25454236/9ac8d5d8-2a80-11e7-8e2e-372e8cbe6e57.png)

**When used on the ask-channel or private message**  
/item dragon scale mail  
![image](https://cloud.githubusercontent.com/assets/12865379/25454012/eaad2910-2a7f-11e7-82f2-3968a2b51f71.png)

---

## /deaths [*player*]
*Other aliases: /deathlist, /death*

If a player is specified, it displays a list of that player's recent deaths. If no player is specified, it will show the recent deaths of all players registered in the database. The number of entries shown per page is higher in ask channel and private channels.

Example:  
**/deaths Dozzle**  
![image](https://cloud.githubusercontent.com/assets/12865379/25454591/daf3047a-2a81-11e7-97c7-c8c160fc2b9d.png)

**/deaths**  
![image](https://cloud.githubusercontent.com/assets/12865379/25454641/12eeba9a-2a82-11e7-8338-6a58d923b6c5.png)

### Subcommand: /deaths monster [*name*]
*Other aliases: /deaths mob, /deaths killer*

Shows recent deaths by a specific monster or killer.

Example:  
**/deaths mob Lloyd**  
![image](https://cloud.githubusercontent.com/assets/12865379/25454867/b690f1fe-2a82-11e7-8273-3d3aff9bbd16.png)

### Subcommand: /deaths user *name*

Shows recent deaths by all characters registered to a user.

Example:  
**/deaths user Dozzle**  
![image](https://cloud.githubusercontent.com/assets/12865379/25455263/fd89616c-2a83-11e7-8aee-510e74a4f9d8.png)

---

## /levels [*player*]
*Other aliases: /levelups, /lvl, /level, /lvls*

If a player is specified, it displays a list of the player's recent level ups. If no player is specified, it will show the recent level ups of all players registered in the database. 

Example:  
**/levels Nezune**  
![image](https://cloud.githubusercontent.com/assets/12865379/25455727/b33c45c8-2a85-11e7-8761-04e1752f6377.png)


**/levels**  
![image](https://cloud.githubusercontent.com/assets/12865379/25455708/a94045c4-2a85-11e7-81c2-295273c4b6ed.png)

### Subcommand: /levels user *name*

Shows recent levels by all characters registered to a user.

Example:  
**/levels user Dozzle**  
![image](https://cloud.githubusercontent.com/assets/12865379/25456010/86f80f64-2a86-11e7-9337-9258eb77e80d.png)

---

## /stats *level,vocation*/*charactername*

Replies with the hitpoints, mana, capacity, total experience and experience to next level (at 0% progress) of a character with that level and vocation, or if a character's name was entered, it replies with its stats.

Example:  
**/stats 543,elder druid**  
![image](https://cloud.githubusercontent.com/assets/12865379/25456403/b1c0814e-2a87-11e7-8925-acbd824bde67.png)
	
**/stats Galarzaa Fidera**  
![image](https://cloud.githubusercontent.com/assets/12865379/25456342/7813c88e-2a87-11e7-8e8b-b22be04c9efb.png)


## /find vocation,charname/vocation,level/vocation,minlevel,maxlevel
*Other aliases: /findteam, /whereteam, /searchteam, /search*

This commands finds registered characters with the desired vocation and in the desired level. There's three ways to use the command. The results show the name, vocation and level of each character, along with the username of the owner. A 🔹 next to a name indicates the character is currently online. Full vocation names and abbreviations are allowed.

**/find vocation,charname**  
Lists all characters of said vocation that are in share range with the character matching the name used.

Example:  
**/find ek,Pepyto**  
![image](https://cloud.githubusercontent.com/assets/12865379/25460463/77c59ebe-2a98-11e7-9756-6d783888bc56.png)

**/find vocation,level**

Lists all characters of said vocation that can share with someone of said level.


Example:  
**/find sorcerer,120**  
![image](https://cloud.githubusercontent.com/assets/12865379/25460511/b1030f4a-2a98-11e7-8238-911be2635f09.png)

**/find vocation,minlevel,maxlevel**

Lists all characters of said vocation with a level between the specified levels.

Example:  
**/find pally,220,260**  
![image](https://cloud.githubusercontent.com/assets/12865379/25460573/1e94e7b8-2a99-11e7-85f8-9b5068d81093.png)

---

## /blessings *level*
*Other aliases: /bless*

Replies with the cost of blessings for that level. For players over level 100, it will also display the cost of the Blessing of the Inquisition.

Example:  
**/bless 110**  
![image](https://cloud.githubusercontent.com/assets/12865379/25456656/60a99376-2a88-11e7-8dff-0c915253b01a.png)

**/bless 90**  
![image](https://cloud.githubusercontent.com/assets/12865379/25456667/65555360-2a88-11e7-9ff7-9e82c12a3958.png)

---

## /spell *name/words*

Replies with information on a certain spell like level, vocation(s) required, level required, cost and NPCs that sell it. Information given is shorter unless it's used in the ask channel or private messages.

Example:  
**/spell ice strike**  
![image](https://cloud.githubusercontent.com/assets/12865379/25456795/ccb9e534-2a88-11e7-9cf2-d49c77648137.png)

**/spell exevo gran mas vis**  
![image](https://cloud.githubusercontent.com/assets/12865379/25457018/a098ecce-2a89-11e7-85da-0ef2c64ef9ff.png)

---

## /monster name
*Other aliases: /mob, /creature, /mon*

Displays information about a specific creature.

Example:   
**/monster Demon** *On a regular channel*  
![image](https://cloud.githubusercontent.com/assets/12865379/25457099/f1d97b62-2a89-11e7-992d-7115e3f0d7a0.png)

**/monster Demon** *On an ask channel or private message*  
![image](https://cloud.githubusercontent.com/assets/12865379/25457180/30f37aa0-2a8a-11e7-8d56-7000167a29bc.png)  
(*The bottom of the image has been cropped*)

----

## /house *name**
*Other aliases: /houses, /guildhall, /gh*

Displays information about a house, including a picture of the a section of the map where it is located. It shows the current status of the house in the world the current discord server is tracking.

Example:  
**/house darashia 8, flat 03**  
![image](https://user-images.githubusercontent.com/12865379/32842320-0091f7de-c9da-11e7-9d43-dfeeced54dbe.png)

----

## /achievements
*Other aliases: /achiev*

Shows information about an achievement. Spoiler info is shown only on ask channels or private messages.

Example:  
**/achievement demonic barkeeper**  
![image](https://cloud.githubusercontent.com/assets/12865379/25457881/a50d2920-2a8c-11e7-8704-968808abdd14.png)

----

## /time
*Other aliases: /serversave, /ss*

Displays the time in CipSoft's (CET/CEST), Brazil's and Mexico's timezones, the time until server save and Rashid's current city.

Example:  
**/time**  
![image](https://cloud.githubusercontent.com/assets/12865379/25457387/f4874a3c-2a8a-11e7-8e25-98203135c530.png)

----

## /loot

Scans an image of a container looking for Tibia items and shows an approximate loot value. An image must be attached with the message. The prices used are NPC prices only, images from the flash client don't work

The image requires the following:
- Must be a screenshot of inventory windows (backpacks, depots, etc).
- Have the original size, the image can't be scaled up or down, however it can be cropped.
- Use the regular client, flash client is not supported.
- The image must show the complete slot.
- JPG images are usually not recognized, and PNG images with low compression settings take longer to be scanned or aren't detected at all.

The bot shows the total loot value calculated and a list of the items detected, separated into the NPC that buy them.

### Subcommand: /loot legend

Shows a legend indicating what the overlayed icons on items mean.