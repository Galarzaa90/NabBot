# Permissions

When the bot is first added to a server, a role is created with the permissions defined in the invite link.
To operate correctly, the bot needs the following permissions.

## Required permissions
### Read Messages
This permission is needed for obvious reasons. If the bot can't read messages, it can't respond to commands.
If this permission is not set for a channel, the bot won't even appear on the online list on that channel.
This permission can be denied for specific channel if you don't want it to be on that channel. If this permission is denied, all other permissions are considered denied automatically.

### Send Messages
An obligatory permission. The bot needs this to be able to respond to commands and make announcements.

### Add Reactions
This permission is needed in order for command pagination to work.

### Read Message History
Due to a Discord API limitation, the bot must be able to read message history in order to be able to know when a message has been reacted to in paginating commands.

### Manage Messages
This permission lets the bot delete other people messages and reactions.
This is used for the ask channel so the bot can remove messages that are not commands.
This is also needed for command pagination so the bot can remove the user's reaction so they can react again easily.

### Embed Links
Many commands feature Discord embeds.
These are rich format replies that allow the use of masked links, thumbnails, time stamps, fields, etcetera.
Denying this permission makes such commands stop working.

### Use External Emojis
This permission is needed for NabBot to be able to display its custom emojis.

## Recommended permissions
### Attach Files
This permission allows the bot to attach files as part of the message.
Some commands like `/item`, `/monster` and `/house` display a related image.
Disabling this permission won't break those commands functionality but images won't be shown anymore.

### View Audit Log
It lets the bot check the audit log for more information when a member leaves, is banned or changes nickname.
With this, the bot is able to tell if a member was kicked or left the server on his own, or if they updated their nickname or someone edited it for them.

This is only relevant for servers that have a `#server-log` channel.

### Manage Channels
This permission is only needed if you're using the watched-list feature. It lets the bot create the channel and update it's status.

### Manage Roles
This permission is only needed if want to use groups (joinable roles) and automatic roles.

