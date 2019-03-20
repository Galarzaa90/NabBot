import datetime as dt
import io
import logging
import random
import re
import sqlite3
from collections import defaultdict
from contextlib import closing
from typing import Dict, List

import discord
import tibiawikisql
from discord.ext import commands
from tibiawikisql import models

from cogs import utils
from cogs.utils.converter import TibiaNumber
from nabbot import NabBot
from .utils import FIELD_VALUE_LIMIT, average_color, checks, config, join_list, split_params
from .utils.context import NabCtx
from .utils.database import wiki_db
from .utils.errors import CannotPaginate
from .utils.messages import split_message
from .utils.pages import Pages
from .utils.tibia import get_map_area, get_tibia_weekday

log = logging.getLogger("nabbot")

WIKI_CHARMS_ARTICLE = "Cyclopedia#List_of_Charms"
WIKI_ICON = "https://vignette.wikia.nocookie.net/tibia/images/b/bc/Wiki.png/revision/latest?path-prefix=en"

DIFFICULTIES = {
    "Harmless": config.difficulty_off_emoji * 4,
    "Trivial": config.difficulty_on_emoji + config.difficulty_off_emoji * 3,
    "Easy": config.difficulty_on_emoji * 2 + config.difficulty_off_emoji * 2,
    "Medium": config.difficulty_on_emoji * 3 + config.difficulty_off_emoji,
    "Hard": config.difficulty_on_emoji * 4
}
OCCURRENCES = {
    "Common": config.occurrence_on_emoji * 1 + config.occurrence_off_emoji * 3,
    "Uncommon": config.occurrence_on_emoji * 2 + config.occurrence_off_emoji * 2,
    "Rare": config.occurrence_on_emoji * 3 + config.occurrence_off_emoji * 1,
    "Very Rare": config.occurrence_on_emoji * 4,
}


