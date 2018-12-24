import datetime as dt
import logging
import math
import re

import discord
from discord.ext import commands

from cogs.utils.context import NabCtx
from cogs.utils.converter import Stamina
from cogs.utils.tibia import DRUID, KNIGHT, NetworkError, PALADIN, SORCERER, get_character, get_stats
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

MANA_PER_UMP = 500
UMP_PER_WEAPON = 610
MANA_PER_WEAPON = UMP_PER_WEAPON*MANA_PER_UMP
EXERCISE_WEAPON_GP = 262500
EXERCISE_WEAPON_COIN = 25


class Calculators:
    """Commands to calculate various Tibia values."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @commands.command(aliases=['bless'])
    async def blessings(self, ctx: NabCtx, level: int):
        """Calculates the price of blessings for a specific level.

        For player over level 100, it will also display the cost of the Blessing of the Inquisition."""
        if level < 1:
            return await ctx.send("Very funny... Now tell me a valid level.")
        bless_price = max(2000, 200 * (min(level, 120) - 20))
        mountain_bless_price = max(2000, 200 * (min(level, 150) - 20))
        inquisition = ""
        if level >= 100:
            inquisition = f"\nBlessing of the Inquisition costs **{int(bless_price*5*1.1):,}** gold coins."
        await ctx.send(f"At that level you will pay **{bless_price:,}** gold coins per blessing for a total of "
                       f"**{bless_price*5:,}** gold coins.{inquisition}"
                       f"\nMountain blessings cost **{mountain_bless_price:,}** each, for a total of "
                       f"**{int(mountain_bless_price*2):,}**.")

    @commands.command()
    async def distanceskill(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str,
                            loyalty: int = 0):
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
        embed = discord.Embed(title="🏹 Distance Skill Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From distance level {current} ({percentage}%) to {target} as a {voc}{loyalty_str}")
        embed.description = "*For the moment, regular training information is not available.*"
        if voc == "paladin":
            factor = MAGIC_FACTOR["druid"]
            mana = self.get_mana_spent(current, percentage, target, factor, loyalty)
            weapons = int(math.ceil(mana / MANA_PER_WEAPON))
            embed.add_field(name="Exercise Dummies", value=self.get_weapon_usage_string(weapons))
            weapons = int(math.ceil(mana / (MANA_PER_WEAPON * 1.1)))
            embed.add_field(name="Expert Exercise Dummies", value=self.get_weapon_usage_string(weapons))
        await ctx.send(embed=embed)

    @commands.command()
    async def magiclevel(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str, loyalty: int = 0):
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
        weapons = int(math.ceil(mana/MANA_PER_WEAPON))
        regen_seconds = mana/MANA_PER_SEC[voc]

        embed = discord.Embed(title="🔮 Magic Level Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From magic level {current} ({percentage}%) to {target} as a {voc}{loyalty_str}")
        try:
            embed.add_field(name="Offline training time", value=f"{dt.timedelta(seconds=regen_seconds*2)}")
        except OverflowError:
            embed.add_field(name="Offline training time", value="Longer than what you will live.")
        embed.add_field(name="Exercise Dummies", value=self.get_weapon_usage_string(weapons))
        weapons = int(math.ceil(mana / (MANA_PER_WEAPON * 1.1)))
        embed.add_field(name="Expert Exercise Dummies", value=self.get_weapon_usage_string(weapons))

        embed.description = f"You need to spend **{mana:,}** mana to reach magic level {target}"
        await ctx.send(embed=embed)

    @commands.command()
    async def meleeskill(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str,
                         loyalty: int = 0):
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

        embed = discord.Embed(title="⚔ Melee Skill Calculator", colour=discord.Colour.teal())
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
            weapons = int(math.ceil(mana / MANA_PER_WEAPON))
            embed.add_field(name="Exercise Dummies", value=self.get_weapon_usage_string(weapons))
            weapons = int(math.ceil(mana / (MANA_PER_WEAPON * 1.1)))
            embed.add_field(name="Expert Exercise Dummies", value=self.get_weapon_usage_string(weapons))
        await ctx.send(embed=embed)

    @commands.command()
    async def stamina(self, ctx: NabCtx, current: Stamina, target: Stamina = None):
        """Tells you the time you have to wait to restore stamina.

        To use it, you must provide your current stamina, in this format: `hh:mm`.
        The bot will show the time needed to reach full stamina if you were to start sleeping now.

        Optionally, you can provide the target stamina you want.

        The footer text shows the time in your timezone where your stamina would be full."""
        if target is None:
            target = Stamina("42:00")
        if current > target:
            return await ctx.error("Current stamina can't be greater than target stamina.")
        if current == target:
            return await ctx.error("Current stamina is already equal to target.")

        delta = dt.timedelta(hours=current.hours, minutes=current.minutes)
        target_delta = dt.timedelta(hours=target.hours, minutes=target.minutes)
        # Stamina takes 3 minutes to regenerate one minute until 40 hours.
        resting_time = max((dt.timedelta(hours=min(target.hours, 40)) - delta).total_seconds(), 0) * 3
        if target.hours > 40 or (target.hours == 40 and target.minutes > 0):
            # Last two hours of stamina take 10 minutes for a minute
            resting_time += (target_delta - max(dt.timedelta(hours=40), delta)).total_seconds() * 10
        # You must be logged off 10 minutes before you start gaining stamina
        resting_time += dt.timedelta(minutes=10).total_seconds()

        current_hours, remainder = divmod(int(resting_time), 3600)
        current_minutes, _ = divmod(remainder, 60)
        if current_hours:
            remaining = f'{current_hours} hours and {current_minutes} minutes'
        else:
            remaining = f'{current_minutes} minutes'

        reply = f"You need to rest **{remaining}** to get back to full stamina."
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send(reply)
            return

        embed = discord.Embed(description=reply)
        embed.set_footer(text="Full stamina")
        embed.colour = discord.Color.green()
        embed.timestamp = dt.datetime.utcnow() + dt.timedelta(seconds=resting_time)
        await ctx.send(embed=embed)

    @commands.command()
    async def stats(self, ctx: NabCtx, *, params: str):
        """Calculates character stats based on vocation and level.

        Shows hitpoints, mana, capacity, total experience and experience to next level.

        This command can be used in two ways:

        1. To calculate the stats for a certain level and vocation. (`stats <level>,<vocation>`)
        2. To calculate the stats of a character. (`stats <character>`)
        """
        invalid_arguments = "Invalid arguments, examples:\n" \
                            f"```{ctx.clean_prefix}stats player\n" \
                            f"{ctx.clean_prefix}stats level,vocation\n```"
        params = params.split(",")
        char = None
        if len(params) == 1:
            _digits = re.compile(r'\d')
            if _digits.search(params[0]) is not None:
                await ctx.send(invalid_arguments)
                return
            else:
                try:
                    char = await get_character(ctx.bot, params[0])
                    if char is None:
                        await ctx.send("Sorry, can you try it again?")
                        return
                except NetworkError:
                    await ctx.send("Character **{0}** doesn't exist!".format(params[0]))
                    return
                level = int(char.level)
                vocation = char.vocation
        elif len(params) == 2:
            try:
                level = int(params[0])
                vocation = params[1]
            except ValueError:
                try:
                    level = int(params[1])
                    vocation = params[0]
                except ValueError:
                    await ctx.send(invalid_arguments)
                    return
        else:
            await ctx.send(invalid_arguments)
            return
        if level <= 0:
            await ctx.send("Not even *you* can go down so low!")
            return
        if level >= 2000:
            await ctx.send("Why do you care? You will __**never**__ reach this level " + str(chr(0x1f644)))
            return
        try:
            stats = get_stats(level, vocation)
        except ValueError as e:
            await ctx.send(e)
            return

        if stats["vocation"] == "no vocation":
            stats["vocation"] = "with no vocation"
        if char:
            await ctx.send("**{5}** is a level **{0}** {1}, {6} has:"
                           "\n\t**{2:,}** HP"
                           "\n\t**{3:,}** MP"
                           "\n\t**{4:,}** Capacity"
                           "\n\t**{7:,}** Total experience"
                           "\n\t**{8:,}** to next level"
                           .format(level, char.vocation.lower(), stats["hp"], stats["mp"], stats["cap"],
                                   char.name, char.he_she.lower(), stats["exp"], stats["exp_tnl"]))
        else:
            await ctx.send("A level **{0}** {1} has:"
                           "\n\t**{2:,}** HP"
                           "\n\t**{3:,}** MP"
                           "\n\t**{4:,}** Capacity"
                           "\n\t**{5:,}** Experience"
                           "\n\t**{6:,}** to next level"
                           .format(level, stats["vocation"], stats["hp"], stats["mp"], stats["cap"],
                                   stats["exp"], stats["exp_tnl"]))

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
