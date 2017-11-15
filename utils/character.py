import datetime as dt
import re
import urllib.parse
from typing import Dict, List

# TODO: Generate character from tibia.com response
import utils.tibia


class Character:
    SEX_MALE = 0
    SEX_FEMALE = 1

    FREE_ACCOUNT = 0
    PREMIUM_ACCOUNT = 1

    URL_CHAR = "https://secure.tibia.com/community/?subtopic=characters&name="

    def __init__(self, name: str, world: str, *, online: bool=False, level: int =0, vocation: str=None):
        self.name = name
        self.level = level
        self.world = world
        self.achievement_points = 0
        self.sex = 0
        self.former_world = None
        self.residence = None
        self.vocation = vocation
        self.married_to = None
        self.guild = None
        self.house = None
        self.last_login = None  # type: dt.datetime
        self.deleted = None  # type: dt.datetime
        self.online = online
        self.achievements = []
        self.deaths = []  # type: List[Death]
        self.other_characters = []
        self.account_status = 0

        # NabBot specific attributes:
        self.highscores = []
        self.owner = 0

    @property
    def he_she(self):
        return ["He", "She"][self.sex]

    @property
    def his_her(self):
        return ["His", "Her"][self.sex]

    @property
    def him_her(self):
        return ["Him", "Her"][self.sex]

    @property
    def url(self):
        return self.get_url(self.name)

    @property
    def guild_name(self):
        return None if self.guild is None else self.guild["name"]

    @property
    def guild_rank(self):
        return None if self.guild is None else self.guild["rank"]

    @classmethod
    def get_url(cls, name: str) -> str:
        """Returns the url pointing to the character's tibia.com page

        :param name: Name of the character
        :return: url of the character's information
        """
        return cls.URL_CHAR + urllib.parse.quote(name.encode('iso-8859-1'))

    @classmethod
    def parse_from_tibiadata(cls, content_json: Dict):
        """Parses the response from TibiaData and returns a Character

        :param content_json: The json object returned by TibiaData
        :return: a Character object or None if the character doesn't exist.
        """
        char = content_json["characters"]
        if "error" in char:
            return None
        data = char["data"]
        character = Character(data["name"],
                              data["world"],
                              level = int(data["level"]))
        character.achievement_points = int(data["achievement_points"])
        character.sex = cls.SEX_MALE if data["sex"] == "male" else cls.SEX_FEMALE
        character.vocation = data["vocation"]
        character.residence = data["residence"]
        if "deleted" in data:
            character.deleted = utils.tibia.parse_tibiadata_time(data["deleted"])
        if "married_to" in data:
            character.married_to = data["married_to"]
        if "former_world" in data:
            character.former_world = data["former_world"]
        if "guild" in data:
            character.guild = data["guild"]
        if "house" in data:
            match = re.search(r'(?P<name>.*) \((?P<town>[^\)]+)\)$', data["house"])
            if match:
                character.house = match.groupdict()
        character.account_status = cls.PREMIUM_ACCOUNT if data["account_status"] == "Premium Account" else cls.FREE_ACCOUNT
        if len(data["last_login"]) > 0:
            character.last_login = utils.tibia.parse_tibiadata_time(data["last_login"][0])

        for achievement in char["achievements"]:
            character.achievements.append(Achievement(achievement["name"], int(achievement["stars"])))

        for death in char["deaths"]:
            try:
                match = re.search("by ([^.]+)", death["reason"])
                killer = match.group(1)
                level = int(death["level"])
                death_time = utils.tibia.parse_tibiadata_time(death["date"])
                by_player = False
                if death["involved"]:
                    by_player = True
                    killer = death["involved"][0]["name"]
                character.deaths.append(Death(level, killer, death_time, by_player))
            except ValueError:
                # TODO: Handle deaths with no level
                continue

        for other_character in char["other_characters"]:
            online = other_character["status"] == "online"
            character.other_characters.append(Character(other_character["name"],
                                                        other_character["world"],
                                                        online=online))

        return character


class Achievement:
    def __init__(self, name: str, grade: int):
        self.name = name
        self.grade = grade


# TODO: Handle deaths by multiple killers
class Death:
    def __init__(self, level: int, killer: str, time: dt.datetime, by_player: bool):
        self.level = level
        self.killer = killer
        self.time = time
        self.by_player = by_player