class TibiaWiki(commands.Cog, utils.CogUtils):
    """Commands that show information about Tibia, provided by TibiaWiki.

    The information is read generated using [tibiawiki-sql](https://github.com/Galarzaa90/tibiawiki-sql)."""

    def __init__(self, bot: NabBot):
        self.bot = bot

    def cog_unload(self):
        log.info(f"{self.tag} Unloading cog")

    # region Commands
    @checks.can_embed()
    @commands.command(aliases=["achiev"])
    async def achievement(self, ctx: NabCtx, *, name: str):
        """Displays an achievement's information.

        Shows the achievement's grade, points, description, and instructions on how to unlock."""

        entries = self.search_entry("achievement", name)
        if not entries:
            await ctx.send("I couldn't find an achievement with that name.")
            return
        if len(entries) > 1:
            title = await ctx.choose([e["title"] for e in entries])
            if title is None:
                return
        else:
            title = entries[0]["title"]

        achievement: models.Achievement = self.get_entry(title, models.Achievement)

        embed = TibiaWiki.get_base_embed(achievement)
        embed.description = achievement.description
        embed.add_field(name="Grade", value="⭐" * int(achievement.grade))
        embed.add_field(name="Points", value=achievement.points)
        embed.add_field(name="Spoiler", value=f"||{achievement.spoiler}||", inline=True)

        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command(usage="[class]")
    async def bestiary(self, ctx: NabCtx, *, _class: str = None):
        """Displays a category's creatures or all the categories.

        If a category is specified, it will list all the creatures that belong to the category and their level.
        If no category is specified, it will list all the bestiary categories."""
        if _class is None:
            categories = self.get_bestiary_classes()
            entries = [f"**{name}** - {count} creatures" for name, count in categories.items()]
            description = ""
            title = "Bestiary Classes"
        else:
            creatures = self.get_bestiary_creatures(_class)
            if not creatures:
                await ctx.error("There's no class with that name.")
                return
            entries = [f"**{name}** - {level}" for name, level in creatures.items()]
            description = f"Use `{ctx.clean_prefix} monster <name>` to see more info"
            title = f"Creatures in the {_class.title()} class"

        pages = Pages(ctx, entries=entries, per_page=20 if await ctx.is_long() else 10, header=description)
        pages.embed.title = title
        pages.embed.set_author(name="TibiaWiki", icon_url=WIKI_ICON, url=tibiawikisql.api.BASE_URL)
        pages.embed.url = "https://tibia.fandom.com/wiki/Bestiary_Creature_Classes"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.can_embed()
    @commands.command(aliases=["charms"])
    async def charm(self, ctx: NabCtx, name: str = None):
        """Displays information about a charm.

        If no name is specified, displays a list of all charms for the user to choose from."""
        if name is None:
            embed = self.get_charms_embed(ctx)
            return await ctx.send(embed=embed)

        charm = models.Charm.get_by_field(wiki_db, "name", name, True)
        if charm is None:
            embed = self.get_charms_embed(ctx)
            return await ctx.error("There's no charm with that name, try one of these:", embed=embed)
        embed = await self.get_charm_embed(charm)
        await self.send_embed_with_image(charm, ctx, embed, True, extension="png")

    @checks.can_embed()
    @commands.command(aliases=["imbue"], usage="<name>[,price1[,price2[,price3]]][,tokenprice]")
    async def imbuement(self, ctx: NabCtx, *, params: str):
        """Displays information about an imbuement.

        You can optionally provide prices for the materials, in the order of the tier they belong to.
        Additionally, for Vampirism, Void and Strike imbuements, you can provide the price for gold tokens.

        The total cost will be calculated, as well as the hourly cost.
        If applicable, it will show the cheapest way to get it using gold tokens.

        It can also accept prices using the 'k' suffix, e.g. 1.5k
        """
        params = split_params(params)
        if len(params) > 5:
            await ctx.send(f"{ctx.tick(False)} Invalid syntax. The correct syntax is: `{ctx.usage}`.")
            return

        try:
            prices = [TibiaNumber(p) for p in params[1:]]
        except commands.BadArgument:
            await ctx.send(f"{ctx.tick(False)} Invalid syntax. The correct syntax is: `{ctx.usage}`.")
            return

        name = params[0]

        entries = self.search_entry("imbuement", name)
        if not entries:
            await ctx.send("I couldn't find an imbuement with that name.")
            return
        if len(entries) > 1:
            title = await ctx.choose([e["title"] for e in entries])
            if title is None:
                return
        else:
            title = entries[0]["title"]

        imbuement: models.Imbuement = self.get_entry(title, models.Imbuement)

        embed = self.get_imbuement_embed(ctx, imbuement, prices)
        await self.send_embed_with_image(imbuement, ctx, embed, True)

    @checks.can_embed()
    @commands.command(aliases=["itemprice"])
    async def item(self, ctx: NabCtx, *, name: str):
        """Displays information about an item.

        Shows who buys and sells the item, what creatures drops it and many attributes.

        The embed is colored if a major loot NPC buys it, so it can be noted at quick glance.
        Yellow for Rashid, Blue and Green for Djinns and Purple for gems.

        More information is shown if used in private messages or in the command channel."""
        entries = self.search_entry("item", name)
        if not entries:
            await ctx.send("I couldn't find an item with that name.")
            return
        if len(entries) > 1:
            title = await ctx.choose([e["title"] for e in entries])
            if title is None:
                return
        else:
            title = entries[0]["title"]

        item: models.Item = self.get_entry(title, models.Item)

        embed = await self.get_item_embed(ctx, item, await ctx.is_long())
        await self.send_embed_with_image(item, ctx, embed)

    @checks.can_embed()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def key(self, ctx: NabCtx, number: str):
        """Displays information about a key.

        Shows the key's known names, how to obtain it and its uses."""
        if number is None:
            await ctx.send("Tell me the number of the key you want to check.")
            return

        try:
            number = int(number)
        except ValueError:
            await ctx.send("Tell me a numeric value, to search keys, try: `/key search`")
            return

        key: models.Key = models.Key.get_by_field(wiki_db, "number", number)
        if not key:
            return await ctx.send("There's no key with that number.")
        embed = self.get_key_embed(key)

        # Attach key's image only if the bot has permissions
        if key.item_id:
            item = models.Item.get_by_field(wiki_db, "article_id", key.item_id)
            return await self.send_embed_with_image(item, ctx, embed, True)
        await ctx.send(embed=embed)

    @checks.can_embed()
    @key.command(name="search")
    async def key_search(self, ctx: NabCtx, *, term: str):
        """Searches for a key by keywords.

        Search for matches on the key's names, location, origin or uses.

        if there are multiple matches, a list is shown.
        If only one matches, the key's information is shwon directly."""
        keys = self.search_key(term)

        if keys is None:
            await ctx.send("I couldn't find any related keys.")
            return

        if len(keys) > 1:
            embed = discord.Embed(title="Possible keys")
            embed.set_author(name="TibiaWiki", url=tibiawikisql.api.BASE_URL, icon_url=WIKI_ICON)
            embed.description = ""
            for key in keys:
                name = f" - {key['name']}" if key["name"] else ""
                embed.description += f"\n**Key {key['number']}**{name}"
            await ctx.send(embed=embed)
            return

        await ctx.invoke(self.bot.all_commands.get('key'), keys[0]["number"])

    @checks.can_embed()
    @commands.command(aliases=['mob', 'creature'])
    async def monster(self, ctx: NabCtx, *, name: str):
        """Displays information about a monster.

        Shows the monster's attributes, resistances, loot and more.

        More information is displayed if used on a private message or in the command channel."""
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

        entries = self.search_entry("creature", name)
        if not entries:
            await ctx.send("I couldn't find a monster with that name.")
            return
        if len(entries) > 1:
            title = await ctx.choose([e["title"] for e in entries])
            if title is None:
                return
        else:
            title = entries[0]["title"]

        monster = self.get_entry(title, models.Creature)
        embed = await self.get_monster_embed(ctx, monster, await ctx.is_long())
        await self.send_embed_with_image(monster, ctx, embed, True)

    @checks.can_embed()
    @commands.command()
    async def npc(self, ctx: NabCtx, *, name: str):
        """Displays information about a NPC.

        Shows the NPC's item offers, their location and their travel destinations.

        More information is displayed if used on private messages or the command channel."""
        entries = self.search_entry("npc", name)
        if not entries:
            await ctx.send("I couldn't find an NPC with that name.")
            return
        if len(entries) > 1:
            title = await ctx.choose([e["title"] for e in entries])
            if title is None:
                return
        else:
            title = entries[0]["title"]

        npc: models.Npc = self.get_entry(title, models.Npc)

        embed = await self.get_npc_embed(ctx, npc, await ctx.is_long())
        # Attach spell's image only if the bot has permissions
        if ctx.bot_permissions.attach_files:
            files = []
            if npc.image is not None:
                thumbnail = io.BytesIO(npc.image)
                filename = re.sub(r"[^A-Za-z0-9]", "", npc.name) + ".gif"
                embed.set_thumbnail(url=f"attachment://{filename}")
                files.append(discord.File(thumbnail, filename))
            if None not in [npc.x, npc.y, npc.z]:
                map_filename = re.sub(r"[^A-Za-z0-9]", "", npc.name) + "-map.png"
                map_image = io.BytesIO(get_map_area(npc.x, npc.y, npc.z))
                embed.set_image(url=f"attachment://{map_filename}")
                embed.add_field(name="Location", value=f"[Mapper link]({self.get_mapper_link(npc.x, npc.y, npc.z)})",
                                inline=False)
                files.append(discord.File(map_image, map_filename))
            await ctx.send(files=files, embed=embed)
        else:
            await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command()
    async def rashid(self, ctx: NabCtx):
        """Shows where Rashid is today.

        For more information, use `npc Rashid`."""
        rashid = self.get_rashid_position()
        npc = models.Npc.get_by_field(wiki_db, "name", "Rashid")
        embed = TibiaWiki.get_base_embed(npc)
        embed.colour = discord.Colour.greyple()
        embed.description = f"Rashid is in **{rashid.city}** today."
        embed.set_footer(text=rashid.location)
        if ctx.bot_permissions.attach_files:
            files = []
            if npc.image is not None:
                thumbnail = io.BytesIO(npc.image)
                filename = re.sub(r"[^A-Za-z0-9]", "", npc.name) + ".gif"
                embed.set_thumbnail(url=f"attachment://{filename}")
                files.append(discord.File(thumbnail, filename))
            if None not in [rashid.x, rashid.y, rashid.z]:
                map_filename = re.sub(r"[^A-Za-z0-9]", "", npc.name) + "-map.png"
                map_image = io.BytesIO(get_map_area(rashid.x, rashid.y, rashid.z))
                embed.set_image(url=f"attachment://{map_filename}")
                embed.add_field(name="Location", value=f"[Mapper link]"
                                                       f"({self.get_mapper_link(rashid.x,rashid.y,rashid.z)})",
                                inline=False)
                files.append(discord.File(map_image, map_filename))
            return await ctx.send(files=files, embed=embed)
        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command(usage="<name|words>")
    async def spell(self, ctx: NabCtx, *, name: str):
        """Displays information about a spell.

        Shows the spell's attributes, NPCs that teach it and more.

        More information is displayed if used on private messages or the command channel."""
        spell = models.Spell.get_by_field(wiki_db, "title", name, True)
        if spell is None:
            spell = models.Spell.get_by_field(wiki_db, "words", name, True)
        if spell is None:
            entries = self.search_entry("spell", name, additional_field="words")
            if not entries:
                await ctx.send("I couldn't find a spell with that name or words.")
                return
            if len(entries) > 1:
                titles = ["{title} ({words})".format(**e) for e in entries]
                title = await ctx.choose(titles)
                if title is None:
                    return
                title = entries[titles.index(title)]["title"]
            else:
                title = entries[0]["title"]
            spell: models.Spell = self.get_entry(title, models.Spell)
        embed = await self.get_spell_embed(ctx, spell, await ctx.is_long())
        await self.send_embed_with_image(spell, ctx, embed)

    @checks.can_embed()
    @commands.command(aliases=["wikiinfo"])
    async def wikistats(self, ctx: NabCtx):
        """Shows information about the TibiaWiki database."""
        embed = discord.Embed(colour=discord.Colour.blurple(), title="TibiaWiki database statistics", description="")
        embed.set_thumbnail(url=WIKI_ICON)
        version = ""
        gen_date = None
        with closing(wiki_db.cursor()) as c:
            info = c.execute("SELECT * FROM database_info").fetchall()
            for entry in info:
                if entry['key'] == "version":
                    version = f" v{entry['value']}"
                if entry['key'] == "timestamp":
                    gen_date = float(entry['value'])
            nb_space = '\u00a0'
            embed.description += f"**‣ Achievements:** {self.count_table('achievement'):,}"
            embed.description += f"\n**‣ Charms:** {self.count_table('charm'):,}"
            embed.description += f"\n**‣ Creatures:** {self.count_table('creature'):,}"
            embed.description += f"\n**{nb_space*8}‣ Drops:** {self.count_table('creature_drop'):,}"
            embed.description += f"\n**‣ Houses:** {self.count_table('house'):,}"
            embed.description += f"\n**‣ Imbuements:** {self.count_table('imbuement'):,}"
            embed.description += f"\n**‣ Items:** {self.count_table('item'):,}"
            embed.description += f"\n**{nb_space*8}‣ Attributes:** {self.count_table('item_attribute'):,}"
            embed.description += f"\n**‣ Keys:** {self.count_table('item_key'):,}"
            embed.description += f"\n**‣ NPCs:** {self.count_table('npc'):,}"
            embed.description += f"\n**{nb_space*8}‣ Buy offers:** {self.count_table('npc_offer_buy'):,}"
            embed.description += f"\n**{nb_space*8}‣ Sell offers:** {self.count_table('npc_offer_sell'):,}"
            embed.description += f"\n**{nb_space*8}‣ Destinations:** {self.count_table('npc_destination'):,}"
            embed.description += f"\n**{nb_space*8}‣ Spell offers:** {self.count_table('npc_spell'):,}"
            embed.description += f"\n**‣ Quests:** {self.count_table('quest'):,}"
            embed.description += f"\n**‣ Spells:** {self.count_table('spell'):,}"
        embed.set_footer(text=f"Database generation date")
        embed.timestamp = dt.datetime.utcfromtimestamp(gen_date)
        embed.set_author(name=f"tibiawiki-sql{version}", icon_url="https://github.com/fluidicon.png",
                         url="https://github.com/Galarzaa90/tibiawiki-sql")
        await ctx.send(embed=embed)
    # endregion

    # region Helper Methods
    @classmethod
    def count_table(cls, table):
        try:
            c = wiki_db.execute("SELECT COUNT(*) as count FROM %s" % table)
            result = c.fetchone()
            if not result:
                return 0
            return int(result["count"])
        except sqlite3.OperationalError:
            return 0

    @classmethod
    def get_charms_embed(cls, ctx: NabCtx):
        charms = models.Charm.search(wiki_db, sort_by="type")
        charms_url = f"{tibiawikisql.api.BASE_URL}/wiki/{WIKI_CHARMS_ARTICLE}"
        embed = discord.Embed(title="Charms", url=charms_url)
        embed.set_author(name="TibiaWiki", url=tibiawikisql.api.BASE_URL, icon_url=WIKI_ICON)
        charm_fields = dict()
        for charm in charms:  # type: models.Charm
            if not charm_fields.get(charm.type):
                charm_fields[charm.type] = ""
            charm_fields[charm.type] += f"\n**{charm.name}** - {charm.points:,}"
        for _type, content in charm_fields.items():
            embed.add_field(name=_type, value=content.strip())
        embed.set_footer(text=f"Use {ctx.clean_prefix}{ctx.invoked_with} <name> to see more information.")
        return embed

    @classmethod
    async def send_embed_with_image(cls, entity, ctx, embed, apply_color=False, extension="gif"):
        if ctx.bot_permissions.attach_files and entity.image:
            thumbnail = io.BytesIO(entity.image)
            filename = f"thumbnail.{extension}"
            embed.set_thumbnail(url=f"attachment://{filename}")
            if apply_color:
                main_color = await ctx.execute_async(average_color, entity.image)
                embed.color = discord.Color.from_rgb(*main_color)
            await ctx.send(file=discord.File(thumbnail, f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=embed)

    @classmethod
    async def get_charm_embed(cls, charm: models.Charm):
        charms_url = f"{tibiawikisql.api.BASE_URL}/wiki/{WIKI_CHARMS_ARTICLE}"
        embed = discord.Embed(title=charm.name, url=charms_url)
        embed.set_author(name="TibiaWiki", url=charms_url, icon_url=WIKI_ICON)
        embed.description = f"**Type**: {charm.type} | **Cost**: {charm.points:,} points"
        embed.add_field(name="Description", value=charm.description)
        return embed

    @classmethod
    def get_base_embed(cls, article, alternate_title="") -> discord.Embed:
        """ Builds the base embed for TibiaWiki articles.

        :param article: The article to display, must be a subclass of Article.
        :param alternate_title: Alternate title to display instead of the article's title.
        :return: The embed object.
        """
        embed = discord.Embed(title=alternate_title if alternate_title else article.title, url=article.url)
        embed.set_author(name="TibiaWiki", icon_url=WIKI_ICON, url=tibiawikisql.api.BASE_URL)
        return embed

    @classmethod
    def get_bestiary_classes(cls) -> Dict[str, int]:
        """Gets all the bestiary classes

        :return: The classes and how many creatures it has.
        """
        rows = wiki_db.execute("SELECT DISTINCT bestiary_class, count(*) as count "
                               "FROM creature WHERE bestiary_class not NUll "
                               "GROUP BY bestiary_class ORDER BY bestiary_class")
        classes = {}
        for r in rows:
            classes[r["bestiary_class"]] = r["count"]
        return classes

    @classmethod
    def get_bestiary_creatures(cls, _class: str) -> Dict[str, str]:
        """Gets the creatures that belong to a bestiary class

        :param _class: The name of the class.
        :return: The creatures in the class, with their difficulty level.
        """
        rows = wiki_db.execute("""
            SELECT title, bestiary_level
            FROM creature
            WHERE bestiary_class LIKE ?
            ORDER BY
                CASE bestiary_level
                    WHEN "Trivial" THEN 0
                    WHEN "Easy" THEN 1
                    WHEN "Medium" THEN 2
                    WHEN "Hard" THEN 3
                END
            """, (_class,))
        creatures = {}
        for r in rows:
            creatures[r["title"]] = r["bestiary_level"]
        return creatures

    @classmethod
    def get_key_embed(cls, key: models.Key):
        if key is None:
            return None
        embed = cls.get_base_embed(key)
        if key.name:
            embed.description = f"**Also known as:** {key.name}"
        if key.location:
            embed.add_field(name="Location", value=key.location)
        if key.origin is not None:
            embed.add_field(name="Origin", value=key.origin)
        if key.name is not None:
            embed.add_field(name="Notes/Use", value=key.notes)
        return embed

    @classmethod
    def get_imbuement_embed(cls, ctx: NabCtx, imbuement: models.Imbuement,  prices):
        """Gets the item embed to show in /item command"""
        embed = cls.get_base_embed(imbuement)
        embed.add_field(name="Effect", value=imbuement.effect)
        if not prices:
            embed.set_footer(text=f"Provide material prices to calculate costs."
                                  f" More info: {ctx.clean_prefix}help {ctx.invoked_with}")
        elif len(prices) < len(imbuement.materials):
            embed.set_footer(text="Not enough material prices provided for this tier.")
            prices = []
        materials = cls.get_imbuement_embed_parse_materials(imbuement, prices)
        if not prices:
            embed.add_field(name="Materials", value=materials)
            return embed
        fees = [5000, 25000, 100000]  # Gold fees for each tier
        fees_100 = [15000, 55000, 150000]  # Gold fees for each tier with 100% chance
        tiers = {"Basic": 0, "Intricate": 1, "Powerful": 2}  # Tiers order
        tokens = [2, 4, 6]  # Token cost for materials of each tier
        tier = tiers[imbuement.tier]  # Current tier
        token_imbuements = ["Vampirism", "Void", "Strike"]  # Imbuements that can be bought with gold tokens

        tier_prices = []  # The total materials cost for each tier
        materials_cost = 0  # The cost of all materials for the current tier
        for m, p in zip(imbuement.materials, prices):
            materials_cost += m.amount * p
            tier_prices.append(materials_cost)

        def parse_prices(_tier: int, _materials: int):
            return f"**Materials:** {_materials:,} gold.\n" \
                   f"**Total:** {_materials+fees[_tier]:,} gold | " \
                   f"{(_materials+fees[_tier])/20:,.0f} gold/hour\n" \
                   f"**Total  (100% chance):** {_materials+fees_100[_tier]:,} gold | " \
                   f"{(_materials+fees_100[_tier])/20:,.0f} gold/hour"
        # If no gold token price was provided or the imbuement type is not applicable, just show material cost
        if len(prices)-1 <= tier or imbuement.type not in token_imbuements:
            embed.add_field(name="Materials", value=materials)
            embed.add_field(name="Cost", value=parse_prices(tier, materials_cost), inline=False)
            if imbuement.type in token_imbuements:
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
                                               f"{imbuement.type}** with gold tokens and buying the rest is "
                                               f"cheaper.\n\n{parse_prices(tier, total_cost)}",
                            inline=False)
        return embed

    @classmethod
    def get_imbuement_embed_parse_materials(cls, imbuement, prices):
        content = ""
        for i, material in enumerate(imbuement.materials):
            price = ""
            if prices:
                price = f" ({prices[i]:,} gold each)"
            content += "\nx{0.amount} {0.item_title}{1}".format(material, price)
        return content

    async def get_item_embed(self, ctx: NabCtx, item: models.Item, long):
        """Gets the item embed to show in /item command"""
        short_limit = 5
        long_limit = 40

        embed = self.get_base_embed(item)
        embed.description = item.flavor_text
        await self.get_item_embed_parse_properties(embed, item)

        too_long = self.get_item_embed_parse_offers(embed, item.sold_by, "Sold", long, short_limit)
        too_long |= self.get_item_embed_parse_offers(embed, item.bought_by, "Bought", long, short_limit, True)
        too_long |= self.get_item_embed_parse_rewards(embed, item.awarded_in, long, short_limit)
        too_long |= self.get_item_embed_parse_loot(embed, item.dropped_by, long, long_limit, short_limit)

        if too_long and not long:
            ask_channel = await ctx.ask_channel_name()
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        return embed

    # region Item Embed Submethods
    @classmethod
    async def get_item_embed_parse_properties(cls, embed, item: models.Item):
        properties = f"Weight: {item.weight} oz"
        for attribute in item.attributes:  # type: models.ItemAttribute
            value = attribute.value
            if attribute.name in ["imbuements"]:
                continue
            if attribute.name == "vocation":
                value = ", ".join(attribute.value.title().split("+"))
            properties += f"\n{attribute.name.replace('_', ' ').title()}: {value}"
        embed.add_field(name="Properties", value=properties)
        imbuement_attribute = discord.utils.get(item.attributes, name="imbuements")
        if imbuement_attribute:
            embed.add_field(name="Used for", value=imbuement_attribute.value)

    @classmethod
    def get_item_embed_parse_loot(cls, embed, item_drops, long, long_limit, short_limit):
        if not item_drops:
            return False
        too_long = True
        name = "Dropped by"
        count = 0
        value = ""
        for drop in item_drops:  # type: models.CreatureDrop
            count += 1
            creature = {"name": drop.creature_title}
            if drop.chance is None:
                creature["chance"] = "??.??%"
            elif drop.chance >= 100:
                creature["chance"] = "Always"
            else:
                creature["chance"] = f"{drop.chance:05.2f}%"
            value += "\n`{chance} {name}`".format(**creature)
            if count >= short_limit and not long:
                value += "\n*...And {0} others*".format(len(item_drops) - short_limit)
                too_long = True
                break
            if long and count >= long_limit:
                value += "\n*...And {0} others*".format(len(item_drops) - long_limit)
                break
        embed.add_field(name=name, value=value, inline=not long)
        return too_long

    @classmethod
    def get_item_embed_parse_rewards(cls, embed, quest_rewards, long, short_limit):
        if not quest_rewards:
            return False
        value = ""
        count = 0
        name = "Awarded in"
        too_long = False
        for quest in quest_rewards:  # type: models.QuestReward
            count += 1
            value += "\n" + quest.quest_title
            if count >= short_limit and not long:
                value += "\n*...And {0} others*".format(len(quest_rewards) - short_limit)
                too_long = True
                break
        embed.add_field(name=name, value=value)
        return too_long

    @classmethod
    def get_item_embed_adjust_city(cls, name, city, embed):
        name = name.lower()
        if name == 'alesar' or name == 'yaman':
            embed.colour = discord.Colour.green()
            return "Green Djinn's Fortress"
        elif name == "nah'bob" or name == "haroun":
            embed.colour = discord.Colour.blue()
            return "Blue Djinn's Fortress"
        elif name == 'rashid':
            embed.colour = discord.Colour(0xF0E916)
            return cls.get_rashid_position().city
        elif name == 'yasir':
            return 'his boat'
        elif name == 'briasol':
            embed.colour = discord.Colour(0xA958C4)
        return city

    @classmethod
    def get_item_embed_parse_offers(cls, embed, offers, label, long, short_limit, adjust_color=False):
        too_long = False
        if not offers:
            return too_long
        item_value = 0
        currency = ""
        count = 0
        value = ""
        for i, offer in enumerate(offers):  # type: models.NpcSellOffer
            if i == 0:
                item_value = offer.value
                currency = offer.currency_title
            if offer.value != item_value:
                break
            city = cls.get_item_embed_adjust_city(offer.npc_title, offer.npc_city, embed if adjust_color else discord.Embed())
            value += f"\n{offer.npc_title} ({city})"
            count += 1
            if count > short_limit and not long:
                value += "\n*...And {0} others*".format(len(offers) - short_limit)
                too_long = True
                break
        embed.add_field(name=f"{label} for {item_value:,} {currency} by", value=value)
        return too_long
    # endregion

    @classmethod
    async def get_monster_embed(cls, ctx: NabCtx, monster: models.Creature, long):
        """Gets the monster embeds to show in /mob command
        The message is split in two embeds, the second contains loot only and is only shown if long is True"""
        embed = cls.get_base_embed(monster)
        cls.get_monster_embed_description(embed, monster)
        cls.get_monster_embed_attributes(embed, monster, ctx)
        cls.get_monster_embed_elemental_modifiers(embed, monster)
        cls.get_monster_embed_bestiary_info(embed, monster)
        cls.get_monster_embed_damage(embed, monster, long)
        cls.get_monster_embed_field_walking(embed, monster)
        embed.add_field(name="Abilities", value=monster.abilities, inline=False)
        cls.get_monster_embed_loot(embed, monster, long)
        await cls.get_monster_embed_footer(ctx, monster, embed, long)
        return embed

    # region Monster Embed Submethods
    @classmethod
    def get_monster_embed_field_walking(cls, embed, monster: models.Creature):
        content = cls.get_monster_embed_parse_walking(monster, "Through: ", "walks_through")
        content += "\n"+cls.get_monster_embed_parse_walking(monster, "Around: ", "walks_around")
        if content.strip():
            embed.add_field(name="Field Walking", value=content.strip(), inline=True)

    @classmethod
    async def get_monster_embed_footer(cls, ctx, monster: models.Creature, embed, long):
        if monster.loot and not long:
            ask_channel = await ctx.ask_channel_name()
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))

    @classmethod
    def get_monster_embed_parse_walking(cls, monster: models.Creature, walk_field_name, attribute_name):
        """Adds the embed field describing which elemnts the monster walks around or through."""
        attribute_value = getattr(monster, attribute_name)
        field_types = ["poison", "fire", "energy"]
        content = ""
        if attribute_value:
            content = walk_field_name
            if config.use_elemental_emojis:
                walks_elements = []
                for element in field_types:
                    if element not in attribute_value.lower():
                        continue
                    walks_elements.append(element)
                for element in walks_elements:
                    content += f"{config.elemental_emojis[element]}"
            else:
                content += attribute_value
        return content

    @classmethod
    def get_monster_embed_damage(cls, embed, monster, long):
        if long or not monster.loot:
            embed.add_field(name="Max damage",
                            value=f"{monster.max_damage:,}" if monster.max_damage else "???")

    @classmethod
    def get_monster_embed_loot(cls, embed, monster, long):
        if monster.loot and long:
            split_loot = cls.get_monster_embed_parse_loot(monster.loot)
            for loot in split_loot:
                if loot == split_loot[0]:
                    name = "Loot"
                else:
                    name = "\u200F"
                embed.add_field(name=name, value="`" + loot + "`")

    @classmethod
    def get_monster_embed_parse_loot(cls, loot: List[models.CreatureDrop]):
        loot_string = ""
        for drop in loot:
            item = {"name": drop.item_title}
            if drop.chance is None:
                item["chance"] = "??.??%"
            elif drop.chance >= 100:
                item["chance"] = "Always"
            else:
                item["chance"] = f"{drop.chance:05.2f}%"
            if drop.max > 1:
                item["count"] = f"({drop.min}-{drop.max})"
            else:
                item["count"] = ""
            loot_string += "{chance} {name} {count}\n".format(**item)
        return split_message(loot_string, FIELD_VALUE_LIMIT - 20)

    @classmethod
    def get_monster_embed_bestiary_info(cls, embed, monster: models.Creature):
        if monster.bestiary_class:
            bestiary_info = monster.bestiary_class
            if monster.bestiary_level:
                difficulty = DIFFICULTIES.get(monster.bestiary_level, f"({monster.bestiary_level})")
                bestiary_info += f"\n{difficulty}"
                if monster.bestiary_occurrence is not None:
                    bestiary_info += f"\n{OCCURRENCES.get(monster.bestiary_occurrence, monster.bestiary_occurrence)}"
                bestiary_info += f"\n{monster.bestiary_kills:,} kills | {monster.charm_points}{config.charms_emoji}"
            embed.add_field(name="Bestiary Class", value=bestiary_info)

    @classmethod
    def get_monster_embed_elemental_modifiers(cls, embed, monster: models.Creature):
        # Iterate through elemental types
        if monster:
            content = ""
            for element, value in monster.elemental_modifiers.items():
                # TODO: Find icon for drown damage
                try:
                    if value is None or value == 100:
                        continue
                    value -= 100
                    if config.use_elemental_emojis:
                        content += f"\n{config.elemental_emojis[element]} {value:+}%"
                    else:
                        content += f"\n{value:+}% {element.title()}"
                except KeyError:
                    pass
            embed.add_field(name="Elemental modifiers", value=content)

    @classmethod
    def get_monster_embed_attributes(cls, embed, monster, ctx):
        attributes = {"summon_cost": "Summonable",
                      "convince_cost": "Convinceable",
                      "illusionable": "Illusionable",
                      "pushable": "Pushable",
                      "paralysable": "Paralysable",
                      "sees_invisible": "Sees Invisible"
                      }
        attributes = "\n".join([f"{ctx.tick(getattr(monster, x))} {repl}" for x, repl in attributes.items()
                                if getattr(monster, x) is not None])
        embed.add_field(name="Attributes", value=attributes or "Unknown")

    @classmethod
    def get_monster_embed_description(cls, embed, monster: models.Creature):
        hp = f"{monster.hitpoints:,}" if monster.hitpoints else "?"
        speed = f"{monster.speed:,}" if monster.speed else "?"
        experience = f"{monster.experience:,}" if monster.experience else "?"
        embed.description = f"**HP:** {hp} | **Exp:** {experience} | **Speed:** {speed}"
        if monster.armor:
            embed.description += f" | **Armor** {monster.armor}"
    # endregion

    @classmethod
    async def get_npc_embed(cls, ctx: NabCtx, npc: models.Npc, long):
        """Gets the embed to show in /npc command"""
        short_limit = 5
        long_limit = 50
        too_long = False

        embed = cls.get_base_embed(npc)
        cls.get_npc_embed_parse_basic_info(embed, npc)
        too_long |= cls.get_npc_embed_parse_offers(embed, npc.sell_offers, long, long_limit, short_limit, "Selling")
        too_long |= cls.get_npc_embed_parse_offers(embed, npc.buy_offers, long, long_limit, short_limit, "Buying")
        if npc.destinations:
            value = ""
            for destination in npc.destinations:  # type: models.NpcDestination
                value += "\n{0.name} \u2192 {0.price} gold".format(destination)
            embed.add_field(name="Destinations", value=value)
        too_long |= await cls.get_npc_embed_parse_spells(embed, npc.teaches, long, short_limit)
        if too_long:
            ask_channel = await ctx.ask_channel_name()
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        return embed

    # region NPC submethods
    @classmethod
    def get_npc_embed_parse_basic_info(cls, embed, npc):
        embed.add_field(name="Job", value=npc.job)
        if npc.name == "Rashid":
            rashid = cls.get_rashid_position()
            npc.city = rashid.city
            npc.x = rashid.x
            npc.y = rashid.y
            npc.z = rashid.z
        if npc.name == "Yasir":
            npc.x = None
            npc.y = None
            npc.z = None
        embed.add_field(name="City", value=npc.city)

    @classmethod
    def get_npc_embed_parse_offers(cls, embed, offers, long, long_limit, short_limit, label):
        if not offers:
            return False
        too_long = False
        count = 0
        value = ""
        for offer in offers:
            count += 1
            currency = offer.currency_title.replace("Gold Coin", "gold")
            value += "\n{0.item_title} \u2192 {0.value:,} {1}".format(offer, currency)
            if count > short_limit and not long:
                value += "\n*...And {0} others*".format(len(offers) - short_limit)
                too_long = True
                break
            if long and count > long_limit:
                value += "\n*...And {0} others*".format(len(offers) - long_limit)
                break
        split_selling = split_message(value, FIELD_VALUE_LIMIT)
        for value in split_selling:
            if value == split_selling[0]:
                name = label
            else:
                name = "\u200F"
            embed.add_field(name=name, value=value)
        return too_long

    @classmethod
    async def get_npc_embed_parse_spells(cls, embed, spells: List[models.NpcSpell], long, short_limit):
        vocs = ["knight", "sorcerer", "paladin", "druid"]
        too_long = False
        values = defaultdict(str)
        count = defaultdict(int)
        skip = defaultdict(bool)
        for spell in spells:
            value = f"\n{spell.spell_title} \u2014 {spell.price:,} gold"
            for voc in vocs:
                if skip[voc] or not getattr(spell, voc):
                    continue
                values[voc] += value
                count[voc] += 1
                if count[voc] >= short_limit and not long:
                    values[voc] += "\n*...And more*"
                    too_long = True
                    skip[voc] = True
        for voc, content in values.items():
            fields = split_message(content, FIELD_VALUE_LIMIT)
            for i, split_field in enumerate(fields):
                name = f"Teaches ({voc.title()}s)" if i == 0 else "\u200F"
                embed.add_field(name=name, value=split_field, inline=not len(fields) > 1)
        return too_long

    # endregion

    @classmethod
    async def get_spell_embed(cls, ctx: NabCtx, spell: models.Spell, long):
        """Gets the embed to show in /spell command"""
        short_limit = 5
        words = spell.words
        if "exani hur" in spell.words:
            words = "exani hur up|down"

        embed = cls.get_base_embed(spell, f"{spell.title} ({words})")
        premium = "**premium** " if spell.premium else ""
        mana = spell.mana if spell.mana else "variable"
        voc_list = list()
        if spell.knight:
            voc_list.append("knights")
        if spell.paladin:
            voc_list.append("paladins")
        if spell.druid:
            voc_list.append("druids")
        if spell.sorcerer:
            voc_list.append("sorcerers")
        vocs = join_list(voc_list, ", ", " and ")

        description = f"A {premium}spell for level **{spell.level}** and up. " \
                      f"It uses **{mana}** mana. It can be used by {vocs}"

        if spell.price == 0:
            description += "\nIt can be obtained for free."
        else:
            description += f"\nIt can be bought for {spell.price:,} gold coins."
        embed.description = description

        too_long = await cls.get_spell_embed_parse_teachers(embed, spell.taught_by, long, short_limit, voc_list, vocs)
        # Set embed color based on element:
        element_color = {
            "Fire": discord.Colour(0xFF9900),
            "Ice": discord.Colour(0x99FFFF),
            "Energy": discord.Colour(0xCC33FF),
            "Earth": discord.Colour(0x00FF00),
            "Holy": discord.Colour(0xFFFF00),
            "Death": discord.Colour(0x990000),
            "Physical": discord.Colour(0xF70000),
            "Bleed": discord.Colour(0xF70000),
        }
        elemental_emoji = ""
        if spell.element in element_color:
            embed.colour = element_color[spell.element]
            if spell.element == "Bleed":
                spell.element = "Physical"
            if config.use_elemental_emojis:
                elemental_emoji = config.elemental_emojis[spell.element.lower()]
        effect = f"\n\n{elemental_emoji}{spell.effect}"
        embed.description += effect
        if too_long:
            ask_channel = await ctx.ask_channel_name()
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))

        return embed

    @classmethod
    async def get_spell_embed_parse_teachers(cls, embed, teachers: List[models.NpcSpell], long, short_limit, voc_list,
                                             vocs):
        if not teachers:
            return False
        too_long = False
        for voc in voc_list:
            value = ""
            name = "Sold by ({0})".format(voc.title())
            if len(vocs) == 1:
                name = "Sold by"
            count = 0
            for npc in teachers:
                if not getattr(npc, voc[:-1]):
                    continue
                count += 1
                value += f"\n{npc.npc_title} ({npc.npc_city})"
                if count >= short_limit and not long:
                    value += "\n*...And more*"
                    too_long = True
                    break
            if value:
                embed.add_field(name=name, value=value)
        return too_long

    @classmethod
    def search_entry(cls, table, term, *, additional_field=""):
        if additional_field:
            query = """SELECT article_id, title, name, %s FROM %s
                       WHERE title LIKE ? or %s LIKE ?
                       ORDER BY LENGTH(title) ASC LIMIT 15
                       """ % (additional_field, table, additional_field)
            params = ("%%%s%%" % term, "%%%s%%" % term)
        else:
            query = "SELECT article_id, title, name FROM %s WHERE title LIKE ? ORDER BY LENGTH(title) ASC LIMIT 15" % \
                     table
            params = ("%%%s%%" % term,)
        c = wiki_db.execute(query, params)
        results = c.fetchall()
        if not results:
            return []
        if results[0]["title"].lower() == term.lower() or \
                (additional_field and results[0][additional_field].lower() == term.lower()):
            return [dict(results[0])]
        return [dict(r) for r in results]

    @classmethod
    def search_key(cls, terms):
        """Returns a dictionary containing a NPC's info, a list of possible matches or None"""
        c = wiki_db.cursor()
        try:
            # search query
            c.execute("SELECT article_id, number, name FROM item_key "
                      "WHERE name LIKE ? OR notes LIKE ? or origin LIKE ? LIMIT 10 ",
                      ("%" + terms + "%",) * 3)
            result = c.fetchall()
            if not result:
                return []
            return result
        finally:
            c.close()

    @classmethod
    def get_entry(cls, title, model):
        entry = model.get_by_field(wiki_db, "title", title)
        return entry

    @classmethod
    def get_rashid_position(cls) -> models.RashidPosition:
        return models.RashidPosition.get_by_field(wiki_db, "day", get_tibia_weekday())

    @classmethod
    def get_mapper_link(cls, x, y, z):
        def convert_pos(pos):
            return f"{(pos&0xFF00)>>8}.{pos&0x00FF}"

        return f"http://tibia.wikia.com/wiki/Mapper?coords={convert_pos(x)}-{convert_pos(y)}-{z}-4-1-1"
    # endregion


def setup(bot):
    bot.add_cog(TibiaWiki(bot))
