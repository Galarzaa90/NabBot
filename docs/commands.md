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

In this case, Galarzaa matches the discord user @Galarzaa, so a list of his registered characters is displayed. However, it also matches the character *Galarzaa* which may not be necessarily related to the user.

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

Shows the party experience share for a determined level. If a name is used as parameter, it retrieves the player's level and it uses that for the calculation.

####Example:
>/share 134<br>
>A level 197 can share experience with levels **131** to **295**.

>/share Galarzaa Fidera<br>
>**Galarzaa Fidera** (194) can share experience with levels **129* to **291**.

##/itemprice *name*
*Other aliases: /checkprice, /item

Shows the in-game look text of the item and a list of NPCs that buy and/or sell the item (only the best price is considered). If the list is too long and the command is on a server chat, it will reply with a summary of the npcs and send a private message to the user with the full list. If the command is used on a private message, the bot will always give the full list. When listing Rashid, it will display the current city he's in.

####Example:
>/item scarab shield<br>
>You see a scarab shield (Def:25). It weighs 47.00 oz.<br>
><br>
>**Scarab Shield** can't be bought from NPCs.<br>
><br>
>**Scarab Shield** can be sold for 2,000 gold coins to:<br>
>**Rashid** in *Liberty Bay*<br>
<br>
>/item spike sword<br>
>You see a spike sword (Atk:24, Def:21 +2). It weighs 50.00 oz. It can be enchanted with an element. <br>
><br>
>Spike Sword can be bought for 8,000 gold coins from:<br>
>    Flint in Rathleton<br>
>    Morpel in Yalahar<br>
>    Ulrik in Thais<br>
>    *And 18 others.*<br>
><br>
>Spike Sword can be sold for 1,000 gold coins to:<br>
>    Nah'Bob in Blue Djinn's Fortress<br>
><br>
>The list of NPCs was too long, so I PM'd you an extended version.<br>

##/deaths [*player*]
*Other aliases: /deathlist, /death

If a player is specified, it displays a list of that player's recent deaths. If no player is specified, it will show the recent deaths of all players registered in the database.

####Example:
>/deaths Galarzaa Fidera<br>
>Galarzaa Fidera recent deaths:<br>
>    Died at level *193* by a lizard high guard - *2 days ago*<br>
<br>
>/deaths<br>
>Latest deaths:<br>
>    Aeon on Fidera (**@Aeon**) - Died at level **117** by a vile grandmaster - *5 minutes ago*<br>
>    Adollo The Sorc (**@AdolloBAXWARsago**) - Died at level **74** by a hero - *22 hours ago*<br>
>    Joey Bandalo (**@joeybandalo**) - Died at level **161** by a hero - *1 day ago*<br>
>    Donna Marocas (**@Pepyto**) - Died at level **64** by an ice golem - *1 day ago*<br>

##/levels [*player*]
*Other aliases: /levelups, /lvl, /level, /lvls

If a player is specified, it displays a list of the player's recent level ups. If no player is specified, it will show the recent level ups of all players registered in the database.

####Example:
>/levels Galarzaa Fidera<br>
>**Galarzaa Fidera** latest level ups:<br>
>    Level **194** - *23 hours ago*<br>
>    Level **193** - *6 days ago*<br>
>    Level **192** - *8 days ago*<br>
>    Level **191** - *8 days ago*<br>
<br>
>/levels<br>
>Latest level ups:<br>
>    Level **69** - Travok Helljaw (**@pfoote**) - *2 hours ago*<br>
>    Level **35** - Wild Majinbuzz (**@MajinBuzz**) - *3 hours ago*<br>
>    Level **149** - Repimboca da Parafuzeta (**@Bicho Doente**) - *3 hours ago*<br>
>    Level **224** - Gixys (**@Gixys**) - 4 hours ago<br>
>    Level **228** - Perplexed Penguin (**@Penguin**) - *4 hours ago*<br>

##/stats *level,vocation*
##/blessings *level*
##/spell *name/words*
##/time##
