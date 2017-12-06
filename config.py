# Special bot channels
# ask_channel is a channel where the bot will give longer replies to some commands (like on pms)
#   If ask_channel_delete is True, any message that is not a command will be deleted, to keep the channel for
#   commands only
# server_log_channel is where the bot will log certain actions such as member joining and registering characters.
ask_channel_name = "ask-nabbot"
ask_channel_delete = True
log_channel_name = "server-log"

# Lite mode:
# If lite is enabled, all user database related functions are disabled.
# /stalk, /im, /whois /levels are disabled
# /whois, /deaths have limited functionality
# Level up and deaths announcements are disabled
lite_servers = [253338519143972864]

# The welcome message that is sent to members when they join a discord server with NabBot in it
# 0 is the member object, examples:
#       0.name - The joined member's name
#       0.server.name - The name of the server the member joined
#       0.server.owner.name - The name of the owner of the server the member joined
#       0.server.owner.mention - A mention to the owner of the server the member joined
# 1 is the bot's object, examples:
#       1.user.name - The bot's name
welcome_pm = "Welcome to **{0.guild.name}**! I'm **{1.user.name}**, to learn more about my commands type `/help`\n" \
             "Start by telling me who is your Tibia character, say **/im *character_name*** so I can begin tracking " \
             "your level ups and deaths!"

# Owners can use mods commands and more sensible commands like /shutdown and restart
# Mods can register chars and users and use makesay
owner_ids = [162060569803751424, 162070610556616705]
mod_ids = [159815675194507265, 164253469912334350]
# Enable of disable specific timezones for /time
display_brasilia_time = True
display_sonora_time = True

# Which highscores to track (can be empty)
highscores_categories = ["sword", "axe", "club", "distance", "shielding", "fist", "fishing", "magic",
                         "magic_ek", "magic_rp", "loyalty", "achievements"]

# Cached online list expiration
online_list_expiration = 5*60

# Max amount of simultaneous images /loot can try to parse
loot_max = 6

# Level threshold for announces (level < announceLevel)
announce_threshold = 30

# Minimum days to show last login in /check command.
last_login_days = 7

# Delay inbreed server checks
online_scan_interval = 40

# Delay in between player death checks in seconds
death_scan_interval = 15

# Delay between each tracked world's highscore check and delay between pages scan
highscores_delay = 45
highscores_page_delay = 10

# Delay between retries when there's a network error in seconds
network_retry_delay = 1

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
