# Lite mode:
# If lite is enabled, all user database related functions are disabled.
# /stalk, /im, /whois /levels are disabled
# /whois, /deaths have limited functionality
# Level up and deaths announcements are disabled
lite_mode = False

# This is the name of the server where the bot will work
# This bot doesn't support multiple servers yet
# main_channel is where the Bot will do announcements, but he will reply to commands everywhere
# ask_channel is a channel where the bot replies with full length messages (like on pms)
#   Messages that are not commands are automatically deleted in ask_channel
# server_log_channel is where the bot will log certain actions
# main_server must be a server id
main_server = "159815897052086272"
main_channel = "general-chat"
ask_channel_name = "ask-nabbot"
log_channel_name = "server-log"

# It's possible to fetch the database contents on a website to show more entries than what the bot can display
# If enabled, certain commands will link to the website
site_Enabled = False
baseUrl = "http://galarzaa.no-ip.org:7005/ReddAlliance/"
charactersPage = "characters.php"
deathsPage = "deaths.php"
levelsPage = "levels.php"

# Owners can use mods commands and more sensible commands like /shutdown and restart
# Mods can register and unregister chars and users and use makesay
owner_ids = ["162060569803751424", "162070610556616705"]
mod_ids = ["159815675194507265", "164253469912334350"]
# Enable of disable specific timezones for /time
display_brasilia_time = True
display_sonora_time = True

# The list of servers to check for with getServerOnline
tibia_servers = ["Fidera"]
tibia_worlds = []
tibia_worlds_dict = {}

# This is the global online list
# don't look at it too closely or you'll go blind!
# characters are added as servername_charactername
# The list is updated periodically on think() using get_server_online()
global_online_list = []

# Max amount of simultaneous images /loot can try to parse
loot_max = 3
global loot_current
loot_current = 0

# Level threshold for announces (level < announceLevel)
announceTreshold = 30

# Minimum days to show last login in /check command.
last_login_days = 7

# Delay inbreed server checks
online_scan_interval = 25

# Delay in between player death checks in seconds
death_scan_interval = 15

# Databases filenames
USERDB = "users.db"
TIBIADB = "Database.db"
LOOTDB = "loot/loot.db"

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
