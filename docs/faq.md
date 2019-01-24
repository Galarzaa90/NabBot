# FAQ
## General
### Why is `im` not working? NabBot gives no answer.
In order for `im` to work, you need to first configure a world for yor server. This can be done using the command `settings world`.

For the moment, only one world can be configured per server.

### How do I invite NabBot to my server?
For an always up to date invite link, go to [Discord Bots](https://discordbots.org/bot/178966653982212096) and click **Invite**.  
Also, if you like NabBot, don't forget to vote for us!

### \_\_\_\_\_\_\_\_\_\_ doesn't look well or doesn't work on mobile
The Android and iOS versions of Discord are really behind the web or standalone client, so NabBot is focused on desktop users.
If we limit ourselves to the mobile versions we would be slowing down the development of NabBot.

### Why does \_\_\_\_\_\_\_\_ command shows scrambled text when switching pages?
This is a discord bug that has been present for a while. Only happens on desktop.
If text looks scrambled, you can switch to another channel and switch back and the content will be fixed.

### Why am I not seeing deaths and level ups for characters in the watched list?
Only characters registered through im get their level ups and deaths tracked.

For the moment, the watch list is only to display their online status in the game.

## Self Hosting

!!! note
    In order to run and manage NabBot, basic knowledge of Python is expected.

### I can't run NabBot, python is not found.
If you get an error like this: `“python” is not recognized as an internal or external command, operable program or batch file.`, it can be due to one of these reasons:
* Python is not installed. To install visit [Python.org](https://www.python.org/)
* The python folder is not in the `PATH` enviroment variable. This is prompted when installing Python.

### My world is getting merged, what do I do?
NabBot can't detect world merges, so you have to run the `/merge` command to change all content of the old world to the new one:

### Someone got a namechange, what now?
Name changes are automatically updated by NabBot, so nothing needs to be done here, the character will be updated automatically the first time he is checked.

Namelocks are more complicated.

### What do I do with namelocked characters?
Because of the way namelocks work, all references lost to the old name are completely gone on tibia.com, so it's 
nearly impossible to detect this change, resulting in people just registering their new character and ending with duplicates.

To fix this, a server administrator can use the namelock command:

```
/namelock Oldname,Newname
```

If new name was already registered again, this will merge both character entries into one.
Otherwise, it will just rename Oldname to new name.

Since there's no way to check this, this should be done with care. The only thing that NabBot can verify is that their vocations match.


```
/merge Fidera Gladera
```

This will tell the bot that **Fidera** has merged into **Gladera**, changing all references of Fidera to Gladera.
Note that this change be irreversible, so this must be used under your own risk.

It's recommended to do this right after the server save that will merge the worlds.

## Miscellaneous
### Can you help me or make a cavebot/macro?
**No.**

### How can I make NabBot work for this OT server?
NabBot was made to work specifically for Tibia, it depends completely on the layout of Tibia.com so even if the URLs were changed to an OT's website, the code used to parse information would have to be changed.

However, if you're an OT owner, an API could be easily developed to let NabBot extract information more efficiently and even show a lot of extra information that is not available in Tibia.com
