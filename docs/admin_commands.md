#/stalk
This is one of the most important admin commands. It's composed of various subcommands that let the admins manage the users database. **This command can only be used via private message.**

##/stalk add *username*
Registers discord user in the database.

##/stalk addacc *username*,*charname*
Registers a character and all other visible characters to an user in the database. Characters in worlds not specified in config are skipped.  
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
Registers a character to an user in the database.  
If the discord user wasn't previously registered, it gets automatically registered with this command.

###Example
>**/stalk addchar Kaiizokuo,Sogeking Imhi**  
>**Sogeking Imhi** was registered succesfully to this user.

##/stalk remove *username*
Removes a user from the database. Note that sometimes users that are no longer in the server can't be seen by the bot and can't be removed with this command.

##/stalk removechar *charactername*
Removes a character from the database.

##/stalk check
Shows a list of users on the server that aren't registed on the database or have no characters registered to them.

##/stalk refreshnames
When a user is registed, his discord username is saved. This command looks for users that have changed their names and updates them.

##/stalk purge
Performs a database cleanup. **This command is still experimental, it's recommended to create a backup in case undesirable results are obtained**.

1. Deletes users no longer in server.
2. Deletes characters belonging to users no longer registered.
3. Removes characters deleted.
4. Updates characters with name changes.
5. Removes users with no chars
