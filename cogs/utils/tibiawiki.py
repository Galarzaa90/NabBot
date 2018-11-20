import urllib.parse

from .database import wiki_db

WIKI_ICON = "https://vignette.wikia.nocookie.net/tibia/images/b/bc/Wiki.png/revision/latest?path-prefix=en"


def get_article_url(title: str) -> str:
    return f"http://tibia.wikia.com/wiki/{urllib.parse.quote(title)}"


def get_item(name):
    """Returns a dictionary containing an item's info, if no exact match was found, it returns a list of suggestions.

    The dictionary has the following keys: name, look_text, npcs_sold*, value_sell, npcs_bought*, value_buy.
        *npcs_sold and npcs_bought are list, each element is a dictionary with the keys: name, city."""

    # Reading item database
    c = wiki_db.cursor()

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
        c.execute("SELECT npc.name, npc.city, npcs_selling.value, currency.name as currency "
                  "FROM npcs_selling "
                  "LEFT JOIN npcs npc on npc.id = npc_id "
                  "LEFT JOIN items currency on currency.id = currency "
                  "WHERE item_id = ? "
                  "ORDER BY npcs_selling.value ASC", (item["id"],))
        item["sellers"] = c.fetchall()

        c.execute("SELECT npc.name, npc.city, npcs_buying.value, currency.name as currency "
                  "FROM npcs_buying "
                  "LEFT JOIN npcs npc on npc.id = npc_id "
                  "LEFT JOIN items currency on currency.id = currency "
                  "WHERE item_id = ? "
                  "ORDER BY npcs_buying.value DESC", (item["id"],))
        item["buyers"] = c.fetchall()
        c.execute("SELECT creature.title as name, chance "
                  "FROM creatures_drops "
                  "LEFT JOIN creatures creature on creature.id = creature_id "
                  "WHERE item_id = ? "
                  "ORDER BY chance DESC ", (item["id"],))
        item["loot_from"] = c.fetchall()
        c.execute("SELECT quests.name "
                  "FROM quests_rewards "
                  "INNER JOIN quests ON quests.id = quests_rewards.quest_id "
                  "WHERE item_id = ? ", (item["id"],))
        item["quests_reward"] = c.fetchall()
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




