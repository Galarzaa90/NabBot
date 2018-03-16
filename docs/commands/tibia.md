Commands related to Tibia, specially commands related to tibia.com

!!! info
    Words in italics are parameters.  
    Parameters enclosed in brackets `[]` are optional.


## /whois
**Syntax:** /whois *playerName/discordUser*  
**Other aliases:** /check, /player, /checkplayer, /char, /character

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

## /guild
**Syntax:** /guild *guildname*  
**Other aliases:** /guildcheck, /checkguild

Show's the number of members a guild has, and a list of their online users.
It also shows whether the guild has a guildhall or not, and their founded date.

??? summary "Examples"

    **/guild Redd Alliance**  
    ![image](../assets/images/commands/guild.png)

---

### /guild members
**Syntax:** /guild *guildname*  
**Other aliases:** /guild list

Shows a paginated list of all the members of a guild. If they are online, 🔹 is shown next to their name.

??? summary "Examples"
    
    **/guild members Redd Alliance**  
    ![image](../assets/images/commands/guildmembers.png)
    
---

### /guild info
**Syntax:** /guild info *guildname*  
**Other aliases:** /guild stats

Shows basic information about a guild, like their description, homepage, guildhall, number of members of members and more.

??? summary "Examples"
    
    **/guild info Bald Dwarfs**  
    ![image](../assets/images/commands/guildinfo.png)


## /share
**Syntax:** /share *level/player*  
**Other aliases:** /expshare, /party

There's three different ways to use this command:

1. Providing a single number, shows the share range of a character of that level.
1. Providing a charater name, shows the share range of that character.
1. Providing up to 5 character names, separated with commas, shows if they are able to share.

??? summary "Examples"

    **/share 300**  
    ![image](../assets/images/commands/share_1.png)
    
    **/share Galarzaa Fidera**  
    ![image](../assets/images/commands/share_2.png)
    
    **/share Galarzaa Fidera, Nezune, Xzilla**  
    ![image](../assets/images/commands/share_3.png)
    
    **/share Galarzaa Fidera, Topheroo**  
    ![image](../assets/images/commands/share_4.png)

---

## /deaths
**Syntax:** /deaths [*player*]  
**Other aliases:** /deathlist, /death

If a player is specified, it displays a list of that player's recent deaths. 
If no player is specified, it will show the recent deaths of all players registered in the database. 
The number of entries shown per page is higher in ask channel and private channels.

??? Summary "Examples"
      
    **/deaths Xzilla**  
    ![image](../assets/images/commands/deaths_1.png)
    
    **/deaths**  
    ![image](../assets/images/commands/deaths_2.png)

### /deaths monster
**Syntax:** /deaths monster *name*  
**Other aliases:** /deaths mob, /deaths killer

Shows recent deaths by a specific monster or killer.

??? Summary "Example"
  
    **/deaths mob Lloyd**  
    ![image](../assets/images/commands/deaths_mob.png)

### /deaths user
**Syntax:** /death user *name*

Shows recent deaths by all characters registered to a user.

??? Summary "Example"
    
    **/deaths user Nezune**  
    ![image](../assets/images/commands/deaths_user.png)

---

## /levels
**Syntax:** /levels [*player*]  
**Other aliases:** /levelups, /lvl, /level, /lvls

If a player is specified, it displays a list of the player's recent level ups.
If no player is specified, it will show the recent level ups of all players registered in the database.

??? Summary "Examples"

    **/levels**  
    ![image](../assets/images/commands/levels_1.png)
    
    **/levels Dre amz**  
    ![image](../assets/images/commands/levels_2.png)



### /levels user
**Syntax:** /levels user *name*  

Shows recent levels by all characters registered to a user.

??? Summary "Examples"
    
    **/levels user Nezune**  
    ![image](../assets/images/commands/levels_user.png)

---

## /timeline
**Syntax:** /timeline [*player*]  
**Other aliases:** /story

