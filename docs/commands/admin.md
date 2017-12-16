!!! note
    The information contained here refers to the `master` branch, it will be updated to `rewrite` documentation soon.


## /diagnose [*serverName*]

Checks the server and every channel's permissions to check if the bot has the needed permissions to work correctly. Also checks if the ask channel and server log channels are set correctly.

If no serverName is specified, it check's the current server. If a server name is specified, it checks the permissions for that server. Note that you must be the owner of the server in order to check. Bot owner can check any server the bot is in.  
The command can't be used without a server name on private messages.

Example:  
**/diagnose**  
![image](https://cloud.githubusercontent.com/assets/12865379/25505914/d9069f64-2b58-11e7-819a-7886cc23d853.png)

----

## /setworld [*world*]

Sets the tibia world this server will track. This lets users in this servers add their characters. If the command is used without a world, the bot will just say which world the server is currently tracking. If the command is used with a world, the bot will ask to confirm the change.

----

## /setmessage [*message*]

Sets the welcome message new users get when joining a server. By default all members receive the following message: 
****
Welcome to **Server Name**! I'm **Nab Bot**, to learn more about my commands type `/help`  
Start by telling me who is your Tibia character, say **/im *character_name*** so I can begin tracking your level ups and deaths!
****

This message can only be edited globally in `config.py`, however, this message can be extended for a specific server by using the command. Using the command with no parameters shows the current welcome message.

Example:  
After using and replying to confirmation messages of this command:  
**/setmessage** `Please take a moment to read <#244288371248201728>`  
`*Unidentified members will be kicked*`

New members will be greeted with the following message:
![image](https://cloud.githubusercontent.com/assets/12865379/25539145/a5632518-2bfa-11e7-90eb-0ff7f719ff31.png)

Note that you can use special formatting to show the current user's name, server name, etc.

## /setchannel [*channelName*]

By default, level up and death announcements are done on the server's default channel (usually called #general). However, if the server admin wants to change this channel to a different one, this command can be used. If the command is used with no parameter, it shows the currently set channel.

When setting a new channel, the bot will check if it has permission to write in there. If at some point the channel becomes deleted or unavailable to the bot in some way, it will keep doing announcements in the default channel again.

