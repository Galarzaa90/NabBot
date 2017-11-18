import random
import re
import datetime as dt

import discord
from discord import Colour
from discord.ext import commands

from config import ask_channel_name
from nabbot import NabBot
from utils.discord import is_private, FIELD_VALUE_LIMIT
from utils.general import join_list, get_local_timezone
from utils.messages import EMOJI, split_message
from utils.tibia import get_map_area, get_tibia_time_zone, get_rashid_city
from utils.tibiawiki import get_item, get_monster, get_spell, get_achievement, get_npc, WIKI_ICON, get_article_url


class TibiaWiki:
    """TibiaWiki related commands."""

    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.command(aliases=['checkprice', 'itemprice'])
    async def item(self, ctx, *, name: str = None):
        """Checks an item's information

        Shows name, picture, npcs that buy and sell and creature drops"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("Tell me the name of the item you want to search.")
            return
        item = get_item(name)
        if item is None:
            await ctx.send("I couldn't find an item with that name.")
            return

        if type(item) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(item))
            await ctx.send("I couldn't find that item, maybe you meant one of these?", embed=embed)
            return

        long = is_private(ctx.channel) or ctx.channel.name == ask_channel_name
        embed = self.get_item_embed(ctx, item, long)

        # Attach item's image only if the bot has permissions
        permissions = ctx.channel.permissions_for(ctx.me)
        if permissions.attach_files or item["image"] != 0:
            filename = re.sub(r"[^A-Za-z0-9]", "", item["name"]) + ".gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(item["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=['mon', 'mob', 'creature'])
    async def monster(self, ctx, *, name: str = None):
        """Gives information about a monster"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("Tell me the name of the monster you want to search.")
            return
        if is_private(ctx.channel):
            bot_member = self.bot.user
        else:
            bot_member = self.bot.get_member(self.bot.user.id, ctx.guild)
        if name.lower() == bot_member.display_name.lower():
            await ctx.send(random.choice(["**" + bot_member.display_name + "** is too strong for you to hunt!",
                                          "Sure, you kill *one* child and suddenly you're a monster!",
                                          "I'M NOT A MONSTER",
                                          "I'm a monster, huh? I'll remember that, human..." + EMOJI[":flame:"],
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

        long = is_private(ctx.channel) or ctx.channel.name == ask_channel_name
        embed = self.get_monster_embed(ctx, monster, long)

        # Attach monster's image only if the bot has permissions
        if permissions.attach_files and monster["image"] != 0:
            filename = re.sub(r"[^A-Za-z0-9]", "", monster["name"]) + ".gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(monster["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["npcs"])
    async def npc(self, ctx, *, name: str = None):
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("Tell me the name of an NPC.")
            return

        npc = get_npc(name)

        if npc is None:
            await ctx.send("I don't know any NPC with that name.")
            return

        if type(npc) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(npc))
            await ctx.send("I couldn't find that NPC, maybe you meant one of these?", embed=embed)
            return

        long = is_private(ctx.channel) or ctx.channel.name == ask_channel_name
        embed = self.get_npc_embed(ctx, npc, long)
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
                files.append(discord.File(map_image, map_filename))
            await ctx.send(files=files, embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command()
    async def spell(self, ctx, *, name: str = None):
        """Tells you information about a certain spell."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("Tell me the name or words of a spell.")
            return

        spell = get_spell(name)

        if spell is None:
            await ctx.send("I don't know any spell with that name or words.")
            return

        if type(spell) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(spell))
            await ctx.send("I couldn't find that spell, maybe you meant one of these?", embed=embed)
            return

        long = is_private(ctx.channel) or ctx.channel.name == ask_channel_name
        embed = self.get_spell_embed(ctx, spell, long)

        # Attach spell's image only if the bot has permissions
        if permissions.attach_files and spell["image"] != 0:
            filename = re.sub(r"[^A-Za-z0-9]", "", spell["name"]) + ".gif"
            embed.set_thumbnail(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(spell["image"], f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(aliases=["achiev"])
    async def achievement(self, ctx, *, name: str = None):
        """Shows an achievement's information

        Spoilers are only shown on ask channel and private messages"""
        permissions = ctx.message.channel.permissions_for(self.bot.get_member(self.bot.user.id, ctx.message.guild))
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("Tell me the name of the achievement you want to check.")
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
        embed.add_field(name="Grade", value=EMOJI[":star:"] * int(achievement["grade"]))
        embed.add_field(name="Points", value=achievement["points"])
        embed.add_field(name="Spoiler", value=achievement["spoiler"], inline=True)

        await ctx.send(embed=embed)

    @staticmethod
    def get_monster_embed(ctx, monster, long):
        """Gets the monster embeds to show in /mob command
        The message is split in two embeds, the second contains loot only and is only shown if long is True"""
        embed = discord.Embed(title=monster["title"], url=get_article_url(monster["title"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(monster["title"]))
        hp = "?" if monster["hitpoints"] is None else "{0:,}".format(monster["hitpoints"])
        experience = "?" if monster["experience"] is None else "{0:,}".format(monster["experience"])
        if not (monster["experience"] is None or monster["hitpoints"] is None or monster["hitpoints"] < 0):
            ratio = "{0:.2f}".format(monster['experience'] / monster['hitpoints'])
        else:
            ratio = "?"
        embed.add_field(name="HP", value=hp)
        embed.add_field(name="Experience", value=experience)
        embed.add_field(name="HP/Exp Ratio", value=ratio)

        weak = []
        resist = []
        immune = []
        elements = ["physical", "holy", "death", "fire", "ice", "energy", "earth", "drown", "lifedrain"]
        # Iterate through elemental types
        for index, value in monster.items():
            if index in elements:
                if monster[index] is None:
                    continue
                if monster[index] == 0:
                    immune.append(index.title())
                elif monster[index] > 100:
                    weak.append([index.title(), monster[index] - 100])
                elif monster[index] < 100:
                    resist.append([index.title(), monster[index] - 100])
        # Add paralysis to immunities
        if monster["paralysable"] == 0:
            immune.append("Paralysis")
        if monster["see_invisible"] == 1:
            immune.append("Invisibility")

        if immune:
            embed.add_field(name="Immune to", value="\n".join(immune))
        else:
            embed.add_field(name="Immune to", value="Nothing")

        if resist:
            embed.add_field(name="Resistant to", value="\n".join(["{1}% {0}".format(*i) for i in resist]))
        else:
            embed.add_field(name="Resistant to", value="Nothing")
        if weak:
            embed.add_field(name="Weak to", value="\n".join(["+{1}% {0}".format(*i) for i in weak]))
        else:
            embed.add_field(name="Weak to", value="Nothing")

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
            split_loot = split_message(loot_string, FIELD_VALUE_LIMIT)
            for loot in split_loot:
                if loot == split_loot[0]:
                    name = "Loot"
                else:
                    name = "\u200F"
                embed.add_field(name=name, value="`" + loot + "`")
        if monster["loot"] and not long:
            ask_channel = ctx.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
            if ask_channel:
                askchannel_string = " or use #" + ask_channel.name
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        return embed

    @staticmethod
    def get_item_embed(ctx, item, long):
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
                return get_rashid_city()
            elif name == 'Yasir':
                return 'his boat'
            return city

        embed = discord.Embed(title=item["title"], description=item["flavor_text"],
                              url=get_article_url(item["title"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(item["title"]))
        properties = f"Weight: {item['weight']} oz"
        # TODO: Look description no longer in database, attributes must be shown in another way.
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
                    embed.colour = Colour.green()
                elif name == "nah'bob" or name == "haroun":
                    embed.colour = Colour.blue()
                elif name == 'rashid':
                    embed.colour = Colour(0xF0E916)
                elif name == 'briasol':
                    embed.colour = Colour(0xA958C4)
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
            ask_channel = ctx.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
            if ask_channel:
                askchannel_string = " or use #" + ask_channel.name
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))

        return embed

    @staticmethod
    def get_spell_embed(ctx, spell, long):
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
            embed.colour = Colour(0xFF9900)
        if spell["element"] == "Ice":
            embed.colour = Colour(0x99FFFF)
        if spell["element"] == "Energy":
            embed.colour = Colour(0xCC33FF)
        if spell["element"] == "Earth":
            embed.colour = Colour(0x00FF00)
        if spell["element"] == "Holy":
            embed.colour = Colour(0xFFFF00)
        if spell["element"] == "Death":
            embed.colour = Colour(0x990000)
        if spell["element"] == "Physical" or spell["element"] == "Bleed":
            embed.colour = Colour(0xF70000)

        embed.description = description

        if too_long:
            ask_channel = ctx.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
            if ask_channel:
                askchannel_string = " or use #" + ask_channel.name
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))

        return embed

    @staticmethod
    def get_npc_embed(ctx, npc, long):
        """Gets the embed to show in /npc command"""
        short_limit = 5
        long_limit = 200
        too_long = False

        if type(npc) is not dict:
            return

        embed = discord.Embed(title=npc["name"], url=get_article_url(npc["title"]))
        embed.set_author(name="TibiaWiki",
                         icon_url=WIKI_ICON,
                         url=get_article_url(npc["title"]))
        embed.add_field(name="Job", value=npc["job"])
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

        # TODO: Teachable spells

        if too_long:
            ask_channel = ctx.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
            if ask_channel:
                askchannel_string = " or use #" + ask_channel.name
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        return embed


def setup(bot):
    bot.add_cog(TibiaWiki(bot))
