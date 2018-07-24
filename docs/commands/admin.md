# Admin commands
Commands for server owners and admins.  
Admins are members with the `Administrator` permission.

!!! info
    Parameters are enclosed with `< >`.   
    Optional parameters are enclosed in brackets `[]`.

## addaccount 
**Syntax:** `addaccount <user>,<character>`  
**Other aliases:** `addacc`

Register a character and all other visible characters to a discord user.

If a character is hidden, only that character will be added. Characters in other worlds are skipped.

----

## addchar
**Syntax:** `addchar <user>,<character>`  
**Other aliases:** `registerchar`

Registers a character to a user.

The character must be in the world you're tracking.
If the desired character is already assigned to someone else, the user must use `claim`.

----

## checkchannel
**Syntax:** `checkchannel [channel]`

Checks the channel's permissions.

Makes sure that the bot has all the required permissions to work properly.
If no channel is specified, the current one is checked.

??? Summary "Examples"
    **/checkchannel**  
    ![image](../assets/images/commands/checkchannel.png)

----

## removechar
**Syntax:** `removechar <name>`  
**Other aliases:** `deletechar`, `unregisterchar`

Note that you can only remove chars if they are from users exclusively in your server.
You can't remove any characters that would alter other servers NabBot is in.