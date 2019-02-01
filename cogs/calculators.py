import datetime as dt
import logging
import math

import discord
from discord.ext import commands

from cogs.utils import config, timing
from nabbot import NabBot
from .utils import tibia
from .utils.context import NabCtx
from .utils.converter import Stamina
from .utils.tibia import get_character, normalize_vocation

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


VOC_ITER = (
    ("knight", config.knight_emoji),
    ("paladin", config.paladin_emoji),
    ("druid", config.druid_emoji+config.sorcerer_emoji)
)


class Calculators:
    """Commands to calculate various Tibia values."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    # region Commands
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

    @commands.command(usage="<current> <percentage> <target> <vocation> [loyalty]")
    async def distanceskill(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str,
                            loyalty: int = 0):
        """Calculates the training time required to reach a target distance skill level.

        For the moment, online and offline training calculation is unavailable."""
        voc = normalize_vocation(vocation, allow_no_voc=False)
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
        if loyalty < 0 or loyalty > 50 or loyalty % 5:
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

    @commands.command(usage="<current> <percentage> <target> <vocation> [loyalty]")
    async def magiclevel(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str,
                         loyalty: int = 0):
        """Calculates the training time required to reach a target magic level.

        It shows the needed mana, offline training time and exercise weapons needed."""
        voc = normalize_vocation(vocation, allow_no_voc=False)
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
        if loyalty < 0 or loyalty > 50 or loyalty % 5:
            return await ctx.error("Loyalty must be between 0 and 50, and a multiple of 5.")

        factor = MAGIC_FACTOR[voc]
        mana = self.get_mana_spent(current, percentage, target, factor, loyalty)
        loyalty_str = f" with a loyalty bonus of {loyalty}%." if loyalty else "."
        weapons = int(math.ceil(mana/MANA_PER_WEAPON))
        regen_seconds = mana/MANA_PER_SEC[voc]

        embed = discord.Embed(title="🔮 Magic Level Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From magic level {current} ({percentage}%) to {target} as a {voc}{loyalty_str}")
        try:
            embed.add_field(name="Offline training time",
                            value=f"{timing.HumanDelta.from_seconds(regen_seconds*2, True).long()}")
        except OverflowError:
            embed.add_field(name="Offline training time", value="Longer than what you will live.")
        embed.add_field(name="Exercise Dummies", value=self.get_weapon_usage_string(weapons))
        weapons = int(math.ceil(mana / (MANA_PER_WEAPON * 1.1)))
        embed.add_field(name="Expert Exercise Dummies", value=self.get_weapon_usage_string(weapons))

        embed.description = f"You need to spend **{mana:,}** mana to reach magic level {target}"
        await ctx.send(embed=embed)

    @commands.command(usage="<current> <percentage> <target> <vocation> [loyalty]")
    async def meleeskill(self, ctx: NabCtx, current: int, percentage: int, target: int, vocation: str,
                         loyalty: int = 0):
        """Calculates the training time required to reach a target skill level.

        It shows the needed hits, online training time and offline training time.
        For knights, it also shows exercise weapons needed.

        This only applies to axe, club and sword fighting."""
        if current >= target:
            return await ctx.error("Target skill must be greater than current skill.")
        if current < 10:
            return await ctx.error("Your current skill can't be lower than 10.")
        if target > 200:
            return await ctx.error("Your target skill can't be greater than 200.")
        if 0 > percentage >= 100:
            return await ctx.error("Percentage must be between 0 and 99.")
        if loyalty < 0 or loyalty > 50 or loyalty % 5:
            return await ctx.error("Loyalty must be between 0 and 50, and a multiple of 5.")
        voc = normalize_vocation(vocation, allow_no_voc=False)
        if not voc:
            return await ctx.error("Unknown vocation.")
        factor = MELEE_FACTOR[voc]
        hits = self.get_hits(current, percentage, target, factor, loyalty)

        loyalty_str = f" with a loyalty bonus of {loyalty}%." if loyalty else "."

        embed = discord.Embed(title="⚔ Melee Skill Calculator", colour=discord.Colour.teal())
        embed.set_footer(text=f"From skill level {current} ({percentage}%) to {target} as a {voc}{loyalty_str}")
        embed.description = f"You need **{hits:,}** hits to reach the target level."
        try:
            embed.add_field(name="Online training time",
                            value=f"{timing.HumanDelta.from_seconds(hits*2, True).long()}")
            embed.add_field(name="Offline training time",
                            value=f"{timing.HumanDelta.from_seconds(hits*4, True).long()}")
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

        The footer text shows the time in your timezone where your stamina would be at the target stamina."""
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

        target_str = "full" if target.hours == 42 else f"**{target.hours}:{target.minutes:02}**"
        reply = f"You need to rest **{remaining}** to get back to {target_str} stamina."
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send(reply)
            return

        embed = discord.Embed(description=reply)
        embed.set_footer(text="Full stamina")
        embed.colour = discord.Color.green()
        embed.timestamp = dt.datetime.utcnow() + dt.timedelta(seconds=resting_time)
        await ctx.send(embed=embed)

    @commands.group(usage="<level>,<vocation> | <character>", invoke_without_command=True, case_insensitive=True)
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
            char = await get_character(ctx.bot, params[0])
            if char is None:
                return await ctx.error(f"Character **{params[0]}** doesn't exist!")
            level = char.level
            vocation = char.vocation.value
        elif len(params) == 2:
            try:
                level = int(params[0])
                vocation = params[1].strip()
            except ValueError:
                try:
                    level = int(params[1])
                    vocation = params[0]
                except ValueError:
                    await ctx.send(invalid_arguments)
                    return
        else:
            return await ctx.error(invalid_arguments)
        if level <= 0:
            return await ctx.error("There's no level lower than 1, it doesn't matter how bad you are at Tibia.")
        if level >= 5000:
            return await ctx.error("Why do you care? You will __**never**__ reach this level 🙄")

        _vocation = normalize_vocation(vocation)
        if _vocation is None:
            return await ctx.error(f"That's not a valid vocation.")
        vocation = _vocation

        hp = tibia.get_hitpoints(level, vocation)
        mp = tibia.get_mana(level, vocation)
        cap = tibia.get_capacity(level, vocation)
        exp = tibia.get_experience_for_level(level)
        exp_tnl = tibia.get_experience_for_next_level(level)

        if vocation == "none":
            vocation = "with no vocation"
        if char:
            content = f"**{char.name}** is a level **{char.level}** {vocation.lower()}, {char.he_she.lower()} has:"
        else:
            content = f"A level **{level}** {normalize_vocation(vocation)}, has:"
        content += f"\n\t🔴 **{hp:,}** HP | 🔵 **{mp:,}** MP | ⚖ **{cap:,}** Capacity\n\t" \
            f"**{exp:,}** Experience\n\t**{exp_tnl:,}** to next level"
        await ctx.send(content)

    @stats.command(name="capacity", aliases=["cap"])
    async def stats_capacity(self, ctx: NabCtx, capacity: int):
        """Calculates the level required to reach the specified capacity.

        The levels needed for each vocation are shown."""
        if capacity <= 400:
            return await ctx.error("Capacity can't be lower than 400.")

        content = f"To reach **{capacity:,}** oz. capacity, you need at least the following levels per vocation:\n\t"
        content += " | ".join(f"**{tibia.get_level_by_capacity(capacity,voc)}** {emoji}" for (voc, emoji) in VOC_ITER)
        await ctx.send(content)

    @stats.command(name="hitpoints", aliases=["hp"])
    async def stats_hitpoints(self, ctx: NabCtx, hitpoints: int):
        """Calculates the level required to reach the specified hitpoints.

        The levels needed for each vocation are shown."""
        if hitpoints <= 150:
            return await ctx.error("Hitpoints can't be lower than 400.")
        content = f"To reach **{hitpoints:,}** hitpoints, you need at least the following levels per vocation:\n\t"
        content += " | ".join(f"**{tibia.get_level_by_hitpoints(hitpoints,voc)}** {emoji}" for (voc, emoji) in VOC_ITER)
        await ctx.send(content)

    @stats.command(name="mana", aliases=["mp"])
    async def stats_mana(self, ctx: NabCtx, mana: int):
        """Calculates the level required to reach the specified mana points.

        The levels needed for each vocation are shown."""
        if mana <= 55:
            return await ctx.error("Capacity can't be lower than 400.")
        content = f"To reach **{mana:,}** mana points, you need at least the following levels per vocation:\n\t"
        content += " | ".join(f"**{tibia.get_level_by_mana(mana,voc)}** {emoji}" for (voc, emoji) in VOC_ITER)
        await ctx.send(content)

    # endregion

    # region Auxiliary methods

    @classmethod
    def get_hits(cls, current, percentage, target, factor, loyalty=0):
        """Gets the amount of hits needed from a skill level to other."""
        hits = 0
        if target - current > 2:
            hits = sum(cls.melee_formula(factor, s) for s in range(current + 1, target))
        hits += int(cls.melee_formula(factor, target) * (1 - percentage / 100))
        hits *= (1 - loyalty/100)
        return int(hits)

    @classmethod
    def get_mana_spent(cls, current, percentage, target, factor, loyalty=0):
        """Gets the amount of mana needed to use to advance from a magic level to other."""
        mana = 0
        if target - current > 2:
            mana = sum(cls.magic_formula(factor, s) for s in range(current + 1, target))
        mana += int(cls.magic_formula(factor, target) * (1 - percentage / 100))
        mana *= (1 - loyalty/100)
        return int(mana)

    @classmethod
    def get_weapon_usage_string(cls, weapons):
        """Gets a string with details about the use of excerscise weapons.

        It includes number of weapons, cost in gold and cost in tibia coins as well as time needed."""
        content = f"You would need **{weapons:,}** exercise weapons.\n" \
            f"Costing **{EXERCISE_WEAPON_GP * weapons:,}** gold coins " \
            f"or **{EXERCISE_WEAPON_COIN * weapons:,}** tibia coins.\n"
        try:
            training_time = timing.HumanDelta.from_seconds(weapons * 500 * 2, True)
            content += f"Using them would take *{training_time.long()}*."
        except OverflowError:
            content += "You will be dead before you can use them all."
        return content

    @classmethod
    def magic_formula(cls, factor, skill):
        """The magic level formula to calculate the mana needed for next magic level."""
        return int(1600 * factor ** skill)

    @classmethod
    def melee_formula(cls, factor, skill):
        """The melee formula to calculate the number of hits for the next skill level."""
        return int((50 * factor**(skill-10)))

    # endregion


def setup(bot):
    bot.add_cog(Calculators(bot))
