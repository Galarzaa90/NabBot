This commands can only be used by the server's owner and users with the `Manage Channels` permission.

!!! info
    Words in italics are parameters.  
    Parameters enclosed in brackets `[]` are optional.

## /makesay
**Syntax:** /makesay [*message*]

Makes the bot say a message. This command can be used in two ways.

If you use this command on any channel, NabBot will delete your original message and then repeat it itself.
Note that the bot requries `Manage Messages` permissions in that channel in order to use it effectively.

Bot owners can use this command on private messages in a more discrete way.
After using `/makesay Some message`, the bot will look for all the channels it shares with the command author, and where both can
send messages. The bot will display the list, numbering each channel.  
The command user must then respond with the number of the channel where they want NabBot to relay the message to.
Alternatively, they can cancel the operation replying with `0`. The bot will confirm that the message was delivered.

----

## /unregistered
Shows a list of discord users that have no registered characters.

??? Summary "Example"

    **/unregistered**  
    ![image](../assets/images/commands/unregistered.png)

----

## /ignore
**Syntax:** /ignore [*channel*]

Makes the bot ignore commands in a channel. This allows you to have a channel where the bot can still make announcements but
he won't respond to any commands.

If the command is used with no parameters, the current channel will be ignored, otherwise, the specified channel will be looked for.

Administrators can bypass this.

### /ignore list
Shows a list of the currently ignored channels in the server.


----

## /unignore
**Syntax:** /unignore [*channel*]

Makes the bot listen to commands in this channel again.

If the command is used with no parameters, the current channel will be unignored, otherwise, the specified channel will be looked for.

----
