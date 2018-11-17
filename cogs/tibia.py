import asyncio
import calendar
import datetime as dt
import random
import re
import time
import urllib.parse
from operator import attrgetter
from typing import Optional

import discord
import pytz
from discord.ext import commands

from nabbot import NabBot
from .utils import checks
from .utils.context import NabCtx
from .utils.database import get_server_property, set_server_property, get_global_property, set_global_property
from .utils import get_time_diff, join_list, online_characters, get_local_timezone, log, \
    is_numeric, get_user_avatar, config
from .utils.messages import html_to_markdown, get_first_image, split_message
from .utils.pages import Pages, CannotPaginate, VocationPages
from .utils.tibia import NetworkError, get_character, tibia_logo, get_share_range, get_voc_emoji, get_voc_abb, get_guild, \
    url_house, get_stats, get_map_area, get_tibia_time_zone, get_world, tibia_worlds, get_world_bosses, get_recent_news, \
    get_news_article, Character, url_guild, highscore_format, get_character_url, url_character, get_house, \
    get_voc_abb_and_emoji, get_world_list, get_highscores_tibiadata


FLAGS = {"North America": "🇺🇸", "South America": "🇧🇷", "Europe": "🇬🇧"}
PVP = {"Optional PvP": "🕊️", "Hardcore PvP": "💀", "Open PvP": "⚔",
       "Retro Open PvP": "⚔", "Retro Hardcore PvP":  "💀"}
TRANSFERS = {"locked": "🔒", "blocked": "⛔"}


