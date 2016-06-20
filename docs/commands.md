# General commands
##/roll
##/choose
##/im
##/online
##/about
##/makesay
##/stalk

# Tibia commands
##/whois *playerName/discordUser*
*Other aliases: /check, /player, /checkplayer, /char, /character*

This commands has 2 functions:
* It retrieves and displays info about a Tibia character
* It retrieves the list of characters linked to a discord user

If the parameter matches a discord user, it displays a list of the characters linked to that user. If the parameter matches a character, it will display the character's info, such as level, vocation, guild, world, etc.

If the character found is registered to a discord user, it will show the owner of the character.

Both cases can match simultaneously.


####Example:
>/whois Galarzaa Fidera<br>
>**Galarzaa Fidera** is a character of **@Galarzaa**.<br>
>**Galarzaa Fidera** is a level 186 __Royal Paladin__. He resides in __Roshamuul__ in the world __Fidera__.<br>
>He is __Leader__ of the **Redd Alliance**.<br>

In this case, it matched *Galarzaa Fidera* to a character, and that character is registered to user @Galarzaa

>/whois Galarzaa<br>
>**@Galarzaa**'s characters are: Galarzaa Fidera (Lvl 186 RP), Galarzaa The Druid (Lvl 101 ED), Galarzaa Redd (Lvl 26 EK) and Galarzaa Deathbringer (Lvl 10 S).<br>
>The character **Galarzaa** is a level 25 __Knight__. He resides in __Venore__ in the world __Calmera__.

In this case, Galarzaa matches the discord user @Galarzaa, so a list of his registered characters is displayed. However, it also matches the character *Galarzaa* which is may not be necessarily related to the user.

##/guild *guildname*
*Other aliases: /guildcheck

Shows who's currently online in a guild.

####Example:
>/guild Wanted<br>
>There are 9 players online in **Wanted**:<br>
>__Commander__<br>
>    Amylee Lynn (*Perigo*) -- 637 EK<br>
>    Jussandro (*Lindao*) -- 654 EK<br>
>    Kragon (*Fake*) -- 522 EK<br>
>    Poszukiwanyz (*Nuncafoi quinhentos*) -- 495 ED<br>
>__Reason__<br>
>    Dhanaro Eirax (*Jusz*) -- 616 ED<br>
>    Freeze Dead -- 571 MS<br>
>    Insane Desire -- 500 ED<br>
>    Matshow -- 424 RP<br>
>    Vinced -- 472 ED<br>

##/share *level/player*
*Other aliases: /expshare, /party*

It shows the party experience share for a determined level. If a name is used as parameter, it retrieves the player's level and it uses that for the calculation.

##/itemprice *name*
##/deaths *player*
##/levels [*player*]
##/stats *level,vocation*
##/blessings *level*
##/spell *name/words*
##/time##
