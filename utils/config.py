import os
import shutil

import yaml

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
    "network_retry_delay"
]


class Config:
    def __init__(self, **kwargs):
        self.ask_channel_name = kwargs.get("ask_channel_name", "ask-nabbot")
        self.ask_channel_delete = kwargs.get("ask_channel_delete", True)
        self.log_channel_name = kwargs.get("log_channel_name", "server_log")
        self.lite_servers = kwargs.get("lite_servers", [])
        self.welcome_pm = kwargs.get("welcome_pm", "")
        self.owner_ids = kwargs.get("owner_ids", [])
        self.display_brasilia_time = kwargs.get("display_brasilia_time", True)
        self.display_sonora_time = kwargs.get("display_sonora_time", True)
        self.online_list_expiration = kwargs.get("online_list_expiration", 300)
        self.loot_max = kwargs.get("loot_max", 6)
        self.announce_threshold = kwargs.get("announce_threshold", 30)
        self.online_scan_interval = kwargs.get("online_scan_interval", 40)
        self.death_scan_interval = kwargs.get("death_scan_interval", 15)
        self.highscores_delay = kwargs.get("highscores_delay", 45)
        self.highscores_page_delay = kwargs.get("highscores_page_delay", 10)
        self.network_retry_delay = kwargs.get("network_retry_delay", 1)

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
            shutil.copyfile(TEMPLATE_PATH, CONFIG_PATH)
        with open(CONFIG_PATH, "r") as f:
            _config = yaml.load(f)
            if _config is None:
                _config = {}
        missing = False
        for key in KEYS:
            if key not in _config:
                print(f"config.yml missing '{key}', using default: {getattr(self, key)}")
                missing = True
            else:
                setattr(self, key, _config[key])
        if missing:
            print("Check data/config_template.yml for reference")


config = Config()
