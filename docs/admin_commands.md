#/stalk
This is one of the most important admin commands. It's composed of various subcommands that let the admins manage the users database.

##/stalk add *username*
Registers discord user in the database.

##/stalk addacc *username*,*charname*
Registers a character and all other visible characters to a user in the database. Characters in worlds not specified in config are skipped.  
If the discord user wasn't previously registered, it gets automatically registered with this command.

If a character is already registered to another user, the command does nothing.

###Example
>**/stalk addacc Galarzaa,Galarzaa Fidera**  
>**Galarzaa Fidera** was registered succesfully to this user.  
>**Don Heron** skipped, character not in server list.  
>**Galarzaa** skipped, character not in server list.  
>**Galarzaa Deathbringer** was registered succesfully to this user.  
>**Galarzaa Redd** was registered succesfully to this user.  
>**Galarzaa The Druid** was registered succesfully to this user.  
>**Lord de los Druidas** skipped, character not in server list.  
>**Sir Galarzaa** skipped, character not in server list.  
>**Sir Heron** skipped, character not in server list.  
>**@Galarzaa** was registered succesfully.

In this case, Fidera is the only world on the server list, so only characters from Fidera were registered.

##/stalk addchar *username*,*charname*

##/stalk remove *username*

##/stalk removechar *charactername*

##/stalk purge

##/stalk check

##/stalk refreshnames
