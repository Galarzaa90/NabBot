# Tracking commands

Commands related to NabBot's tracking functions.

!!! info
    Words in italics are parameters.  
    Parameters enclosed in brackets `[]` are optional.


## /im
**Syntax:** /im *characterName*

The bot scans the character and other characters on the account and registers them to the user.
Registered characters have their deaths and level ups announced on the chat.

The bot will skip characters on different worlds than the world the discord server tracks.
Also, if it finds a character owned by another user, the whole process will be stopped.

If a character is already registered to someone else, [/claim](#claim) can be used.

??? Summary "Example"

    **/im Elf**  
    ![image](../assets/images/commands/im.png)

----

## /imnot
**Syntax:** /imnot *characterName*  

Unregisters a character you previously registered.

??? Summary "Example"
  
    **/imnot tomas haake**  
    ![image](../assets/images/commands/imnot.png)

----

## /claim
**Syntax:** /claim *characterName*

Claims a character as yours, even if it is already registered to someone else.

In order for this to work, you have to put a special code in the character's comment.
You can see this code by using the command with no parameters. The code looks like this: `/NB-23FC13AC7400000/`

Once you had set the code, you can use the command with that character, if the code matches, it will be reassigned to you.
Note that it may take some time for the code to be visible to NabBot because of caching.

This code is unique for your discord user, so the code will only work for your discord account and no one else.
No one can claim a character of yours unless you put **their** code on your character's comment.

----

## /online

Shows a list of tracked characters that are online, along with their level, vocation and owner.

The list is shown with pages and vocation filter.

??? Summary "Example"
  
    **/online**  
    ![image](../assets/images/commands/online.png)

----

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

## /watched
**Syntax:** /watched  *[name]*  
**Other aliases:** /watchlist, /hunted, /huntedlist

Creates a new text channel for the watched list to be posted. The watch list shows which characters from it are online.
Entire guilds can be added too.

If no name is specified, the default name `#hunted-list` will be used.

When the channel is created, only NabBot and people with `Administrator` permissions can read it.
You can change the permissions to whatever you see fit afterwards.

The channel may be renamed at anytime without problems. But if it's deleted, it must be created again using the command.

??? Summary "Examples"
  
    **/watched**  
    ![image](../assets/images/commands/watched.png)
    
    **Initial message shown in the channel**
    ![image](../assets/images/commands/watched_message_1.png)
    
    **Message once characters and/or guilds have been added**
    ![image](../assets/images/commands/watched_message_2.png)

----

### /watched add
**Syntax:** /watched  *name*  
**Other aliases:** /watched addplayer, /watched addchar

Adds a character to the character list. The character must be in the same world the server is tracking.

The bot asks for confirmation before adding, by using emoji reactions: 🇾/🇳.

??? Summary "Examples"
  
    **/watched add Galarzaa Fidera**  
    ![image](../assets/images/commands/watched_add.png)
    
----

### /watched remove
**Syntax:** /watched remove *name*  
**Other aliases:** /watched removeplayer, /watched removechar

Removes a character from the watched list.

The bot asks for confirmation before adding, by using emoji reactions: 🇾/🇳.

??? Summary "Examples"
  
    **/watched remove Kaiizokuo**  
    ![image](../assets/images/commands/watched_remove.png)
    
    
### /watched addguild
**Syntax:** /watched addguild *name*

Adds a guild to the watched list. Every online members will be listed on the list.


The bot asks for confirmation before adding, by using emoji reactions: 🇾/🇳.

??? Summary "Examples"
  
    **/watched addguild Redd Alliance**  
    ![image](../assets/images/commands/watched_addguild.png)

----
    
### /watched removeguild
**Syntax**:  /watched *name*

Removes a guild from the watched list.

The bot asks for confirmation before adding, by using emoji reactions: 🇾/🇳.

??? Summary "Examples"
  
    **/watched removeguild Redd Alliance**  
    ![image](../assets/images/commands/watched_removeguild.png)

----
    
### /watched list

Shows a list of all characters currently in the list.

??? Summary "Examples"
  
    **/watched list**  
    ![image](../assets/images/commands/watched_list.png)

----
    
### /watched guildlist
**Other aliases:** /watched guilds, /watched listguilds

Shows a list of all guilds currently in the list.

??? Summary "Examples"
  
    **/watched guildlist**  
    ![image](../assets/images/commands/watched_guilds.png)
    
