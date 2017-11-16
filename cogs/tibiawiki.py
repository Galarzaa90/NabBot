import random

import discord
import re

from discord import Colour
from discord.ext import commands

from config import ask_channel_name
from nabbot import NabBot
from utils.discord import is_private, FIELD_VALUE_LIMIT
from utils.general import join_list
from utils.messages import EMOJI, split_message
from utils.tibiawiki import get_item, get_monster, get_spell, get_achievement


class TibiaWiki:
    """TibiaWiki related commands."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.command(aliases=['checkprice', 'itemprice'])
    async def item(self, ctx, *, name: str=None):
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
    async def monster(self, ctx, *, name: str=None):
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
            await ctx.send(random.choice(["**"+bot_member.display_name+"** is too strong for you to hunt!",
                                          "Sure, you kill *one* child and suddenly you're a monster!",
                                          "I'M NOT A MONSTER",
                                          "I'm a monster, huh? I'll remember that, human..."+EMOJI[":flame:"],
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
    async def achievement(self, ctx, *, name: str=None):
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

        embed = discord.Embed(title=achievement["name"], description=achievement["description"])
        embed.add_field(name="Grade", value=EMOJI[":star:"]*int(achievement["grade"]))
        embed.add_field(name="Points", value=achievement["points"])
        embed.add_field(name="Spoiler", value=achievement["spoiler"], inline=True)

        await ctx.send(embed=embed)

    @staticmethod
    def get_monster_embed(ctx, monster, long):
        """Gets the monster embeds to show in /mob command
        The message is split in two embeds, the second contains loot only and is only shown if long is True"""
        embed = discord.Embed(title=monster["title"])
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

        # TODO: Look description no longer in database, attributes must be shown in another way.
        embed = discord.Embed(title=item["title"], description=item["flavor_text"])
        if "color" in item:
            embed.colour = item["color"]
        if "imbueslots" in item["attributes"]:
            embed.add_field(name="Imbuement slots", value=item["attributes"]["imbueslots"])
        if "imbuements" in item["attributes"] and len(item["attributes"]["imbuements"]) > 0:
            embed.add_field(name="Used for", value="\n".join(item["attributes"]["imbuements"]))
        if 'npcs_bought' in item and len(item['npcs_bought']) > 0:
            name = "Bought for {0:,} gold coins from".format(item['value_buy'])
            value = ""
            count = 0
            for npc in item['npcs_bought']:
                count += 1
                value += "\n{name} ({city})".format(**npc)
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item['npcs_bought']) - short_limit)
                    npcs_too_long = True
                    break

            embed.add_field(name=name, value=value)

        if 'npcs_sold' in item and len(item['npcs_sold']) > 0:
            name = "Sold for {0:,} gold coins to".format(item['value_sell'])
            value = ""
            count = 0
            for npc in item['npcs_sold']:
                count += 1
                value += "\n{name} ({city})".format(**npc)
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item['npcs_sold']) - short_limit)
                    npcs_too_long = True
                    break

            embed.add_field(name=name, value=value)

        if item["quests"]:
            value = ""
            count = 0
            name = "Awarded in"
            for quest in item["quests"]:
                count += 1
                value += "\n" + quest
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item["quests"]) - short_limit)
                    quests_too_long = True
                    break
            embed.add_field(name=name, value=value)

        if item["dropped_by"]:
            name = "Dropped by"
            count = 0
            value = ""

            for creature in item["dropped_by"]:
                count += 1
                if creature["percentage"] is None:
                    creature["percentage"] = "??.??%"
                elif creature["percentage"] >= 100:
                    creature["percentage"] = "Always"
                else:
                    creature["percentage"] = f"{creature['percentage']:05.2f}%"
                value += "\n`{percentage} {name}`".format(**creature)
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item["dropped_by"]) - short_limit)
                    drops_too_long = True
                    break
                if long and count >= long_limit:
                    value += "\n*...And {0} others*".format(len(item["dropped_by"]) - long_limit)
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
        embed = discord.Embed(title="{name} ({words})".format(**spell))
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


def setup(bot):
    bot.add_cog(TibiaWiki(bot))
