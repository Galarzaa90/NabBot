import asyncio
import calendar
import datetime as dt
import random
import re
import time
import urllib.parse
from typing import Optional

import discord
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.database import get_server_property, userDatabase
from utils.discord import is_private, is_lite_mode, get_user_avatar
from utils.general import get_time_diff, join_list, get_brasilia_time_zone, global_online_list, get_local_timezone, log, \
    is_numeric
from utils.messages import html_to_markdown, get_first_image, split_message
from utils.emoji import EMOJI
from utils.paginator import Pages, CannotPaginate, VocationPages
from utils.tibia import NetworkError, get_character, tibia_logo, get_share_range, get_voc_emoji, get_voc_abb, get_guild, \
    url_house, get_stats, get_map_area, get_tibia_time_zone, get_world, tibia_worlds, get_world_bosses, get_recent_news, \
    get_news_article, Character, url_guild, highscore_format, get_character_url, url_character, get_house, \
    get_voc_abb_and_emoji
from utils.tibiawiki import get_rashid_info


class Tibia:
    """Tibia related commands."""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.news_announcements_task = self.bot.loop.create_task(self.scan_news())

    async def __error(self, ctx, error):
        if isinstance(error, commands.UserInputError):
            await self.bot.show_help(ctx)

    @commands.command(aliases=['check', 'char', 'character'])
    async def whois(self, ctx, *, name):
        """Tells you a character's or a discord user's information.

        If it matches a discord user, it displays their registered users
        If it matches a character, it displays its information.

        Note that the bot has no way to know the characters of a member that just joined.
        The bot has to be taught about the character's of a user."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_lite_mode(ctx):
            try:
                char = await get_character(name)
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
            char = await get_character(name)
        except NetworkError:
            await ctx.send("Sorry, I couldn't fetch the character's info, maybe you should try again...")
            return
        char_string = self.get_char_string(char)
        user = self.bot.get_member(name, ctx.guild)
        embed = self.get_user_embed(ctx, user)

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
                if is_private(ctx.channel):
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
                    placeholders = ", ".join("?" for w in user_tibia_worlds)
                    c = userDatabase.cursor()
                    try:
                        c.execute("SELECT name, ABS(level) as level "
                                  "FROM chars "
                                  "WHERE user_id = {0} AND world IN ({1}) ORDER BY level DESC".format(user.id, placeholders),
                                  tuple(user_tibia_worlds))
                        character = c.fetchone()
                    finally:
                        c.close()
                    if character:
                        char = await get_character(character["name"])
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
                owner = None if char.owner == 0 else self.bot.get_member(char.owner, ctx.guild)
                if owner is not None:
                    # Char is owned by a discord user
                    embed = self.get_user_embed(ctx, owner)
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

    @commands.command(aliases=['expshare', 'party'])
    async def share(self, ctx, *, param: str=None):
        """Shows the sharing range for that level or character

        params -> level
        params -> name
        params -> name1,name2, name3...

        This command can be used in three ways:
        1. Find the share range of a certain level.
        2. Find the share range of a character.
        3. Find the joint share range of a group of characters.
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

    @commands.group(aliases=['checkguild'], invoke_without_command=True, case_insensitive=True)
    async def guild(self, ctx, *, name):
        """Checks who is online in a guild."""
        permissions = ctx.channel.permissions_for(ctx.me)
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

    @guild.command(name="members", aliases=['list'])
    async def guild_members(self, ctx, *, name: str):
        """Shows a list of all guild members.

        Online members have a 🔹 icon next to their name."""
        permissions = ctx.channel.permissions_for(ctx.me)
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
            member["online"] = EMOJI[":small_blue_diamond:"] if member["status"] == "online" else ""
            entries.append("{rank}\u2014 {online}**{name}** {nick} (Lvl {level} {vocation}{emoji})".format(**member))
        if is_private(ctx.channel) or ctx.channel.name == config.ask_channel_name:
            per_page = 20
        else:
            per_page = 5
        pages = VocationPages(ctx, entries=entries, per_page=per_page, vocations=vocations)
        pages.embed.set_author(name=title, icon_url=guild.logo, url=guild.url)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @guild.command(name="info", aliases=["stats"])
    async def guild_info(self, ctx, *, name: str):
        """Shows basic information and stats about a guild"""
        permissions = ctx.channel.permissions_for(ctx.me)
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
        applications = f"{EMOJI[':white_check_mark:']} Open" if guild.application else f"{EMOJI[':x:']} Closed"
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

    @commands.group(aliases=['deathlist', 'death'], invoke_without_command=True, case_insensitive=True)
    async def deaths(self, ctx, *, name: str = None):
        """Shows a character's recent deaths.

        If this discord server is tracking a tibia world, it will show deaths registered to the character.
        Additionally, if no name is provided, all recent deaths will be shown."""
        if name is None and is_lite_mode(ctx):
            return
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_guilds = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_guilds = [ctx.guild]
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None and name is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        show_links = False
        if is_private(ctx.channel) or ctx.channel.name == config.ask_channel_name:
            per_page = 20
        else:
            per_page = 5
            show_links = True
        try:
            if name is None:
                title = "Latest deaths"
                c.execute("SELECT char_deaths.level, date, name, user_id, byplayer, killer, world, vocation "
                          "FROM char_deaths, chars "
                          "WHERE char_id = id AND char_deaths.level > ? "
                          "ORDER BY date DESC", (config.announce_threshold,))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    user = self.bot.get_member(row["user_id"], user_guilds)
                    if user is None:
                        continue
                    if row["world"] not in user_worlds:
                        continue
                    count += 1
                    row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                    row["user"] = user.display_name
                    row["emoji"] = get_voc_emoji(row["vocation"])
                    entries.append("{emoji} {name} (**@{user}**) - At level **{level}** by {killer} - *{time} ago*"
                                   .format(**row))
                    if count >= 100:
                        break
            else:
                try:
                    char = await get_character(name)
                    if char is None:
                        await ctx.send("That character doesn't exist.")
                        return
                except NetworkError:
                    await ctx.send("Sorry, I had trouble checking that character, try it again.")
                    return
                deaths = char.deaths
                last_time = now
                name = char.name
                voc_emoji = get_voc_emoji(char.vocation)
                title = "{1} {0} latest deaths:".format(name, voc_emoji)
                if ctx.guild is not None and char.owner:
                    owner = ctx.guild.get_member(char.owner)  # type: discord.Member
                    if owner is not None:
                        author = owner.display_name
                        author_icon = owner.avatar_url
                for death in deaths:
                    last_time = death.time.timestamp()
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

                c.execute("SELECT id, name FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is not None and not is_lite_mode(ctx):
                    id = result["id"]
                    c.execute("SELECT char_deaths.level, date, byplayer, killer "
                              "FROM char_deaths "
                              "WHERE char_id = ? AND date < ? "
                              "ORDER BY date DESC",
                              (id, last_time))
                    while True:
                        row = c.fetchone()
                        if row is None:
                            break
                        count += 1
                        row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                        entries.append("At level **{level}** by {killer} - *{time} ago*".format(**row))
                        if count >= 100:
                            break

            if count == 0:
                await ctx.send("There are no registered deaths.")
                return
        finally:
            c.close()

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        pages.embed.set_author(name=author, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="monster", aliases=["mob", "killer"])
    @checks.is_in_tracking_world()
    async def deaths_monsters(self, ctx, *, name: str):
        """Returns a list of the latest kills by that monster."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()
        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        if name[:1] in ["a", "e", "i", "o", "u"]:
            name_with_article = "an "+name
        else:
            name_with_article = "a "+name
        try:
            c.execute("SELECT char_deaths.level, date, name, user_id, byplayer, killer, vocation "
                      "FROM char_deaths, chars "
                      "WHERE char_id = id AND (killer LIKE ? OR killer LIKE ?) "
                      "ORDER BY date DESC", (name, name_with_article))
            while True:
                row = c.fetchone()
                if row is None:
                    break
                user = self.bot.get_member(row["user_id"], ctx.guild)
                if user is None:
                    continue
                count += 1
                row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                row["user"] = user.display_name
                row["emoji"] = get_voc_emoji(row["vocation"])
                entries.append("{emoji} {name} (**@{user}**) - At level **{level}** - *{time} ago*".format(**row))
                if count >= 100:
                    break
            if count == 0:
                await ctx.send("There are no registered deaths by that killer.")
                return
        finally:
            c.close()

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = f"{name.title()} latest kills"

        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="user")
    @checks.is_in_tracking_world()
    async def deaths_user(self, ctx, *, name: str):
        """Shows a user's recent deaths on his/her registered characters."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        user = self.bot.get_member(name, user_servers)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()

        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        try:
            c.execute("SELECT name, world, char_deaths.level, killer, byplayer, date, vocation "
                      "FROM chars, char_deaths "
                      "WHERE char_id = id AND user_id = ? "
                      "ORDER BY date DESC", (user.id,))
            while True:
                row = c.fetchone()
                if row is None:
                    break
                if row["world"] not in user_worlds:
                    continue
                count += 1
                row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                row["emoji"] = get_voc_emoji(row["vocation"])
                entries.append("{emoji} {name} - At level **{level}** by {killer} - *{time} ago*".format(**row))

                if count >= 100:
                    break
            if count == 0:
                await ctx.send("There are not registered deaths by this user.")
                return
        finally:
            c.close()

        title = "{0} latest kills".format(user.display_name)
        icon_url = user.avatar_url
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.set_author(name=title, icon_url=icon_url)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="stats")
    @checks.is_in_tracking_world()
    async def deaths_stats(self, ctx, *, period: str = None):
        """Shows death statistic.
        
        A shorter period can be shown by adding week or month."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return
        placeholders = ", ".join("?" for w in user_worlds)
        c = userDatabase.cursor()
        now = time.time()
        embed = discord.Embed(title="Death statistics")
        if period in ["week", "weekly"]:
            start_date = now - (1 * 60 * 60 * 24 * 7)
            description_suffix = " in the last 7 days"
        elif period in ["month", "monthly"]:
            start_date = now - (1 * 60 * 60 * 24 * 30)
            description_suffix = " in the last 30 days"
        else:
            start_date = 0
            description_suffix = ""
            embed.set_footer(text="For a shorter period, try /death stats week or /deaths stats month")
        try:
            c.execute("SELECT COUNT() AS total FROM char_deaths WHERE date >= ?", (start_date,))
            total = c.fetchone()["total"]
            embed.description = f"There are {total:,} deaths registered{description_suffix}."
            c.execute("SELECT COUNT() as count, chars.name, chars.user_id FROM char_deaths, chars "
                      f"WHERE id = char_id AND world IN ({placeholders}) AND date >= {start_date} "
                      "GROUP BY char_id ORDER BY count DESC LIMIT 3", tuple(user_worlds))
            content = ""
            count = 0
            while True:
                row = c.fetchone()
                if row is None:
                    break
                user = self.bot.get_member(row["user_id"], ctx.guild)
                if user is None:
                    continue
                count += 1
                content += f"**{row['name']}** \U00002014 {row['count']}\n"
                if count >= 3:
                    break
            if count > 0:
                embed.add_field(name="Most deaths per character", value=content, inline=False)

            c.execute("SELECT COUNT() as count, chars.user_id FROM char_deaths, chars "
                      f"WHERE id = char_id AND world IN ({placeholders}) AND date >= {start_date} "
                      "GROUP BY user_id ORDER BY count DESC", tuple(user_worlds))
            content = ""
            count = 0
            while True:
                row = c.fetchone()
                if row is None:
                    break
                user = self.bot.get_member(row["user_id"], ctx.guild)
                if user is None:
                    continue
                count += 1
                content += f"@**{user.display_name}** \U00002014 {row['count']}\n"
                if count >= 3:
                    break
            if count > 0:
                embed.add_field(name="Most deaths per user", value=content, inline=False)

            c.execute("SELECT COUNT() as count, killer FROM char_deaths, chars "
                      f"WHERE id = char_id and world IN ({placeholders}) AND date >= {start_date} "
                      "GROUP BY killer ORDER BY count DESC LIMIT 3", tuple(user_worlds))
            total_per_killer = c.fetchall()
            content = ""
            for row in total_per_killer:
                killer = re.sub(r"(a|an)(\s+)", " ", row["killer"]).title().strip()
                content += f"**{killer}** \U00002014 {row['count']}\n"
            embed.add_field(name="Most deaths per killer", value=content, inline=False)
            await ctx.send(embed=embed)
        finally:
            c.close()

    @commands.group(aliases=['levelups', 'lvl', 'level', 'lvls'], invoke_without_command=True, case_insensitive=True)
    @checks.is_in_tracking_world()
    async def levels(self, ctx, *, name: str=None):
        """Shows a player's or everyone's recent level ups.

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_guilds = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_guilds = [ctx.guild]
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        await ctx.channel.trigger_typing()
        try:
            if name is None:
                title = "Latest level ups"
                c.execute("SELECT char_levelups.level, date, name, user_id, world, vocation "
                          "FROM char_levelups, chars "
                          "WHERE char_id = id AND char_levelups.level >= ? "
                          "ORDER BY date DESC", (config.announce_threshold, ))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    user = self.bot.get_member(row["user_id"], user_guilds)
                    if user is None:
                        continue
                    if row["world"] not in user_worlds:
                        continue
                    count += 1
                    row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                    row["user"] = user.display_name
                    row["emoji"] = get_voc_emoji(row["vocation"])
                    entries.append("{emoji} {name} - Level **{level}** - (**@{user}**) - *{time} ago*".format(**row))
                    if count >= 100:
                        break
            else:
                c.execute("SELECT id, name, user_id, vocation FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is None:
                    await ctx.send("I don't have a character with that name registered.")
                    return
                # If user doesn't share a server with the owner, don't display it
                owner = self.bot.get_member(result["user_id"], user_guilds)
                if owner is None:
                    await ctx.send("I don't have a character with that name registered.")
                    return
                author = owner.display_name
                author_icon = owner.avatar_url
                name = result["name"]
                emoji = get_voc_emoji(result["vocation"])
                title = f"{emoji} {name} latest level ups"
                c.execute("SELECT char_levelups.level, date FROM char_levelups, chars "
                          "WHERE id = char_id AND name LIKE ? "
                          "ORDER BY date DESC", (name,))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    count += 1
                    row["time"] = get_time_diff(dt.timedelta(seconds=now-row["date"]))
                    entries.append("Level **{level}** - *{time} ago*".format(**row))
                    if count >= 100:
                        break
        finally:
            c.close()

        if count == 0:
            await ctx.send("There are no registered levels.")
            return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        pages.embed.set_author(name=author, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @levels.command(name="user")
    @checks.is_in_tracking_world()
    async def levels_user(self, ctx, *, name: str):
        """Shows a user's recent level ups on his/her registered characters."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        user = self.bot.get_member(name, user_servers)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()

        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        try:
            c.execute("SELECT name, world, char_levelups.level, date, vocation "
                      "FROM chars, char_levelups "
                      "WHERE char_id = id AND user_id = ? "
                      "ORDER BY date DESC", (user.id,))
            while True:
                row = c.fetchone()
                if row is None:
                    break
                if row["world"] not in user_worlds:
                    continue
                count += 1
                row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                row["emoji"] = get_voc_emoji(row["vocation"])
                entries.append("{emoji} {name} - Level **{level}** - *{time} ago*".format(**row))
                if count >= 100:
                    break
            if count == 0:
                await ctx.send("There are not registered level ups by this user.")
                return
        finally:
            c.close()

        title = f"{user.display_name} latest level ups"
        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.set_author(name=title, icon_url=get_user_avatar(user))
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.group(aliases=["story"], invoke_without_command=True, case_insensitive=True)
    @checks.is_in_tracking_world()
    async def timeline(self, ctx, *, name: str = None):
        """Shows a player's recent level ups and deaths."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        await ctx.channel.trigger_typing()
        try:
            if name is None:
                title = "Timeline"
                c.execute("SELECT name, user_id, world, char_deaths.level as level, killer, 'death' AS `type`, date, "
                          "vocation "
                          "FROM char_deaths, chars WHERE char_id = id AND char_deaths.level >= ? "
                          "UNION "
                          "SELECT name, user_id, world, char_levelups.level as level, null, 'levelup' AS `type`, date, "
                          "vocation "
                          "FROM char_levelups, chars WHERE char_id = id AND char_levelups.level >= ? "
                          "ORDER BY date DESC", (config.announce_threshold, config.announce_threshold))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    user = self.bot.get_member(row["user_id"], user_servers)
                    if user is None:
                        continue
                    if row["world"] not in user_worlds:
                        continue
                    count += 1
                    row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                    row["user"] = user.display_name
                    row["voc_emoji"] = get_voc_emoji(row["vocation"])
                    if row["type"] == "death":
                        row["emoji"] = EMOJI[":skull:"]
                        entries.append("{emoji}{voc_emoji} {name} (**@{user}**) - At level **{level}** by {killer} - "
                                       "*{time} ago*".format(**row))
                    else:
                        row["emoji"] = EMOJI[":star2:"]
                        entries.append("{emoji}{voc_emoji} {name} (**@{user}**) - Level **{level}** - *{time} ago*"
                                       .format(**row))
                    if count >= 200:
                        break
            else:
                c.execute("SELECT id, name, user_id, vocation FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is None:
                    await ctx.send("I don't have a character with that name registered.")
                    return
                # If user doesn't share a server with the owner, don't display it
                owner = self.bot.get_member(result["user_id"], user_servers)
                if owner is None:
                    await ctx.send("I don't have a character with that name registered.")
                    return
                author = owner.display_name
                author_icon = owner.avatar_url
                name = result["name"]
                emoji = get_voc_emoji(result["vocation"])
                title = f"{emoji} {name} timeline"
                c.execute("SELECT level, killer, 'death' AS `type`, date "
                          "FROM char_deaths WHERE char_id = ? AND level >= ? "
                          "UNION "
                          "SELECT level, null, 'levelup' AS `type`, date "
                          "FROM char_levelups WHERE char_id = ? AND level >= ? "
                          "ORDER BY date DESC", (result["id"], config.announce_threshold, result["id"], config.announce_threshold))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    count += 1
                    row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                    if row["type"] == "death":
                        row["emoji"] = EMOJI[":skull:"]
                        entries.append("{emoji} At level **{level}** by {killer} - *{time} ago*"
                                       .format(**row)
                                       )
                    else:
                        row["emoji"] = EMOJI[":star2:"]
                        entries.append("{emoji} Level **{level}** - *{time} ago*".format(**row))
                    if count >= 200:
                        break
        finally:
            c.close()

        if count == 0:
            await ctx.send("There are no registered events.")
            return

        pages = Pages(ctx, entries=entries, per_page=per_page)
        pages.embed.title = title
        pages.embed.set_author(name=author, icon_url=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @timeline.command(name="user")
    @checks.is_in_tracking_world()
    async def timeline_user(self, ctx, *, name: str):
        """Shows a users's recent level ups and deaths on his/her characters."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("You must tell me a user's name to look for his/her story.")
            return

        if is_private(ctx.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [self.bot.tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        user = self.bot.get_member(name, user_servers)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        entries = []
        count = 0
        now = time.time()

        ask_channel = self.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        await ctx.channel.trigger_typing()
        try:
            title = f"{user.display_name} timeline"
            c.execute("SELECT name, user_id, world, char_deaths.level AS level, killer, 'death' AS `type`, date, vocation "
                      "FROM char_deaths, chars WHERE char_id = id AND char_deaths.level >= ? AND user_id = ? "
                      "UNION "
                      "SELECT name, user_id, world, char_levelups.level as level, null, 'levelup' AS `type`, date, vocation "
                      "FROM char_levelups, chars WHERE char_id = id AND char_levelups.level >= ? AND user_id = ? "
                      "ORDER BY date DESC", (config.announce_threshold, user.id, config.announce_threshold, user.id))
            while True:
                row = c.fetchone()
                if row is None:
                    break
                if row["world"] not in user_worlds:
                    continue
                count += 1
                row["time"] = get_time_diff(dt.timedelta(seconds=now - row["date"]))
                row["voc_emoji"] = get_voc_emoji(row["vocation"])
                if row["type"] == "death":
                    row["emoji"] = EMOJI[":skull:"]
                    entries.append("{emoji}{voc_emoji} {name} - At level **{level}** by {killer} - *{time} ago*"
                                   .format(**row)
                                   )
                else:
                    row["emoji"] = EMOJI[":star2:"]
                    entries.append("{emoji}{voc_emoji} {name} - Level **{level}** - *{time} ago*".format(**row))
                if count >= 200:
                    break
        finally:
            c.close()

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

    @commands.command()
    async def stats(self, ctx, *, params:str=None):
        """Calculates character stats based on vocation and level.

        params -> character
        params -> level,vocation
        params -> vocation,level"""
        invalid_arguments = "Invalid arguments, examples:\n" \
                            "```/stats player\n" \
                            "/stats level,vocation\n" \
                            "/stats vocation,level```"
        if params is None:
            await ctx.send(invalid_arguments)
            return
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

    @commands.command(aliases=['bless'])
    async def blessings(self, ctx, level: int):
        """Calculates the price of blessings at a specific level."""
        if level < 1:
            await ctx.send("Very funny... Now tell me a valid level.")
            return
        bless_price = max(2000, 200 * (min(level, 120) - 20))
        mountain_bless_price = max(2000, 200 * (min(level, 150) - 20))
        inquisition = ""
        if level >= 100:
            inquisition = f"\nBlessing of the Inquisition costs **{int(bless_price*5*1.1):,}** gold coins."
        await ctx.send(f"At that level you will pay **{bless_price:,}** gold coins per blessing for a total of "
                       f"**{bless_price*5:,}** gold coins.{inquisition}"
                       f"\nMountain blessings cost **{mountain_bless_price:,}** each, for a total of "
                       f"**{int(mountain_bless_price*2):,}**.")

    @commands.command(aliases=["houses", "guildhall", "gh"])
    async def house(self, ctx, *, name: str):
        """Shows info for a house or guildhall.

        By default, it shows the current status of a house for the current tracked world (if any).
        If used on private messages, no world is looked up unless specified.

        To specify a world, add the world at the end separated with '/'.

        Example:
        /house The Tibianic/Antica
        """
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        params = name.split("/", 2)
        name = params[0]
        world = None
        if ctx.guild is not None and len(params) == 1:
            world = self.bot.tracked_worlds.get(ctx.guild.id)
        elif len(params) == 2:
            world = params[1].title()
            if world not in tibia_worlds:
                await ctx.send("That's not a valid world.")
                return

        house = await get_house(name, world)
        if house is None:
            await ctx.send("I couldn't find a house with that name.")
            return

        if type(house) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(house))
            await ctx.send("I couldn't find that house, maybe you meant one of these?", embed=embed)
            return

        # Attach image only if the bot has permissions
        if permissions.attach_files:
            filename = re.sub(r"[^A-Za-z0-9]", "", house["name"]) + ".png"
            mapimage = get_map_area(house["x"], house["y"], house["z"])
            embed = self.get_house_embed(house)
            embed.set_image(url=f"attachment://{filename}")
            await ctx.send(file=discord.File(mapimage, f"{filename}"), embed=embed)
        else:
            await ctx.send(embed=self.get_house_embed(house))

    @commands.command(aliases=['serversave', 'ss'])
    async def time(self, ctx):
        """Displays tibia server's time and time until server save."""
        offset = get_tibia_time_zone() - get_local_timezone()
        tibia_time = dt.datetime.now()+dt.timedelta(hours=offset)
        server_save = tibia_time
        if tibia_time.hour >= 10:
            server_save += dt.timedelta(days=1)
        server_save = server_save.replace(hour=10, minute=0, second=0, microsecond=0)
        time_until_ss = server_save - tibia_time
        hours, remainder = divmod(int(time_until_ss.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        timestrtibia = tibia_time.strftime("%H:%M")
        server_save_str = '{h} hours and {m} minutes'.format(h=hours, m=minutes)

        reply = "It's currently **{0}** in Tibia's servers.".format(timestrtibia)
        if config.display_brasilia_time:
            offsetbrasilia = get_brasilia_time_zone() - get_local_timezone()
            brasilia_time = dt.datetime.now()+dt.timedelta(hours=offsetbrasilia)
            timestrbrasilia = brasilia_time.strftime("%H:%M")
            reply += "\n**{0}** in Brazil (Brasilia).".format(timestrbrasilia)
        if config.display_sonora_time:
            offsetsonora = -7 - get_local_timezone()
            sonora_time = dt.datetime.now()+dt.timedelta(hours=offsetsonora)
            timestrsonora = sonora_time.strftime("%H:%M")
            reply += "\n**{0}** in Mexico (Sonora).".format(timestrsonora)
        reply += "\nServer save is in {0}.\nRashid is in **{1}** today."\
            .format(server_save_str, get_rashid_info()["city"])
        await ctx.send(reply)

    @commands.command(name="world")
    async def world_info(self, ctx, name: str):
        """Shows basic information about a Tibia world"""
        try:
            world = await get_world(name)
            if world is None:
                await ctx.send("There's no world with that name.")
                return
        except NetworkError:
            await ctx.send("I'm having connection issues right now.")
            return

        flags = {"North America": EMOJI[":flag_us:"], "South America": EMOJI[":flag_br:"], "Europe": EMOJI[":flag_gb:"]}
        pvp = {"Optional PvP": EMOJI[":dove:"], "Hardcore PvP": EMOJI[":skull:"], "Open PvP": EMOJI[":crossed_swords:"],
               "Retro Open PvP": EMOJI[":crossed_swords:"], "Retro Hardcore PvP":  EMOJI[":skull:"]}
        transfers = {"locked": EMOJI[":lock:"], "blocked": EMOJI[":no_entry_sign:"]}

        url = 'https://secure.tibia.com/community/?subtopic=worlds&world=' + name.capitalize()
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

        embed.add_field(name="Location", value=f"{flags.get(world.location,'')} {world.location}")
        embed.add_field(name="PvP Type", value=f"{pvp.get(world.pvp_type,'')} {world.pvp_type}")
        if world.premium_type is not None:
            embed.add_field(name="Premium restricted", value=EMOJI[":white_check_mark:"])
        if world.transfer_type is not None:
            embed.add_field(name="Transfers", value=f"{transfers.get(world.transfer_type,'')} {world.transfer_type}")

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

    @commands.command(name="searchworld", aliases=["whereworld","findworld"])
    async def world_search(self, ctx, *, params):
        """Searches for online characters that meet the criteria.

        There are 3 ways to use this command:
        -Find a character in share range with another character:
        /searchworld charname

        -Find a character in share range with a certain level
        /searchworld level

        -Find a character in a level range
        /searchworld min_level,max_level

        By default, the tracked world is searched, unless specified at the end of the parameters.

        Results can be filtered by using the vocation filters: \U00002744\U0001F525\U0001F3F9\U0001F6E1"""
        permissions = ctx.channel.permissions_for(ctx.me)
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

        tracked_world = None if is_private(ctx.channel) else self.bot.tracked_worlds.get(ctx.guild.id)
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

        if is_private(ctx.channel) or ctx.channel.name == config.ask_channel_name:
            per_page = 20
        else:
            per_page = 5

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

    @commands.command()
    async def bosses(self, ctx, world=None):
        """Shows predictions for bosses."""
        ask_channel = ctx.bot.get_channel_by_name(config.ask_channel_name, ctx.guild)

        if world is None and not is_private(ctx.channel) and self.bot.tracked_worlds.get(ctx.guild.id) is not None:
            world = self.bot.tracked_worlds.get(ctx.guild.id)
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
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            if fields["No Chance"]:
                embed.add_field(name="No Chance - Expect in", value=fields["No Chance"])
            if fields["Unpredicted"]:
                embed.add_field(name="Unpredicted - Last seen", value=fields["Unpredicted"])
        else:
            if ask_channel:
                askchannel_string = " or use #" + ask_channel.name
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))
        await ctx.send(embed=embed)

    @commands.command()
    async def news(self, ctx, news_id: int=None):
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
                "Featured Article": EMOJI[":bookmark_tabs:"],
                "News": EMOJI[":newspaper:"],
            }
            for news in recent_news:
                news["emoji"] = type_emojis.get(news["type"], "")
            limit = 10
            if is_private(ctx.channel) or ctx.channel.name == config.ask_channel_name:
                limit = 20
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
            limit = 600
            if is_private(ctx.channel) or ctx.channel.name == config.ask_channel_name:
                limit = 1900
            embed = self.get_article_embed(article, limit)
            await ctx.send(embed=embed)

    @commands.command()
    async def stamina(self, ctx, current_stamina:str):
        """Tells you the time you have to wait to restore stamina.

        To use it, you must provide your current stamina, in this format: `34:03`.
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

        hours, remainder = divmod(int(resting_time), 3600)
        minutes, _ = divmod(remainder, 60)
        if hours:
            remaining = f'{hours} hours and {minutes} minutes'
        else:
            remaining = f'{minutes} minutes'

        reply = f"You need to rest **{remaining}** to get back to full stamina."
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send(reply)
            return

        embed = discord.Embed(description=reply)
        embed.set_footer(text="Full stamina")
        embed.colour = discord.Color.green()
        embed.timestamp = dt.datetime.utcnow()+dt.timedelta(seconds=resting_time)
        await ctx.send(embed=embed)

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
        embed.set_footer(text=f"Posted on {article['date']:%A, %B %d, %Y}")
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
            reply += "\n" + EMOJI[":trophy:"] + " {0}".format(highscore_string)

        return reply

    def get_user_embed(self, ctx, user: discord.Member) -> Optional[discord.Embed]:
        if user is None:
            return None
        embed = discord.Embed()
        if is_private(ctx.channel):
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

        placeholders = ", ".join("?" for w in user_tibia_worlds)
        c = userDatabase.cursor()
        try:
            c.execute("SELECT name, ABS(level) as level, vocation "
                      "FROM chars "
                      "WHERE user_id = {0} AND world IN ({1}) ORDER BY level DESC".format(user.id, placeholders),
                      tuple(user_tibia_worlds))
            characters = c.fetchall()
            if not characters:
                embed.description = f"I don't know who **{display_name}** is..."
                return embed
            online_list = [x.name for x in global_online_list]
            char_list = []
            for char in characters:
                char["online"] = EMOJI[":small_blue_diamond:"] if char["name"] in online_list else ""
                char["vocation"] = get_voc_abb(char["vocation"])
                char["url"] = url_character + urllib.parse.quote(char["name"].encode('iso-8859-1'))
                if len(characters) <= 10:
                    char_list.append("[{name}]({url}){online} (Lvl {level} {vocation})".format(**char))
                else:
                    char_list.append("**{name}**{online} (Lvl {level} {vocation})".format(**char))
                char_string = "@**{0.display_name}**'s character{1}: {2}"
                plural = "s are" if len(char_list) > 1 else " is"
                embed.description = char_string.format(user, plural, join_list(char_list, ", ", " and "))
        finally:
            c.close()
        return embed

    @staticmethod
    def get_house_embed(house):
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
                try:
                    with open("data/last_article.txt", 'r') as f:
                        last_id = int(f.read())
                except (ValueError, FileNotFoundError):
                    log.info("scan_news: No last article id saved")
                    last_id = 0
                if last_id == 0:
                    with open("data/last_article.txt", 'w+') as f:
                        f.write(str(last_article))
                    await asyncio.sleep(60 * 60 * 2)
                    continue
                new_articles = []
                for article in recent_news:
                    if int(article["id"]) == last_id:
                        break
                    # Do not post articles older than a week (in case bot was offline)
                    if (dt.date.today() - article["date"]).days > 7:
                        break
                    fetched_article = await get_news_article(int(article["id"]))
                    if fetched_article is not None:
                        new_articles.insert(0, fetched_article)
                with open("data/last_article.txt", 'w+') as f:
                    f.write(str(last_article))
                if len(new_articles) == 0:
                    await asyncio.sleep(60 * 60 * 2)
                    continue
                for article in new_articles:
                    log.info("Announcing new article: {id} - {title}".format(**article))
                    for guild in self.bot.guilds:
                        channel = self.bot.get_channel_or_top(guild, get_server_property("events_channel", guild.id,
                                                                                         is_int=True))
                        try:
                            await channel.send("New article posted on Tibia.com",
                                               embed=self.get_article_embed(article, 400))
                        except discord.Forbidden:
                            log.warning("scan_news: Missing permissions.")
                        except discord.HTTPException:
                            log.warning("scan_news: Malformed message.")
                await asyncio.sleep(60 * 60 * 2)
            except NetworkError:
                await asyncio.sleep(30)
                continue
            except asyncio.CancelledError:
                # Task was cancelled, so this is fine
                break
            except Exception:
                log.exception("Task: scan_news")

    def __unload(self):
        print("cogs.tibia: Cancelling pending tasks...")
        self.news_announcements_task.cancel()


def setup(bot):
    bot.add_cog(Tibia(bot))
