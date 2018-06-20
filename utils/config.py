import os
import re
import shutil

import yaml
import yaml.reader

yaml.reader.Reader.NON_PRINTABLE = re.compile(
    u'[^\x09\x0A\x0D\x20-\x7E\x85\xA0-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]')

CONFIG_PATH = "config.yml"
TEMPLATE_PATH = "data/config_template.yml"

KEYS = [
    "ask_channel_name",
    "ask_channel_delete",
    "log_channel_name",
    "lite_servers",
    "welcome_pm",
    "owner_ids",
    "display_brasilia_time",
    "display_sonora_time",
    "online_list_expiration",
    "loot_max",
    "announce_threshold",
    "online_scan_interval",
    "death_scan_interval",
    "highscores_delay",
    "highscores_page_delay",
    "network_retry_delay",
    "extra_cogs",
    "command_prefix",
    "use_status_emojis",
    "status_emojis"
]

_DEFAULT_STATUS_EMOJIS = {
    "online": "💚",
    "dnd": "♥",
    "idle": "💛",
    "offline": "🖤"
}

class Config:
    def __init__(self,):
        # Default values will be used if the keys are not found in config.yml
        self.ask_channel_name = "ask-nabbot"
        self.ask_channel_delete = True
        self.log_channel_name = "server_log"
        self.command_prefix = ("/", )
        self.lite_servers = []
        self.welcome_pm = ""
        self.owner_ids = []
        self.extra_cogs = []
        self.display_brasilia_time = True
        self.display_sonora_time = True
        self.online_list_expiration = 300
        self.loot_max = 6
        self.announce_threshold = 30
        self.online_scan_interval = 90
        self.death_scan_interval = 15
        self.highscores_delay = 45
        self.highscores_page_delay = 10
        self.network_retry_delay = 1
        self.use_status_emojis = False
        self.status_emojis = _DEFAULT_STATUS_EMOJIS

    def __repr__(self) -> str:
        kwargs = vars(self)
        attributes = []
        for k, v in kwargs.items():
            if v is None:
                continue
            if isinstance(v, int) and v == 0:
                continue
            if isinstance(v, list) and len(v) == 0:
                continue
            attributes.append(f"{k} = {v.__repr__()}")
        return f"Config({', '.join(attributes)})"

    def parse(self):

        if not os.path.isfile(CONFIG_PATH):
            print("\tconfig.yml not found, copying from template...")
            shutil.copyfile(TEMPLATE_PATH, CONFIG_PATH)
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.load(f)
            if _config is None:
                _config = {}
        missing = False
        for key in KEYS:
            if key not in _config:
                print(f"\33[33m\tMissing '{key}', using default: {repr(getattr(self, key))}\033[0m")
                missing = True
            else:
                # command prefix must always be a tuple
                if key == "command_prefix":
                    if isinstance(_config[key], str):
                        print("is str")
                        _config[key] = (_config[key],)
                    else:
                        _config[key] = tuple(_config[key])
                setattr(self, key, _config[key])
        for key in _config:
            if key not in KEYS:
                print(f"\33[34m\tExtra entry found: '{key}', ignoring\033[0m")
        if missing:
            print("\33[35mCheck data/config_template.yml for reference\033[0m")
        print("\tDone")


config = Config()
