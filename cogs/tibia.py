import asyncio
import calendar
import datetime as dt
import logging
import random
import re
from collections import Counter, defaultdict
from operator import attrgetter
from typing import Optional

import asyncpg
import discord
import pytz
import tibiapy
import tibiawikisql
from discord.ext import commands
from tibiapy import Category, GuildHouse, House, HouseStatus, Sex, TransferType, VocationFilter
from tibiawikisql import models

from nabbot import NabBot
from .utils import CogUtils, checks, config, errors, get_time_diff, get_user_avatar, is_numeric, \
    join_list, online_characters, timing
from .utils.context import NabCtx
from .utils.database import DbChar, DbDeath, DbLevelUp, get_global_property, get_recent_timeline, get_server_property, \
    set_global_property
from .utils.messages import get_first_image, html_to_markdown, split_message
from .utils.pages import Pages, VocationPages
from .utils.tibia import HIGHSCORES_FORMAT, HIGHSCORE_CATEGORIES, NabChar, TIBIACOM_ICON, TIBIA_URL, get_character, \
    get_guild, get_highscores, get_house, get_house_id, get_level_by_experience, get_map_area, get_news_article, \
    get_rashid_city, get_recent_news, get_share_range, get_tibia_time_zone, get_voc_abb, get_voc_abb_and_emoji, \
    get_voc_emoji, get_world, get_world_bosses, get_world_list, normalize_vocation, tibia_worlds

log = logging.getLogger("nabbot")


FLAGS = {"North America": "🇺🇸", "South America": "🇧🇷", "Europe": "🇬🇧"}
PVP = {"Optional PvP": "🕊️", "Hardcore PvP": "💀", "Open PvP": "⚔",
       "Retro Open PvP": "⚔", "Retro Hardcore PvP":  "💀"}
TRANSFERS = {"locked": "🔒", "blocked": "⛔"}


