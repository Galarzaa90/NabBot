#  Copyright 2019 Allan Galarza
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

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
    "owner_ids",
    "online_list_expiration",
    "announce_threshold",
    "online_scan_interval",
    "death_scan_interval",
    "network_retry_delay",
    "extra_cogs",
    "command_prefix",
    "online_emoji",
    "true_emoji",
    "false_emoji",
    "warn_emoji",
    "online_emoji",
    "true_emoji",
    "false_emoji",
    "levelup_emoji",
    "death_emoji",
    "pvpdeath_emoji",
    "novoc_emoji",
    "druid_emoji",
    "sorcerer_emoji",
    "paladin_emoji",
    "knight_emoji",
    "charms_emoji",
    "loading_emoji",
    "difficulty_on_emoji",
    "difficulty_off_emoji",
    "occurrence_on_emoji",
    "occurrence_off_emoji",
    "use_status_emojis",
    "status_emojis",
    "use_elemental_emojis",
    "elemental_emojis"
]

_DEFAULT_STATUS_EMOJIS = {
    "online": "💚",
    "dnd": "♥",
    "idle": "💛",
    "offline": "🖤"
}

_DEFAULT_ELEMENTAL_EMOJIS = {
    "physical": "⚔",
    "earth": "🌿",
    "fire": "🔥",
    "energy": "⚡",
    "ice": "❄",
    "death": "💀",
    "holy": "🔱",
    "poison": "🐍",
    "drown": "💧"
}


class Config:
    def __init__(self,):
        # Default values will be used if the keys are not found in config.yml
        self.ask_channel_name = "ask-nabbot"
        self.ask_channel_delete = True
        self.log_channel_name = "server_log"
        self.command_prefix = ("/", )
        self.lite_servers = []
        self.owner_ids = []
        self.extra_cogs = []
        self.online_list_expiration = 300
        self.announce_threshold = 30
        self.online_scan_interval = 90
        self.death_scan_interval = 15
        self.network_retry_delay = 1
        self.online_emoji = "🔹"
        self.true_emoji = "✅"
        self.false_emoji = "❌"
        self.warn_emoji = "⚠"
        self.levelup_emoji = "🌟"
        self.death_emoji = "☠"
        self.pvpdeath_emoji = "💀"
        self.novoc_emoji = "🐣"
        self.druid_emoji = "❄"
        self.sorcerer_emoji = "🔥"
        self.paladin_emoji = "🏹"
        self.knight_emoji = "🛡"
        self.charms_emoji = "⚜"
        self.loading_emoji = "⏳"
        self.difficulty_on_emoji = "⭐"
        self.difficulty_off_emoji = "▪"
        self.occurrence_on_emoji = "🔹"
        self.occurrence_off_emoji = "▪"
        self.use_status_emojis = False
        self.status_emojis = _DEFAULT_STATUS_EMOJIS
        self.use_elemental_emojis = False
        self.elemental_emojis = _DEFAULT_ELEMENTAL_EMOJIS

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
            _config = yaml.safe_load(f)
            if _config is None:
                _config = {}
        self._assign_keys(_config)
        missing_keys = [k for k in KEYS if k not in _config.keys()]
        for key in missing_keys:
            print(f"\33[33m\tMissing '{key}', using default: {repr(getattr(self, key))}\033[0m")
        for key in _config:
            if key not in KEYS:
                print(f"\33[34m\tExtra entry found: '{key}'\033[0m")
        if missing_keys:
            print("\33[35mCheck data/config_template.yml for reference\033[0m")
        print("\tDone")

    def _assign_keys(self, _config):
        """Assings found keys"""
        for key in _config:
            if key == "command_prefix":
                if isinstance(_config[key], str):
                    _config[key] = (_config[key],)
                else:
                    _config[key] = tuple(_config[key])
            if key == "elemental_emojis":
                self._fill_missing_elements(key, _config[key], _DEFAULT_ELEMENTAL_EMOJIS)
            if key == "status_emojis":
                self._fill_missing_elements(key, _config[key], _DEFAULT_STATUS_EMOJIS)
            setattr(self, key, _config[key])

    @staticmethod
    def _fill_missing_elements(name, subdict, defaults):
        """Checks if the dictionary is missing keys compared against a default dictionary model."""
        missing = [k for k in defaults if k not in subdict]
        for k in missing:
            subdict[k] = defaults[k]
            print(f"\33[33m\tMissing '{k}' in '{name}', using default: {repr(defaults[k])}\033[0m")


config = Config()
