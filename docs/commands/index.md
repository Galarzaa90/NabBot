!!! note
    The information contained here refers to the `master` branch, it will be updated to `rewrite` documentation soon.


One of the main feature of discord bots is being able to respond to commands.
All commands require a prefix in order to be recognized and to avoid command triggering accidentally.

By default, the command prefix is `/`, this can be changed in the main file by changing `command_prefix`.

Commands can be used on any channel where the bot can read and write.
Some commands may require extra permissions such as `Embed Links` or `Attach Files`, or might not be allowed in private messages.
Some commands can show longer responses if used in `ask-channel` (by default, #ask-nabbot).

For descriptions of each command check the different commands sections in the sidebar.

## Paginator

Some commands responses feature a *paginator* ([based on Rapptz' paginator class](https://github.com/Rapptz/RoboDanny/blob/master/cogs/utils/paginator.py)). These can be easily spotted by the reactions automatically added to the reply (◀️▶️⏹️). These reactions act as buttons, letting you scroll through the results.

![Command with pagination](https://cloud.githubusercontent.com/assets/12865379/25454641/12eeba9a-2a82-11e7-8338-6a58d923b6c5.png)

When you click on one of the arrow reactions, the page is scrolled in that direction and your reaction is removed so you can use it again. Using the stop reaction removes the paginating interface. Only the user that used the command can turn the pages. Note that when used in private messages, the bot has no way of removing your reactions, so you must remove them and add it yourself again.