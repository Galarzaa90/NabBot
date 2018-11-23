import datetime as dt
import logging
import math

import discord
from discord.ext import commands

from cogs.utils.context import NabCtx
from cogs.utils.tibia import DRUID, KNIGHT, PALADIN, SORCERER
from nabbot import NabBot

log = logging.getLogger("nabbot")

MELEE_FACTOR = {
    "knight": 1.1,
    "paladin": 1.2,
    "druid": 1.8,
    "sorcerer": 2
}

MAGIC_FACTOR = {
    "knight": 3,
    "paladin": 1.4,
    "druid": 1.1,
    "sorcerer": 1.1
}

MANA_PER_SEC = {
    "knight": 1/3,
    "paladin": 2/3,
    "druid": 1,
    "sorcerer": 1
}

MANA_PER_CHARGE = 600
EXERCISE_WEAPON_GP = 262500
EXERCISE_WEAPON_COIN = 25


class Calculators:
    """Commands to calculate various Tibia values."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.command()
    async def distancecalc(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str, loyalty: int=0):
        """Calculates the training time required to reach a target distance skill level.

        For the moment, online and offline training calculation is unavailable."""
        voc = self.parse_vocation(vocation)
        if not voc:
            return await ctx.error("Unknown vocation.")
        if voc != "paladin":
            return await ctx.error("For the moment, this is only available for **paladins**.")
        if current >= target:
            return await ctx.error("Target skill must be greater than current skill.")
        if current < 10:
            return await ctx.error("Your current skill can't be lower than 10.")
        if target > 200:
            return await ctx.error("Your target skill can't be greater than 200.")
        if 0 > percentage >= 100:
            return await ctx.error("Percentage must be between 0 and 99.")
        if 0 > loyalty > 50 or loyalty % 5:
            return await ctx.error("Loyalty must be between 0 and 50, and a multiple of 5.")

        loyalty_str = f" with a loyalty bonus of {loyalty}%." if loyalty else "."
        embed = discord.Embed(title="🔢🏹 Distance Skill Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From distance level {current} ({percentage}%) to {target} as a {voc}{loyalty_str}")
        embed.description = "*For the moment, regular training information is not available.*"
        if voc == "paladin":
            factor = MAGIC_FACTOR["druid"]
            mana = self.get_mana_spent(current, percentage, target, factor, loyalty)
            weapons = int(math.ceil(mana / MANA_PER_CHARGE / 500))
            embed.add_field(name="Exercise Dummies", value=self.get_weapon_usage_string(weapons))
            weapons = int(math.ceil(mana / (MANA_PER_CHARGE * 1.1) / 500))
            embed.add_field(name="Expert Exercise Dummies", value=self.get_weapon_usage_string(weapons))
        await ctx.send(embed=embed)

    @commands.command()
    async def magiccalc(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str, loyalty: int=0):
        """Calculates the training time required to reach a target skill level.

        This only applies to axe, club and sword fighting."""
        voc = self.parse_vocation(vocation)
        if not voc:
            return await ctx.error("Unknown vocation.")
        if current >= target:
            return await ctx.error("Target level must be greater than current level.")
        if current < 0:
            return await ctx.error("Your current level can't be lower than 0.")
        if target > 200:
            return await ctx.error("Your target level can't be greater than 200.")
        if target > 30 and voc == "knight":
            return await ctx.error("Your target level can't be greater than 30 for knights.")
        if target > 60 and voc == "paladin":
            return await ctx.error("Your target level can't be greater than 60 for paladins.")
        if 0 > percentage >= 100:
            return await ctx.error("Percentage must be between 0 and 99.")
        if 0 > loyalty > 50 or loyalty % 5:
            return await ctx.error("Loyalty must be between 0 and 50, and a multiple of 5.")

        factor = MAGIC_FACTOR[voc]
        mana = self.get_mana_spent(current, percentage, target, factor, loyalty)
        loyalty_str = f" with a loyalty bonus of {loyalty}%." if loyalty else "."
        weapons = int(math.ceil(mana/MANA_PER_CHARGE/500))
        regen_seconds = mana/MANA_PER_SEC[voc]

        embed = discord.Embed(title="🔢🔮 Magic Level Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From magic level {current} ({percentage}%) to {target} as a {voc}{loyalty_str}")
        try:
            embed.add_field(name="Offline training time", value=f"{dt.timedelta(seconds=regen_seconds*2)}")
        except OverflowError:
            embed.add_field(name="Offline training time", value="Longer than what you will live.")
        embed.add_field(name="Exercise Dummies", value=self.get_weapon_usage_string(weapons))
        weapons = int(math.ceil(mana / (MANA_PER_CHARGE * 1.1) / 500))
        embed.add_field(name="Expert Exercise Dummies", value=self.get_weapon_usage_string(weapons))

        embed.description = f"You need to spend **{mana:,}** mana to reach magic level {target}"
        await ctx.send(embed=embed)

    @commands.command()
    async def meeleecalc(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str, loyalty: int=0):
        """Calculates the training time required to reach a target skill level.

        This only applies to axe, club and sword fighting."""
        if current >= target:
            return await ctx.error("Target skill must be greater than current skill.")
        if current < 10:
            return await ctx.error("Your current skill can't be lower than 10.")
        if target > 200:
            return await ctx.error("Your target skill can't be greater than 200.")
        if 0 > percentage >= 100:
            return await ctx.error("Percentage must be between 0 and 99.")
        if 0 > loyalty > 50 or loyalty % 5:
            return await ctx.error("Loyalty must be between 0 and 50, and a multiple of 5.")
        voc = self.parse_vocation(vocation)
        if not voc:
            return await ctx.error("Unknown vocation.")
        factor = MELEE_FACTOR[voc]
        hits = self.get_hits(current, percentage, target, factor, loyalty)

        loyalty_str = f" with a loyalty bonus of {loyalty}%." if loyalty else "."

        embed = discord.Embed(title="🔢⚔ Melee Skill Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From skill level {current} ({percentage}%) to {target} as a {voc}{loyalty_str}")
        embed.description = f"You need **{hits:,}** hits to reach the target level."
        try:
            embed.add_field(name="Online training time", value=f"{dt.timedelta(seconds=hits*2)}")
            embed.add_field(name="Offline training time", value=f"{dt.timedelta(seconds=hits*4)}")
        except OverflowError:
            embed.add_field(name="Online training time", value="Longer than what you will live.")
            embed.add_field(name="Offline training time", value="Longer than what you will live.")
        if voc == "knight":
            factor = MAGIC_FACTOR["druid"]
            mana = self.get_mana_spent(current, percentage, target, factor)
            weapons = int(math.ceil(mana / MANA_PER_CHARGE / 500))
            embed.add_field(name="Exercise Dummies", value=self.get_weapon_usage_string(weapons))
            weapons = int(math.ceil(mana / (MANA_PER_CHARGE * 1.1) / 500))
            embed.add_field(name="Expert Exercise Dummies", value=self.get_weapon_usage_string(weapons))
        await ctx.send(embed=embed)

    @classmethod
    def magic_formula(cls, factor, skill):
        return int(1600 * factor ** skill)

    @classmethod
    def melee_formula(cls, factor, skill):
        return int((50 * factor**(skill-10)))

    @classmethod
    def get_hits(cls, current, percentage, target, factor, loyalty=0):
        hits = 0
        if target - current > 2:
            hits = sum(cls.melee_formula(factor, s) for s in range(current + 1, target))
        hits += int(cls.melee_formula(factor, target) * (1 - percentage / 100))
        hits *= (1 - loyalty/100)
        return int(hits)

    @classmethod
    def get_mana_spent(cls, current, percentage, target, factor, loyalty=0):
        mana = 0
        if target - current > 2:
            mana = sum(cls.magic_formula(factor, s) for s in range(current + 1, target))
        mana += int(cls.magic_formula(factor, target) * (1 - percentage / 100))
        mana *= (1 - loyalty/100)
        return int(mana)

    @classmethod
    def get_weapon_usage_string(cls, weapons):
        content = f"You would need **{weapons:,}** exercise weapons.\n" \
            f"Costing **{EXERCISE_WEAPON_GP * weapons:,}** gold coins " \
            f"or **{EXERCISE_WEAPON_COIN * weapons:,}** tibia coins.\n"
        try:
            content += f"Using them would take {dt.timedelta(seconds=weapons * 500 * 2)}."
        except OverflowError:
            content += "You will be dead before you can use them all."
        return content

    @classmethod
    def parse_vocation(cls, name):
        if name.lower() in KNIGHT:
            return "knight"
        elif name.lower() in PALADIN:
            return "paladin"
        elif name.lower() in DRUID:
            return "druid"
        elif name.lower() in SORCERER:
            return "sorcerer"
        return None


def setup(bot):
    bot.add_cog(Calculators(bot))