Shows recent levels and deaths by all registered characters.
If a character name is provided, their level ups and deaths are shown. 

* 🌟 Indicates level ups
* 💀 Indicates deaths

??? Summary "Examples"
    
    **/timeline**  
    ![image](../assets/images/commands/timeline_1.png)
    
    **/timeline Fila Bro**  
    ![image](../assets/images/commands/timeline_2.png)

---

### /timeline
**Syntax:** /timeline user *name*

Shows recent levels and deaths by all characters registed to the user.

??? Summary "Examples"
    
    **/timeline user Pepyto 🍌**  
    ![image](../assets/images/commands/timeline_user.png)

---

## /stats
**Syntax:** /stats *level,vocation*/*charactername*

Replies with the hitpoints, mana, capacity, total experience and experience to next level (at 0% progress) 
of a character with that level and vocation, or if a character's name was entered, it replies with its stats.

??? Summary "Examples"
      
    **/stats 543,elder druid**  
    ![image](../assets/images/commands/stats_1.png)
        
    **/stats Galarzaa Fidera**  
    ![image](../assets/images/commands/stats_2.png)


## /findteam
**Syntax:** /findteam *char/level/minlevel*,*maxlevel*  
**Other aliases:** /whereteam, /searchteam, /team

This commands finds registered characters with the desired levels.
Vocations can be filtered using the reaction buttons.

There's three ways to use the command:

1. Provide a character's name, shows a list of characters in share range. (`/findteam char`)
1. Provide a level, shows a list of characters in share range with that level. (`/findteam level`)
1. Provide two levels, shows a list of characters in that level range. (`/findteam min,max`)

Online characters are shown first on the list, they also have a 🔹 icon.

??? Summary "Examples"
    
    **/findteam Galarzaa Fidera**  
    ![image](../assets/images/commands/findteam_1.png)
    
    **/findteam 234**  
    ![image](../assets/images/commands/findteam_2.png)
    
    **/findteam 100,120**  
    ![image](../assets/images/commands/findteam_3.png)

---

## /world
**Syntax:** /world *name*

Displays information about a world like pvp type, online count, location and more.

??? Summary "Examples"
    
    **/world Fidera**    
    ![image](../assets/images/commands/world_1.png)
    
    **/world Ferobra**  
    ![image](../assets/images/commands/world_2.png)

 
---

## news
**Syntax:** news [*article_id*]

Displays a list of recent news and articles. Or if an article id is provided, a summary of that article is displayed.

If the command is used on the ask channel or in private, the list or summary displayed will be longer.

??? Summary "Examples"

    **/news**    
    ![image](../assets/images/commands/news_1.png)
    
    **/news 4400**  
    ![image](../assets/images/commands/news_2.png)




## /house
**Syntax:** /house *name*[/*world*]  
**Other aliases:** /houses, /guildhall, /gh

Displays information about a house, including a picture of the a section of the map where it is located.
It shows the current status of the house in the world the current discord server is tracking.

To specify a different world, add the world after a slash `/`

??? Summary "Examples"
    
    **/house darashia 8, flat 03**  
    ![image](../assets/images/commands/house_1.png)
      
    **/house caveman shelter/calmera**  
    ![image](../assets/images/commands/house_2.png)

----

## /blessings
**Syntax:** /blessings *level*  
**Other aliases:** /bless

Replies with the cost of blessings for that level.
For players over level 100, it will also display the cost of the Blessing of the Inquisition.

??? Summary "Examples"
  
    **/bless 90**  
    ![image](../assets/images/commands/bless_1.png)
    
    **/bless 140**  
    ![image](../assets/images/commands/bless_2.png)


----

## /time
**Other aliases:** /serversave, /ss

Displays the time in CipSoft's (CET/CEST), Brazil's and Mexico's timezones, the time until server save and Rashid's current city.

??? Summary "Examples"
    
    **/time**  
    ![image](../assets/images/commands/time.png)
