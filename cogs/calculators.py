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
    """Commands related to role management."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.command(usage="<current>")
    async def magiccalc(self, ctx: NabCtx, current: int, percentage: int, target: int, *, vocation: str):
        """Calculates the training time required to reach a target skill level.

        This only applies to axe, club and sword fighting."""
        if current >= target:
            return await ctx.error("Target level must be greater than current skill.")
        if 0 > percentage >= 100:
            return await ctx.error("Percentage must be between 0 and 99.")
        voc = self.parse_vocation(vocation)
        if not voc:
            return await ctx.error("Unknown vocation.")
        mana = 0
        factor = MAGIC_FACTOR[voc]
        if target - current > 2:
            mana = sum(self.magic_formula(factor, s) for s in range(current + 1, target))
        mana += int(self.magic_formula(factor, target) * (1 - percentage / 100))
        weapons = int(math.ceil(mana/MANA_PER_CHARGE/500))

        embed = discord.Embed(title="🔢 Magic Level Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From level {current} ({percentage}%) to {target} as a {voc}")
        embed.add_field(name="Exercise Dummies",
                        value=f"You need **{weapons:,}** exercise weapons.\n"
                        f"Costing **{EXERCISE_WEAPON_GP*weapons:,}** gold coins "
                        f"or **{EXERCISE_WEAPON_COIN*weapons:,}** tibia coins.\n"
                        f"Using them would take {dt.timedelta(seconds=weapons*500*2)}.")
        weapons = int(math.ceil(mana / (MANA_PER_CHARGE * 1.1) / 500))
        embed.add_field(name="Expert Exercise Dummies",
                        value=f"You need **{weapons:,}** exercise weapons.\n"
                        f"Costing **{EXERCISE_WEAPON_GP * weapons:,}** gold coins "
                        f"or **{EXERCISE_WEAPON_COIN * weapons:,}** tibia coins.\n"
                        f"Using them would take {dt.timedelta(seconds=weapons * 500 * 2)}.")

        embed.description = f"You need to spend **{mana:,}** mana to reach magic level {target}"
        await ctx.send(embed=embed)

    @commands.command(usage="<current>")
    async def meeleecalc(self, ctx: NabCtx, current: int, percentage: int, target: int, *, vocation: str):
        """Calculates the training time required to reach a target skill level.

        This only applies to axe, club and sword fighting."""
        if current >= target:
            return await ctx.error("Target skill must be greater than current skill.")
        if 0 > percentage >= 100:
            return await ctx.error("Percentage must be between 0 and 99.")
        voc = self.parse_vocation(vocation)
        if not voc:
            return await ctx.error("Unknown vocation.")
        hits = 0
        factor = MELEE_FACTOR[voc]
        if target-current > 2:
            hits = sum(self.melee_formula(factor, s) for s in range(current+1, target))
        hits += int(self.melee_formula(factor, target) * (1 - percentage / 100))

        embed = discord.Embed(title="🔢 Melee Skill Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From skill level {current} ({percentage}%) to {target} as a {voc}")
        embed.description = f"You need **{hits:,}** hits to reach the target level."
        embed.add_field(name="Online training time", value=f"{dt.timedelta(seconds=hits*2)}")
        embed.add_field(name="Offline training time", value=f"{dt.timedelta(seconds=hits*4)}")
        await ctx.send(embed=embed)

    @classmethod
    def melee_formula(cls, factor, skill):
        return int((50 * factor**(skill-10)))

    @classmethod
    def magic_formula(cls, factor, skill):
        return int((1600 * factor ** (skill - 10)))

    @classmethod
    def get_mana_spent(cls, current, percentage, target, factor):
        if target - current > 2:
            mana = sum(cls.magic_formula(factor, s) for s in range(current + 1, target))
        mana += int(cls.magic_formula(factor, target) * (1 - percentage / 100))
        return mana

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
