# Mod commands

Commands server moderators.

!!! info
    Parameters are enclosed with `< >`.   
    Optional parameters are enclosed in brackets `[]`.

## ignore
**Syntax:** `ignore [channel]`

Makes the bot ignore a channel

Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

If the parameter is used with no parameters, it ignores the current channel.

Note that server administrators can bypass this.

----

### ignore list
Shows a list of ignored channels.

----

## makesay
**Syntax:** `makesay <message>`

Makes the bot say a message.
 
If it's used directly on a text channel, the bot will delete the command's message and repeat it itself.  
Note that deleting the message requires `Manage Messages` permissions in the channel.

If it's used on a private message, the bot will ask on which channel he should say the message.  
Each channel in the list is numerated, by choosing a number, the message will be sent in the chosen channel.

----

## unignore
**Syntax:** `unignore [channel]`

Unignores a channel.

If no channel is provided, the current channel will be unignored.

Ignored channels don't process commands. However, the bot may still announce deaths and level ups if needed.

If the parameter is used with no parameters, it unignores the current channel.

----

## unregistered
Shows a list of users with no registered characters.

??? Summary "Example"
    **/unregistered**  
    ![image](../assets/images/commands/unregistered.png)

----
