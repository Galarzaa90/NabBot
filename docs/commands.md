# General commands  
## /roll *TdN*  
*Other aliases: /dice*

This command simply rolls a die with N-sides T-times.

#### Example:
>/roll 4d3  
>2, 2, 1, 2

A 3-sided die was rolled 4 times, giving those results.

---

## /choose [*option1 option2 ...optionN*]

This commands returns one of the options given selected randomly.

#### Example:
>/choose Red Blue Yellow<br>  
>Alright, **@Galarzaa**, I choose: "Yellow"

A simple choice was made randomly.

---

## /im *playerName*
*Other aliases: /iam, /i'm*

This command can only be used by new members joining the bot's discord server. When a user join, Nab Bot greets the user and asks him to use the command to add the user's characters for tracking. When the user replies with the command, the bot looks up the character and his other visible characters in the selected servers and registers them.

#### Example:
>Welcome @Galarzaa! Please tell us about yourself, who is your Tibia character?  
Say /im charactername and I'll begin tracking it for you!  
>/im Galarzaa Fidera  
>Thanks @Galarzaa! I have added the following character(s) to your account: Galarzaa Fidera, Galarzaa Redd.

Characters were identified and registered for that discord user.

---

## /online

Displays a list of the tibia characters registered to the bot that are currently online. It shows the character's name, level, vocation and the discord user that owns it.

#### Example:
>/online  
>The following discord users are online:  
    Knight Simbiotico (Lvl 122 EK, @Flue)  
    Galarzaa Fidera (Lvl 210 RP, @Galarzaa)  
    Repimboca da Parafuzeta (Lvl 192 EK, @Bicho Doente)  
    Malakhai (Lvl 104 ED, @Stark)  
    Perplexed Penguin (Lvl 237 ED, @Penguin)  
    Toph Ironman (Lvl 77 MS, @Christophersen)  
    Enchanter Andrew (Lvl 147 MS, @Emperor Andrew)  
    Ursinnet (Lvl 278 MS, @Ursinnet)  
    Donna Marocas (Lvl 126 RP, @Pepyto)  
    Mordekaiser Uno (Lvl 192 ED, @Hokusho)
    
---

## /about

Gives some information about the bot, such as uptime, number of registered users and characters.

#### Example:
>/about  
>Beep boop beep boop. I'm just a bot!  
    - Authors: @Galarzaa#8515, @Nezune#2269  
    - Platform: Python 🐍  
    - Created: March 30th 2016  
    - Uptime: 3 days, 23 hours, 46 minutes, and 0 seconds  
    - Tracked users: 84  
    - Tracked chars: 243

---

## /roles

Returns information about all roles in the Discord server, except @everyone and @NabBot

#### Example:
>/roles  
>These are the active roles for this server:  
>    Vice Leader  
>    Leader  
>    Redd Alliance  
>    Bald Dwarf  

---

## /role [*roleName*]

Returns information about members in a specific role in the Discord server.

#### Example:
>/role vice leader  
>These are the members from **Vice Leader**:  
>    Nezune  
>    kaiizokuo  
>    Booby  
>    Bicho Doente  
>    Crayola the Noob  
>    AdolloBAXWARsago  
>    Galarzaa  
>    Pepyto  
>    Ursinnet  

---

# Tibia commands
## /whois [*playerName/discordUser*]
*Other aliases: /check, /player, /checkplayer, /char, /character*

This commands has 2 functions:
* It retrieves and displays info about a Tibia character
* It retrieves the list of characters linked to a discord user

If the parameter matches a discord user, it displays a list of the characters linked to that user. If the parameter matches a character, it will display the character's info, such as level, vocation, guild, world, etc.

If the character found is registered to a discord user, it will show the owner of the character.

Both cases can match simultaneously.

#### Examples:
>/whois Galarzaa Fidera  
>**Galarzaa Fidera** is a character of **@Galarzaa**.  
>**Galarzaa Fidera** is a level 186 __Royal Paladin__. He resides in __Roshamuul__ in the world __Fidera__.  
>He is __Leader__ of the **Redd Alliance**.  

In this case, it matched *Galarzaa Fidera* to a character, and that character is registered to user @Galarzaa

>/whois Galarzaa  
>**@Galarzaa**'s characters are: Galarzaa Fidera (Lvl 186 RP), Galarzaa The Druid (Lvl 101 ED), Galarzaa Redd (Lvl 26 EK) and Galarzaa Deathbringer (Lvl 10 S).  
>The character **Galarzaa** is a level 25 __Knight__. He resides in __Venore__ in the world __Calmera__.

In this case, Galarzaa matches the discord user @Galarzaa, so a list of his registered characters is displayed. However, it also matches the character *Galarzaa* which may not be necessarily related to the user.

---

## /guild *guildname*
*Other aliases: /guildcheck, /checkguild*

Shows who's currently online in a guild.

#### Example:
>/guild Wanted  
>There are 9 players online in **Wanted**:  
>__Commander__  
>    Amylee Lynn (*Perigo*) -- 637 EK  
>    Jussandro (*Lindao*) -- 654 EK  
>    Kragon (*Fake*) -- 522 EK  
>    Poszukiwanyz (*Nuncafoi quinhentos*) -- 495 ED  
>__Reason__  
>    Dhanaro Eirax (*Jusz*) -- 616 ED  
>    Freeze Dead -- 571 MS  
>    Insane Desire -- 500 ED  
>    Matshow -- 424 RP  
>    Vinced -- 472 ED  

