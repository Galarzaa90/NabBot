!!! note
    The information contained here refers to the `master` branch, it will be updated to `rewrite` documentation soon.


All commands can only be run by user in the `owner_ids` list.

Command parameters are shown in italics, optional parameters are surrounded with `[ ]`

## /restart
*Other aliases: /reload, /reset*

Completely restarts the bot, reloading all files.

----

## /debug *code*

Evaluates Python code. This command can be used to run python command and get the response as a reply.

Example:  
**/debug bot.get_member("162060569803751424")**  
![image](https://cloud.githubusercontent.com/assets/12865379/25505280/f547a16c-2b55-11e7-9313-b74b4caa14af.png)

----

## /servers

Shows a list of servers where the bot is in, along with their owners and tracked world.

![image](https://cloud.githubusercontent.com/assets/12865379/25505351/39557618-2b56-11e7-8c80-950648772211.png)

----

## /admins_message [*message*]
*Other aliases: /message_admins, /adminsmessage, /msgadmins, /adminsmsg*

Sends a private message to all the server owners of the servers the bot is. If no message is specified at first, the command will prompt the user to enter a message to send.

Messages contain a signature to indicate who wrote the message.

