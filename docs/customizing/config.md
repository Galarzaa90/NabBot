path: tree/master/data
source: config_template.yml

# Configuration
Some aspects of NabBot can be customized using its `config.yml` file.
This file is generated on the first startup, based on the template found in `data/config_template.yml`.
On every startup, the config file is checked and it notifies via console if any key is missing or there's a key not supported.

If a key is missing, a default value is taken, so the bot is still able to function without trouble.

If there's an extra key found, this can mean that a previous configuration entry was removed or a typo was made.

The correct structure can always be found in `config_template.yml`.

## Channels
```yaml
ask_channel_name: ask-nabbot
ask_channel_delete: true
log_channel_name: server-log
```

Specifies the names of NabBot's special channels. The ask channel is a special channel where NabBot will give longer replies.
This is used to reduce spam in main channels by keeping responses short.

The `ask_channel_delete` key specifies if messages that are not commands in the ask channel should be deleted or not.
This way you can keep #ask-nabbot as a commands only channel.

The log channel is a special channel where NabBot posts server events such as members joining, leaving or getting banned.
The bot will announce the following events here:

- A new member joined, with a list of their previously registered characters, if available
- A member left or was kicked (if the bot has `View Audit Log` permission, it can tell the difference)
- A member was banned
- A member changed his name or nick.
- A member registered or unregistered characters.
- The server's name was changed
- The server's region was changed.

## Command prefix
```yaml
command_prefix:
  - "/"
command_mention: false
```

The prefix for commands that the bot will use. By default, the bot will listen to commands like: `/about`, `/help`.
The prefix `/` can be changed, or even more prefixes can be added like:

```yaml
command_prefix:
  - "/"
  - "$"
```

So the bot would now also answer to `$about` and `$help`.  
Note that the bot will always answering by being mentioned, e.g. `@NabBot help`, `@NabBot about`.

It's recommended to keep this list as short as possible, and to make sure it does not overlap with the command prefix of other bots.

This setting can be overriden on a per-server basis by using the command [settings](../commands/settings.md#settings-prefix)
    
## Extra cogs
For more information, see [Cogs](cogs.md)

```yaml
# Add extra features by adding your own cogs.
extra_cogs: []
```

## Welcome PM
When a member joins a server, he is greeted via private message with a message. This can be customized:
```yaml
# The welcome message that is sent to members when they join a discord server with NabBot in it
# The following keyboards can be used:
# {user.name} - The joining user's name
# {user.mention} - The joining user's mention
# {server.name} - The name of the server the member joined.
# {owner.name} - The name of the owner of the server.
# {owner.mention} - A mention to the owner of the server.
# {bot.name} - The name of the bot
# {bot.mention} - The name of the bot
welcome_pm: |
  Welcome to **{server.name}**! I'm **{bot.name}**, to learn more about my commands type `/help`

  Start by telling me who is your Tibia character, say **/im *character_name*** so I can begin tracking
  your level ups and deaths!
```

The string can have special formatting that is replaced at runtime, for example, `{server.name}` would be replaced by `NabBot Support` if the member joined that server.

The `|` character in the first line lets the string be multiline. If two line jumps are added together, it will turn into a single line jump.

A custom message can be appended to this for a specific server by using [/setwelcome](../commands/admin/#setwelcome).


!!! note
    This is not reliable anymore since Discord introduced privacy features that allow users to disable private messages from members of servers they join.
    
## Owner IDs
```yaml
owner_ids:
  - 162060569803751424
  - 162070610556616705
```

This gives the users with those user ids permission to use any commands and by pass most regulations.
The owner of the bot's application is always considered even if their id is not here.

This allows them to use sensitive commands like `/shutdown` and `/restart` or execute Python code directly.

## Timezones
```yaml
display_brasilia_time: true
display_sonora_time: true
```

Specifies how many concurrent loot scanning jobs can be active.

## Announce Threshold
```yaml
announce_threshold: 30
```

This is the mininum level for NabBot to announce levels and deaths. Note that even if they are not announced, they are still tracked and stored.

Checking a character directly using `/deaths` or `/levels` will show all entries, but seeing them in overall lists using the commands without parameters will hide such entries.

## Online List Expiration
```yaml
online_list_expiration: 300
```

In order to prevent losing level up announcements because NabBot was restarted, the state of online players is saved in a file.
However, if the data is too old, it must be discarded to prevent errors.

This is in the interval in seconds to consider the online list still valid.

## Scan intervals
```yaml
# Delay inbreed server checks
online_scan_interval: 40

# Delay in between player death checks in seconds
death_scan_interval: 15

# Delay between each tracked world's highscore check and delay between pages scan
highscores_delay: 45
highscores_page_delay: 10

# Delay between retries when there's a network error in seconds
network_retry_delay: 1
```

These are intervals related to fetching operations.
These were relevant when Tibia.com was used for most of the data, to reduce errors due to CipSoft blocking constant requests.

Now that TibiaData is used, this is not as relevant, as they use caching.

This might be removed in future updates.

## Emojis
Some information is displayed using emojis, to make it easier to identify at quick glance.
These emojis can be personalized by editing the configuration file.

Apart of unicode (standard) emojis, custom discord emojis can be used.
Discord bots are able to use emojis from any server they are in, anywhere, like they had [Nitro](https://discordapp.com/nitro).

It is recommended to use custom emojis from a server where no one else can modify them, as this may break NabBot.
A server dedicated for emojis may be created, inviting the bot for it to use them.

To use a custom emoji, you have to declare it like: `<:name:id>`, for example: `<:fireDamage:458794525050142740>`.
For animated emojis, you have to add `a`, example: `<a:paladin:45233654759231>`.

To find out the id of an emoji, there's two ways to do it:

1. Right click and emoji, select `Copy Link`, a link like `https://cdn.discordapp.com/emojis/458794525050142740.png?v=1` will be created.  
   The numeric part is the emoji's id.
2. Send a message with the emoji, placing `\` before, e.g. `\:fireDamage:`.  
   The resulting message will contain the escaped emoji: `<:fireDamage:458794525050142740>`.
   
Alternatively, if you have the `server-log` enabled, you can see the id of an emoji when it's created or modified.

The following are values that always require to have an emoji assigned. These will always default to a unicode emoji.
```yaml
# Required emojis
# These values must always have an emoji to display
online_emoji: 🔹
true_emoji: ✅
false_emoji: ❌
levelup_emoji: 🌟
death_emoji: ☠
pvpdeath_emoji: 💀
# These emojis are also used in vocation filtering
novoc_emoji: 🐣
druid_emoji: ❄
sorcerer_emoji: 🔥
paladin_emoji: 🏹
knight_emoji: 🛡
```

The following are optional emojis. By default, these values will show text, for example creature elemental resistances.
The unicode emojis used by default are only placeholders, and it is advised to use custom emojis that better represent their values.

The `images\emoji` folder contains a set of suggested images to use for custom emojis.
```yaml
# Optional emojis
# Whether to use or not emojis to show discord status in serverinfo command.
use_status_emojis: false
status_emojis:
  online: 💚
  dnd: ♥
  idle: 💛
  offline: 🖤

# Whether to use emojis to represent elemental damage in spells and monsters info
use_elemental_emojis: false
elemental_emojis:
  physical: ⚔
  earth: 🌿
  fire: 🔥
  energy: ⚡
  ice: ❄
  death: 💀
  holy: 🔱
```