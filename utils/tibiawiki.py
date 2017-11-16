import datetime as dt

from discord import Colour

from utils.database import tibiaDatabase
from utils.general import get_local_timezone
from utils.tibia import get_tibia_time_zone, get_rashid_city


def get_monster(name):
    """Returns a dictionary with a monster's info, if no exact match was found, it returns a list of suggestions.

    The dictionary has the following keys: name, id, hp, exp, maxdmg, elem_physical, elem_holy,
    elem_death, elem_fire, elem_energy, elem_ice, elem_earth, elem_drown, elem_lifedrain, senseinvis,
    arm, image."""

    # Reading monster database
    c = tibiaDatabase.cursor()
    c.execute("SELECT * FROM creatures WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
    result = c.fetchall()
    if len(result) == 0:
        return None
    elif result[0]["title"].lower() == name.lower() or len(result) == 1:
        monster = result[0]
    else:
        return [x['title'] for x in result]
    try:
        if monster['hitpoints'] is None or monster['hitpoints'] < 1:
            monster['hitpoints'] = None
        c.execute("SELECT items.title as item, chance, min, max "
                  "FROM creatures_drops, items "
                  "WHERE items.id = creatures_drops.item_id AND creature_id = ? "
                  "ORDER BY chance DESC",
                  (monster["id"],))
        monster["loot"] = c.fetchall()
        return monster
    finally:
        c.close()


def get_item(name):
    """Returns a dictionary containing an item's info, if no exact match was found, it returns a list of suggestions.

    The dictionary has the following keys: name, look_text, npcs_sold*, value_sell, npcs_bought*, value_buy.
        *npcs_sold and npcs_bought are list, each element is a dictionary with the keys: name, city."""

    # Reading item database
    c = tibiaDatabase.cursor()

    # Search query
    c.execute("SELECT * FROM items WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
    result = c.fetchall()
    if len(result) == 0:
        return None
    elif result[0]["title"].lower() == name.lower() or len(result) == 1:
        item = result[0]
    else:
        return [x['title'] for x in result]
    try:
        # Checking if item exists
        if item is not None:
            # Checking NPCs that buy the item
            c.execute("SELECT npcs.title, city, npcs_buying.value "
                      "FROM items, npcs_buying, npcs "
                      "WHERE items.name LIKE ? AND npcs_buying.item_id = items.id AND npcs.id = npc_id "
                      "ORDER BY npcs_buying.value DESC", (item["name"],))
            npcs = []
            value_sell = None
            for npc in c:
                name = npc["title"]
                city = npc["city"].title()
                if value_sell is None:
                    value_sell = npc["value"]
                elif npc["value"] != value_sell:
                    break
                # Replacing cities for special npcs and adding colors
                if name == 'Alesar' or name == 'Yaman':
                    city = 'Green Djinn\'s Fortress'
                    item["color"] = Colour.green()
                elif name == 'Nah\'Bob' or name == 'Haroun':
                    city = 'Blue Djinn\'s Fortress'
                    item["color"] = Colour.blue()
                elif name == 'Rashid':
                    city = get_rashid_city()
                    item["color"] = Colour(0xF0E916)
                elif name == 'Yasir':
                    city = 'his boat'
                elif name == 'Briasol':
                    item["color"] = Colour(0xA958C4)
                npcs.append({"name": name, "city": city})
            item['npcs_sold'] = npcs
            item['value_sell'] = value_sell

            # Checking NPCs that sell the item
            c.execute("SELECT npcs.title, city, npcs_selling.value "
                      "FROM items, npcs_selling, NPCs "
                      "WHERE items.name LIKE ? AND npcs_selling.item_id = items.id AND npcs.id = npc_id "
                      "ORDER BY npcs_selling.value ASC", (item["name"],))
            npcs = []
            value_buy = None
            for npc in c:
                name = npc["title"]
                city = npc["city"].title()
                if value_buy is None:
                    value_buy = npc["value"]
                elif npc["value"] != value_buy:
                    break
                # Replacing cities for special npcs
                if name == 'Alesar' or name == 'Yaman':
                    city = 'Green Djinn\'s Fortress'
                elif name == 'Nah\'Bob' or name == 'Haroun':
                    city = 'Blue Djinn\'s Fortress'
                elif name == 'Rashid':
                    offset = get_tibia_time_zone() - get_local_timezone()
                    # Server save is at 10am, so in tibia a new day starts at that hour
                    tibia_time = dt.datetime.now() + dt.timedelta(hours=offset - 10)
                    city = [
                        "Svargrond",
                        "Liberty Bay",
                        "Port Hope",
                        "Ankrahmun",
                        "Darashia",
                        "Edron",
                        "Carlin"][tibia_time.weekday()]
                elif name == 'Yasir':
                    city = 'his boat'
                npcs.append({"name": name, "city": city})
            item['npcs_bought'] = npcs
            item['value_buy'] = value_buy

            # Get creatures that drop it
            c.execute("SELECT creatures.title as name, creatures_drops.chance as percentage "
                      "FROM creatures_drops, creatures "
                      "WHERE creatures_drops.creature_id = creatures.id AND creatures_drops.item_id = ? "
                      "ORDER BY percentage DESC", (item["id"],))
            item["dropped_by"] = c.fetchall()
            # Checking quest rewards:
            c.execute("SELECT quests.name FROM quests, quests_rewards "
                      "WHERE quests.id = quests_rewards.quest_id AND item_id = ?", (item["id"],))
            quests = c.fetchall()
            item["quests"] = list()
            for quest in quests:
                item["quests"].append(quest["name"])
            # Get item's properties:
            c.execute("SELECT * FROM items_attributes WHERE item_id = ?", (item["id"],))
            results = c.fetchall()
            item["attributes"] = {}
            for row in results:
                if row["attribute"] == "imbuement":
                    temp = item["attributes"].get("imbuements", list())
                    temp.append(row["value"])
                    item["attributes"]["imbuements"] = temp
                else:
                    item["attributes"][row["attribute"]] = row["value"]
            return item
    finally:
        c.close()
    return


def get_spell(name):
    """Returns a dictionary containing a spell's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        c.execute("""SELECT * FROM spells WHERE words LIKE ? OR name LIKE ? ORDER BY LENGTH(name) LIMIT 15""",
                  ("%" + name + "%", "%" + name + "%"))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["name"].lower() == name.lower() or result[0]["words"].lower() == name.lower() or len(
                result) == 1:
            spell = result[0]
        else:
            return ["{name} ({words})".format(**x) for x in result]

        spell["npcs"] = []
        c.execute("""SELECT npcs.title as name, npcs.city, npcs_spells.knight, npcs_spells.paladin,
                  npcs_spells.sorcerer, npcs_spells.druid FROM npcs, npcs_spells
                  WHERE npcs_spells.spell_id = ? AND npcs_spells.npc_id = npcs.id""", (spell["id"],))
        result = c.fetchall()
        for npc in result:
            npc["city"] = npc["city"].title()
            spell["npcs"].append(npc)
        return spell

    finally:
        c.close()


def get_npc(name):
    """Returns a dictionary containing a NPC's info, a list of possible matches or None"""
    c = tibiaDatabase.cursor()
    try:
        # search query
        c.execute("SELECT * FROM NPCs WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15", ("%" + name + "%",))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["title"].lower() == name.lower or len(result) == 1:
            npc = result[0]
        else:
            return [x["title"] for x in result]
        npc["image"] = 0

        c.execute("SELECT Items.name, Items.category, BuyItems.value FROM BuyItems, Items "
                  "WHERE Items.id = BuyItems.itemid AND BuyItems.vendorid = ?", (npc["id"],))
        npc["sell_items"] = c.fetchall()

        c.execute("SELECT Items.name, Items.category, SellItems.value FROM SellItems, Items "
                  "WHERE Items.id = SellItems.itemid AND SellItems.vendorid = ?", (npc["id"],))
        npc["buy_items"] = c.fetchall()
        return npc
    finally:
        c.close()


def get_achievement(name):
    """Returns an achievement (dictionary), a list of possible matches or none"""
    c = tibiaDatabase.cursor()
    try:
        # Search query
        c.execute("SELECT * FROM achievements WHERE name LIKE ? ORDER BY LENGTH(name) ASC LIMIT 15",
                  ("%" + name + "%",))
        result = c.fetchall()
        if len(result) == 0:
            return None
        elif result[0]["name"].lower() == name.lower() or len(result) == 1:
            return result[0]
        else:
            return [x['name'] for x in result]
    finally:
        c.close()