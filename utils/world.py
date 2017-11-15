import datetime as dt
from typing import List, Dict

from utils.character import Character
import utils.tibia


class World:
    def __init__(self, name):
        self.name = name
        self.online = 0
        self.record_online = 0
        self.record_date = None  # type: dt.datetime
        self.creation = None
        self.pvp_type = None
        self.premium_type = None
        self.transfer_type = None
        self.location = 0
        self.players_online = []  # type: List[Character]
        self.quests = None  # type: List[str]

    @classmethod
    def parse_from_tibiadata(cls, name: str, content_json: Dict):
        _world = content_json["worlds"]
        if "error" in _world:
            return None
        world_info = _world["world_information"]
        world = World(name.capitalize())
        world.online = int(world_info["players_online"])
        if "online_record" in world_info:
            world.record_online = int(world_info["online_record"]["players"])
            world.record_date = utils.tibia.parse_tibiadata_time(world_info["online_record"]["date"])
        world.creation = world_info["creation_date"]
        world.location = world_info["location"]
        world.pvp_type = world_info["pvp_type"]
        world.premium_type = world_info.get("premium_type")
        world.transfer_type = world_info.get("transfer_type")
        # TODO: Parse battleye status
        if "world_quest_titles" in world_info:
            world.quests = world_info["world_quest_titles"]

        for player in _world["players_online"]:
            world.players_online.append(Character(player["name"],
                                                  world.name,
                                                  level=int(player["level"]),
                                                  vocation=player["vocation"],
                                                  online=True))
        return world