class Tibia(CogUtils):
    """Commands related to Tibia, gathered from information present in Tibia.com"""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.news_announcements_task = self.bot.loop.create_task(self.scan_news())

    # region Events

    async def scan_news(self):
        tag = f"{self.tag}[scan_news]"
        await self.bot.wait_until_ready()
        log.info(f"{tag} Task started")
        while not self.bot.is_closed():
            try:
                recent_news = await get_recent_news()
                if recent_news is None:
                    await asyncio.sleep(30)
                    continue
                log.debug(f"{tag} Checking recent news")
                last_article = recent_news[0]["id"]
                last_id = await get_global_property(self.bot.pool, "last_article")
                await set_global_property(self.bot.pool, "last_article", last_article)
                # Do not announce anything if this is the first time the task is executed.
                if last_id is None:
                    break
                new_articles = []
                for article in recent_news:
                    # Do not post articles older than a week (in case bot was offline)
                    if int(article["id"]) == last_id or (dt.date.today() - article["date"]).days > 7:
                        break
                    fetched_article = await get_news_article(int(article["id"]))
                    if fetched_article is not None:
                        new_articles.insert(0, fetched_article)
                for article in new_articles:
                    log.info(f"{tag} New article: {article['id']} - {article['title']}")
                    for guild in self.bot.guilds:
                        news_channel_id = await get_server_property(self.bot.pool, guild.id, "news_channel", default=0)
                        if news_channel_id == 0:
                            continue
                        channel = self.bot.get_channel_or_top(guild, news_channel_id)
                        try:
                            await channel.send("New article posted on Tibia.com",
                                               embed=self.get_article_embed(article, 1000))
                        except discord.Forbidden:
                            log.warning(f"{tag} Missing permissions.")
                        except discord.HTTPException:
                            log.warning(f"{tag} Malformed message.")
                await asyncio.sleep(60 * 60 * 2)
            except (IndexError, KeyError):
                log.warning(f"{tag} Error getting recent news")
                await asyncio.sleep(60*30)
                continue
            except errors.NetworkError:
                await asyncio.sleep(30)
                continue
            except asyncio.CancelledError:
                # Task was cancelled, so this is fine
                break
            except Exception as e:
                log.exception(f"{tag} Exception: {e}")

    # endregion

    # region Commands
    # TODO: Needs a revision
    @checks.can_embed()
    @commands.command()
    async def bosses(self, ctx: NabCtx, world=None):
        """Shows predictions for bosses."""
        if world is None and not ctx.is_private and ctx.world:
            world = ctx.world
        elif world is None:
            await ctx.error("You need to tell me a world's name.")
            return
        world = world.title()
        if world not in tibia_worlds:
            await ctx.error("That world doesn't exist.")
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

        If this discord server is tracking a tibia world, it will also show previous registered deaths.

        Additionally, if no name is provided, relevant recent deaths will be shown."""
        if name is None and ctx.is_lite:
            return await ctx.error("You must tell me the name of a character.")

        if ctx.world is None and name is None and not ctx.is_private:
            return await ctx.error("This server is not tracking any tibia worlds.")

        entries = []
        embed_info = defaultdict(lambda: discord.Embed.Empty)
        per_page = 20 if await ctx.is_long() else 5
        if name is None:
            embed_info["title"] = "☠ Recent deaths"
            entries = await self.get_recent_deaths(ctx)
        else:
            char = await get_character(self.bot, name)
            if char is None:
                return await ctx.error("That character doesn't exist.")
            last_time = await self.get_recent_deaths_from_tibiacom(ctx, char, embed_info, entries)
            await self.get_recent_deaths_from_database(ctx, name, embed_info, entries, last_time)
        if not entries:
            await ctx.send("There are no recent deaths.")
            return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = embed_info["title"]
        pages.embed.url = embed_info["url"]
        if embed_info["author"]:
            pages.embed.set_author(name=embed_info["author"], icon_url=embed_info["author_icon"], url=embed_info["author_url"])
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.error(e)

    @checks.tracking_world_only()
    @checks.can_embed()
    @deaths.command(name="monster", aliases=["mob", "killer"])
    async def deaths_monsters(self, ctx: NabCtx, *, name: str):
        """Shows the latest deaths caused by a specific monster."""
        entries = []
        now = dt.datetime.now(dt.timezone.utc)
        per_page = 20 if await ctx.is_long() else 5
        async with ctx.pool.acquire() as conn:
            async for death in DbDeath.get_by_killer(conn, name, worlds=ctx.world):
                user = ctx.guild.get_member(death.char.user_id)
                if user is None:
                    continue
                death_time = get_time_diff(now-death.date)
                user_name = user.display_name
                emoji = get_voc_emoji(death.char.vocation)
                entries.append(f"{emoji} {death.char.name} (**@{user_name}**) - At level **{death.level}** - "
                               f"*{death_time} ago*")
                if len(entries) >= 100:
                    break
        if not entries:
            await ctx.send("There are no registered deaths by that killer.")
            return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = f"{name.title()} latest kills"

        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="user")
    @checks.can_embed()
    @checks.tracking_world_only()
    async def deaths_user(self, ctx: NabCtx, *, name: str):
        """Shows a user's recent deaths on his/her registered characters."""
        user = self.bot.get_member(name, ctx.guild)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return
        entries = []
        now = dt.datetime.now(dt.timezone.utc)
        per_page = 20 if await ctx.is_long() else 5
        async with ctx.pool.acquire() as conn:
            async for death in DbDeath.get_latest(conn, config.announce_threshold, user_id=user.id, worlds=ctx.world):
                death_time = get_time_diff(now - death.date)
                emoji = get_voc_emoji(death.char.vocation)
                entries.append(f"{emoji} {death.char.name} - At level **{death.level}** by {death.killer.name} - "
                               f"*{death_time} ago*")
                if len(entries) >= 100:
                    break
        if not entries:
            await ctx.send("There are not registered deaths by this user.")
            return

        title = f"{user.display_name} latest deaths"
        icon_url = user.avatar_url
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.set_author(name=title, icon_url=icon_url)
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="stats", usage="[week/month]")
    @checks.tracking_world_only()
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
            total = await conn.fetchval("""SELECT count(*) FROM character_death WHERE CURRENT_TIMESTAMP-date < $1""",
                                        period)
            embed.description = f"There are {total:,} deaths registered{description_suffix}."
            async with conn.transaction():
                count = 0
                content = ""
                async for row in conn.cursor("""
                        SELECT COUNT(*), name, user_id
                        FROM character_death d
                        LEFT JOIN "character" c on c.id = d.character_id
                        WHERE CURRENT_TIMESTAMP-date < $1 AND world = $2
                        GROUP by name, user_id ORDER BY count DESC""", period, ctx.world):
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

    @checks.can_embed()
    @commands.group(aliases=['checkguild'], invoke_without_command=True, case_insensitive=True)
    async def guild(self, ctx: NabCtx, *, name):
        """Shows online characters in a guild.

        Show's the number of members the guild has and a list of their users.
        It also shows whether the guild has a guildhall or not, and their funding date.
        """
        guild = await get_guild(name)
        if guild is None:
            return await ctx.error("The guild {0} doesn't exist.".format(name))

        embed = self.get_tibia_embed(f"{guild.name} ({guild.world})", guild.url)
        embed.description = ""
        embed.set_thumbnail(url=guild.logo_url)
        if guild.guildhall is not None:
            url = GuildHouse.get_url(get_house_id(guild.guildhall.name), guild.world)
            embed.description += f"They own the guildhall [{guild.guildhall.name}]({url}).\n"

        if len(guild.online_members) < 1:
            embed.description += f"Nobody is online. It has **{guild.member_count:,}** members."
            await ctx.send(embed=embed)
            return

        embed.set_footer(text=f"The guild was founded on {guild.founded}")

        plural = ""
        if len(guild.online_members) > 1:
            plural = "s"
        embed.description += f"It has **{guild.online_count:,}** player{plural} online out of " \
            f"**{guild.member_count:,}**:"
        current_field = ""
        result = ""
        for member in guild.online_members:
            if current_field == "":
                current_field = member.rank
            elif member.rank != current_field and member.rank != "":
                embed.add_field(name=current_field, value=result, inline=False)
                result = ""
                current_field = member.rank
            title = '(*' + member.title + '*) ' if member.title else ''
            vocation = get_voc_abb(member.vocation.value)

            result += f"{member.name} {title}\u2192 {member.level:,} {vocation}\n"
        embed.add_field(name=current_field, value=result, inline=False)
        await ctx.send(embed=embed)

    @checks.can_embed()
    @guild.command(name="info", aliases=["stats"])
    async def guild_info(self, ctx: NabCtx, *, name: str):
        """Shows basic information and stats about a guild.

        It shows their description, homepage, guildhall, number of members and more."""
        guild = await get_guild(name)
        if guild is None:
            return await ctx.send("The guild {0} doesn't exist.".format(name))
        embed = self.get_tibia_embed(f"{guild.name} ({guild.world})", guild.url)
        embed.description = ""
        embed.set_thumbnail(url=guild.logo_url)
        embed.set_footer(text=f"The guild was founded on {guild.founded}")
        if guild.description:
            embed.description = guild.description
        if guild.guildhall is not None:
            url = GuildHouse.get_url(get_house_id(guild.guildhall.name), guild.world)
            embed.description += f"\nThey own the guildhall [{guild.guildhall.name}]({url}).\n"
        applications = f"{ctx.tick(True)} Open" if guild.open_applications else f"{ctx.tick(False)} Closed"
        embed.add_field(name="Applications", value=applications)
        if guild.homepage is not None:
            embed.add_field(name="Homepage", value=f"[{guild.homepage}]({guild.homepage})")
        knight = 0
        paladin = 0
        sorcerer = 0
        druid = 0
        none = 0
        total_level = 0
        highest_member = guild.members[0]
        for member in guild.members:
            if highest_member.level < member.level:
                highest_member = member
            total_level += member.level
            if "knight" in member.vocation.value.lower():
                knight += 1
            if "sorcerer" in member.vocation.value.lower():
                sorcerer += 1
            if "druid" in member.vocation.value.lower():
                druid += 1
            if "paladin" in member.vocation.value.lower():
                paladin += 1
            if "none" in member.vocation.value.lower():
                none += 1

        embed.add_field(name="Members online", value=f"{guild.online_count}/{guild.member_count}")
        embed.add_field(name="Average level", value=f"{total_level/guild.member_count:.0f}")
        embed.add_field(name="Highest member", value=f"{highest_member.name} - {highest_member.level:,}"
                                                     f"{get_voc_emoji(highest_member.vocation)}")
        embed.add_field(name="Vocations distribution", value=f"{knight} {get_voc_emoji('knight')} | "
                                                             f"{druid} {get_voc_emoji('druid')} | "
                                                             f"{sorcerer} {get_voc_emoji('sorcerer')} | "
                                                             f"{paladin} {get_voc_emoji('paladin')} | "
                                                             f"{none} {get_voc_emoji('none')}",
                        inline=False)

        await ctx.send(embed=embed)

    @checks.can_embed()
    @guild.command(name="members", aliases=['list'])
    async def guild_members(self, ctx: NabCtx, *, name: str):
        """Shows a list of all guild members.

        Online members have an icon next to their name."""
        guild = await get_guild(name)
        if guild is None:
            return await ctx.error(f"The guild {name} doesn't exist.")
        title = "{0.name} ({0.world})".format(guild)
        entries = []
        vocations = []
        for m in guild.members:
            nick = f'(*{m.title}*) ' if m.title else ''
            vocations.append(m.vocation.value)
            emoji = get_voc_emoji(m.vocation.value)
            voc_abb = get_voc_abb(m.vocation.value)
            online = config.online_emoji if m.online else ""
            entries.append(f"{m.rank} \u2014 {online}**{m.name}** {nick} (Lvl {m.level} {voc_abb}{emoji})")
        per_page = 20 if await ctx.is_long() else 5
        pages = VocationPages(ctx, entries=entries, per_page=per_page, vocations=vocations)
        pages.embed.set_author(name=title, icon_url=guild.logo_url, url=guild.url)
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.error(e)

    @checks.can_embed()
    @commands.group(usage="[world,][category][,vocation]", invoke_without_command=True, case_insensitive=True)
    async def highscores(self, ctx: NabCtx, *, params=None):
        """Shows the entries in the highscores.

        If the server is already tracking a world, the tracked world will be used if no world is specified.

        Available categories are: experience, magic, shielding, distance, sword, club, axe, fist, fishing,
        achievements and loyalty.
        Available vocations are: all, paladin, druid, sorcerer, knight."""
        if params is None:
            params = []
        else:
            params = params.split(",")
        world = ctx.world
        if params and params[0].strip().title() in tibia_worlds:
            world = params[0].strip().title()
            del params[0]
        if world is None:
            return await ctx.error("You have to specify a world.")

        # Default parameters
        if not params:
            category = Category.EXPERIENCE
            vocation = VocationFilter.ALL
        else:
            category = tibiapy.utils.try_enum(Category, params[0].strip().lower())
            if category is None:
                return await ctx.error(f"Invalid category, valid categories are: "
                                       f"{join_list([f'`{c.value}`' for c in Category])}")
            try:
                vocation = VocationFilter.from_name(params[1].strip().lower())
                if vocation is None:
                    return await ctx.error(f"Invalid vocation, valid vocations are: "
                                           f"`{join_list([f'`{v.name.lower()}`' for v in VocationFilter])}.")
            except IndexError:
                vocation = VocationFilter.ALL

        with ctx.typing():
            highscores = await get_highscores(world, category, vocation)
            if highscores is None:
                return await ctx.error("I couldn't find any highscores entries.")
        entries = []
        for entry in highscores.entries:
            name = f"[{entry.name}]({entry.url})" if not await ctx.is_long() else entry.name
            emoji = get_voc_emoji(entry.vocation)
            content = f"**{name}**{emoji} - "
            if category == Category.EXPERIENCE:
                content += f"Level {entry.level} ({entry.value:,} exp)"
            elif category in [Category.LOYALTY_POINTS, Category.ACHIEVEMENTS]:
                content += f"{entry.value:,} points"
            else:
                content += f"Level {entry.value}"
            entries.append(content)
        pages = Pages(ctx, entries=entries, per_page=20 if await ctx.is_long() else 10)
        pages.embed.url = highscores.url
        pages.embed.set_author(name="Tibia.com", url=TIBIA_URL, icon_url=TIBIACOM_ICON)
        pages.embed.title = f"🏆 {category.name.replace('_', ' ').title()} highscores for {world}"
        if vocation != VocationFilter.ALL:
            pages.embed.title += f" ({vocation.name.lower()})"
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @checks.can_embed()
    @highscores.command(name="global")
    async def highscores_global(self, ctx: NabCtx, category="experience"):
        """Shows the combined highscores of all worlds.

        Ties are grouped under the same rank and ordered alphabetically.

        Only the following categories are available: experience, sword, axe, club, distance, shielding, fist, fishing,
        magic, magic_knights, magic_paladins, loyalty, achievements.
        """
        if category not in HIGHSCORE_CATEGORIES:
            return await ctx.error(f"Invalid category, valid categories are: "
                                   f"{join_list([f'`{k}`' for k,v in HIGHSCORE_CATEGORIES.items()])}")

        _category, vocation = HIGHSCORE_CATEGORIES[category]
        rows = await ctx.pool.fetch("""SELECT rank() OVER (ORDER BY value DESC), name, world, vocation, value 
                                       FROM highscores_entry WHERE category = $1
                                       ORDER BY value DESC, name ASC LIMIT 300""", category)
        entries = []
        for rank, name, world, voc, value in rows:
            if not await ctx.is_long():
                name = f"[{name}]({tibiapy.Character.get_url(name)})"

            emoji = get_voc_emoji(voc)
            content = f"{rank}. **{name}**{emoji} ({world}) - "
            if _category == Category.EXPERIENCE:
                level = get_level_by_experience(value)
                content += f"Level {level} ({value:,} exp)"
            elif _category in [Category.LOYALTY_POINTS, Category.ACHIEVEMENTS]:
                content += f"{value:,} points"
            else:
                content += f"Level {value}"
            entries.append(content)

        pages = Pages(ctx, entries=entries, per_page=20 if await ctx.is_long() else 10, show_numbers=False)
        pages.embed.title = f"🏆Global {_category.name.replace('_', ' ').title()} highscores"
        if vocation != VocationFilter.ALL:
            pages.embed.title += f" ({vocation.name.lower()})"
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @checks.can_embed()
    @commands.command(aliases=["guildhall"], usage="<name>[,world]")
    async def house(self, ctx: NabCtx, *, name: str):
        """Shows info for a house or guildhall.

        By default, it shows the current status of a house for the current tracked world (if any).
        If used on private messages, no world is looked up unless specified.

        To specify a world, add the world at the end separated with a comma.
        """
        house = None
        params = name.split(",")
        footer = ""
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

        wiki_cog = self.bot.get_cog("TibiaWiki")
        if wiki_cog is None:
            return await ctx.error("TibiaWiki cog is unavailable for the moment, try again later.")

        entries = wiki_cog.search_entry("house", name)
        if not entries:
            await ctx.send("I couldn't find a house with that name.")
            return
        if len(entries) > 1:
            title = await ctx.choose([e["title"] for e in entries])
            if title is None:
                return
        else:
            title = entries[0]["title"]
        wiki_house: models.House = wiki_cog.get_entry(title, models.House)

        if world:
            try:
                house = await get_house(wiki_house.house_id, world)
            except errors.NetworkError:
                pass
        # Attach image only if the bot has permissions
        if ctx.bot_permissions.attach_files:
            mapimage = get_map_area(wiki_house.x, wiki_house.y, wiki_house.z)
            embed = self.get_house_embed(ctx, wiki_house, house)
            embed.set_image(url="attachment://thumbnail.png")
            await ctx.send(file=discord.File(mapimage, "thumbnail.png"), embed=embed)
        else:
            await ctx.send(embed=self.get_house_embed(ctx, wiki_house, house))

    @commands.group(aliases=['levelups'], invoke_without_command=True, case_insensitive=True)
    @checks.tracking_world_only()
    @checks.can_embed()
    async def levels(self, ctx: NabCtx, *, name: str = None):
        """Shows a character's or everyone's recent level ups.

        If a character is specified, it displays a list of its recent level ups.
        If no character is specified, it will show the recent level ups of all registered characters in the server.

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        now = dt.datetime.now(dt.timezone.utc)
        per_page = 20 if await ctx.is_long() else 5
        user_cache = dict()
        if name is None:
            title = "Latest level ups"
            async with ctx.pool.acquire() as conn:
                async for lvl in DbLevelUp.get_latest(conn, minimum_level=config.announce_threshold, worlds=ctx.world):
                    user = self.get_cached_user_(lvl.char.user_id, user_cache, ctx.guild)
                    if user is None:
                        continue
                    diff = get_time_diff(now - lvl.date)
                    emoji = get_voc_emoji(lvl.char.vocation)
                    entries.append(f"{emoji} {lvl.char.name} - Level **{lvl.level}** - **@{user.display_name}** - "
                                   f"*{diff} ago*")
                    if len(entries) >= 100:
                        break
        else:
            async with ctx.pool.acquire() as conn:
                db_char = await DbChar.get_by_name(conn, name)
                if not db_char:
                    return await ctx.send("I don't have a character with that name registered.")
                owner = ctx.guild.get_member(db_char.user_id)
                if not owner:
                    return await ctx.send("I don't have a character with that name registered.")
                author = owner.display_name
                author_icon = owner.avatar_url
                name = db_char.name
                emoji = get_voc_emoji(db_char.vocation)
                title = f"{emoji} {name} latest level ups"
                async for lvl in db_char.get_level_ups(conn):
                    diff = get_time_diff(now - lvl.date)
                    entries.append(f"Level **{lvl.level}** - *{diff} ago*")
                    if len(entries) >= 100:
                        break
        if not entries:
            await ctx.send("There are no registered levels.")
            return
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        if author is not None:
            pages.embed.set_author(name=author, icon_url=author_icon)
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @levels.command(name="user")
    @checks.tracking_world_only()
    @checks.can_embed()
    async def levels_user(self, ctx: NabCtx, *, name: str):
        """Shows a user's recent level ups on their registered characters."""
        user = self.bot.get_member(name, ctx.guild)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        count = 0
        entries = []
        now = dt.datetime.now(dt.timezone.utc)
        per_page = 20 if await ctx.is_long() else 5
        async with ctx.pool.acquire() as conn:
            async for l in DbLevelUp.get_latest(conn, user_id=ctx.author.id, worlds=ctx.world):
                    count += 1
                    level_time = get_time_diff(now - l.date)
                    emoji = get_voc_emoji(l.char.vocation)
                    entries.append(f"{emoji} {l.char.name} - Level **{l.level}** - *{level_time} ago*")
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
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @checks.can_embed()
    @commands.command(usage="[id]")
    async def news(self, ctx: NabCtx, news_id: int = None):
        """Shows the latest news articles from Tibia.com.

        If no id is supplied, a list of recent articles is shown, otherwise, a snippet of the article is shown."""
        if news_id is None:
            recent_news = await get_recent_news()
            if recent_news is None:
                await ctx.error("Something went wrong getting recent news.")
            embed = self.get_tibia_embed("Recent news", "https://www.tibia.com/news/?subtopic=latestnews")
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
            return await ctx.send(embed=embed)
        try:
            article = await get_news_article(news_id)
            if article is None:
                return await ctx.error("There's no article with that id.")
        except errors.NetworkError:
            return await ctx.error("I couldn't fetch the recent news, I'm having network problems.")
        limit = 1900 if await ctx.is_long() else 600
        embed = self.get_article_embed(article, limit)
        await ctx.send(embed=embed)

    @checks.can_embed()
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
            return await ctx.error(invalid_arguments)

        tracked_world = ctx.world
        if world_name is None:
            if tracked_world is None:
                return await ctx.error("You must specify the world where you want to look in.")
            else:
                world_name = tracked_world

        world = await get_world(world_name)
        if world is None:
            # This really shouldn't happen...
            await ctx.error(f"There's no world named **{world_name}**.")
            return

        online_list = world.online_players
        if not online_list:
            return await ctx.error(f"There is no one online in {world_name}.")

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
                return await ctx.error(invalid_arguments)
            char = await get_character(ctx.bot, params[0])
            if char is None:
                await ctx.error("I couldn't find a character with that name.")
                return
            filter_name = char.name
            if char.world != world.name:
                content = f"**Note**: The character is in **{char.world}** and I'm searching **{world.name}**."
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
                    await ctx.error(invalid_arguments)
                    return
                if level1 <= 0 or level2 <= 0:
                    await ctx.error("You entered an invalid level.")
                    return
                low = min(level1, level2)
                high = max(level1, level2)
                title = "Characters online between level {0} and {1}".format(low, high)
                empty = "I didn't find anyone between levels **{0}** and **{1}**".format(low, high)
            # We only got a level, so we get the share range for it
            else:
                if int(params[0]) <= 0:
                    await ctx.error("You entered an invalid level.")
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
        except errors.CannotPaginate as e:
            await ctx.error(e)

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
                return await ctx.error("I can only check up to 5 characters at a time.")
            if len(chars) == 1:
                with ctx.typing():
                    char = await get_character(ctx.bot, chars[0])
                    if char is None:
                        await ctx.error('There is no character with that name.')
                        return
                    name = char.name
                    level = char.level
                    low, high = get_share_range(char.level)
                    await ctx.send(f"**{name}** ({level}) can share experience with levels **{low}** to **{high}**.")
                    return
            char_data = []
            # Check if all characters are the same.
            if all(x.lower() == chars[0].lower() for x in chars):
                await ctx.success("I'm not sure if sharing with yourself counts as sharing, but yes, you can share.")
                return
            with ctx.typing():
                for char in chars:
                    fetched_char = await get_character(ctx.bot, char)
                    if fetched_char is None:
                        await ctx.error(f"There is no character named **{char}**.")
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
                    await ctx.error(f"**{lowest_name}** ({lowest_level}) needs {low-lowest_level} more level"
                                    f"{'s' if low-lowest_level > 1 else ''} to share experience "
                                    f"with **{highest_name}** ({highest_level}).")
                    return
                # If it's more than two, just say they can all share
                if len(chars) > 2:
                    reply = f"They can all share experience with each other."
                else:
                    reply = f"**{lowest_name}** ({lowest_level}) and **{highest_name}** ({highest_level}) can " \
                            f"share experience."
                await ctx.success(f"{reply}\nTheir share range is from level **{low}** to **{high}**.")

    @checks.tracking_world_only()
    @checks.can_embed()
    @commands.group(aliases=["story"], invoke_without_command=True, case_insensitive=True)
    async def timeline(self, ctx: NabCtx, *, name: str = None):
        """Shows a character's recent level ups and deaths.

        If no character is provided, the timeline of all registered characters in the server will be shown.

        Characters must be registered in order to have a timeline.

        - 🌟 Indicates level ups
        - 💀 Indicates deaths
        """
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = dt.datetime.now(dt.timezone.utc)
        per_page = 20 if await ctx.is_long() else 5
        await ctx.channel.trigger_typing()
        user_cache = dict()
        if name is None:
            title = "Timeline"
            async with ctx.pool.acquire() as conn:
                async for entry in get_recent_timeline(conn, minimum_level=config.announce_threshold, worlds=ctx.world):
                    user = self.get_cached_user_(entry.char.user_id, user_cache, ctx.guild)
                    if user is None:
                        continue
                    count += 1
                    entry_time = get_time_diff(now - entry.date)
                    user_name = user.display_name
                    voc_emoji = get_voc_emoji(entry.char.vocation)
                    if isinstance(entry, DbDeath):
                        emoji = config.death_emoji
                        entries.append(f"{emoji}{voc_emoji} {entry.char.name} (**@{user_name}**) - "
                                       f"At level **{entry.level}** by {entry.killer.name} - *{entry_time} ago*")
                    else:
                        emoji = config.levelup_emoji
                        entries.append(f"{emoji}{voc_emoji} {entry.char.name} (**@{user_name}**) -"
                                       f" Level **{entry.level}** - *{entry_time} ago*")
                    if count >= 100:
                        break
        else:
            async with ctx.pool.acquire() as conn:
                db_char = await DbChar.get_by_name(conn, name)
                if db_char is None or db_char.world != ctx.world:
                    return await ctx.send("I don't have a character with that name registered.")
                owner = ctx.guild.get_member(db_char.user_id)
                if owner is None:
                    return await ctx.send("I don't have a character with that name registered.")
                author = owner.display_name
                author_icon = owner.avatar_url
                name = db_char.name
                emoji = get_voc_emoji(db_char.vocation)
                title = f"{emoji} {name} timeline"
                async for entry in db_char.get_timeline(conn):
                    count += 1
                    entry_time = get_time_diff(now - entry.date)
                    if isinstance(entry, DbDeath):
                        emoji = config.death_emoji
                        entries.append(f"{emoji} At level **{entry.level}** by {entry.killer.name} - "
                                       f"*{entry_time} ago*")
                    else:
                        emoji = config.levelup_emoji
                        entries.append(f"{emoji} Level **{entry.level}** - *{entry_time} ago*")
                    if count >= 100:
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
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @timeline.command(name="user")
    @checks.tracking_world_somewhere()
    async def timeline_user(self, ctx: NabCtx, *, name: str):
        """Shows a users's recent level ups and deaths on their characters."""
        user = self.bot.get_member(name, ctx.guild)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        entries = []
        count = 0
        now = dt.datetime.now(dt.timezone.utc)
        per_page = 20 if await ctx.is_long() else 5

        async with ctx.pool.acquire() as conn:
            title = f"{user.display_name} timeline"
            async for entry in get_recent_timeline(conn, worlds=ctx.world, user_id=user.id):
                count += 1
                entry_time = get_time_diff(now - entry.date)
                voc_emoji = get_voc_emoji(entry.char.vocation)
                if isinstance(entry, DbDeath):
                    emoji = config.death_emoji
                    entries.append(f"{emoji}{voc_emoji} {entry.char.name} - At level **{entry.level}** "
                                   f"by {entry.killer.name} - *{entry_time} ago*")
                else:
                    emoji = config.levelup_emoji
                    entries.append(f"{emoji}{voc_emoji} {entry.char.name} Level **{entry.level}** - *{entry_time} ago*")
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
        except errors.CannotPaginate as e:
            await ctx.send(e)

    @commands.group(aliases=['serversave'], invoke_without_command=True)
    async def time(self, ctx: NabCtx):
        """Displays Tibia server's time and time until server save.

        Server moderators can manage displayed timezones using the subcommands."""
        now = dt.datetime.now()
        tibia_timezone = get_tibia_time_zone()
        timezone_name = "CET" if tibia_timezone == 1 else "CEST"

        offset = tibia_timezone - timing.get_local_timezone()
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
                f"Server save is in **{server_save_str}**.\n" \
                f"Rashid is in **{get_rashid_city()}** today."
        if ctx.is_private:
            return await ctx.send(reply)

        saved_times = await self.get_timezones(ctx.guild.id)
        if not saved_times:
            return await ctx.send(reply)
        time_entries = sorted(saved_times, key=lambda k: now.astimezone(pytz.timezone(k["zone"])).utcoffset())
        reply += "\n\n"
        for entry in time_entries:
            timezone_time = now.astimezone(pytz.timezone(entry["zone"]))
            reply += f"**{timezone_time.strftime('%H:%M')}** in {entry['name']}\n"
        await ctx.send(reply)

    @checks.server_mod_only()
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

        try:
            await ctx.pool.execute("INSERT INTO server_timezone(server_id, zone, name) VALUES($1, $2, $3)",
                                   ctx.guild.id, _timezone, display_name.strip())
        except asyncpg.UniqueViolationError:
            return await ctx.error("That timezone already exists.")
        await ctx.send(f"{ctx.tick()} Timezone `{_timezone}` saved successfully as `{display_name.strip()}`.")

    @checks.server_mod_only()
    @checks.can_embed()
    @time.command(name="list")
    async def time_list(self, ctx: NabCtx):
        """Shows a list of all the currently added timezones.

        Only Server Moderators can use this command."""
        saved_times = await self.get_timezones(ctx.guild.id)
        if not saved_times:
            return await ctx.error(f"This server doesn't have any timezones saved yet.")

        pages = Pages(ctx, entries=[f"**{e['name']}** — *{e['zone']}*" for e in saved_times], per_page=10)
        pages.embed.title = "Saved times"
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.error(e)

    @checks.server_mod_only()
    @time.command(name="remove", aliases=["delete"], usage="<timezone>")
    async def time_remove(self, ctx: NabCtx, *, _timezone):
        """Removes a timezone from the list.

        Only Server Moderators can use this command."""
        saved_times = await self.get_timezones(ctx.guild.id)
        if not saved_times:
            return await ctx.error(f"This server doesn't have any timezones saved yet.")

        timezone = await ctx.pool.fetchrow("""SELECT zone, name FROM server_timezone
                                              WHERE lower(zone) = $1 AND server_id = $2""",
                                           _timezone.lower(), ctx.guild.id)
        if not timezone:
            return await ctx.error("There's no timezone saved with that name.\n"
                                   "Remember to use the timezone's real name, not the display name.\n")

        await ctx.pool.execute("DELETE FROM server_timezone WHERE server_id = $1 AND zone = $2",
                               ctx.guild.id, timezone["zone"])
        await ctx.success(f"Timezone {timezone['zone']} ({timezone['name']}) removed successfully.")

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
        if name.lower() == ctx.me.display_name.lower():
            await ctx.invoke(self.bot.all_commands.get('about'))
            return

        char = await get_character(ctx.bot, name)

        if ctx.is_lite or (not ctx.is_private and not ctx.world):
            if char is None:
                return await ctx.error("I couldn't find a character with that name.")
            log.debug("{self.tag} Found character, lite mode")
            return await ctx.send(embed=self.get_char_embed(char))
        # If the command is used on a DM, only search users in the servers the author is in
        # Otherwise, just search on the current server
        if ctx.is_private:
            guild_filter = self.bot.get_user_guilds(ctx.author.id)
            user_tibia_worlds = [world for server, world in self.bot.tracked_worlds.items() if
                                 server in [s.id for s in guild_filter]]
        else:
            guild_filter = ctx.guild
            user_tibia_worlds = [ctx.world] if ctx.world else []
        # If the user is a bot, then don't, just don't
        user = self.bot.get_member(name, guild_filter)
        if user and user.bot:
            user = None

        # No user or char with that name
        if char is None and user is None:
            return await ctx.error("I don't see any user or character with that name.")
        # We found a user
        if user is not None:
            user_embed = await self.get_user_embed(ctx, user)
            # Check if we found a char too
            if char is not None:
                char_embed = self.get_char_embed(char)
                # If it's owned by the user, we append it to the same embed.
                if char.owner_id == int(user.id):
                    if char_embed.fields:
                        highscores = char_embed.fields[0]
                        char_embed.add_field(name=highscores.name, value=highscores.value, inline=False)
                        char_embed.set_field_at(0, name="Character", value=char_embed.description, inline=False)
                    else:
                        char_embed.add_field(name="Character", value=char_embed.description, inline=False)
                    char_embed.description = user_embed.description
                    char_embed.colour = user_embed.colour
                    char_embed.set_thumbnail(url=user_embed.thumbnail.url)
                    log.debug(f"{self.tag} Matches user and char, same name.")
                    return await ctx.send(embed=char_embed)
                # Not owned by same user, we display a separate embed
                else:
                    log.debug(f"{self.tag} Matches user and char, different owner")
                    await ctx.send(embed=user_embed)
                    await ctx.send(embed=char_embed)
                    return
            # Tries to display user's highest level character since there is no character match
            if user_tibia_worlds:
                chars = await DbChar.get_chars_by_user(ctx.pool, user.id, worlds=user_tibia_worlds)
                if chars:
                    chars.sort(key=lambda c: c.level, reverse=True)
                    character = chars[0]
                    try:
                        char = await get_character(ctx.bot, character["name"])
                    except errors.NetworkError:
                        pass
                    else:
                        if char is not None:
                            char_embed = self.get_char_embed(char)
                            user_embed.add_field(name="Highest character", value=char_embed.description, inline=False)
                            if char.last_login is not None:
                                user_embed.set_footer(text="Last login")
                                user_embed.timestamp = char.last_login
            log.debug(f"{self.tag} Found user only, no char")
            return await ctx.send(embed=user_embed)
        owner = self.bot.get_member(char.owner_id, guild_filter) if char.owner_id else None
        if owner is not None and char.world in user_tibia_worlds:
            # Char is owned by a discord user
            user_embed = await self.get_user_embed(ctx, owner)
            char_embed = self.get_char_embed(char)
            if char_embed.fields:
                highscores = char_embed.fields[0]
                char_embed.add_field(name=highscores.name, value=highscores.value, inline=False)
                char_embed.set_field_at(0, name="Character", value=char_embed.description, inline=False)
            else:
                char_embed.add_field(name="Character", value=char_embed.description, inline=False)
            char_embed.description = user_embed.description
            char_embed.set_thumbnail(url=user_embed.thumbnail.url)
            log.debug(f"{self.tag} Found char only, owner is in same server")
            await ctx.send(embed=char_embed)
            return
        log.debug(f"{self.tag} Found char only")
        await ctx.send(embed=self.get_char_embed(char))

    @commands.command(name="world")
    async def world_info(self, ctx: NabCtx, name: str):
        """Shows basic information about a Tibia world.

        Shows information like PvP type, online count, server location, vocation distribution, and more."""
        world = await get_world(name)
        if world is None:
            await ctx.send("There's no world with that name.")
            return

        embed = self.get_tibia_embed(world.name, url=world.url)
        if world.status != "Online":
            embed.description = "This world is offline."
            embed.colour = discord.Colour.red()
        else:
            embed.colour = discord.Colour.green()
        embed.add_field(name="Players online", value=str(world.online_count))
        embed.set_footer(text=f"The players online record is {world.record_count}")
        embed.timestamp = world.record_date
        month = calendar.month_name[world.creation_month]
        embed.add_field(name="Created", value=f"{month} {world.creation_year}")

        embed.add_field(name="Location", value=f"{FLAGS.get(world.location.value,'')} {world.location.value}")
        embed.add_field(name="PvP Type", value=f"{PVP.get(world.pvp_type.value,'')} {world.pvp_type.value}")
        if world.premium_only:
            embed.add_field(name="Premium restricted", value=ctx.tick(True))
        if world.transfer_type != TransferType.REGULAR:
            embed.add_field(name="Transfers",
                            value=f"{TRANSFERS.get(world.transfer_type.value,'')} {world.transfer_type.value}")

        voc_counter = Counter(normalize_vocation(char.vocation) for char in world.online_players)
        embed.add_field(name="Vocations distribution",
                        value=f"{voc_counter.get('knight', 0)} {get_voc_emoji('knight')} | "
                              f"{voc_counter.get('druid', 0)} {get_voc_emoji('druid')} | "
                              f"{voc_counter.get('sorcerer', 0)} {get_voc_emoji('sorcerer')} | "
                              f"{voc_counter.get('paladin', 0)} {get_voc_emoji('paladin')} | "
                              f"{voc_counter.get('none', 0)} {get_voc_emoji('none')}",
                        inline=False)

        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command(usage="[query]")
    async def worlds(self, ctx: NabCtx, *, query=None):
        """Shows a list of worlds.

        You can pass a list of parameters separated by commas to change the sorting or filter worlds.

        `online` to sort by online count.
        `descending` to reverse the order.
        `europe`, `south america` or `north america` to filter by location.
        `optional pvp`, `open pvp`, `retro open pvp`, `hardcore pvp` or `retro hardcore pvp` to filter by pvp type."""
        worlds = await get_world_list()
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
            worlds = filter(lambda w: w.location.value == region_filter, worlds)
        if pvp_filter:
            worlds = filter(lambda w: w.pvp_type.value == pvp_filter, worlds)

        worlds = sorted(worlds, key=attrgetter(sort), reverse=reverse)
        if not worlds:
            return await ctx.send("There's no worlds matching the query.")

        entries = [f"{w.name} {FLAGS[w.location.value]}{PVP[w.pvp_type.value]} - `{w.online_count:,} online`" for w in worlds]
        per_page = 20 if await ctx.is_long() else 5
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        pages.embed.colour = discord.Colour.blurple()
        pages.embed.set_author(name="Tibia.com", icon_url=TIBIACOM_ICON, url=TIBIA_URL)
        pages.embed.url = tibiapy.WorldOverview.get_url()
        try:
            await pages.paginate()
        except errors.CannotPaginate as e:
            await ctx.send(e)

    # endregion

    # region Auxiliary methods
    @classmethod
    def get_article_embed(cls, article, limit):
        url = f"http://www.tibia.com/news/?subtopic=newsarchive&id={article['id']}"
        embed = cls.get_tibia_embed(article["title"], url=url)
        content = html_to_markdown(article["content"])
        thumbnail = get_first_image(article["content"])
        if thumbnail is not None:
            embed.set_thumbnail(url=thumbnail)

        messages = split_message(content, limit)
        embed.description = messages[0]
        embed.set_footer(text=f"ID: {article['id']} | Posted on {article['date']:%A, %B %d, %Y}")
        if len(messages) > 1:
            embed.description += f"\n*[Read more...]({url})*"
        return embed

    @classmethod
    def get_char_embed(cls, char: NabChar) -> discord.Embed:
        """Returns a formatted string containing a character's info."""
        embed = cls.get_tibia_embed()

        description = f"[{char.name}]({char.url}) is a level {char.level} __{char.vocation}__." \
                      f" {char.he_she} resides in __{char.residence}__ in the world of __{char.world}__"
        if char.former_world is not None:
            description += f" (formerly __{char.former_world}__)"
        description += f". {char.he_she} has {char.achievement_points:,} achievement points."

        if char.guild_membership is not None:
            description += f"\n{char.he_she} is __{char.guild_rank}__ of the [{char.guild_name}]({char.guild_url})."
        if char.married_to is not None:
            description += f"\n{char.he_she} is married to [{char.married_to}]({char.married_to_url})."
        if char.house is not None:
            description += f"\n{char.he_she} owns [{char.house.name}]({char.house.url}) in {char.house.town}."
        if char.last_login:
            embed.set_footer(text="Last login")
            embed.timestamp = char.last_login
        else:
            embed.set_footer(text=f"{char.he_she} has never logged in.")

        extra = [f"**{char.account_status.value}**"]
        if char.hidden:
            extra.append("**Hidden**")
        if char.account_information:
            if char.account_information.loyalty_title:
                extra.append(f"**{char.account_information.loyalty_title}**")
            if char.account_information.position:
                extra.append(f"**{char.account_information.position}**")
        description += f"\n{' | '.join(extra)}"

        # Insert any highscores this character holds
        highscores_field = ""
        for category, highscore in char.highscores.items():
            highscore_string = HIGHSCORES_FORMAT[category].format(char.he_she.lower(),
                                                                  highscore["value"], highscore["rank"])
            highscores_field += "\n🏆 {0}".format(highscore_string)
        if highscores_field:
            embed.add_field(name="Highscores entries", value=highscores_field, inline=False)
        embed.description = description
        return embed

    @classmethod
    async def get_user_embed(cls, ctx: NabCtx, user: discord.Member) -> Optional[discord.Embed]:
        embed = discord.Embed()
        user_tibia_worlds = []
        if ctx.is_private:
            display_name = f'@{user.name}'
            user_guilds = ctx.bot.get_user_guilds(ctx.author.id)
            user_tibia_worlds = [world for server, world in ctx.bot.tracked_worlds.items() if
                                 server in [s.id for s in user_guilds]]
        else:
            display_name = f'@{user.display_name}'
            embed.colour = user.colour
            if ctx.world:
                user_tibia_worlds = [ctx.world]
        embed.set_thumbnail(url=user.avatar_url)
        characters = await DbChar.get_chars_by_user(ctx.pool, user.id, worlds=user_tibia_worlds)
        if not characters:
            embed.description = f"**{display_name}** has no registered characters here."
            return embed
        characters.sort(key=lambda c: c.level, reverse=True)
        online_list = [x.name for k, v in online_characters.items() if k in user_tibia_worlds for x in v]
        char_list = []
        for char in characters:
            online = config.online_emoji if char.name in online_list else ""
            voc_abb = get_voc_abb(char.vocation)
            if len(characters) <= 10:
                char_list.append(f"[{char.name}]({char.url}){online} (Lvl {abs(char.level)} {voc_abb})")
            else:
                char_list.append(f"**{char.name}**{online} (Lvl {abs(char.level)} {voc_abb})")
            plural = "s are" if len(char_list) > 1 else " is"
            embed.description = f"**{display_name}**'s character{plural}: {join_list(char_list, ', ', ' and ')}"
        return embed

    @classmethod
    def get_house_embed(cls, ctx: NabCtx, wiki_house: models.House, house: House):
        """Gets the embed to show in /house command"""
        embed = discord.Embed(title=wiki_house.name, url=wiki_house.url)
        WIKI_ICON = "https://vignette.wikia.nocookie.net/tibia/images/b/bc/Wiki.png/revision/latest?path-prefix=en"
        embed.set_author(name="TibiaWiki", url=tibiawikisql.api.BASE_URL, icon_url=WIKI_ICON)

        house_type = "house" if not wiki_house.guildhall else "guildhall"
        beds = "bed" if wiki_house.beds == 1 else "beds"
        description = f"This {house_type} has **{wiki_house.beds}** {beds} and a size of **{wiki_house.size}** sqm." \
            f" This {house_type} is in **{wiki_house.city}**. The rent is **{wiki_house.rent:,}** gold per month."
        # Only TibiaWiki Information
        if not house:
            embed.description = description
            embed.set_footer(text=f"To check a specific world, try: '{ctx.clean_prefix}{ctx.invoked_with} "
                                  f"{wiki_house.name},{random.choice(tibia_worlds)}'")
            return embed
        # Update embed
        embed.url = house.url
        embed.set_author(name="Tibia.com", url=TIBIA_URL, icon_url=TIBIACOM_ICON)

        description += f"\nIn **{house.world}**, this {house_type} is "
        embed.url = house.url
        verb = "wants to" if not house.transfer_accepted else "will"
        # House is rented
        if house.status == HouseStatus.RENTED:
            pronoun = "He" if house.owner_sex == Sex.MALE else "She"
            description += f"rented by [{house.owner}]({house.owner_url})." \
                f" The rent is paid until **{house.paid_until:%d %b %Y %H:%M %Z}**"
            # Owner is moving out
            if house.transfer_date:
                description += f".\n {pronoun} will move out on **{house.transfer_date:%d %b %Y %H:%M %Z}**"
            # Owner is transferring
            if house.transferee:
                description += f" and {verb} pass the house to [{house.transferee}]({house.transferee_url}) " \
                    f"for **{house.transfer_price:,}** gold"
            description += "."
        else:
            description += "on auction."
            # House is on auction, auction started
            if house.auction_end:
                description += f" The highest bid is **{house.highest_bid:,}** gold, by " \
                    f"[{house.highest_bidder}]({house.highest_bidder_url})." \
                    f" The auction ends on **{house.auction_end:%d %b %Y %H:%M %Z}**"
            # House is on auction, auction hasn't started
            else:
                description += " The auction has not started yet."
        description += f"\n*🌐[TibiaWiki article]({wiki_house.url})*"
        embed.description = description
        return embed

    @classmethod
    async def get_recent_deaths_from_database(cls, ctx: NabCtx, name, embed_info, entries, last_time):
        # Do not show database deaths if author is not in any servers tracking worlds.
        if ctx.is_lite:
            return None
        user_servers = ctx.bot.get_user_guilds(ctx.author.id) if ctx.is_private else [ctx.guild]
        user_worlds = ctx.bot.get_guilds_worlds(user_servers) if ctx.is_private else [ctx.world]
        now = dt.datetime.now(dt.timezone.utc)
        async with ctx.pool.acquire() as conn:
            db_char = await DbChar.get_by_name(conn, name)
            # Character is not registered
            if db_char is None:
                return None
            owner = ctx.bot.get_member(db_char.user_id, user_servers)
            # Owner is not visible to the command caller
            if owner is None:
                return None
            # Character is not in a world visible by the command caller
            if db_char.world not in user_worlds:
                return None
            async for death in db_char.get_deaths(conn):
                # Do not show deaths that are already displayed from Tibia.com
                if death.date > last_time:
                    continue
                death_time = get_time_diff(now - death.date)
                entries.append(f"At level **{death.level}** by {death.killer.name} - *{death_time} ago*")
                if len(entries) >= 100:
                    break
        embed_info["author"] = f"{owner if ctx.is_private else owner.display_name}"
        embed_info["author_url"] = discord.Embed.Empty
        embed_info["author_icon"] = get_user_avatar(owner)
        embed_info["embed_url"] = discord.Embed.Empty

    @classmethod
    async def get_recent_deaths_from_tibiacom(cls, ctx, char, embed_info, entries):
        show_links = not await ctx.is_long()
        embed_info["author"] = "Tibia.com"
        embed_info["author_url"] = TIBIA_URL
        embed_info["author_icon"] = TIBIACOM_ICON
        embed_info["url"] = char.url
        last_time = dt.datetime.now(dt.timezone.utc) if not char.deaths else char.deaths[-1].time
        embed_info["title"] = f"{get_voc_emoji(char.vocation)} {char.name} latest deaths"
        for death in char.deaths:
            death_time = get_time_diff(dt.datetime.now(tz=dt.timezone.utc) - death.time)
            if death.by_player and show_links:
                killer = f"[{death.killer.name}]({NabChar.get_url(death.killer.name)})"
            elif death.by_player:
                killer = f"**{death.killer.name}**"
            else:
                killer = f"{death.killer.name}"
            entries.append(f"At level **{death.level}** by {killer} - *{death_time} ago*")
        return last_time

    async def get_recent_deaths(self, ctx: NabCtx):
        now = dt.datetime.now(dt.timezone.utc)
        entries = []
        cache = dict()
        min_level = config.announce_threshold
        user_servers = self.bot.get_user_guilds(ctx.author.id) if ctx.is_private else [ctx.guild]
        user_worlds = self.bot.get_user_worlds(ctx.author.id) if ctx.is_private else [ctx.world]
        async with ctx.pool.acquire() as conn:
            if ctx.guild:
                min_level = await get_server_property(conn, ctx.guild.id, "announce_level", min_level)
            async for death in DbDeath.get_latest(conn, min_level, worlds=user_worlds):
                if ctx.is_private:
                    user = self.get_cached_user_(death.char.user_id, cache, user_servers)
                else:
                    user = ctx.guild.get_member(death.char.user_id)
                if user is None:
                    continue
                user_name = user.name if ctx.is_private else user.display_name
                if death.char.world not in user_worlds:
                    continue
                time_diff = get_time_diff(now - death.date)
                emoji = get_voc_emoji(death.char.vocation)
                entries.append(f"{emoji} {death.char.name} (**@{user_name}**) - "
                               f"At level **{death.char.level}** by {death.killer.name} - *{time_diff} ago*")
                if len(entries) >= 100:
                    break
        return entries

    @classmethod
    def get_tibia_embed(cls, title=None, url=None):
        embed = discord.Embed(title=title, url=url)
        embed.set_author(name="Tibia.com", url=TIBIA_URL, icon_url=TIBIACOM_ICON)
        return embed

    def get_cached_user_(self, user_id, users_cache, user_servers):
        if user_id in users_cache:
            return users_cache.get(user_id)
        else:
            member_user = self.bot.get_member(user_id, user_servers)
            users_cache[user_id] = member_user
            return member_user

    async def get_timezones(self, server_id: int):
        async with self.bot.pool.acquire() as conn:
            results = await conn.fetch("SELECT zone, name FROM server_timezone WHERE server_id = $1", server_id)
            return results

    # endregion

    def __unload(self):
        log.info(f"{self.tag} Unloading cog")
        self.news_announcements_task.cancel()


def setup(bot):
    bot.add_cog(Tibia(bot))