---

## /share *level/player*
*Other aliases: /expshare, /party*

Shows the party experience share for a determined level. If a name is used as parameter, it retrieves the player's level and it uses that for the calculation.

#### Example:
>/share 134  
>A level 197 can share experience with levels **131** to **295**.

>/share Galarzaa Fidera<br>
>**Galarzaa Fidera** (194) can share experience with levels **129** to **291**.

---

## /itemprice *name*
*Other aliases: /checkprice, /item*

Shows the in-game look text of the item and a list of NPCs that buy and/or sell the item (only the best price is considered). If the list is too long and the command is on a server chat, it will reply with a summary of the npcs and send a private message to the user with the full list. If the command is used on a private message, the bot will always give the full list. When listing Rashid, it will display the current city he's in.

#### Example:
>/item scarab shield  
>You see a scarab shield (Def:25). It weighs 47.00 oz.  
>**Scarab Shield** can't be bought from NPCs.  
>**Scarab Shield** can be sold for 2,000 gold coins to:  
>**Rashid** in *Liberty Bay*  

>/item spike sword  
>You see a spike sword (Atk:24, Def:21 +2). It weighs 50.00 oz. It can be enchanted with an element.  
>**Spike Sword** can be bought for 8,000 gold coins from:  
>    Flint in Rathleton  
>    Morpel in Yalahar  
>    Ulrik in Thais  
>    *And 18 others.*  
>**Spike Sword** can be sold for 1,000 gold coins to:  
>    Nah'Bob in Blue Djinn's Fortress  
>The list of NPCs was too long, so I PM'd you an extended version.

---

## /deaths [*player*]
*Other aliases: /deathlist, /death*

If a player is specified, it displays a list of that player's recent deaths. If no player is specified, it will show the recent deaths of all players registered in the database.

#### Example:
>/deaths Galarzaa Fidera  
>Galarzaa Fidera recent deaths:  
>    Died at level *193* by a lizard high guard - *2 days ago*  

>/deaths  
>Latest deaths:  
>    Aeon on Fidera (**@Aeon**) - Died at level **117** by a vile grandmaster - *5 minutes ago*  
>    Adollo The Sorc (**@AdolloBAXWARsago**) - Died at level **74** by a hero - *22 hours ago*  
>    Joey Bandalo (**@joeybandalo**) - Died at level **161** by a hero - *1 day ago*  
>    Donna Marocas (**@Pepyto**) - Died at level **64** by an ice golem - *1 day ago*

---

## /levels [*player*]
*Other aliases: /levelups, /lvl, /level, /lvls*

If a player is specified, it displays a list of the player's recent level ups. If no player is specified, it will show the recent level ups of all players registered in the database.

#### Example:
>/levels Galarzaa Fidera  
>**Galarzaa Fidera** latest level ups:  
>    Level **194** - *23 hours ago*  
>    Level **193** - *6 days ago*  
>    Level **192** - *8 days ago*  
>    Level **191** - *8 days ago*  

>/levels  
>Latest level ups:  
>    Level **69** - Travok Helljaw (**@pfoote**) - *2 hours ago*  
>    Level **35** - Wild Majinbuzz (**@MajinBuzz**) - *3 hours ago*  
>    Level **149** - Repimboca da Parafuzeta (**@Bicho Doente**) - *3 hours ago*  
>    Level **224** - Gixys (**@Gixys**) - 4 hours ago  
>    Level **228** - Perplexed Penguin (**@Penguin**) - *4 hours ago*  

---

## /stats [*level,vocation*]/[*charactername*]

Replies with the hitpoints, mana and capacity of a character with that level and vocation, or if a character's name was entered, it replies with it's stats.

#### Example
>/stats 50,ek  
>A level 50 knight has:  
>    815 HP  
>    300 MP  
>    1,520 Capacity  
	
>/stats Galarzaa Fidera  
> Galarzaa Fidera is a level 213 royal paladin, he has:  
>    2,235 HP  
>    3,165 MP  
>    4,570 Capacity  

>/stats mage,400  
A level 400 mage has:  
    2,145 HP  
    11,850 MP  
    4,390 Capacity  

---

## /blessings *level*
*Other aliases: /bless*

Replies with the cost of blessings for that level. For players over level 100, it will also display the cost of the Blessing of the Inquisition.

#### Example:
>/bless 110  
>At that level, you will pay **18,000** gold coins per blessing for a total of **90,000** gold coins.  
>Blessing of the Inquisition costs **99,000** gold coins.  

>/bless 90  
>At that level, you will pay 14,000 gold coins per blessing for a total of 70,000 gold coins.  

---

## /spell *name/words*

Replies with information on a certain spell.

---

## /time
*Other aliases: /serversave, /ss*

Displays the time in CipSoft's (CET/CEST), Brazil's and Mexico's timezones, the time until server save and Rashid's current city.

### Example:
>/time  
>It's currently **02:24** in Tibia's servers.  
>**21:24** in Brazil (Brasilia).  
>**17:24** in Mexico (Sonora).  
>Server save is in 7 hours and 35 minutes.  
>Rashid is in **Ankrahmun** today.  