class Tibia:
    """Commands related to Tibia, gathered from information present in Tibia.com"""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.news_announcements_task = self.bot.loop.create_task(self.scan_news())

    # Commands
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

    # TODO: Needs a revision
    @checks.can_embed()
    @commands.command()
    async def bosses(self, ctx: NabCtx, world=None):
        """Shows predictions for bosses."""
        if world is None and not ctx.is_private and ctx.world:
            world = ctx.world
        elif world is None:
            await ctx.send("You need to tell me a world's name.")
            return
        world = world.title()
        if world not in tibia_worlds:
            await ctx.send("That world doesn't exist.")
            return
        bosses = await get_world_bosses(world)
        if type(bosses) is not dict:
            await ctx.send("Something went wrong")
        fields = {"High Chance": "", "Low Chance": "", "No Chance": "", "Unpredicted": ""}
        for boss, info in bosses.items():
            try:
                if info["days"] > 1000:
                    continue
                info["name"] = boss.title()
                fields[info["chance"]] += "{name} - {days:,} days.\n".format(**info)
            except KeyError:
                continue
        embed = discord.Embed(title=f"Bosses for {world}")
        if fields["High Chance"]:
            embed.add_field(name="High Chance - Last seen", value=fields["High Chance"])
        if fields["Low Chance"]:
            embed.add_field(name="Low Chance - Last seen", value=fields["Low Chance"])
        if await ctx.is_long():
            if fields["No Chance"]:
                embed.add_field(name="No Chance - Expect in", value=fields["No Chance"])
            if fields["Unpredicted"]:
                embed.add_field(name="Unpredicted - Last seen", value=fields["Unpredicted"])
        else:
            ask_channel = await ctx.ask_channel_name()
            if ask_channel:
                askchannel_string = " or use #" + ask_channel
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.group(aliases=['deathlist'], invoke_without_command=True, case_insensitive=True)
    async def deaths(self, ctx: NabCtx, *, name: str = None):
        """Shows a character's recent deaths.

        If this discord server is tracking a tibia world, it will show deaths registered to the character.
        Additionally, if no name is provided, all recent deaths will be shown."""
        if name is None and ctx.is_lite:
            return

        if ctx.is_private:
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None and name is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        show_links = not await ctx.is_long()
        per_page = 20 if await ctx.is_long() else 5
        users_cache = dict()
        if name is None:
            title = "Latest deaths"
            async with ctx.pool.acquire() as conn:
                async with conn.transaction():
                    async for row in conn.cursor("""SELECT c.name, user_id, world, vocation, d.level, date,
                                                    k.name as killer, player
                                                    FROM character_death d
                                                    LEFT JOIN "character" c on c.id = character_id
                                                    LEFT JOIN character_death_killer k on death_id = d.id
                                                    WHERE d.level > $1 AND position = 0 AND world = any($2)
                                                    ORDER by date DESC""", config.announce_threshold, user_worlds):

                        user = self._get_cached_user_(self, row["user_id"], users_cache, user_servers)
                        if user is None:
                            continue
                        if row["world"] not in user_worlds:
                            continue
                        count += 1
                        time_diff = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                        user_name = user.display_name
                        emoji = get_voc_emoji(row["vocation"])
                        entries.append("{emoji} {name} (**@{user}**) - At level **{level}** by {killer} - *{time} ago*"
                                       .format(**row, time=time_diff, emoji=emoji, user=user_name))
                        if count >= 100:
                            break
        else:
            try:
                char = await get_character(self.bot, name)
                if char is None:
                    await ctx.send("That character doesn't exist.")
                    return
            except NetworkError:
                await ctx.send("Sorry, I had trouble checking that character, try it again.")
                return
            deaths = char.deaths
            last_time = dt.datetime.now()
            name = char.name
            voc_emoji = get_voc_emoji(char.vocation)
            title = "{1} {0} latest deaths:".format(name, voc_emoji)
            if ctx.guild is not None and char.owner:
                owner: discord.Member = ctx.guild.get_member(char.owner)
                if owner is not None:
                    author = owner.display_name
                    author_icon = owner.avatar_url
            for death in deaths:
                last_time = death.time
                death_time = get_time_diff(dt.datetime.now(tz=dt.timezone.utc) - death.time)
                if death.by_player and show_links:
                    killer = f"[{death.killer}]({Character.get_url(death.killer)})"
                elif death.by_player:
                    killer = f"**{death.killer}**"
                else:
                    killer = f"{death.killer}"
                entries.append("At level **{0.level}** by {name} - *{time} ago*".format(death, time=death_time,
                                                                                        name=killer))
                count += 1

            char_id = await ctx.pool.fetchval('SELECT id FROM "character" WHERE name = $1', name)
            if char_id is not None and not ctx.is_lite:
                async with ctx.pool.acquire() as conn:
                    async with conn.transaction():
                        async for row in conn.cursor("""SELECT level, date, player, name as killer
                                                                    FROM character_death d
                                                                    LEFT JOIN character_death_killer k ON k.death_id = d.id
                                                                    WHERE position = 0 AND character_id = $1 and date < $2
                                                                    ORDER BY date DESC""",
                                                     char_id, last_time):
                            count += 1
                            death_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                            entries.append("At level **{level}** by {killer} - *{time} ago*".format(**row,
                                                                                                    time=death_time))
                            if count >= 100:
                                break
            if count == 0:
                await ctx.send("There are no registered deaths.")
                return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        if author is not None:
            pages.embed.set_author(name=author, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.is_tracking_world()
    @checks.can_embed()
    @deaths.command(name="monster", aliases=["mob", "killer"])
    async def deaths_monsters(self, ctx: NabCtx, *, name: str):
        """Shows the latest deaths caused by a specific monster."""
        count = 0
        entries = []
        now = time.time()
        per_page = 20 if await ctx.is_long() else 5

        if name[:1] in ["a", "e", "i", "o", "u"]:
            name_with_article = "an " + name
        else:
            name_with_article = "a " + name
        async with ctx.pool.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor("""SELECT c.name, user_id, vocation, world, d.level, date,
                                                k.name as killer, player
                                                FROM character_death_killer k
                                                LEFT JOIN character_death d ON d.id = k.death_id
                                                LEFT JOIN "character" c on c.id = d.character_id
                                                WHERE lower(k.name) = $1 OR lower(k.name) = $2 AND world = $3
                                                ORDER BY date DESC""",
                                             name.lower(), name_with_article.lower(), ctx.world):
                    user = self.bot.get_member(row["user_id"], ctx.guild)
                    if user is None:
                        continue
                    count += 1
                    death_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                    user_name = user.display_name
                    emoji = get_voc_emoji(row["vocation"])
                    entries.append("{emoji} {name} (**@{user}**) - At level **{level}** - *{time} ago*"
                                   .format(**row, time=death_time, user=user_name, emoji=emoji))
                    if count >= 100:
                        break

        if count == 0:
            await ctx.send("There are no registered deaths by that killer.")
            return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = f"{name.title()} latest kills"

        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="user")
    @checks.can_embed()
    @checks.is_tracking_world()
    async def deaths_user(self, ctx: NabCtx, *, name: str):
        """Shows a user's recent deaths on his/her registered characters."""
        user = self.bot.get_member(name, ctx.guild)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        count = 0
        entries = []
        now = time.time()
        per_page = 20 if await ctx.is_long() else 5
        async with ctx.pool.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor("""SELECT d.level, date, player, k.name as killer, user_id, c.name, world,
                                                vocation
                                                FROM character_death d
                                                LEFT JOIN character_death_killer k ON k.death_id = d.id
                                                LEFT JOIN "character" c on c.id = d.character_id
                                                WHERE position = 0 AND user_id = $1 AND world = $2
                                                ORDER BY date DESC """, user.id, ctx.world):
                    count += 1
                    death_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                    emoji = get_voc_emoji(row["vocation"])
                    entries.append("{emoji} {name} - At level **{level}** by {killer} - *{time} ago*"
                                   .format(**row, time=death_time, emoji=emoji))
                    if count >= 100:
                        break
        if count == 0:
            await ctx.send("There are not registered deaths by this user.")
            return

        title = "{0} latest deaths".format(user.display_name)
        icon_url = user.avatar_url
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.set_author(name=title, icon_url=icon_url)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="stats", usage="[week/month]")
    @checks.is_tracking_world()
    @checks.can_embed()
    async def deaths_stats(self, ctx: NabCtx, *, period: str = None):
        """Shows death statistics

        Shows the total number of deaths, the characters and users with more deaths, and the most common killers.

        To see a shorter period, use `week` or `month` as a parameter.
        """
        embed = discord.Embed(title="Death statistics")
        if period in ["week", "weekly"]:
            period = dt.timedelta(weeks=1)
            description_suffix = " in the last 7 days"
        elif period in ["month", "monthly"]:
            period = dt.timedelta(days=30)
            description_suffix = " in the last 30 days"
        else:
            period = dt.timedelta(weeks=300)
            description_suffix = ""
            embed.set_footer(text=f"For a shorter period, try {ctx.clean_prefix}{ctx.command.qualified_name} week or "
                                  f"{ctx.clean_prefix}{ctx.command.qualified_name} month")
        async with ctx.pool.acquire() as conn:
            total = await conn.fetchval("""SELECT count(*) FROM character_death
                                           WHERE CURRENT_TIMESTAMP-date < $1""", period)
            embed.description = f"There are {total:,} deaths registered{description_suffix}."
            async with conn.transaction():
                count = 0
                content = ""
                async for row in conn.cursor("""SELECT COUNT(*), name, user_id
                                                FROM character_death d
                                                LEFT JOIN "character" c on c.id = d.character_id
                                                WHERE CURRENT_TIMESTAMP-date < $1 AND world = $2
                                                GROUP by name, user_id
                                                ORDER BY count DESC""", period, ctx.world):
                    user = self.bot.get_member(row["user_id"], ctx.guild)
                    if user is None:
                        continue
                    count += 1
                    content += f"**{row['name']}** \U00002014 {row['count']}\n"
                    if count >= 3:
                        break
            if count > 0:
                embed.add_field(name="Most deaths per character", value=content, inline=False)
            async with conn.transaction():
                count = 0
                content = ""
                async for row in conn.cursor("""SELECT COUNT(*), user_id
                                                FROM character_death d
                                                LEFT JOIN "character" c on c.id = d.character_id
                                                WHERE CURRENT_TIMESTAMP-date < $1 AND world = $2
                                                AND user_id != 0
                                                GROUP by user_id
                                                ORDER BY count DESC""", period, ctx.world):
                    user = self.bot.get_member(row["user_id"], ctx.guild)
                    if user is None:
                        continue
                    count += 1
                    content += f"@**{user.display_name}** \U00002014 {row['count']}\n"
                    if count >= 3:
                        break
            if count > 0:
                embed.add_field(name="Most deaths per user", value=content, inline=False)
            rows = await conn.fetch("""SELECT COUNT(*), k.name
                                       FROM character_death d
                                       LEFT JOIN character_death_killer k on k.death_id = d.id
                                       LEFT JOIN "character" c on c.id = d.character_id
                                       WHERE CURRENT_TIMESTAMP-date < $1 AND world = $2
                                       GROUP by k.name ORDER BY count DESC LIMIT 3""", period, ctx.world)
            content = ""
            for row in rows:
                killer = re.sub(r"(a|an)(\s+)", " ", row["name"]).title().strip()
                content += f"**{killer}** \U00002014 {row['count']}\n"
            embed.add_field(name="Most deaths per killer", value=content, inline=False)
        await ctx.send(embed=embed)

    @commands.group(aliases=['checkguild'], invoke_without_command=True, case_insensitive=True)
    async def guild(self, ctx: NabCtx, *, name):
        """Shows online characters in a guild.

        Show's the number of members the guild has and a list of their users.
        It also shows whether the guild has a guildhall or not, and their funding date.
        """
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        try:
            guild = await get_guild(name)
            if guild is None:
                await ctx.send("The guild {0} doesn't exist.".format(name))
                return
        except NetworkError:
            await ctx.send("Can you repeat that? I had some trouble communicating.")
            return

        embed = discord.Embed()
        embed.set_author(name="{0.name} ({0.world})".format(guild), url=guild.url, icon_url=tibia_logo)
        embed.description = ""
        embed.set_thumbnail(url=guild.logo)
        if guild.guildhall is not None:
            embed.description += "They own the guildhall [{0}]({1}).\n".format(guild.guildhall["name"],
                                                                               url_house.format(id=guild.guildhall["id"],
                                                                                                world=guild.world))

        if len(guild.online) < 1:
            embed.description += f"Nobody is online. It has **{len(guild.members)}** members."
            await ctx.send(embed=embed)
            return

        embed.set_footer(text=f"The guild was founded on {guild.founded}")

        plural = ""
        if len(guild.online) > 1:
            plural = "s"
        embed.description += f"It has **{len(guild.online)}** player{plural} online out of **{len(guild.members)}**:"
        current_field = ""
        result = ""
        for member in guild.online:
            if current_field == "":
                current_field = member['rank']
            elif member['rank'] != current_field and member["rank"] != "":
                embed.add_field(name=current_field, value=result, inline=False)
                result = ""
                current_field = member['rank']

            member["nick"] = '(*' + member['nick'] + '*) ' if member['nick'] != '' else ''
            member["vocation"] = get_voc_abb(member["vocation"])

            result += "{name} {nick}\u2192 {level} {vocation}\n".format(**member)
        embed.add_field(name=current_field, value=result, inline=False)
        await ctx.send(embed=embed)

    @guild.command(name="info", aliases=["stats"])
    async def guild_info(self, ctx: NabCtx, *, name: str):
        """Shows basic information and stats about a guild.

        It shows their description, homepage, guildhall, number of members and more."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        try:
            guild = await get_guild(name)
            if guild is None:
                await ctx.send("The guild {0} doesn't exist.".format(name))
                return
        except NetworkError:
            await ctx.send("Can you repeat that? I had some trouble communicating.")
            return
        embed = discord.Embed(title=f"{guild.name} ({guild.world})", description=guild.description, url=guild.url)
        embed.set_thumbnail(url=guild.logo)
        embed.set_footer(text=f"The guild was founded on {guild.founded}")
        if guild.guildhall is not None:
            embed.description += "\nThey own the guildhall [{0}]({1}).\n".format(guild.guildhall["name"],
                                                                               url_house.format(id=guild.guildhall["id"],
                                                                                               world=guild.world))
        applications = f"{ctx.tick(True)} Open" if guild.application else f"{ctx.tick(False)} Closed"
        embed.add_field(name="Applications", value=applications)
        if guild.homepage is not None:
            embed.add_field(name="Homepage", value=f"[{guild.homepage}]({guild.homepage})")
        knight = 0
        paladin = 0
        sorcerer = 0
        druid = 0
        none = 0
        total_level = 0
        highest_member = None
        for member in guild.members:
            if highest_member is None:
                highest_member = member
            elif highest_member["level"] < member["level"]:
                highest_member = member
            total_level += member["level"]
            if "knight" in member["vocation"].lower():
                knight += 1
            if "sorcerer" in member["vocation"].lower():
                sorcerer += 1
            if "druid" in member["vocation"].lower():
                druid += 1
            if "paladin" in member["vocation"].lower():
                paladin += 1
            if "none" in member["vocation"].lower():
                none += 1

        embed.add_field(name="Members online", value=f"{len(guild.online)}/{len(guild.members)}")
        embed.add_field(name="Average level", value=f"{total_level/len(guild.members):.0f}")
        embed.add_field(name="Highest member", value="{name} - {level} {emoji}".
                        format(**highest_member, emoji=get_voc_emoji(highest_member["vocation"])))
        embed.add_field(name="Vocations distribution", value=f"{knight} {get_voc_emoji('knight')} | "
                                                             f"{druid} {get_voc_emoji('druid')} | "
                                                             f"{sorcerer} {get_voc_emoji('sorcerer')} | "
                                                             f"{paladin} {get_voc_emoji('paladin')} | "
                                                             f"{none} {get_voc_emoji('none')}",
                        inline=False)

        await ctx.send(embed=embed)

    @guild.command(name="members", aliases=['list'])
    async def guild_members(self, ctx: NabCtx, *, name: str):
        """Shows a list of all guild members.

        Online members have an icon next to their name."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        if name is None:
            await ctx.send("Tell me the guild you want me to check.")
            return

        try:
            guild = await get_guild(name)
            if guild is None:
                await ctx.send("The guild {0} doesn't exist.".format(name))
                return
        except NetworkError:
            await ctx.send("Can you repeat that? I had some trouble communicating.")
            return
        title = "{0.name} ({0.world})".format(guild)
        entries = []
        vocations = []
        for member in guild.members:
            member["nick"] = '(*' + member['nick'] + '*) ' if member['nick'] != '' else ''
            vocations.append(member["vocation"])
            member["emoji"] = get_voc_emoji(member["vocation"])
            member["vocation"] = get_voc_abb(member["vocation"])
            member["online"] = config.online_emoji if member["status"] == "online" else ""
            entries.append("{rank}\u2014 {online}**{name}** {nick} (Lvl {level} {vocation}{emoji})".format(**member))
        per_page = 20 if await ctx.is_long() else 5
        pages = VocationPages(ctx, entries=entries, per_page=per_page, vocations=vocations)
        pages.embed.set_author(name=title, icon_url=guild.logo, url=guild.url)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command(usage="[world,category[,vocation]]")
    async def highscores(self, ctx: NabCtx, *, params=None):
        """Shows the entries in the highscores.

        If the server is already tracking a world, there's no need to specify a world.

        Available categories are: experience, magic, shielding, distance, sword, club, axe, fist and fishing.
        Available vocations are: all, paladin, druid, sorcerer, knight."""
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        categories = ["experience", "magic", "shielding", "distance", "sword", "club", "axe", "fist", "fishing",
                      "achievements","loyalty"]
        vocations = ["all", "paladin", "druid", "knight", "sorcerer"]
        if params is None:
            params = []
        else:
            params = params.split(",")
        world = None
        if params and params[0].strip().title() in tibia_worlds:
            world = params[0].strip().title()
            del params[0]
        if world is None:
            world = ctx.world
        if world is None:
            return await ctx.send(f"{ctx.tick(False)} You have to specify a world.")

        if not params:
            category = "experience"
            vocation = "all"

        else:
            if params[0].strip().lower() not in categories:
                return await ctx.send(f"{ctx.tick(False)} Invalid category, valid categories are: "
                                      f"`{','.join(categories)}`.")
            category = params[0].strip().lower()
            del params[0]
            if not params:
                vocation = "all"
            elif params[0].strip().lower() not in vocations:
                return await ctx.send(f"{ctx.tick(False)} Invalid vocation, valid vocations are: "
                                      f"`{','.join(vocations)}`.")
            else:
                vocation = params[0].strip().lower()
        with ctx.typing():
            try:
                highscores = await get_highscores_tibiadata(world, category, vocation)
                if highscores is None:
                    return await ctx.send(f"{ctx.tick(False)} I couldn't find any highscores entries.")
            except NetworkError:
                return await ctx.send(f"{ctx.tick(False)} I couldn't fetch the highscores.")
        entries = []
        for entry in highscores:
            entry["voc"] = get_voc_emoji(entry["vocation"])
            if category == "experience":
                entries.append("**{name}**{voc} - Level {level} ({points:,} exp)".format(**entry))
            else:
                entries.append("**{name}**{voc} - Level {level}".format(**entry))
        pages = Pages(ctx, entries=entries, per_page=20 if await ctx.is_long() else 10)
        pages.embed.title = f"🏆 {category.title()} highscores for {world}"
        if vocation != "all":
            pages.embed.title += f" ({vocation}s)"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command(aliases=["guildhall"], usage="<name>[,world]")
    async def house(self, ctx: NabCtx, *, name: str):
        """Shows info for a house or guildhall.

        By default, it shows the current status of a house for the current tracked world (if any).
        If used on private messages, no world is looked up unless specified.

        To specify a world, add the world at the end separated with a comma.
        """
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        params = name.split(",")
        if len(params) > 1:
            name = ",".join(params[:-1])
            world = params[-1]
        else:
            name = params[0]
            world = None
        if world is not None and world.title().strip() not in tibia_worlds:
            name += f",{world}"
            world = None
        if ctx.guild is not None and world is None:
            world = ctx.world
        name = name.strip()
        if world:
            world = world.title().strip()
        house = await get_house(name, world)
        if house is None:
            await ctx.send(f"{ctx.tick(False)} I couldn't find a house named `{name}`.")
            return

        if type(house) is list:
            name = await ctx.choose(house)
            if name is None:
                return

            house = await get_house(name, world)

        # Attach image only if the bot has permissions
        if permissions.attach_files:
            filename = re.sub(r"[^A-Za-z0-9]", "", house["name"]) + ".png"
            mapimage = get_map_area(house["x"], house["y"], house["z"])
            embed = self.get_house_embed(ctx, house)
            embed.set_image(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(mapimage, f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=self.get_house_embed(ctx, house))

    @commands.group(aliases=['levelups'], invoke_without_command=True, case_insensitive=True)
    @checks.is_tracking_world()
    @checks.can_embed()
    async def levels(self, ctx: NabCtx, *, name: str=None):
        """Shows a character's or everyone's recent level ups.

        If a character is specified, it displays a list of its recent level ups.
        If no character is specified, it will show the recent level ups of all registered characters in the server.

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        per_page = 20 if await ctx.is_long() else 5
        user_cache = dict()
        if name is None:
            title = "Latest level ups"
            async with ctx.pool.acquire() as conn:
                async with conn.transaction():
                    async for row in conn.cursor("""SELECT name, user_id, world, vocation, l.level, date
                                                    FROM character_levelup l
                                                    LEFT JOIN "character" c ON c.id = l.character_id
                                                    WHERE l.level >= $1 AND world = $2
                                                    ORDER BY date DESC""", config.announce_threshold, ctx.world):
                        user = self._get_cached_user_(self, row["user_id"], user_cache, ctx.guild)
                        if user is None:
                            continue
                        count += 1
                        level_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                        user_name = user.display_name
                        emoji = get_voc_emoji(row["vocation"])
                        entries.append("{emoji} {name} - Level **{level}** - (**@{user}**) - *{time} ago*"
                                       .format(**row, time=level_time, user=user_name, emoji=emoji))
                        if count >= 100:
                            break
        else:
            async with ctx.pool.acquire() as conn:
                char = await conn.fetchrow('SELECT id, user_id, name, vocation FROM "character" WHERE lower(name) = $1',
                                           name.lower())
                if char is None:
                    return await ctx.send("I don't have a character with that name registered.")
                owner = ctx.guild.get_member(char["user_id"])
                if owner is None:
                    return await ctx.send("I don't have a character with that name registered.")
                author = owner.display_name
                author_icon = owner.avatar_url
                name = char["name"]
                emoji = get_voc_emoji(char["vocation"])
                title = f"{emoji} {name} latest level ups"
                async with conn.transaction():
                    async for row in conn.cursor("""SELECT l.level, date
                                                    FROM character_levelup l
                                                    LEFT JOIN "character" c ON c.id = l.character_id
                                                    WHERE character_id = $1
                                                    ORDER BY date DESC""", char["id"]):
                        count += 1
                        level_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                        entries.append("Level **{level}** - *{time} ago*".format(**row, time=level_time))
                        if count >= 100:
                            break
            if count == 0:
                await ctx.send("There are no registered levels.")
                return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        if author is not None:
            pages.embed.set_author(name=author, icon_url=author_icon)

        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @levels.command(name="user")
    @checks.is_tracking_world()
    @checks.can_embed()
    async def levels_user(self, ctx: NabCtx, *, name: str):
        """Shows a user's recent level ups on their registered characters."""
        user = self.bot.get_member(name, ctx.guild)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        count = 0
        entries = []
        now = time.time()
        per_page = 20 if await ctx.is_long() else 5
        async with ctx.pool.acquire() as conn:
            async with conn.transaction():
                async for row in conn.cursor("""SELECT name, l.level, date, world, vocation
                                                FROM character_levelup l
                                                LEFT JOIN "character" c on c.id = l.character_id
                                                WHERE user_id = $1 AND world = $2
                                                ORDER BY date DESC""", user.id, ctx.world):
                    count += 1
                    level_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                    emoji = get_voc_emoji(row["vocation"])
                    entries.append("{emoji} {name} - Level **{level}** - *{time} ago*".format(**row, time=level_time,
                                                                                              emoji=emoji))
                    if count >= 100:
                        break
        if count == 0:
            await ctx.send("There are not registered level ups by this user.")
            return

        title = f"{user.display_name} latest level ups"
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.set_author(name=title, icon_url=get_user_avatar(user))
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command(usage="[id]")
    async def news(self, ctx: NabCtx, news_id: int=None):
        """Shows the latest news articles from Tibia.com.

        If no id is supplied, a list of recent articles is shown, otherwise, a snippet of the article is shown."""
        if news_id is None:
            try:
                recent_news = await get_recent_news()
                if recent_news is None:
                    await ctx.send("Something went wrong getting recent news.")
            except NetworkError:
                await ctx.send("I couldn't fetch the recent news, I'm having network problems.")
                return
            embed = discord.Embed(title="Recent news")
            embed.set_footer(text="To see a specific article, use the command /news <id>")
            news_format = "{emoji} `{id}`\t[{news}]({tibiaurl})"
            type_emojis = {
                "Featured Article": "📑",
                "News": "📰",
            }
            for news in recent_news:
                news["emoji"] = type_emojis.get(news["type"], "")
            limit = 20 if await ctx.is_long() else 10
            embed.description = "\n".join([news_format.format(**n) for n in recent_news[:limit]])
            await ctx.send(embed=embed)
        else:
            try:
                article = await get_news_article(news_id)
                if article is None:
                    await ctx.send("There's no article with that id.")
                    return
            except NetworkError:
                await ctx.send("I couldn't fetch the recent news, I'm having network problems.")
                return
            limit = 1900 if await ctx.is_long() else 600
            embed = self.get_article_embed(article, limit)
            await ctx.send(embed=embed)

    @commands.command(name="searchworld", aliases=["whereworld", "findworld"], usage="<params>[,world]")
    async def search_world(self, ctx: NabCtx, *, params):
        """Searches for online characters that meet the criteria.

        There are 3 ways to use this command:

        - Find a character in share range with another character. (`searchworld <name>`)
        - Find a character in share range with a certain level. (`searchworld <level>`)
        - Find a character in a level range. (`searchworld <min>,<max>`)

        By default, the tracked world is searched, unless specified at the end of the parameters

        You can add the world where you want to look in by adding a comma, followed by the name of the world.
        Example: `searchworld Cachero,Calmera`
        """
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        invalid_arguments = "Invalid arguments used, examples:\n" \
                            "```/searchworld charname[,world]\n" \
                            "/searchworld level[,world]\n" \
                            "/searchworld minlevel,maxlevel[,world]```"

        world_name = None
        params = params.split(",")
        # If last element matches a world
        if len(params) > 1 and params[-1].strip().capitalize() in tibia_worlds:
            world_name = params[-1].capitalize().strip()
            del params[-1]
        if not (1 <= len(params) <= 2):
            await ctx.send(invalid_arguments)
            return

        tracked_world = ctx.world
        if world_name is None:
            if tracked_world is None:
                await ctx.send("You must specify the world where you want to look in.")
                return
            else:
                world_name = tracked_world

        try:
            world = await get_world(world_name)
            if world is None:
                # This really shouldn't happen...
                await ctx.send(f"There's no world named **{world_name}**.")
                return
        except NetworkError:
            await ctx.send("I'm having 'network problems' as you humans say, please try again later.")
            return

        online_list = world.players_online
        if len(online_list) == 0:
            await ctx.send(f"There is no one online in {world_name}.")
            return

        # Sort by level, descending
        online_list = sorted(online_list, key=lambda x: x.level, reverse=True)

        entries = []
        vocations = []
        filter_name = ""
        per_page = 20 if await ctx.is_long() else 5

        content = ""
        # params[0] could be a character's name, a character's level or one of the level ranges
        # If it's not a number, it should be a player's name
        if not is_numeric(params[0]):
            # We shouldn't have another parameter if a character name was specified
            if len(params) == 2:
                await ctx.send(invalid_arguments)
                return
            try:
                char = await get_character(params[0])
                if char is None:
                    await ctx.send("I couldn't find a character with that name.")
                    return
                filter_name = char.name
                if char.world != world.name:
                    content = f"**Note**: The character is in **{char.world}** and I'm searching **{world.name}**."
            except NetworkError:
                await ctx.send("I couldn't fetch that character.")
                return
            low, high = get_share_range(char.level)
            title = "Characters online in share range with {0}({1}-{2}):".format(char.name, low, high)
            empty = "I didn't find anyone in share range with **{0}**({1}-{2})".format(char.name, low, high)
        else:
            # Check if we have another parameter, meaning this is a level range
            if len(params) == 2:
                try:
                    level1 = int(params[0])
                    level2 = int(params[1])
                except ValueError:
                    await ctx.send(invalid_arguments)
                    return
                if level1 <= 0 or level2 <= 0:
                    await ctx.send("You entered an invalid level.")
                    return
                low = min(level1, level2)
                high = max(level1, level2)
                title = "Characters online between level {0} and {1}".format(low, high)
                empty = "I didn't find anyone between levels **{0}** and **{1}**".format(low, high)
            # We only got a level, so we get the share range for it
            else:
                if int(params[0]) <= 0:
                    await ctx.send("You entered an invalid level.")
                    return
                low, high = get_share_range(int(params[0]))
                title = "Characters online in share range with level {0} ({1}-{2})".format(params[0], low, high)
                empty = "I didn't find anyone in share range with level **{0}** ({1}-{2})".format(params[0],
                                                                                                  low, high)

        online_list = list(filter(lambda x: low <= x.level <= high and x.name != filter_name, online_list))

        if len(online_list) == 0:
            await ctx.send(empty)
            return

        for player in online_list:
            line_format = "**{0.name}** - Level {0.level} {1}"
            entries.append(line_format.format(player, get_voc_abb_and_emoji(player.vocation)))
            vocations.append(player.vocation)

        pages = VocationPages(ctx, entries=entries, per_page=per_page, vocations=vocations, header=content)
        pages.embed.title = title

        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command(aliases=['expshare', 'party'])
    async def share(self, ctx: NabCtx, *, param):
        """Shows the sharing range for that level or character or list of characters.

        This command can be used in three ways:

        1. Find the share range of a certain level. (`share <level>`)
        2. Find the share range of a character. (`share <name>`)
        3. Find the joint share range of a group of characters. (`share <name1, name2...>`)
        """
        invalid_level = ["Invalid level.",
                         "I don't think that's a valid level.",
                         "You're doing it wrong!",
                         "Nope, you can't share with anyone.",
                         "You probably need a couple more levels"
                         ]
        # Check if param is numeric
        try:
            level = int(param)
            if level < 1:
                await ctx.send(random.choice(invalid_level))
                return
            low, high = get_share_range(level)
            await ctx.send(f"A level {level} can share experience with levels **{low}** to **{high}**.")
            return
        except ValueError:
            chars = param.split(",")
            if len(chars) > 5:
                await ctx.send("I can only check up to 5 characters at a time.")
                return
            if len(chars) == 1:
                with ctx.typing():
                    try:
                        char = await get_character(chars[0])
                        if char is None:
                            await ctx.send('There is no character with that name.')
                            return
                    except NetworkError:
                        await ctx.send("I'm having connection issues right now, please try again.")
                        return
                    name = char.name
                    level = char.level
                    low, high = get_share_range(char.level)
                    await ctx.send(f"**{name}** ({level}) can share experience with levels **{low}** to **{high}**.")
                    return
            char_data = []
            # Check if all characters are the same.
            if all(x.lower() == chars[0].lower() for x in chars):
                await ctx.send("I'm not sure if sharing with yourself counts as sharing, but yes, you can share.")
                return
            with ctx.typing():
                for char in chars:
                    try:
                        fetched_char = await get_character(char)
                        if fetched_char is None:
                            await ctx.send(f"There is no character named **{char}**.")
                            return
                    except NetworkError:
                        await ctx.send("I'm having connection issues, please try again in a bit.")
                        return
                    char_data.append(fetched_char)
                # Sort character list by level ascending
                char_data = sorted(char_data, key=lambda k: k.level)
                low, _ = get_share_range(char_data[-1].level)
                _, high = get_share_range(char_data[0].level)
                lowest_name = char_data[0].name
                lowest_level = char_data[0].level
                highest_name = char_data[-1].name
                highest_level = char_data[-1].level
                if low > char_data[0].level:
                    await ctx.send(f"**{lowest_name}** ({lowest_level}) needs {low-lowest_level} more level"
                                   f"{'s' if low-lowest_level > 1 else ''} to share experience with **{highest_name}** "
                                   f"({highest_level}).")
                    return
                # If it's more than two, just say they can all share
                reply = ""
                if len(chars) > 2:
                    reply = f"They can all share experience with each other."
                else:
                    reply = f"**{lowest_name}** ({lowest_level}) and **{highest_name}** ({highest_level}) can " \
                            f"share experience."
                await ctx.send(reply+f"\nTheir share range is from level **{low}** to **{high}**.")

    @commands.command()
    async def stamina(self, ctx: NabCtx, current_stamina: str):
        """Tells you the time you have to wait to restore stamina.

        To use it, you must provide your current stamina, in this format: `hh:mm`.
        The bot will show the time needed to reach full stamina if you were to start sleeping now.

        The footer text shows the time in your timezone where your stamina would be full."""

        hour_pattern = re.compile(r"(\d{1,2}):(\d{1,2})")
        match = hour_pattern.match(current_stamina.strip())
        if not match:
            await ctx.send("You need to tell me your current stamina, in this format: `34:03`.")
            return
        hours = int(match.group(1))
        minutes = int(match.group(2))
        if minutes >= 60:
            await ctx.send("Invalid time, minutes can't be 60 or greater.")
            return
        current = dt.timedelta(hours=hours, minutes=minutes)
        if hours > 42 or (hours == 42 and minutes > 0):
            await ctx.send("You can't have more than 42 hours of stamina.")
            return
        elif hours == 42:
            await ctx.send("Your stamina is full already.")
            return
        # Stamina takes 3 minutes to regenerate one minute until 40 hours.
        resting_time = max((dt.timedelta(hours=40)-current).total_seconds(), 0)*3
        # Last two hours of stamina take 10 minutes for a minute
        resting_time += (dt.timedelta(hours=42)-max(dt.timedelta(hours=40), current)).total_seconds()*10
        # You must be logged off 10 minutes before you start gaining stamina
        resting_time += dt.timedelta(minutes=10).total_seconds()

        hours, remainder = divmod(int(resting_time), 3600)
        minutes, _ = divmod(remainder, 60)
        if hours:
            remaining = f'{hours} hours and {minutes} minutes'
        else:
            remaining = f'{minutes} minutes'

        reply = f"You need to rest **{remaining}** to get back to full stamina."
        permissions = ctx.bot_permissions
        if not permissions.embed_links:
            await ctx.send(reply)
            return

        embed = discord.Embed(description=reply)
        embed.set_footer(text="Full stamina")
        embed.colour = discord.Color.green()
        embed.timestamp = dt.datetime.utcnow()+dt.timedelta(seconds=resting_time)
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
            _digits = re.compile('\d')
            if _digits.search(params[0]) is not None:
                await ctx.send(invalid_arguments)
                return
            else:
                try:
                    char = await get_character(params[0])
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

    @commands.group(aliases=["story"], invoke_without_command=True, case_insensitive=True)
    @checks.is_tracking_world()
    @checks.can_embed()
    async def timeline(self, ctx: NabCtx, *, name: str = None):
        """Shows a character's recent level ups and deaths.

        If no character is provided, the timeline of all registered characters in the server will be shown.

        Characters must be registered in order to see their timelines.

        - 🌟 Indicates level ups
        - 💀 Indicates deaths
        """
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        per_page = 20 if await ctx.is_long() else 5
        await ctx.channel.trigger_typing()
        user_cache = dict()
        if name is None:
            title = "Timeline"
            async with ctx.pool.acquire() as conn:
                async with conn.transaction():
                    async for row in conn.cursor("""(SELECT c.user_id, c.name, c.vocation, d.level, k.name as killer,
                                                    'death' AS type, d.date
                                                    FROM character_death d
                                                    LEFT JOIN character_death_killer k ON k.death_id = d.id
                                                    LEFT JOIN "character" c ON c.id = d.character_id
                                                    WHERE world = $1 AND d.level >= $2)
                                                    UNION
                                                    (SELECT c.user_id, c.name, c.vocation, l.level, NULL,
                                                    'level' AS type, l.date
                                                    FROM character_levelup l
                                                    LEFT JOIN "character" c ON c.id = l.character_id
                                                    WHERE world = $1 AND l.level >= $2)
                                                    ORDER by DATE DESC""", ctx.world, config.announce_threshold):
                        user = self._get_cached_user_(self, row["user_id"], user_cache, ctx.guild)
                        if user is None:
                            continue
                        count += 1
                        entry_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                        user_name = user.display_name
                        voc_emoji = get_voc_emoji(row["vocation"])
                        if row["type"] == "death":
                            emoji = config.death_emoji
                            entries.append("{emoji}{voc_emoji} {name} (**@{user}**) - At level **{level}** by {killer} "
                                           "- *{time} ago*".format(**row, voc_emoji=voc_emoji, user=user_name,
                                                                   time=entry_time, emoji=emoji))
                        else:
                            emoji = config.levelup_emoji
                            entries.append("{emoji}{voc_emoji} {name} (**@{user}**) - Level **{level}** - *{time} ago*"
                                           .format(**row, voc_emoji=voc_emoji, user=user_name, time=entry_time,
                                                   emoji=emoji))
                        if count >= 200:
                            break
        else:
            async with ctx.pool.acquire() as conn:
                char = await conn.fetchrow("""SELECT id, name, vocation, user_id FROM "character"
                                              WHERE lower(name) = $1 AND world = $2""", name.lower(), ctx.world)
                if char is None:
                    return await ctx.send("I don't have a character with that name registered.")
                owner = ctx.guild.get_member(char["user_id"])
                if owner is None:
                    return await ctx.send("I don't have a character with that name registered.")
                author = owner.display_name
                author_icon = owner.avatar_url
                name = char["name"]
                emoji = get_voc_emoji(char["vocation"])
                title = f"{emoji} {name} timeline"
                async with conn.transaction():
                    async for row in conn.cursor("""(SELECT d.level, k.name as killer, 'death' AS type, d.date
                                                    FROM character_death d
                                                    LEFT JOIN character_death_killer k ON k.death_id = d.id
                                                    WHERE character_id = $1)
                                                    UNION
                                                    (SELECT l.level, NULL, 'level' AS type, l.date
                                                    FROM character_levelup l
                                                    WHERE character_id = $1)
                                                    ORDER by DATE DESC""", char["id"]):
                        count += 1
                        entry_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                        if row["type"] == "death":
                            emoji = config.death_emoji
                            entries.append("{emoji} At level **{level}** by {killer} - *{time} ago*"
                                           .format(**row, time=entry_time, emoji=emoji)
                                           )
                        else:
                            emoji = config.levelup_emoji
                            entries.append("{emoji} Level **{level}** - *{time} ago*".format(**row, time=entry_time,
                                                                                             emoji=emoji))
                        if count >= 200:
                            break
        if count == 0:
            await ctx.send("There are no registered events.")
            return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        if author is not None:
            pages.embed.set_author(name=author, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @timeline.command(name="user")
    @checks.is_in_tracking_world()
    async def timeline_user(self, ctx: NabCtx, *, name: str):
        """Shows a users's recent level ups and deaths on their characters."""
        user = self.bot.get_member(name, ctx.guild)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        entries = []
        count = 0
        now = time.time()
        per_page = 20 if await ctx.is_long() else 5

        async with ctx.pool.acquire() as conn:
            title = f"{user.display_name} timeline"
            async with conn.transaction():
                async for row in conn.cursor("""(SELECT c.name, c.vocation, d.level, k.name as killer,
                                                'death' AS type, d.date
                                                FROM character_death d
                                                LEFT JOIN character_death_killer k ON k.death_id = d.id
                                                LEFT JOIN "character" c ON c.id = d.character_id
                                                WHERE world = $1 AND user_id = $2)
                                                UNION
                                                (SELECT c.name, c.vocation, l.level, NULL,
                                                'level' AS type, l.date
                                                FROM character_levelup l
                                                LEFT JOIN "character" c ON c.id = l.character_id
                                                WHERE world = $1 AND user_id = $2)
                                                ORDER by DATE DESC""", ctx.world, user.id):
                    count += 1
                    entry_time = get_time_diff(dt.timedelta(seconds=now - row["date"].timestamp()))
                    voc_emoji = get_voc_emoji(row["vocation"])
                    if row["type"] == "death":
                        emoji = config.death_emoji
                        entries.append("{emoji}{voc_emoji} {name} - At level **{level}** by {killer} - *{time} ago*"
                                       .format(**row, time=entry_time, voc_emoji=voc_emoji, emoji=emoji)
                                       )
                    else:
                        emoji = config.levelup_emoji
                        entries.append("{emoji}{voc_emoji} {name} - Level **{level}** - *{time} ago*"
                                       .format(**row, time=entry_time, voc_emoji=voc_emoji, emoji=emoji))
                    if count >= 200:
                        break

        if count == 0:
            await ctx.send("There are no registered events.")
            return
        author_icon = user.avatar_url
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.set_author(name=title, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.group(aliases=['serversave'], invoke_without_command=True)
    async def time(self, ctx: NabCtx):
        """Displays Tibia server's time and time until server save.

        Server moderators can manage displayed timezones using the subcommands."""
        now = dt.datetime.now()
        tibia_timezone = get_tibia_time_zone()
        timezone_name = "CET" if tibia_timezone == 1 else "CEST"

        offset = tibia_timezone - get_local_timezone()
        tibia_time = now+dt.timedelta(hours=offset)
        server_save = tibia_time
        if tibia_time.hour >= 10:
            server_save += dt.timedelta(days=1)
        server_save = server_save.replace(hour=10, minute=0, second=0, microsecond=0)
        time_until_ss = server_save - tibia_time
        hours, remainder = divmod(int(time_until_ss.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        server_save_str = '{h} hours and {m} minutes'.format(h=hours, m=minutes)

        reply = f"It's currently **{tibia_time.strftime('%H:%M')}** in Tibia's website ({timezone_name}).\n" \
                f"Server save is in {server_save_str}.\n" \
                f"Rashid is in **{get_rashid_info()['city']}** today."
        if ctx.is_private:
            return await ctx.send(reply)

        saved_times = await get_server_property(ctx.pool, ctx.guild.id, "times", default=[])
        if not saved_times:
            return await ctx.send(reply)
        time_entries = sorted(saved_times, key=lambda k: now.astimezone(pytz.timezone(k["timezone"])).utcoffset())
        reply += "\n\n"
        for entry in time_entries:
            timezone_time = now.astimezone(pytz.timezone(entry["timezone"]))
            reply += f"**{timezone_time.strftime('%H:%M')}** in {entry['name']}\n"
        await ctx.send(reply)

    @checks.is_mod()
    @commands.guild_only()
    @time.command(name="add", usage="<timezone>")
    async def time_add(self, ctx: NabCtx, *, _timezone):
        """Adds a new timezone to display.

        You can look by city, country or region.
        Once the timezone is found, you can set the name you want to show on the `time` command.

        Only Server Moderators can use this command."""
        _timezone = _timezone.lower().replace(" ", "_")
        matches = []
        for tz in pytz.all_timezones:
            if _timezone in tz.lower():
                matches.append(tz)
        if not matches:
            return await ctx.send(f"{ctx.tick(False)} No timezones found matching that name.")
        _timezone = await ctx.choose(matches)
        if _timezone is None:
            return
        timezone_time = dt.datetime.now().astimezone(pytz.timezone(_timezone))
        msg = await ctx.send(f"The time in `{_timezone}` is **{timezone_time.strftime('%H:%M')}**.\n"
                             f"What display name do you want to assign? You can `cancel` if you changed your mind.")
        display_name = await ctx.input(timeout=60, clean=True, delete_response=True)
        if display_name is None or display_name.lower() == "cancel":
            return await ctx.send("I guess you changed your mind.")
        try:
            await msg.delete()
        except discord.DiscordException:
            pass

        if len(display_name) > 40:
            return await ctx.send(f"{ctx.tick(False)} The display name can't be longer than 40 characters.")

        saved_times = await get_server_property(ctx.pool, ctx.guild.id, "times", default=[])
        if any(e["name"].lower() == display_name.lower() for e in saved_times):
            return await ctx.send(f"{ctx.tick(False)} There's already a saved timezone with that display name,"
                                  f"please use the command again.")

        saved_times.append({"name": display_name.strip(), "timezone": _timezone})
        await set_server_property(ctx.pool, ctx.guild.id, "times", saved_times)
        await ctx.send(f"{ctx.tick()} Timezone `{_timezone}` saved successfully as `{display_name.strip()}`.")

    @checks.is_mod()
    @checks.can_embed()
    @commands.guild_only()
    @time.command(name="list")
    async def time_list(self, ctx: NabCtx):
        """Shows a list of all the currently added timezones.

        Only Server Moderators can use this command."""
        saved_times = await get_server_property(ctx.pool, ctx.guild.id, "times", default=[])
        if not saved_times:
            return await ctx.send(f"{ctx.tick(False)} There are no saved times for this server.")

        pages = Pages(ctx, entries=[f"**{e['name']}** — *{e['timezone']}*" for e in saved_times], per_page=10)
        pages.embed.title = "Saved times"
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @checks.is_mod()
    @commands.guild_only()
    @time.command(name="remove", aliases=["delete"], usage="<timezone>")
    async def time_remove(self, ctx: NabCtx, *, _timezone):
        """Removes a timezone from the list.

        Only Server Moderators can use this command."""
        _timezone = _timezone.strip()
        saved_times: list = await get_server_property(ctx.pool, ctx.guild.id, "times", default=[])
        if not saved_times:
            return await ctx.send(f"{ctx.tick(False)} There are no saved times for this server.")

        for entry in saved_times:
            if entry["name"].lower() == _timezone.lower():
                saved_times.remove(entry)
                await set_server_property(ctx.pool, ctx.guild.id, "times", saved_times)
                return await ctx.send(f"{ctx.tick()} Timezone `{entry['name']}` removed succesfully.")
        await ctx.send(f"{ctx.tick(False)} There's no timezone named `{_timezone}`.")

    @checks.can_embed()
    @commands.command(aliases=['check', 'char', 'character'])
    async def whois(self, ctx: NabCtx, *, name):
        """Shows a character's or a discord user's information.

        If the parameter matches a discord user, it displays a list of the characters linked to that user.
        If the parameter matches a character, it will display the character's info

        If the character found is registered to a discord user, it will show the owner of the character.

        Users can be looked through their username, user#discriminator or their user id.

        Additionally, if the character is in the highscores, their ranking will be shown.
        """
        if ctx.is_lite:
            try:
                char = await get_character(ctx.bot, name)
                if char is None:
                    await ctx.send("I couldn't find a character with that name")
                    return
            except NetworkError:
                await ctx.send("Sorry, I couldn't fetch the character's info, maybe you should try again...")
                return
            embed = discord.Embed(description=self.get_char_string(char))
            embed.set_author(name=char.name, url=char.url, icon_url=tibia_logo)
            await ctx.send(embed=embed)
            return

        if name.lower() == ctx.me.display_name.lower():
            await ctx.invoke(self.bot.all_commands.get('about'))
            return

        try:
            char = await get_character(ctx.bot, name)
        except NetworkError:
            await ctx.send("Sorry, I couldn't fetch the character's info, maybe you should try again...")
            return
        char_string = self.get_char_string(char)
        # If the command is used on a DM, only search users in the servers the author is in
        # Otherwise, just search on the current server
        if ctx.is_private:
            guild_filter = self.bot.get_user_guilds(ctx.author.id)
        else:
            guild_filter = ctx.guild
        # If the user is a bot, then don't, just don't
        user = self.bot.get_member(name, guild_filter)
        if user is not None and user.bot:
            user = None
        embed = await self.get_user_embed(ctx, user)

        # No user or char with that name
        if char is None and user is None:
            await ctx.send("I don't see any user or character with that name.")
            return
        # We found a user
        if embed is not None:
            # Check if we found a char too
            if char is not None:
                # If it's owned by the user, we append it to the same embed.
                if char.owner == int(user.id):
                    embed.add_field(name="Character", value=char_string, inline=False)
                    if char.last_login is not None:
                        embed.set_footer(text="Last login")
                        embed.timestamp = char.last_login
                    await ctx.send(embed=embed)
                    return
                # Not owned by same user, we display a separate embed
                else:
                    char_embed = discord.Embed(description=char_string)
                    char_embed.set_author(name=char.name, url=char.url, icon_url=tibia_logo)
                    if char.last_login is not None:
                        char_embed.set_footer(text="Last login")
                        char_embed.timestamp = char.last_login
                    await ctx.send(embed=embed)
                    await ctx.send(embed=char_embed)
                    return
            else:
                # Tries to display user's highest level character since there is no character match
                if ctx.is_private:
                    display_name = '@'+user.name
                    user_guilds = self.bot.get_user_guilds(ctx.author.id)
                    user_tibia_worlds = [world for server, world in self.bot.tracked_worlds.items() if
                                         server in [s.id for s in user_guilds]]
                else:
                    if self.bot.tracked_worlds.get(ctx.guild.id) is None:
                        user_tibia_worlds = []
                    else:
                        user_tibia_worlds = [self.bot.tracked_worlds[ctx.guild.id]]
                if len(user_tibia_worlds) != 0:
                    character = await ctx.pool.fetchrow("""SELECT name, abs(level) as level FROM "character"
                                                           WHERE user_id = $1 and world = any($2)
                                                           ORDER by level DESC""", user.id, user_tibia_worlds)
                    if character:
                        char = await get_character(ctx.bot, character["name"])
                        char_string = self.get_char_string(char)
                        if char is not None:
                            char_embed = discord.Embed(description=char_string)
                            char_embed.set_author(name=char.name, url=char.url, icon_url=tibia_logo)
                            embed.add_field(name="Highest character", value=char_string, inline=False)
                            if char.last_login is not None:
                                embed.set_footer(text="Last login")
                                embed.timestamp = char.last_login
                await ctx.send(embed=embed)
        else:
            embed = discord.Embed(description="")
            if char is not None:
                owner = None if char.owner == 0 else self.bot.get_member(char.owner, guild_filter)
                if owner is not None:
                    # Char is owned by a discord user
                    embed = await self.get_user_embed(ctx, owner)
                    if embed is None:
                        embed = discord.Embed(description="")
                    embed.add_field(name="Character", value=char_string, inline=False)
                    if char.last_login is not None:
                        embed.set_footer(text="Last login")
                        embed.timestamp = char.last_login
                    await ctx.send(embed=embed)
                    return
                else:
                    embed.set_author(name=char.name, url=char.url, icon_url=tibia_logo)
                    embed.description += char_string
                    if char.last_login:
                        embed.set_footer(text="Last login")
                        embed.timestamp = char.last_login

            await ctx.send(embed=embed)

    @commands.command(name="world")
    async def world_info(self, ctx: NabCtx, name: str):
        """Shows basic information about a Tibia world.

        Shows information like PvP type, online count, server location, vocation distribution, and more."""
        try:
            world = await get_world(name)
            if world is None:
                await ctx.send("There's no world with that name.")
                return
        except NetworkError:
            await ctx.send("I'm having connection issues right now.")
            return

        url = 'https://www.tibia.com/community/?subtopic=worlds&world=' + name.capitalize()
        embed = discord.Embed(url=url, title=name.capitalize())
        if world.online == 0:
            embed.description = "This world is offline."
            embed.colour = discord.Colour.red()
        else:
            embed.colour = discord.Colour.green()
        embed.add_field(name="Players online", value=str(world.online))
        embed.set_footer(text=f"The players online record is {world.record_online}")
        embed.timestamp = world.record_date
        created = world.creation.split("-")
        try:
            month = calendar.month_name[int(created[1])]
            year = int(created[0])
            embed.add_field(name="Created", value=f"{month} {year}")
        except (IndexError, ValueError):
            pass

        embed.add_field(name="Location", value=f"{FLAGS.get(world.location,'')} {world.location}")
        embed.add_field(name="PvP Type", value=f"{PVP.get(world.pvp_type,'')} {world.pvp_type}")
        if world.premium_type is not None:
            embed.add_field(name="Premium restricted", value=ctx.tick(True))
        if world.transfer_type is not None:
            embed.add_field(name="Transfers", value=f"{TRANSFERS.get(world.transfer_type,'')} {world.transfer_type}")

        knight = 0
        paladin = 0
        sorcerer = 0
        druid = 0
        none = 0
        for character in world.players_online:
            if "knight" in character.vocation.lower():
                knight += 1
            if "sorcerer" in character.vocation.lower():
                sorcerer += 1
            if "druid" in character.vocation.lower():
                druid += 1
            if "paladin" in character.vocation.lower():
                paladin += 1
            if "none" in character.vocation.lower():
                none += 1

        embed.add_field(name="Vocations distribution", value=f"{knight} {get_voc_emoji('knight')} | "
                                                             f"{druid} {get_voc_emoji('druid')} | "
                                                             f"{sorcerer} {get_voc_emoji('sorcerer')} | "
                                                             f"{paladin} {get_voc_emoji('paladin')} | "
                                                             f"{none} {get_voc_emoji('none')}",
                        inline=False)

        await ctx.send(embed=embed)

    @commands.command(usage="[query]")
    async def worlds(self, ctx: NabCtx, *, query=None):
        """Shows a list of worlds.

        You can pass a list of parameters separated by commas to change the sorting or filter worlds.

        `online` to sort by online count.
        `descending` to reverse the order.
        `europe`, `south america` or `north america` to filter by location.
        `optional pvp`, `open pvp`, `retro open pvp`, `hardcore pvp` or `retro hardcore pvp` to filter by pvp type."""
        try:
            worlds = await get_world_list()
            if worlds is None:
                return await ctx.send(f"{ctx.tick(False)} Something went wrong...")
        except NetworkError:
            return await ctx.send(f"{ctx.tick(False)} I'm having network errors, please try again later.")
        if query is None:
            params = []
        else:
            params = query.lower().replace(" ", "").replace("-", "").split(",")
        sort = "name"
        if "online" in params:
            sort = "online_count"
        reverse = False
        if {"desc", "descending"}.intersection(params):
            reverse = True

        title = "Worlds"

        region_filter = None
        if {"eu", "europe"}.intersection(params):
            region_filter = "Europe"
        elif {"southamerica", "sa", "brazil", "brasil", "br"}.intersection(params):
            region_filter = "South America"
        elif {"northamerica", "na", "usa", "us"}.intersection(params):
            region_filter = "North America"

        if region_filter:
            title = f"Worlds in {region_filter}"

        pvp_filter = None
        if {"optionalpvp", "npvp", "nonpvp", "nopvp"}.intersection(params):
            pvp_filter = "Optional PvP"
        elif {"pvp", "openpvp"}.intersection(params):
            pvp_filter = "Open PvP"
        elif {"retropvp", "retroopenpvp"}.intersection(params):
            pvp_filter = "Retro Open PvP"
        elif {"hardcore", "hardcorepvp", "enforcedpvp"}.intersection(params):
            pvp_filter = "Hardcore PvP"
        elif {"retrohardcore", "retrohardcorepvp"}.intersection(params):
            pvp_filter = "Retro Hardcore PvP"

        if pvp_filter:
            title = f"{pvp_filter} {title}"

        if region_filter:
            worlds = filter(lambda w: w.location == region_filter, worlds)
        if pvp_filter:
            worlds = filter(lambda w: w.pvp_type == pvp_filter, worlds)

        worlds = sorted(worlds, key=attrgetter(sort), reverse=reverse)
        if not worlds:
            return await ctx.send("There's no worlds matching the query.")

        entries = [f"{w.name} {FLAGS[w.location]}{PVP[w.pvp_type]} - `{w.online_count:,} online`" for w in worlds]
        per_page = 20 if await ctx.is_long() else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        pages.embed.colour = discord.Colour.blurple()
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    # Utilities
    @staticmethod
    def get_article_embed(article, limit):
        url = f"http://www.tibia.com/news/?subtopic=newsarchive&id={article['id']}"
        embed = discord.Embed(title=article["title"], url=url)
        content = html_to_markdown(article["content"])
        thumbnail = get_first_image(article["content"])
        if thumbnail is not None:
            embed.set_thumbnail(url=thumbnail)

        messages = split_message(content, limit)
        embed.description = messages[0]
        embed.set_author(name="Tibia.com", url="http://www.tibia.com/news/?subtopic=latestnews", icon_url=tibia_logo)
        embed.set_footer(text=f"ID: {article['id']} | Posted on {article['date']:%A, %B %d, %Y}")
        if len(messages) > 1:
            embed.description += f"\n*[Read more...]({url})*"
        return embed

    @staticmethod
    def get_char_string(char: Character) -> str:
        """Returns a formatted string containing a character's info."""
        if char is None:
            return None
        reply = "[{0.name}]({0.url}) is a level {0.level} __{0.vocation}__. " \
                "{0.he_she} resides in __{0.residence}__ in the world of __{0.world}__".format(char)
        if char.former_world is not None:
            reply += " (formerly __{0.former_world}__)".format(char)
        reply += ". {0.he_she} has {0.achievement_points:,} achievement points.".format(char)

        if char.guild is not None:
            guild_url = url_guild+urllib.parse.quote(char.guild_name)
            reply += "\n{0.he_she} is __{1}__ of the [{2}]({3}).".format(char,
                                                                         char.guild_rank,
                                                                         char.guild_name,
                                                                         guild_url)
        if char.married_to is not None:
            married_url = Character.get_url(char.married_to)
            reply += "\n{0.he_she} is married to [{0.married_to}]({1}).".format(char, married_url)
        if char.house is not None:
            house_url = url_house.format(id=char.house["houseid"], world=char.world)
            reply += "\n{0.he_she} owns [{1}]({2}) in {3}.".format(char,
                                                                   char.house["name"],
                                                                   house_url,
                                                                   char.house["town"])
        if char.last_login is not None:
            now = dt.datetime.utcnow()
            now = now.replace(tzinfo=dt.timezone.utc)
            time_diff = now - char.last_login
            if time_diff.days > 7:
                reply += "\n{1.he_she} hasn't logged in for **{0}**.".format(get_time_diff(time_diff), char)
        else:
            reply += "\n{0.he_she} has never logged in.".format(char)

        # Insert any highscores this character holds
        for highscore in char.highscores:
            highscore_string = highscore_format[highscore["category"]].format(char.his_her,
                                                                              highscore["value"],
                                                                              highscore['rank'])
            reply += "\n🏆 {0}".format(highscore_string)

        return reply

    async def get_user_embed(self, ctx: NabCtx, user: discord.Member) -> Optional[discord.Embed]:
        if user is None:
            return None
        embed = discord.Embed()
        if ctx.is_private:
            display_name = '@'+user.name
            user_guilds = self.bot.get_user_guilds(ctx.author.id)
            user_tibia_worlds = [world for server, world in self.bot.tracked_worlds.items() if
                                 server in [s.id for s in user_guilds]]
        else:
            display_name = '@'+user.display_name
            embed.colour = user.colour
            if self.bot.tracked_worlds.get(ctx.guild.id) is None:
                user_tibia_worlds = []
            else:
                user_tibia_worlds = [self.bot.tracked_worlds[ctx.guild.id]]
        if len(user_tibia_worlds) == 0:
            return None
        embed.set_thumbnail(url=user.avatar_url)
        characters = await ctx.pool.fetch("""SELECT name, abs(level) AS level, vocation
                                             FROM "character"
                                             WHERE user_id = $1 AND world = any($2)
                                             ORDER BY level DESC""", user.id, user_tibia_worlds)
        if not characters:
            embed.description = f"I don't know who **{display_name}** is..."
            return embed
        online_list = [x.name for v in online_characters.values() for x in v]
        char_list = []
        for char in characters:
            online = config.online_emoji if char["name"] in online_list else ""
            voc_abb = get_voc_abb(char["vocation"])
            char_url = url_character + urllib.parse.quote(char["name"].encode('iso-8859-1'))
            if len(characters) <= 10:
                char_list.append("[{name}]({url}){online} (Lvl {level} {voc})".format(**char, url=char_url, voc=voc_abb,
                                                                                      online=online))
            else:
                char_list.append("**{name}**{online} (Lvl {level} {voc})".format(**char, voc=voc_abb, online=online))
            char_string = "@**{0.display_name}**'s character{1}: {2}"
            plural = "s are" if len(char_list) > 1 else " is"
            embed.description = char_string.format(user, plural, join_list(char_list, ", ", " and "))
        return embed

    @staticmethod
    def get_house_embed(ctx: NabCtx, house):
        """Gets the embed to show in /house command"""
        if type(house) is not dict:
            return
        embed = discord.Embed(title=house["name"])
        house["type"] = "house" if house["guildhall"] == 0 else "guildhall"
        house["_beds"] = "bed" if house["beds"] == 1 else "beds"
        description = "This {type} has **{beds}** {_beds} and a size of **{size}** sqm." \
                      " This {type} is in **{city}**.".format(**house)
        # House was fetched correctly
        if house["fetch"]:
            embed.url = house["url"]
            description += " The rent is **{rent:,}** gold per month.".format(**house)
            if house["status"] == "empty":
                description += "\nIn **{world}**, this {type} is unoccupied.".format(**house)
            elif house["status"] in ["rented", "moving", "transfering"]:
                house["owner_url"] = get_character_url(house["owner"])
                description += "\nIn **{world}**, this {type} is rented by [{owner}]({owner_url}).".format(**house)
                if house["status"] == "moving":
                    description += "\n{owner_pronoun} is moving out on **{move_date}**."
                if house["status"] == "transfering":
                    house["transferee_url"] = get_character_url(house["transferee"])
                    description += "\nIt will be transferred to [{transferee}]({transferee_url}) for **{transfer_price:,}** " \
                                   "gold on **{move_date}**.".format(**house)
                    if not house["accepted"]:
                        description += "\nThe transfer hasn't been accepted."
            elif house["status"] == "auctioned":
                house["bidder_url"] = get_character_url(house["top_bidder"])
                description += "\nIn **{world}**, this {type} is being auctioned. " \
                               "The top bid is **{top_bid:,}** gold, by [{top_bidder}]({bidder_url}).\n" \
                               "The auction ends at **{auction_end}**".format(**house)

        description += f"\n*[TibiaWiki article](https://tibia.wikia.com/wiki/{urllib.parse.quote(house['name'])})*"
        embed.description = description
        if "world" not in house:
            embed.set_footer(text=f"To check a specific world, try: '{ctx.clean_prefix}{ctx.invoked_with} "
                                  f"{house['name']},{random.choice(tibia_worlds)}'")
        return embed

    async def scan_news(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                recent_news = await get_recent_news()
                if recent_news is None:
                    await asyncio.sleep(30)
                    continue
                last_article = recent_news[0]["id"]
                last_id = await get_global_property(self.bot.pool, "last_article", default=0)
                await set_global_property(self.bot.pool, "last_article", last_article)
                new_articles = []
                for article in recent_news:
                    # Do not post articles older than a week (in case bot was offline)
                    if int(article["id"]) == last_id or (dt.date.today() - article["date"]).days > 7:
                        break
                    fetched_article = await get_news_article(int(article["id"]))
                    if fetched_article is not None:
                        new_articles.insert(0, fetched_article)
                for article in new_articles:
                    log.info("Announcing new article: {id} - {title}".format(**article))
                    for guild in self.bot.guilds:
                        news_channel_id = await get_server_property(self.bot.pool, guild.id, "news_channel", default=0)
                        if news_channel_id == 0:
                            continue
                        channel = self.bot.get_channel_or_top(guild, news_channel_id)
                        try:
                            await channel.send("New article posted on Tibia.com",
                                               embed=self.get_article_embed(article, 1000))
                        except discord.Forbidden:
                            log.warning("scan_news: Missing permissions.")
                        except discord.HTTPException:
                            log.warning("scan_news: Malformed message.")
                await asyncio.sleep(60 * 60 * 2)
            except (IndexError, KeyError):
                log.warning("scan_news: Error getting recent news")
                await asyncio.sleep(60*30)
                continue
            except NetworkError:
                await asyncio.sleep(30)
                continue
            except asyncio.CancelledError:
                # Task was cancelled, so this is fine
                break
            except Exception:
                log.exception("Task: scan_news")

    @staticmethod
    def _get_cached_user_(self, user_id, users_cache, user_servers):
        if user_id in users_cache:
            return users_cache.get(user_id)
        else:
            member_user = self.bot.get_member(user_id, user_servers)
            users_cache[user_id] = member_user
            return member_user

    def __unload(self):
        print("cogs.tibia: Cancelling pending tasks...")
        self.news_announcements_task.cancel()


def setup(bot):
    bot.add_cog(Tibia(bot))