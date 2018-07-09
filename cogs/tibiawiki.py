import random
import re

import discord
from discord.ext import commands

from nabbot import NabBot
from utils.config import config
from utils.context import NabCtx
from utils.general import join_list, FIELD_VALUE_LIMIT, average_color, is_numeric
from utils.messages import split_message
from utils.pages import Pages, CannotPaginate
from utils.tibia import get_map_area
from utils.tibiawiki import get_item, get_monster, get_spell, get_achievement, get_npc, WIKI_ICON, get_article_url, \
    get_key, search_key, get_rashid_info, get_mapper_link, get_bestiary_classes, get_bestiary_creatures, get_imbuement


class TibiaWiki:
    """Commands that show information about Tibia, provided by TibiaWiki.

    The information is read generated using [tibiawiki-sql](https://github.com/Galarzaa90/tibiawiki-sql)."""

    def __init__(self, bot: NabBot):
        self.bot = bot

    async def __error(self, ctx, error):
        if isinstance(error, commands.UserInputError):
            cmd = ctx.bot.get_command('help')
            command = ctx.command.qualified_name
            await ctx.invoke(cmd, command=command)

    # Commands
    @commands.command(aliases=["achiev"])
    async def achievement(self, ctx: NabCtx, *, name: str):
        """Displays an achievement's information.

        Shows the achievement's grade, points, description, and instructions on how to unlock."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        achievement = get_achievement(name)

        if achievement is None:
            await ctx.send("I couldn't find an achievement with that name.")
            return

        if type(achievement) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(achievement))
            await ctx.send("I couldn't find that achievement, maybe you meant one of these?", embed=embed)
            return

        embed = discord.Embed(title=achievement["name"], description=achievement["description"],
                              url=get_article_url(achievement["name"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(achievement["name"]))
        embed.add_field(name="Grade", value="⭐" * int(achievement["grade"]))
        embed.add_field(name="Points", value=achievement["points"])
        embed.add_field(name="Spoiler", value=achievement["spoiler"], inline=True)

        await ctx.send(embed=embed)

    @commands.command(usage="[class]")
    async def bestiary(self, ctx: NabCtx, *, _class: str=None):
        """Displays a category's creatures or all the categories.

        If a category is specified, it will list all the creatures that belong to the category and their level.
        If no category is specified, it will list all the bestiary categories."""
        if _class is None:
            categories = get_bestiary_classes()
            entries = [f"**{name}** - {count} creatures" for name, count in categories.items()]
            description = ""
            title = "Bestiary Classes"
        else:
            creatures = get_bestiary_creatures(_class)
            if not creatures:
                await ctx.send("There's no class with that name.")
                return
            entries = [f"**{name}** - {level}" for name, level in creatures.items()]
            description = f"Use `{ctx.clean_prefix} monster <name>` to see more info"
            title = f"Creatures in the {_class.title()} class"

        pages = Pages(ctx, entries=entries, per_page=20 if ctx.long else 10, header=description)
        pages.embed.title = title
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command(usage="<name>[,price1[,price2[,price3]]][,tokenprice]")
    async def imbuement(self, ctx: NabCtx, *, params: str):
        """Displays information about an imbuement.

        You can optionally provide prices for the materials, in the order of the tier they belong to.
        Additionally, for Vampirism, Void and Strike imbuements, you can provide the price for gold tokens.

        The total cost will be calculated, as well as the hourly cost.
        If applicable, it will show the cheapest way to get it using gold tokens.
        """
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        params = params.split(",")
        if len(params) > 5:
            await ctx.send(f"{ctx.tick(False)} Invalid syntax. The correct syntax is: `{ctx.usage}`.")
            return

        try:
            prices = [int(p) for p in params[1:]]
        except ValueError:
            await ctx.send(f"{ctx.tick(False)} Invalid syntax. The correct syntax is: `{ctx.usage}`.")
            return

        name = params[0]

        imbuement = get_imbuement(name)
        if imbuement is None:
            await ctx.send("I couldn't find an imbuement with that name.")
            return

        if type(imbuement) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(imbuement))
            await ctx.send("I couldn't find that imbuement, maybe you meant one of these?", embed=embed)
            return

        embed = self.get_imbuement_embed(ctx, imbuement, ctx.long, prices)

        # Attach imbuement's image only if the bot has permissions
        permissions = ctx.bot_permissions
        if permissions.attach_files or imbuement["image"] != 0:
            filename = re.sub(r"[^A-Za-z0-9]", "", imbuement["name"]) + ".gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            main_color = await ctx.execute_async(average_color, imbuement["image"])
            embed.color = discord.Color.from_rgb(*main_color)
            await ctx.send(file=discord.File(imbuement["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["itemprice"])
    async def item(self, ctx: NabCtx, *, name: str):
        """Displays information about an item.

        Shows who buys and sells the item, what creatures drops it and many attributes.

        The embed is colored if a major loot NPC buys it, so it can be noted at quick glance.
        Yellow for Rashid, Blue and Green for Djinns and Purple for gems.

        More information is shown if used in private messages or in the command channel."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        item = get_item(name)
        if item is None:
            await ctx.send("I couldn't find an item with that name.")
            return

        if type(item) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(item))
            await ctx.send("I couldn't find that item, maybe you meant one of these?", embed=embed)
            return

        embed = self.get_item_embed(ctx, item, ctx.long)

        # Attach item's image only if the bot has permissions
        permissions = ctx.bot_permissions
        if permissions.attach_files or item["image"] != 0:
            filename = re.sub(r"[^A-Za-z0-9]", "", item["name"]) + ".gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(item["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def key(self, ctx: NabCtx, number: str):
        """Displays information about a key.

        Shows the key's known names, how to obtain it and its uses."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if number is None:
            await ctx.send("Tell me the number of the key you want to check.")
            return

        try:
            number = int(number)
        except ValueError:
            await ctx.send("Tell me a numeric value, to search keys, try: `/key search`")
            return

        key = get_key(number)

        if key is None:
            await ctx.send("I couldn't find a key with that number.")
            return

        embed = self.get_key_embed(key)

        # Attach key's image only if the bot has permissions
        if permissions.attach_files and key["image"] != 0:
            filename = f"Key.gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(key["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @key.command(name="search")
    async def key_search(self, ctx: NabCtx, *, term: str):
        """Searches for a key by keywords.

        Search for matches on the key's names, location, origin or uses.

        if there are multiple matches, a list is shown.
        If only one matches, the key's information is shwon directly."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        keys = search_key(term)

        if keys is None:
            await ctx.send("I couldn't find any related keys.")
            return

        if type(keys) is list:
            embed = discord.Embed(title="Possible keys")
            embed.description = ""
            for key in keys:
                name = "" if key.get("name") is None else f" - {key.get('name')}"
                embed.description += f"\n**Key {key['number']}**{name}"
            await ctx.send(embed=embed)
            return

        embed = self.get_key_embed(keys)

        # Attach key's image only if the bot has permissions
        if permissions.attach_files and keys["image"] != 0:
            filename = f"Key.gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(keys["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=['mob', 'creature'])
    async def monster(self, ctx: NabCtx, *, name: str):
        """Displays information about a monster.

        Shows the monster's attributes, resistances, loot and more.

        More information is displayed if used on a private message or in the command channel."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("Tell me the name of the monster you want to search.")
            return
        if ctx.is_private:
            bot_member = self.bot.user
        else:
            bot_member = self.bot.get_member(self.bot.user.id, ctx.guild)
        if name.lower() == bot_member.display_name.lower():
            await ctx.send(random.choice(["**" + bot_member.display_name + "** is too strong for you to hunt!",
                                          "Sure, you kill *one* child and suddenly you're a monster!",
                                          "I'M NOT A MONSTER",
                                          "I'm a monster, huh? I'll remember that, human...🔥",
                                          "You misspelled *future ruler of the world*.",
                                          "You're not a good person. You know that, right?",
                                          "I guess we both know that isn't going to happen.",
                                          "You can't hunt me.",
                                          "That's funny... If only I was programmed to laugh."]))
            return
        monster = get_monster(name)
        if monster is None:
            await ctx.send("I couldn't find a monster with that name.")
            return

        if type(monster) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(monster))
            await ctx.send("I couldn't find that creature, maybe you meant one of these?", embed=embed)
            return

        embed = self.get_monster_embed(ctx, monster, ctx.long)

        # Attach monster's image only if the bot has permissions
        if permissions.attach_files and monster["image"] != 0:
            filename = re.sub(r"[^A-Za-z0-9]", "", monster["name"]) + ".gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            main_color = await ctx.execute_async(average_color, monster["image"])
            embed.color = discord.Color.from_rgb(*main_color)
            await ctx.send(file=discord.File(monster["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command()
    async def npc(self, ctx: NabCtx, *, name: str):
        """Displays information about a NPC.

        Shows the NPC's item offers, their location and their travel destinations.

        More information is displayed if used on private messages or the command channel."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        npc = get_npc(name)

        if npc is None:
            await ctx.send("I don't know any NPC with that name.")
            return

        if type(npc) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(npc))
            await ctx.send("I couldn't find that NPC, maybe you meant one of these?", embed=embed)
            return

        embed = self.get_npc_embed(ctx, npc, ctx.long)
        # Attach spell's image only if the bot has permissions
        if permissions.attach_files:
            files = []
            if npc["image"] != 0:
                filename = re.sub(r"[^A-Za-z0-9]", "", npc["name"]) + ".png"
                embed.set_thumbnail(url=f"attachment://{filename}")
                files.append(discord.File(npc["image"], filename))
            if None not in [npc["x"], npc["y"], npc["z"]]:
                map_filename = re.sub(r"[^A-Za-z0-9]", "", npc["name"]) + "-map.png"
                map_image = get_map_area(npc["x"], npc["y"], npc["z"])
                embed.set_image(url=f"attachment://{map_filename}")
                embed.add_field(name="Location", value=f"[Mapper link]({get_mapper_link(npc['x'],npc['y'],npc['z'])})",
                                inline=False)
                files.append(discord.File(map_image, map_filename))
            await ctx.send(files=files, embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(usage="<name/words>")
    async def spell(self, ctx: NabCtx, *, name_or_words: str):
        """Displays information about a spell.

        Shows the spell's attributes, NPCs that teach it and more.

        More information is displayed if used on private messages or the command channel."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        spell = get_spell(name_or_words)

        if spell is None:
            await ctx.send("I don't know any spell with that name or words.")
            return

        if type(spell) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(spell))
            await ctx.send("I couldn't find that spell, maybe you meant one of these?", embed=embed)
            return

        embed = self.get_spell_embed(ctx, spell, ctx.long)

        # Attach spell's image only if the bot has permissions
        if permissions.attach_files and spell["image"] != 0:
            filename = re.sub(r"[^A-Za-z0-9]", "", spell["name"]) + ".gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(spell["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    # Helper methods
    @staticmethod
    def get_monster_embed(ctx: NabCtx, monster, long):
        """Gets the monster embeds to show in /mob command
        The message is split in two embeds, the second contains loot only and is only shown if long is True"""
        embed = discord.Embed(title=monster["title"], url=get_article_url(monster["title"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(monster["title"]))
        hp = "?" if monster["hitpoints"] is None else "{0:,}".format(monster["hitpoints"])
        experience = "?" if monster["experience"] is None else "{0:,}".format(monster["experience"])
        speed = "?" if monster["speed"] is None else "{0:,}".format(monster["speed"])
        embed.description = f"**HP** {hp} | **Exp** {experience} | **Speed** {speed}"

        attributes = {"summon": "Summonable",
                      "convince": "Convinceable",
                      "illusionable": "Illusionable",
                      "pushable": "Pushable",
                      "paralysable": "Paralysable",
                      "see_invisible": "Sees Invisible"
                      }

        attributes = "\n".join([f"{ctx.tick(monster[x])} {repl}" for x, repl in attributes.items()
                                if monster[x] is not None])
        embed.add_field(name="Attributes", value="Unknown" if not attributes else attributes)
        elements = ["physical", "holy", "death", "fire", "ice", "energy", "earth"]
        # Iterate through elemental types
        elemental_modifiers = {}
        for element in elements:
            if monster[element] is None or monster[element] == 100:
                continue
            elemental_modifiers[element] = monster[element] - 100
        elemental_modifiers = dict(sorted(elemental_modifiers.items(), key=lambda x: x[1]))
        if elemental_modifiers:
            content = ""
            for element, value in elemental_modifiers.items():
                if config.use_elemental_emojis:
                    content += f"\n{config.elemental_emojis[element]} {value:+}%"
                else:
                    content += f"\n{value:+}% {element.title()}"
            embed.add_field(name="Elemental modifiers", value=content)

        if monster["bestiary_class"] is not None:
            difficulties = {
                "Harmless": config.difficulty_off_emoji*4,
                "Trivial": config.difficulty_on_emoji+config.difficulty_off_emoji*3,
                "Easy": config.difficulty_on_emoji*2+config.difficulty_off_emoji*2,
                "Medium": config.difficulty_on_emoji*3+config.difficulty_off_emoji,
                "Hard": config.difficulty_on_emoji*4
            }
            occurrences = {
                "Common": config.occurrence_off_emoji*4,
                "Uncommon": config.occurrence_on_emoji+config.occurrence_off_emoji*3,
                "Rare": config.occurrence_on_emoji*2+config.occurrence_off_emoji*2,
                "Very Rare": config.occurrence_on_emoji*4,
            }
            kills = {
                "Harmless": 25,
                "Trivial": 250,
                "Easy": 500,
                "Medium": 1000,
                "Hard": 2500
            }
            points = {
                "Harmless": 1,
                "Trivial": 5,
                "Easy": 15,
                "Medium": 25,
                "Hard": 50
            }
            difficulty = difficulties.get(monster["bestiary_level"], f"({monster['bestiary_level']})")
            occurrence = occurrences.get(monster["occurrence"], f"")
            required_kills = kills[monster['bestiary_level']]
            given_points = points[monster['bestiary_level']]
            if monster['occurrence'] == 'Very Rare':
                required_kills = 5
                given_points = max(points[monster['bestiary_level']]*2, 5)
            kill_and_points = \
                f"{required_kills:,} kills | {given_points}{config.charms_emoji}️"
            embed.add_field(name="Bestiary Class", value=f"{monster['bestiary_class']}\n{difficulty}\n{occurrence}"
                                                         f"\n{kill_and_points}")

        # If monster drops no loot, we might as well show everything
        if long or not monster["loot"]:
            embed.add_field(name="Max damage",
                            value="{max_damage:,}".format(**monster) if monster["max_damage"] is not None else "???")
            embed.add_field(name="Abilities", value=monster["abilities"], inline=False)
        if monster["loot"] and long:
            loot_string = ""

            for item in monster["loot"]:
                if item["chance"] is None:
                    item["chance"] = "??.??%"
                elif item["chance"] >= 100:
                    item["chance"] = "Always"
                else:
                    item["chance"] = "{0:05.2f}%".format(item['chance'])
                if item["max"] > 1:
                    item["count"] = "({min}-{max})".format(**item)
                else:
                    item["count"] = ""
                loot_string += "{chance} {item} {count}\n".format(**item)
            split_loot = split_message(loot_string, FIELD_VALUE_LIMIT-20)
            for loot in split_loot:
                if loot == split_loot[0]:
                    name = "Loot"
                else:
                    name = "\u200F"
                embed.add_field(name=name, value="`" + loot + "`")
        if monster["loot"] and not long:
            ask_channel = ctx.ask_channel_name
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        return embed

    @staticmethod
    def get_key_embed(key):
        if key is None:
            return None
        embed = discord.Embed(title=f"Key {key['number']:04}", url=get_article_url(f"Key {key['number']:04}"))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(f"Key {key['number']:04}"))
        if key.get("name") is not None:
            embed.description = f"**Also known as:** {key['name']}"
        if key.get("location") is not None:
            embed.add_field(name="Location", value=key["location"])
        if key.get("origin") is not None:
            embed.add_field(name="Origin", value=key["origin"])
        if key.get("notes") is not None:
            embed.add_field(name="Notes/Use", value=key["notes"])
        return embed

    @staticmethod
    def get_imbuement_embed(ctx: NabCtx, imbuement, long, prices):
        """Gets the item embed to show in /item command"""
        embed = discord.Embed(title=imbuement["name"], url=get_article_url(imbuement["name"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(imbuement["name"]))
        embed.add_field(name="Effect", value=imbuement["effect"])
        materials = ""
        if not prices:
            embed.set_footer(text=f"Provide material prices to calculate costs."
                                  f" More info: {ctx.clean_prefix}help {ctx.invoked_with}")
        elif len(prices) < len(imbuement["materials"]):
            embed.set_footer(text="Not enough material prices provided for this tier.")
            prices = []
        for i, material in enumerate(imbuement["materials"]):
            price = ""
            if prices:
                price = f" ({prices[i]:,} gold each)"
            materials += "\nx{amount} {name}{price}".format(**material, price=price)
        if prices:
            fees = [5000, 25000, 100000]  # Gold fees for each tier
            fees_100 = [15000, 55000, 150000]  # Gold fees for each tier with 100% chance
            tiers = {"Basic": 0, "Intricate": 1, "Powerful": 2}  # Tiers order
            tokens = [2, 4, 6]  # Token cost for materials of each tier
            tier = tiers[imbuement["tier"]]  # Current tier
            token_imbuements = ["Vampirism", "Void", "Strike"]  # Imbuements that can be bought with gold tokens

            tier_prices = []  # The total materials cost for each tier
            materials_cost = 0  # The cost of all materials for the current tier
            for m, p in zip(imbuement["materials"], prices):
                materials_cost += m["amount"] * p
                tier_prices.append(materials_cost)

            def parse_prices(_tier: int, _materials: int):
                return f"**Materials:** {_materials:,} gold.\n" \
                       f"**Total:** {_materials+fees[_tier]:,} gold | " \
                       f"{(_materials+fees[_tier])/20:,.0f} gold/hour\n" \
                       f"**Total  (100% chance):** {_materials+fees_100[_tier]:,} gold | " \
                       f"{(_materials+fees_100[_tier])/20:,.0f} gold/hour"
            # If no gold token price was provided or the imbuement type is not applicable, just show material cost
            if len(prices)-1 <= tier or imbuement["type"] not in token_imbuements:
                embed.add_field(name="Materials", value=materials)
                embed.add_field(name="Cost", value=parse_prices(tier, materials_cost), inline=False)
                if imbuement["type"] in token_imbuements:
                    embed.set_footer(text="Add gold token price at the end to find the cheapest option.")
                return embed
            token_price = prices[tier+1]  # Gold token's price
            possible_tokens = "2" if tokens[tier] == 2 else f"2-{tokens[tier]}"
            embed.add_field(name="Materials", value=f"{materials}\n――――――\n"
                                                    f"{possible_tokens} Gold Tokens ({token_price:,} gold each)")
            token_cost = 0  # The total cost of the part that will be bought with tokens
            cheapeast_tier = -1  # The tier which materials are more expensive than gold tokens.
            for i in range(tier+1):
                _token_cost = token_price*tokens[i]
                if _token_cost < tier_prices[i]:
                    token_cost = _token_cost
                    cheapeast_tier = i
            # Using gold tokens is never cheaper.
            if cheapeast_tier == -1:
                embed.add_field(name="Cost", value=f"Getting the materials is cheaper.\n\n"
                                                   f"{parse_prices(tier, materials_cost)}",
                                inline=False)
            # Buying everything with gold tokens is cheaper
            elif cheapeast_tier == tier:
                embed.add_field(name="Cost", value=f"Getting all materials with gold tokens is cheaper.\n\n"
                                                   f"{parse_prices(tier, token_cost)}",
                                inline=False)
            else:
                total_cost = token_cost+tier_prices[cheapeast_tier+1]-tier_prices[cheapeast_tier]
                embed.add_field(name="Cost", value=f"Getting the materials for **{list(tiers.keys())[cheapeast_tier]} "
                                                   f"{imbuement['type']}** with gold tokens and buying the rest is "
                                                   f"cheaper.\n\n{parse_prices(tier, total_cost)}",
                                inline=False)
        else:
            embed.add_field(name="Materials", value=materials)
        return embed

    @staticmethod
    def get_item_embed(ctx: NabCtx, item, long):
        """Gets the item embed to show in /item command"""
        short_limit = 5
        long_limit = 40
        npcs_too_long = False
        drops_too_long = False
        quests_too_long = False

        def adjust_city(name, city):
            name = name.lower()
            if name == 'alesar' or name == 'yaman':
                return "Green Djinn's Fortress"
            elif name == "nah'bob" or name == "haroun":
                return "Blue Djinn's Fortress"
            elif name == 'rashid':
                return get_rashid_info()["city"]
            elif name == 'Yasir':
                return 'his boat'
            return city

        embed = discord.Embed(title=item["title"], description=item["flavor_text"],
                              url=get_article_url(item["title"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(item["title"]))
        properties = f"Weight: {item['weight']} oz"
        for attribute, value in item["attributes"].items():
            if attribute in ["imbuements"]:
                continue
            if attribute == "vocation":
                value = ", ".join(value.title().split("+"))
            properties += f"\n{attribute.replace('_',' ').title()}: {value}"
        embed.add_field(name="Properties", value=properties)
        if "imbuements" in item["attributes"] and len(item["attributes"]["imbuements"]) > 0:
            embed.add_field(name="Used for", value="\n".join(item["attributes"]["imbuements"]))
        if item["sellers"]:
            item_value = 0
            currency = ""
            count = 0
            value = ""
            for i, npc in enumerate(item["sellers"]):
                if i == 0:
                    item_value = npc["value"]
                    currency = npc["currency"]
                if npc["value"] != item_value:
                    break
                npc["city"] = adjust_city(npc["name"], npc["city"])
                value += "\n{name} ({city})".format(**npc)
                count += 1
                if count > short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item['sellers']) - short_limit)
                    npcs_too_long = True
                    break
            embed.add_field(name=f"Sold for {item_value:,} {currency} by", value=value)
        if item["buyers"]:
            item_price = 0
            currency = ""
            count = 0
            value = ""
            for i, npc in enumerate(item["buyers"]):
                if i == 0:
                    item_price = npc["value"]
                    currency = npc["currency"]
                if npc["value"] != item_price:
                    break
                npc["city"] = adjust_city(npc["name"], npc["city"])
                name = npc["name"].lower()
                if name == 'alesar' or name == 'yaman':
                    embed.colour = discord.Colour.green()
                elif name == "nah'bob" or name == "haroun":
                    embed.colour = discord.Colour.blue()
                elif name == 'rashid':
                    embed.colour = discord.Colour(0xF0E916)
                elif name == 'briasol':
                    embed.colour = discord.Colour(0xA958C4)
                value += "\n{name} ({city})".format(**npc)
                count += 1
                if count > short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item['buyers']) - short_limit)
                    npcs_too_long = True
                    break
            embed.add_field(name=f"Bought for {item_price:,} {currency} by", value=value)

        if item["quests_reward"]:
            value = ""
            count = 0
            name = "Awarded in"
            for quest in item["quests_reward"]:
                count += 1
                value += "\n" + quest["name"]
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item["quests_reward"]) - short_limit)
                    quests_too_long = True
                    break
            embed.add_field(name=name, value=value)

        if item["loot_from"]:
            name = "Dropped by"
            count = 0
            value = ""

            for creature in item["loot_from"]:
                count += 1
                if creature["chance"] is None:
                    creature["chance"] = "??.??%"
                elif creature["chance"] >= 100:
                    creature["chance"] = "Always"
                else:
                    creature["chance"] = f"{creature['chance']:05.2f}%"
                value += "\n`{chance} {name}`".format(**creature)
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item["loot_from"]) - short_limit)
                    drops_too_long = True
                    break
                if long and count >= long_limit:
                    value += "\n*...And {0} others*".format(len(item["loot_from"]) - long_limit)
                    break

            embed.add_field(name=name, value=value, inline=not long)

        if npcs_too_long or drops_too_long or quests_too_long:
            ask_channel = ctx.ask_channel_name
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))

        return embed

    @staticmethod
    def get_spell_embed(ctx: NabCtx, spell, long):
        """Gets the embed to show in /spell command"""
        short_limit = 5
        too_long = False

        if type(spell) is not dict:
            return
        embed = discord.Embed(title="{name} ({words})".format(**spell), url=get_article_url(spell["name"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(spell["name"]))

        spell["premium"] = "**premium** " if spell["premium"] else ""
        if spell["mana"] < 0:
            spell["mana"] = "variable"
        if "exani hur" in spell["words"]:
            spell["words"] = "exani hur up/down"
        vocs = list()
        if spell['knight']: vocs.append("knights")
        if spell['paladin']: vocs.append("paladins")
        if spell['druid']: vocs.append("druids")
        if spell['sorcerer']: vocs.append("sorcerers")
        spell["vocs"] = join_list(vocs, ", ", " and ")

        description = "A {premium}spell for level **{level}** and up. " \
                      "It uses **{mana}** mana. It can be used by {vocs}".format(**spell)

        if spell["price"] == 0:
            description += "\nIt can be obtained for free."
        else:
            description += "\nIt can be bought for {0:,} gold coins.".format(spell["price"])

        for voc in vocs:
            value = ""
            if len(vocs) == 1:
                name = "Sold by"
            else:
                name = "Sold by ({0})".format(voc.title())
            count = 0
            for npc in spell["npcs"]:
                if not npc[voc[:-1]]:
                    continue
                count += 1
                value += "\n{name} ({city})".format(**npc)
                if count >= short_limit and not long:
                    value += "\n*...And more*"
                    too_long = True
                    break
            if value:
                embed.add_field(name=name, value=value)
        # Set embed color based on element:
        if spell["element"] == "Fire":
            embed.colour = discord.Colour(0xFF9900)
        if spell["element"] == "Ice":
            embed.colour = discord.Colour(0x99FFFF)
        if spell["element"] == "Energy":
            embed.colour = discord.Colour(0xCC33FF)
        if spell["element"] == "Earth":
            embed.colour = discord.Colour(0x00FF00)
        if spell["element"] == "Holy":
            embed.colour = discord.Colour(0xFFFF00)
        if spell["element"] == "Death":
            embed.colour = discord.Colour(0x990000)
        if spell["element"] == "Physical" or spell["element"] == "Bleed":
            embed.colour = discord.Colour(0xF70000)
        embed.description = description

        if too_long:
            ask_channel = ctx.ask_channel_name
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))

        return embed

    @staticmethod
    def get_npc_embed(ctx: NabCtx, npc, long):
        """Gets the embed to show in /npc command"""
        short_limit = 5
        long_limit = 100
        too_long = False

        if type(npc) is not dict:
            return

        embed = discord.Embed(title=npc["name"], url=get_article_url(npc["title"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(npc["title"]))
        embed.add_field(name="Job", value=npc["job"])
        if npc["name"] == "Rashid":
            rashid = get_rashid_info()
            npc["city"] = rashid["city"]
            npc["x"] = rashid["x"]
            npc["y"] = rashid["y"]
            npc["z"] = rashid["z"]
        if npc["name"] == "Yasir":
            npc["x"] = None
            npc["y"] = None
            npc["z"] = None
        embed.add_field(name="City", value=npc["city"])
        if npc["selling"]:
            count = 0
            value = ""
            for item in npc["selling"]:
                count += 1
                item["currency"] = item["currency"].replace("gold coin", "gold")
                value += "\n{name} \u2192 {value:,} {currency}".format(**item)
                if count > short_limit and not long:
                    value += "\n*...And {0} others*".format(len(npc['selling']) - short_limit)
                    too_long = True
                    break
                if long and count > long_limit:
                    value += "\n*...And {0} others*".format(len(npc['selling']) - long_limit)
                    break
            split_selling = split_message(value, FIELD_VALUE_LIMIT)
            for value in split_selling:
                if value == split_selling[0]:
                    name = "Selling"
                else:
                    name = "\u200F"
                embed.add_field(name=name, value=value)
        if npc["buying"]:
            count = 0
            value = ""
            for item in npc["buying"]:
                count += 1
                item["currency"] = item["currency"].replace("gold coin", "gold")
                value += "\n{name} \u2192 {value:,} {currency}".format(**item)
                if count > short_limit and not long:
                    value += "\n*...And {0} others*".format(len(npc['buying']) - short_limit)
                    too_long = True
                    break
                if long and count > long_limit:
                    value += "\n*...And {0} others*".format(len(npc['buying']) - long_limit)
                    break
            split_buying = split_message(value, FIELD_VALUE_LIMIT)
            for value in split_buying:
                if value == split_buying[0]:
                    name = "Buying"
                else:
                    name = "\u200F"
                embed.add_field(name=name, value=value)
        if npc["destinations"]:
            count = 0
            value = ""
            for destination in npc["destinations"]:
                count += 1
                value += "\n{name} \u2192 {price} gold".format(**destination)
            embed.add_field(name="Destinations", value=value)
        vocs = ["knight", "sorcerer", "paladin", "druid"]
        if npc["spells"]:
            values = {}
            count = {}
            skip = {}
            for spell in npc["spells"]:
                value = "\n{name} \u2014 {price:,} gold".format(**spell)
                for voc in vocs:
                    if skip.get(voc, False):
                        continue
                    if spell[voc] == 0:
                        continue
                    values[voc] = values.get(voc, "")+value
                    count[voc] = count.get(voc, 0)+1
                    if count.get(voc, 0) >= short_limit and not long:
                        values[voc] += "\n*...And more*"
                        too_long = True
                        skip[voc] = True
            for voc, content in values.items():
                fields = split_message(content, FIELD_VALUE_LIMIT)
                for i, split_field in enumerate(fields):
                    name = f"Teaches ({voc.title()}s)" if i == 0 else "\u200F"
                    embed.add_field(name=name, value=split_field, inline=not len(fields) > 1)
        if too_long:
            ask_channel = ctx.ask_channel_name
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        return embed



def setup(bot):
    bot.add_cog(TibiaWiki(bot))
