import calendar
import os
import random
from contextlib import closing
from typing import Optional

import discord
from discord.ext import commands

from config import *
from nabbot import NabBot
from utils import checks
from utils.database import tracked_worlds
from utils.discord import get_user_color, FIELD_VALUE_LIMIT, is_private, is_lite_mode
from utils.general import is_numeric, get_time_diff, join_list, get_brasilia_time_zone, start_time
from utils.loot import loot_scan
from utils.loot import item_show
from utils.loot import item_add
from utils.messages import split_message
from utils.paginator import Paginator, CannotPaginate
from utils.tibia import *


class Tibia:
    """Tibia related commands."""
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.parsing_count = 0

    @commands.group(invoke_without_command=True)
    @checks.is_not_lite()
    async def loot(self, ctx):
        """Scans a loot image and returns it's loot value

        The bot will return a list of the items found along with their values, grouped by NPC.
        If the image is compressed or was taken using Tibia's software render, the bot might struggle finding matches.

        The bot can only scan 6 images simultaneously."""
        author = ctx.message.author
        if self.parsing_count >= loot_max:
            await ctx.send("Sorry, I am already parsing too many loot images, "
                           "please wait a couple of minutes and try again.")
            return

        if len(ctx.message.attachments) == 0:
            await ctx.send("You need to upload a picture of your loot and type the command in the comment.")
            return

        attachment = ctx.message.attachments[0]  # type: discord.Attachment
        if attachment.size > 2097152:
            await ctx.send("That image was too big! Try splitting it into smaller images, or cropping out anything "
                           "irrelevant.")
            return
        file_name = attachment.url.split("/")[len(attachment.url.split("/"))-1]
        file_url = attachment.url
        try:
            with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    original_image = await resp.read()
            loot_image = Image.open(io.BytesIO(bytearray(original_image))).convert("RGBA")
        except Exception:
            await ctx.send("Either that wasn't an image or I failed to load it, please try again.")
            return

        self.parsing_count += 1
        await ctx.send("I've begun parsing your image, **@{0.display_name}**. "
                       "Please be patient, this may take a few moments.".format(author))
        progress_msg = await ctx.send("Status: ...")
        progress_bar = await ctx.send(EMOJI[":black_large_square:"]*10)

        loot_list, loot_image_overlay = await loot_scan(loot_image, file_name, progress_msg, progress_bar)
        self.parsing_count -= 1
        embed = discord.Embed()
        long_message = "These are the results for your image: [{0}]({1})".format(file_name, file_url)

        if len(loot_list) == 0:
            message = "Sorry {0.mention}, I couldn't find any loot in that image. Loot parsing will only work on " \
                      "high quality images, so make sure your image wasn't compressed."
            await ctx.send(message.format(author))
            return

        total_value = 0

        unknown = False
        for item in loot_list:
            if loot_list[item]['group'] == "Unknown":
                unknown = loot_list[item]
                break

        groups = []
        for item in loot_list:
            if not loot_list[item]['group'] in groups and loot_list[item]['group'] != "Unknown":
                groups.append(loot_list[item]['group'])
        has_marketable = False
        for group in groups:
            value = ""
            group_value = 0
            for item in loot_list:
                if loot_list[item]['group'] == group and loot_list[item]['group'] != "Unknown":
                    if group == "No Value":
                        value += "x{1} {0}\n".format(item, loot_list[item]['count'])
                    else:
                        with closing(tibiaDatabase.cursor()) as c:
                            c.execute("SELECT name FROM Items, ItemProperties "
                                      "WHERE name LIKE ? AND id = itemid AND property LIKE 'Imbuement'"
                                      " LIMIT 1", (item, ))
                            result = c.fetchone()
                        if result:
                            has_marketable = True
                            emoji = EMOJI[":gem:"]
                        else:
                            emoji = ""
                        value += "x{1} {0}{3} \u2192 {2:,}gp total.\n".format(
                            item,
                            loot_list[item]['count'],
                            loot_list[item]['count']*loot_list[item]['value'],
                            emoji)

                    total_value += loot_list[item]['count']*loot_list[item]['value']
                    group_value += loot_list[item]['count']*loot_list[item]['value']
            if group == "No Value":
                name = group
            else:
                name = "{0} - {1:,} gold".format(group, group_value)
            # Split into multiple fields if they exceed field max length
            split_group = split_message(value, FIELD_VALUE_LIMIT)
            for subgroup in split_group:
                if subgroup != split_group[0]:
                    name = "\u200F"
                embed.add_field(name=name, value=subgroup, inline=False)

        if unknown:
            long_message += "\n*There were {0} unknown items.*\n".format(unknown['count'])

        long_message += "\nThe total loot value is: **{0:,}** gold coins.".format(total_value)
        if has_marketable:
            long_message += f"\n{EMOJI[':gem:']} Items marked with this are used in imbuements and might be worth " \
                            f"more in the market."
        embed.description = long_message
        embed.set_image(url="attachment://results.png")

        # Short message
        short_message = f"I've finished parsing your image {author.mention}." \
                        f"\nThe total value is {total_value:,} gold coins."
        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
        if not is_private(ctx.message.channel) and ctx.message.channel != ask_channel:
            short_message += "\nI've also sent you a PM with detailed information."

        # Send on ask_channel or PM
        if ctx.message.channel == ask_channel:
            await ctx.send(short_message, embed=embed, file=discord.File(loot_image_overlay, "results.png"))
        else:
            await ctx.send(short_message)
            await ctx.author.send(file=discord.File(loot_image_overlay, "results.png"), embed=embed)


    @loot.command(name="show")
    @checks.is_mod()
    @checks.is_not_lite()
    async def loot_show(self, ctx, *, item=None):
        """Shows the meaning of the overlayed icons."""
        result = await item_show(item)
        if result is not None:
            await ctx.send(file=discord.File(result,"results.png"))

    @loot.command(name="add")
    @checks.is_mod()
    @checks.is_not_lite()
    async def loot_add(self, ctx, *, item=None):
        """Shows the meaning of the overlayed icons."""
        if len(ctx.message.attachments) == 0:
            await ctx.send("You need to upload the image you want to add to this item.")
            return

        attachment = ctx.message.attachments[0]
        if attachment.width != 32 or attachment.height != 32:
            await ctx.send("Image size has to be 32x32.")
            return

        file_name = attachment.url.split("/")[len(attachment.url.split("/"))-1]
        file_url = attachment.url
        try:
            with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    original_image = await resp.read()
            frame_image = Image.open(io.BytesIO(bytearray(original_image))).convert("RGBA")
        except Exception:
            await ctx.send("Either that wasn't an image or I failed to load it, please try again.")
            return

        result = await item_add(item, frame_image)
        if result is None:
            await ctx.send("Couldn't find an item with that name.")
            return
        else:
            result = await item_show(item)
            await ctx.send("Image added to item.", file=discord.File(result, "results.png"))
            return

    @loot.command(name="legend", aliases=["help", "symbols", "symbol"])
    @checks.is_not_lite()
    async def loot_legend(self, ctx):
        """Shows the meaning of the overlayed icons."""
        with open("./images/legend.png", "r+b") as f:
            await ctx.send(file=discord.File(f))
            f.close()

    @commands.command(aliases=['check', 'player', 'checkplayer', 'char', 'character'])
    async def whois(self, ctx, *, name=None):
        """Tells you a character's or a discord user's information

        If it matches a discord user, it displays its registered users
        If it matches a character, it displays its information.

        Note that the bot has no way to know the characters of a member that just joined.
        The bot has to be taught about the character's of an user."""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        if name is None:
            await ctx.send("Tell me which character or user you want to check.")
            return

        if is_lite_mode(ctx):
            char = await get_character(name)
            if char == ERROR_DOESNTEXIST:
                await ctx.send("I couldn't find a character with that name")
            elif char == ERROR_NETWORK:
                await ctx.send("Sorry, I couldn't fetch the character's info, maybe you should try again...")
            else:
                embed = discord.Embed(description=self.get_char_string(char))
                embed.set_author(name=char["name"],
                                 url=url_character + urllib.parse.quote(char["name"]),
                                 icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                 )
                await ctx.send(embed=embed)
            return

        if name.lower() == ctx.me.display_name.lower():
            await ctx.invoke(self.bot.all_commands.get('about'))
            return

        char = await get_character(name)
        char_string = self.get_char_string(char)
        user = self.bot.get_member_by_name(name, ctx.guild)
        embed = self.get_user_embed(ctx, user)

        # No user or char with that name
        if char == ERROR_DOESNTEXIST and user is None:
            await ctx.send("I don't see any user or character with that name.")
            return
        # We found an user
        if embed is not None:
            # Check if we found a char too
            if type(char) is dict:
                # If it's owned by the user, we append it to the same embed.
                if char["owner_id"] == int(user.id):
                    embed.add_field(name="Character", value=char_string, inline=False)
                    if char['last_login'] is not None:
                        embed.set_footer(text="Last login")
                        embed.timestamp = parse_tibia_time(char["last_login"])
                    await ctx.send(embed=embed)
                    return
                # Not owned by same user, we display a separate embed
                else:
                    char_embed = discord.Embed(description=char_string)
                    char_embed.set_author(name=char["name"],
                                          url=get_character_url(char["name"]),
                                          icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                          )
                    if char['last_login'] is not None:
                        char_embed.set_footer(text="Last login")
                        char_embed.timestamp = parse_tibia_time(char["last_login"])
                    await ctx.send(embed=embed)
                    await ctx.send(embed=char_embed)
                    return
            else:
                if char == ERROR_NETWORK:
                    await ctx.send(embed=embed)
                    await ctx.send("I failed to do a character search for some reason "+EMOJI[":astonished:"])
                else:
                    # Tries to display user's highest level character since there is no character match
                    if is_private(ctx.message.channel):
                        display_name = '@'+user.name
                        user_guilds = self.bot.get_user_guilds(ctx.author.id)
                        user_tibia_worlds = [world for server, world in tracked_worlds.items() if
                                             server in [s.id for s in user_guilds]]
                    else:
                        if tracked_worlds.get(ctx.message.guild.id) is None:
                            user_tibia_worlds = []
                        else:
                            user_tibia_worlds = [tracked_worlds[ctx.message.guild.id]]
                    if len(user_tibia_worlds) != 0:
                        placeholders = ", ".join("?" for w in user_tibia_worlds)
                        c = userDatabase.cursor()
                        try:
                            c.execute("SELECT name, ABS(last_level) as level "
                                      "FROM chars "
                                      "WHERE user_id = {0} AND world IN ({1}) ORDER BY level DESC".format(user.id, placeholders),
                                      tuple(user_tibia_worlds))
                            character = c.fetchone()
                        finally:
                            c.close()
                        if character:
                            char = await get_character(character["name"])
                            char_string = self.get_char_string(char)
                            if type(char) is dict:
                                char_embed = discord.Embed(description=char_string)
                                char_embed.set_author(name=char["name"],
                                                      url=get_character_url(char["name"]),
                                                      icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                                      )
                                embed.add_field(name="Highest character", value=char_string, inline=False)
                                if char['last_login'] is not None:
                                    embed.set_footer(text="Last login")
                                    embed.timestamp = parse_tibia_time(char["last_login"])
                    await ctx.send(embed=embed)
        else:
            if char == ERROR_NETWORK:
                await ctx.send("I failed to do a character search for some reason " + EMOJI[":astonished:"])
            embed = discord.Embed(description="")
            if type(char) is dict:
                owner = self.bot.get_member(char["owner_id"], ctx.message.guild)
                if owner is not None:
                    # Char is owned by a discord user
                    embed = self.get_user_embed(ctx, owner)
                    if embed is None:
                        embed = discord.Embed(description="")
                    embed.add_field(name="Character", value=char_string, inline=False)
                    if char['last_login'] is not None:
                        embed.set_footer(text="Last login")
                        embed.timestamp = parse_tibia_time(char["last_login"])
                    await ctx.send(embed=embed)
                    return
                else:
                    embed.set_author(name=char["name"],
                                     url=get_character_url(char["name"]),
                                     icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                     )
                    embed.description += char_string
                    if char['last_login'] is not None:
                        embed.set_footer(text="Last login")
                        embed.timestamp = parse_tibia_time(char["last_login"])

            await ctx.send(embed=embed)

    @commands.command(aliases=['expshare', 'party'])
    async def share(self, ctx, *, param: str=None):
        """Shows the sharing range for that level or character

        There's three ways to use this command:
        /share level
        /share char_name
        /share char_name1,char_name2...char_name5"""
        invalid_level = ["Invalid level.",
                         "I don't think that's a valid level.",
                         "You're doing it wrong!",
                         "Nope, you can't share with anyone.",
                         "You probably need a couple more levels"
                         ]
        if param is None:
            await ctx.send("You need to tell me a level, a character's name, or two character's names.")
            return
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
                    char = await get_character(chars[0])
                    if type(char) is not dict:
                        await ctx.send('There is no character with that name.')
                        return
                    name = char["name"]
                    level = char["level"]
                    low, high = get_share_range(char["level"])
                    await ctx.send(f"**{name}** ({level}) can share experience with levels **{low}** to **{high}**.")
                    return
            char_data = []
            # Check if all characters are the same.
            if all(x.lower() == chars[0].lower() for x in chars):
                await ctx.send("I'm not sure if sharing with yourself counts as sharing, but yes, you can share.")
                return
            with ctx.typing():
                for char in chars:
                    fetched_char = await get_character(char)
                    if fetched_char == ERROR_DOESNTEXIST:
                        await ctx.send(f"There is no character named **{char}**.")
                        return
                    elif fetched_char == ERROR_NETWORK:
                        await ctx.send("I'm having connection issues, please try again in a bit.")
                        return
                    char_data.append(fetched_char)
                # Sort character list by level ascending
                char_data = sorted(char_data, key=lambda k: k["level"])
                low, _ = get_share_range(char_data[-1]["level"])
                _, high = get_share_range(char_data[0]["level"])
                lowest_name = char_data[0]['name']
                lowest_level = char_data[0]['level']
                highest_name = char_data[-1]['name']
                highest_level = char_data[-1]['level']
                if low > char_data[0]["level"]:
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

    @commands.guild_only()
    @commands.command(name="find", aliases=["whereteam", "team", "findteam", "searchteam", "search"])
    @checks.is_not_lite()
    async def find_team(self, ctx, *, params=None):
        """Searches for a registered character that meets the criteria

        There are 3 ways to use this command:
        -Find a character of a certain vocation in share range with another character:
        /find vocation,charname

        -Find a character of a certain vocation in share range with a certain level
        /find vocation,level

        -Find a character of a certain vocation between a level range
        /find vocation,min_level,max_level"""
        permissions = ctx.message.channel.permissions_for(self.bot.get_member(self.bot.user.id, ctx.message.guild))
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        invalid_arguments = "Invalid arguments used, examples:\n" \
                            "```/find vocation,charname\n" \
                            "/find vocation,level\n" \
                            "/find vocation,minlevel,maxlevel```"

        tracked_world = tracked_worlds.get(ctx.message.guild.id)
        if tracked_world is None:
            await ctx.send("This server is not tracking any tibia worlds.")
            return

        if params is None:
            await ctx.send(invalid_arguments)
            return

        entries = []
        online_entries = []

        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
        if is_private(ctx.message.channel) or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        char = None
        params = params.split(",")
        if len(params) < 2 or len(params) > 3:
            await ctx.send(invalid_arguments)
            return
        params[0] = params[0].lower()
        if params[0] in KNIGHT:
            vocation = "knight"
        elif params[0] in DRUID:
            vocation = "druid"
        elif params[0] in SORCERER:
            vocation = "sorcerer"
        elif params[0] in PALADIN:
            vocation = "paladin"
        elif params[0] in ["any", "all", "everything", "anything"]:
            vocation = "characters"
        else:
            await ctx.send(invalid_arguments)
            return

        # params[1] could be a character's name, a character's level or one of the level ranges
        # If it's not a number, it should be a player's name
        if not is_numeric(params[1]):
            # We shouldn't have another parameter if a character name was specified
            if len(params) == 3:
                await ctx.send(invalid_arguments)
                return
            char = await get_character(params[1])
            if type(char) is not dict:
                await ctx.send("I couldn't find a character with that name.")
                return
            low, high = get_share_range(char["level"])
            title = "I found the following {0}s in share range with {1} ({2}-{3}):".format(vocation, char["name"],
                                                                                           low, high)
            empty = "I didn't find any {0}s in share range with **{1}** ({2}-{3})".format(vocation, char["name"],
                                                                                          low, high)
        else:
            # Check if we have another parameter, meaning this is a level range
            if len(params) == 3:
                try:
                    level1 = int(params[1])
                    level2 = int(params[2])
                except ValueError:
                    await ctx.send(invalid_arguments)
                    return
                if level1 <= 0 or level2 <= 0:
                    await ctx.send("You entered an invalid level.")
                    return
                low = min(level1, level2)
                high = max(level1, level2)
                title = "I found the following {0}s between levels {1} and {2}".format(vocation, low, high)
                empty = "I didn't find any {0}s between levels **{1}** and **{2}**".format(vocation, low, high)
            # We only got a level, so we get the share range for it
            else:
                if int(params[1]) <= 0:
                    await ctx.send("You entered an invalid level.")
                    return
                low, high = get_share_range(int(params[1]))
                title = "I found the following {0}s in share range with level {1} ({2}-{3})".format(vocation, params[1],
                                                                                                    low, high)
                empty = "I didn't find any {0}s in share range with level **{1}** ({2}-{3})".format(vocation,
                                                                                                    params[1],
                                                                                                    low, high)

        c = userDatabase.cursor()
        try:
            if vocation == "characters":
                vocation = ""
            c.execute("SELECT name, user_id, ABS(last_level) as level, vocation FROM chars "
                      "WHERE vocation LIKE ? AND level >= ? AND level <= ? AND world = ?"
                      "ORDER by level DESC", ("%"+vocation, low, high, tracked_world, ))
            count = 0
            online_list = [x.split("_", 1)[1] for x in global_online_list]
            while True:
                player = c.fetchone()
                if player is None:
                    break
                # Do not show the same character that was searched for
                if char is not None and char["name"] == player["name"]:
                    continue
                owner = self.bot.get_member(player["user_id"], ctx.message.guild)
                # If the owner is not in server, skip
                if owner is None:
                    continue
                count += 1
                player["owner"] = owner.display_name
                player["online"] = ""
                line_format = "**{name}** - Level {level} - @**{owner}** {online}"
                if vocation == "":
                    line_format = "**{name}** - Level {level} - {vocation} - @**{owner}** {online}"
                if player["name"] in online_list:
                    player["online"] = EMOJI[":small_blue_diamond:"]
                    online_entries.append(line_format.format(**player))
                else:
                    entries.append(line_format.format(**player))
            if count < 1:
                await ctx.send(empty)
                return
        finally:
            c.close()
        if online_entries:
            description = EMOJI[":small_blue_diamond:"]+" = online"
        else:
            description = ""
        pages = Paginator(self.bot, message=ctx.message, entries=online_entries+entries, per_page=per_page,
                          title=title, description=description)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command(aliases=['guildcheck', 'checkguild'])
    async def guild(self, ctx, *, name=None):
        """Checks who is online in a guild"""
        permissions = ctx.message.channel.permissions_for(self.bot.get_member(self.bot.user.id, ctx.message.guild))
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return
        if name is None:
            await ctx.send("Tell me the guild you want me to check.")
            return

        guild = await get_guild_online(name)
        if guild == ERROR_DOESNTEXIST:
            await ctx.send("The guild {0} doesn't exist.".format(name))
            return
        if guild == ERROR_NETWORK:
            await ctx.send("Can you repeat that? I had some trouble communicating.")
            return

        embed = discord.Embed()
        embed.set_author(name="{name} ({world})".format(**guild),
                         url=url_guild + urllib.parse.quote(guild["name"]),
                         icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                         )
        embed.description = ""
        embed.set_thumbnail(url=guild["logo_url"])
        if guild.get("guildhall") is not None:
            guildhouse = await get_house(guild["guildhall"])
            if type(guildhouse) is dict:
                embed.description += "They own the guildhall [{0}]({1}).\n".format(guild["guildhall"],
                                                                                   url_house.format(id=guildhouse["id"],
                                                                                                    world=guild["world"])
                                                                                   )
            else:
                # In case there's no match in the houses table, we just show the name.
                embed.description += "They own the guildhall **{0}**.\n".format(guild["guildhall"])

        if len(guild['members']) < 1:
            embed.description += "Nobody is online."
            await ctx.send(embed=embed)
            return

        plural = ""
        if len(guild['members']) > 1:
            plural = "s"
        embed.description += "It has {0} player{1} online:".format(len(guild['members']), plural)
        current_field = ""
        result = ""
        for member in guild['members']:
            if current_field == "":
                current_field = member['rank']
            elif member['rank'] != current_field and member["rank"] != "":
                embed.add_field(name=current_field, value=result, inline=False)
                result = ""
                current_field = member['rank']

            member["title"] = ' (*' + member['title'] + '*)' if member['title'] != '' else ''
            member["vocation"] = get_voc_abb(member["vocation"])

            result += "{name} {title} -- {level} {vocation}\n".format(**member)
        embed.add_field(name=current_field, value=result, inline=False)
        await ctx.send(embed=embed)

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

    @commands.group(aliases=['deathlist', 'death'], invoke_without_command=True)
    async def deaths(self, ctx, *, name: str = None):
        """Shows a player's or everyone's recent deaths

        If the character is not tracked (owned by someone), only deaths on tibia.com are shown.
        Tracked characters show all their saved deaths"""
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
            user_worlds = [tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None and name is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        try:
            if name is None:
                title = "Latest deaths"
                c.execute("SELECT level, date, name, user_id, byplayer, killer, world, vocation "
                          "FROM char_deaths, chars "
                          "WHERE char_id = id AND level > ? "
                          "ORDER BY date DESC", (announce_threshold,))
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
                    row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
                    row["user"] = user.display_name
                    row["emoji"] = get_voc_emoji(row["vocation"])
                    entries.append("{emoji} {name} (**@{user}**) - At level **{level}** by {killer} - *{time} ago*"
                                   .format(**row))
                    if count >= 100:
                        break
            else:
                char = await get_character(name)
                if char == ERROR_DOESNTEXIST:
                    await ctx.send("That character doesn't exist.")
                    return
                elif char == ERROR_NETWORK:
                    await ctx.send("Sorry, I had trouble checking that character, try it again.")
                    return
                deaths = char["deaths"]
                last_time = now
                name = char["name"]
                voc_emoji = get_voc_emoji(char["vocation"])
                title = "{1} {0} latest deaths:".format(name, voc_emoji)
                if ctx.guild is not None and char["owner_id"]:
                    owner = ctx.guild.get_member(char["owner_id"])  # type: discord.Member
                    if owner is not None:
                        author = owner.display_name
                        author_icon = owner.avatar_url
                for death in deaths:
                    last_time = parse_tibia_time(death["time"]).timestamp()
                    death["time"] = get_time_diff(datetime.now() - parse_tibia_time(death['time']))
                    entries.append("At level **{level}** by {killer} - *{time} ago*".format(**death))
                    count += 1

                c.execute("SELECT id, name FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is not None and not is_lite_mode(ctx):
                    id = result["id"]
                    c.execute("SELECT level, date, byplayer, killer "
                              "FROM char_deaths "
                              "WHERE char_id = ? AND date < ? "
                              "ORDER BY date DESC",
                              (id, last_time))
                    while True:
                        row = c.fetchone()
                        if row is None:
                            break
                        count += 1
                        row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
                        entries.append("At level **{level}** by {killer} - *{time} ago*".format(**row))
                        if count >= 100:
                            break

            if count == 0:
                await ctx.send("There are no registered deaths.")
                return
        finally:
            c.close()

        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title, author=author,
                          author_icon=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="monster", aliases=["mob", "killer"])
    @checks.is_not_lite()
    async def deaths_monsters(self, ctx, *, name: str=None):
        """Returns a list of the latest kills by that monster"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("You must tell me a monster's name to look for its kills.")
            return
        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()
        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        if name[:1] in ["a", "e", "i", "o", "u"]:
            name_with_article = "an "+name
        else:
            name_with_article = "a "+name
        try:
            c.execute("SELECT level, date, name, user_id, byplayer, killer, vocation "
                      "FROM char_deaths, chars "
                      "WHERE char_id = id AND (killer LIKE ? OR killer LIKE ?) "
                      "ORDER BY date DESC", (name, name_with_article))
            while True:
                row = c.fetchone()
                if row is None:
                    break
                user = self.bot.get_member(row["user_id"], ctx.message.guild)
                if user is None:
                    continue
                count += 1
                row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
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

        title = "{0} latest kills".format(name.title())
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="user")
    @checks.is_not_lite()
    async def deaths_user(self, ctx, *, name: str=None):
        """Shows an user's recent deaths on his/her registered characters"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("You must tell me an user's name to look for his/her deaths.")
            return

        if is_private(ctx.message.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        user = self.bot.get_member_by_name(name, user_servers)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()

        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        try:
            c.execute("SELECT name, world, level, killer, byplayer, date, vocation "
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
                row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
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
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, author=title,
                          author_icon=icon_url)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @deaths.command(name="stats")
    @checks.is_not_lite()
    async def deaths_stats(self, ctx, *, period: str = None):
        """Shows death statistic
        
        A shorter period can be shown by adding week or month"""
        permissions = ctx.message.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_worlds = [tracked_worlds.get(ctx.guild.id)]
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

    @commands.group(aliases=['levelups', 'lvl', 'level', 'lvls'], invoke_without_command=True)
    @checks.is_not_lite()
    async def levels(self, ctx, *, name: str=None):
        """Shows a player's or everoyne's recent level ups

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
            user_guilds = [ctx.message.guild]
            user_worlds = [tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        await ctx.channel.trigger_typing()
        try:
            if name is None:
                title = "Latest level ups"
                c.execute("SELECT level, date, name, user_id, world, vocation "
                          "FROM char_levelups, chars "
                          "WHERE char_id = id AND level >= ? "
                          "ORDER BY date DESC", (announce_threshold, ))
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
                    row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
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
                c.execute("SELECT level, date FROM char_levelups, chars "
                          "WHERE id = char_id AND name LIKE ? "
                          "ORDER BY date DESC", (name,))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    count += 1
                    row["time"] = get_time_diff(timedelta(seconds=now-row["date"]))
                    entries.append("Level **{level}** - *{time} ago*".format(**row))
                    if count >= 100:
                        break
        finally:
            c.close()

        if count == 0:
            await ctx.send("There are no registered levels.")
            return

        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title, author=author,
                          author_icon=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @levels.command(name="user")
    @checks.is_not_lite()
    async def levels_user(self, ctx, *, name: str = None):
        """Shows an user's recent level ups on his/her registered characters"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("You must tell me an user's name to look for his/her level ups.")
            return

        if is_private(ctx.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        user = self.bot.get_member_by_name(name, user_servers)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()

        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        try:
            c.execute("SELECT name, world, level, date "
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
                row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
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
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, author=title,
                          author_icon=user.avatar_url)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.group(aliases=["story"], invoke_without_command=True)
    @checks.is_not_lite()
    async def timeline(self, ctx, *, name: str = None):
        """Shows a player's recent level ups and deaths"""
        permissions = ctx.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if is_private(ctx.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        author = None
        author_icon = discord.Embed.Empty
        count = 0
        now = time.time()
        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        await ctx.channel.trigger_typing()
        try:
            if name is None:
                title = "Timeline"
                c.execute("SELECT name, user_id, world, level, killer, 'death' AS `type`, date, vocation "
                          "FROM char_deaths, chars WHERE char_id = id AND level >= ? "
                          "UNION "
                          "SELECT name, user_id, world, level, null, 'levelup' AS `type`, date, vocation "
                          "FROM char_levelups, chars WHERE char_id = id AND level >= ? "
                          "ORDER BY date DESC", (announce_threshold, announce_threshold))
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
                    row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
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
                c.execute("SELECT name, user_id, world, level, killer, 'death' AS `type`, date, vocation "
                          "FROM char_deaths, chars WHERE char_id = id AND level >= ? AND name LIKE ?"
                          "UNION "
                          "SELECT name, user_id, world, level, null, 'levelup' AS `type`, date, vocation "
                          "FROM char_levelups, chars WHERE char_id = id AND level >= ? AND name LIKE ? "
                          "ORDER BY date DESC", (announce_threshold, name, announce_threshold, name))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    count += 1
                    row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
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

        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title, author=author,
                          author_icon=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @timeline.command(name="user")
    @checks.is_not_lite()
    async def timeline_user(self, ctx, *, name: str = None):
        """Shows an users's recent level ups and deaths on his/her characters"""
        permissions = ctx.message.channel.permissions_for(ctx.me)
        if not permissions.embed_links:
            await ctx.send("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            await ctx.send("You must tell me an user's name to look for his/her story.")
            return

        if is_private(ctx.channel):
            user_servers = self.bot.get_user_guilds(ctx.author.id)
            user_worlds = self.bot.get_user_worlds(ctx.author.id)
        else:
            user_servers = [ctx.guild]
            user_worlds = [tracked_worlds.get(ctx.guild.id)]
            if user_worlds[0] is None:
                await ctx.send("This server is not tracking any tibia worlds.")
                return

        user = self.bot.get_member_by_name(name, user_servers)
        if user is None:
            await ctx.send("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        entries = []
        count = 0
        now = time.time()

        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.guild)
        if is_private(ctx.channel) or ctx.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        await ctx.channel.trigger_typing()
        try:
            title = f"{user.display_name} timeline"
            c.execute("SELECT name, user_id, world, level, killer, 'death' AS `type`, date, vocation "
                      "FROM char_deaths, chars WHERE char_id = id AND level >= ? AND user_id = ? "
                      "UNION "
                      "SELECT name, user_id, world, level, null, 'levelup' AS `type`, date, vocation "
                      "FROM char_levelups, chars WHERE char_id = id AND level >= ? AND user_id = ? "
                      "ORDER BY date DESC", (announce_threshold, user.id, announce_threshold, user.id))
            while True:
                row = c.fetchone()
                if row is None:
                    break
                if row["world"] not in user_worlds:
                    continue
                count += 1
                row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
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
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, author=title,
                          author_icon=author_icon)
        try:
            await pages.paginate()
        except CannotPaginate as e:
            await ctx.send(e)

    @commands.command()
    async def stats(self, ctx, *, params: str=None):
        """Calculates character stats

        There are 3 ways to use this command:
        /stats player
        /stats level,vocation
        /stats vocation,level"""
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
                char = await get_character(params[0])
                if char == ERROR_NETWORK:
                    await ctx.send("Sorry, can you try it again?")
                    return
                if char == ERROR_DOESNTEXIST:
                    await ctx.send("Character **{0}** doesn't exist!".format(params[0]))
                    return
                level = int(char['level'])
                vocation = char['vocation']
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
            pronoun = "he" if char['gender'] == "male" else "she"
            await ctx.send("**{5}** is a level **{0}** {1}, {6} has:"
                           "\n\t**{2:,}** HP"
                           "\n\t**{3:,}** MP"
                           "\n\t**{4:,}** Capacity"
                           "\n\t**{7:,}** Total experience"
                           "\n\t**{8:,}** to next level"
                           .format(level, char["vocation"].lower(), stats["hp"], stats["mp"], stats["cap"],
                                   char['name'], pronoun, stats["exp"], stats["exp_tnl"]))
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
    async def blessings(self, ctx, level: int = None):
        """Calculates the price of blessings at a specific level"""
        if level is None:
            await ctx.send("I need a level to tell you blessings's prices")
            return
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

    @commands.command()
    async def spell(self, ctx, *, name: str= None):
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

    @commands.command(aliases=["houses", "guildhall", "gh"])
    async def house(self, ctx, *, name: str=None):
        """Shows info for a house or guildhall

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
        if name is None:
            await ctx.send("Tell me the name of the house or guildhall you want to check.")
            return
        world = None
        if ctx.guild is not None and len(params) == 1:
            world = tracked_worlds.get(ctx.guild.id)
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

        ask_channel = self.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
        if not (ask_channel == ctx.message.channel or is_private(ctx.message.channel)):
            achievement["spoiler"] = "*To see spoilers, pm me"
            if ask_channel is not None:
                achievement["spoiler"] += " or use "+ask_channel.mention
            achievement["spoiler"] += ".*"

        embed = discord.Embed(title=achievement["name"], description=achievement["description"])
        embed.add_field(name="Grade", value=EMOJI[":star:"]*int(achievement["grade"]))
        embed.add_field(name="Points", value=achievement["points"])
        embed.add_field(name="Spoiler", value=achievement["spoiler"], inline=True)

        await ctx.send(embed=embed)

    @commands.command(aliases=['serversave', 'ss'])
    async def time(self, ctx):
        """Displays tibia server's time and time until server save"""
        offset = get_tibia_time_zone() - get_local_timezone()
        tibia_time = datetime.now()+timedelta(hours=offset)
        server_save = tibia_time
        if tibia_time.hour >= 10:
            server_save += timedelta(days=1)
        server_save = server_save.replace(hour=10, minute=0, second=0, microsecond=0)
        time_until_ss = server_save - tibia_time
        hours, remainder = divmod(int(time_until_ss.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        timestrtibia = tibia_time.strftime("%H:%M")
        server_save_str = '{h} hours and {m} minutes'.format(h=hours, m=minutes)

        reply = "It's currently **{0}** in Tibia's servers.".format(timestrtibia)
        if display_brasilia_time:
            offsetbrasilia = get_brasilia_time_zone() - get_local_timezone()
            brasilia_time = datetime.now()+timedelta(hours=offsetbrasilia)
            timestrbrasilia = brasilia_time.strftime("%H:%M")
            reply += "\n**{0}** in Brazil (Brasilia).".format(timestrbrasilia)
        if display_sonora_time:
            offsetsonora = -7 - get_local_timezone()
            sonora_time = datetime.now()+timedelta(hours=offsetsonora)
            timestrsonora = sonora_time.strftime("%H:%M")
            reply += "\n**{0}** in Mexico (Sonora).".format(timestrsonora)
        reply += "\nServer save is in {0}.\nRashid is in **{1}** today.".format(server_save_str, get_rashid_city())
        await ctx.send(reply)

    @commands.command(name="world")
    async def world_info(self, ctx, name: str = None):
        """Shows basic information about a Tibia world"""
        if name is None:
            await ctx.send("You must tell me the name of the world you want to check.")
            return

        world = await get_world_info(name)
        if world is None:
            await ctx.send("There's no world with that name.")
            return

        flags = {"North America": EMOJI[":flag_us:"], "South America": EMOJI[":flag_br:"], "Europe": EMOJI[":flag_gb:"]}
        pvp = {"Optional PvP": EMOJI[":dove:"], "Hardcore PvP": EMOJI[":skull:"], "Open PvP": EMOJI[":crossed_swords:"],
               "Retro Open PvP": EMOJI[":crossed_swords:"]}
        transfers = {"locked": EMOJI[":lock:"], "blocked": EMOJI[":no_entry_sign:"]}

        url = 'https://secure.tibia.com/community/?subtopic=worlds&world=' + name.capitalize()
        embed = discord.Embed(url=url, title=name.capitalize())
        if world["status"] == "Offline":
            embed.description = "This world is offline."
            embed.colour = discord.Colour.red()
        else:
            embed.colour = discord.Colour.green()
        if "online" in world:
            embed.add_field(name="Players online", value=str(world["online"]))
        embed.add_field(name="Online record", value="{record_online} online on {record_date}".format(**world))
        created = world["created"].split("/")
        try:
            month = calendar.month_name[int(created[0])]
            year = int(created[1])
            if year > 90:
                year += 1900
            else:
                year += 2000
            embed.add_field(name="Created", value=f"{month} {year}")
        except (IndexError, ValueError):
            pass

        embed.add_field(name="Location", value=f"{flags.get(world['location'],'')} {world['location']}")
        embed.add_field(name="PvP Type", value=f"{pvp.get(world['pvp'],'')} {world['pvp']}")
        if "premium" in world:
            embed.add_field(name="Premium restricted", value=EMOJI[":white_check_mark:"])
        if "transfer" in world:
            embed.add_field(name="Transfers", value=f"{transfers.get(world['transfer'],'')} {world['transfer']}")

        await ctx.send(embed=embed)

    @commands.command()
    async def bosses(self, ctx, world=None):
        """Shows predictions for bosses"""
        ask_channel = ctx.bot.get_channel_by_name(ask_channel_name, ctx.guild)

        if world is None and not is_private(ctx.channel) and tracked_worlds.get(ctx.guild.id) is not None:
            world = tracked_worlds.get(ctx.guild.id)
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

    @staticmethod
    def get_char_string(char) -> str:
        """Returns a formatted string containing a character's info."""
        if char == ERROR_NETWORK or char == ERROR_DOESNTEXIST:
            return char
        char["he_she"] = "He"
        char["his_her"] = "His"
        if char['gender'] == "female":
            char["he_she"] = "She"
            char["his_her"] = "Her"
        char["url"] = get_character_url(char["name"])
        reply = "[{name}]({url}) is a level {level} __{vocation}__. " \
                "{he_she} resides in __{residence}__ in the world of __{world}__.".format(**char)
        if char["guild"] is not None:
            char["guild_url"] = url_guild+urllib.parse.quote(char["guild"])
            reply += "\n{he_she} is __{rank}__ of the [{guild}]({guild_url}).".format(**char)
        if "married" in char:
            char["married_url"] = url_character + urllib.parse.quote(char["married"].encode('iso-8859-1'))
            reply += "\n{he_she} is married to [{married}]({married_url}).".format(**char)
        if "house" in char:
            char["house_url"] = url_house.format(id=char["house_id"], world=char["world"])
            reply += "\n{he_she} owns [{house}]({house_url}) in {house_town}.".format(**char)
        if char['last_login'] is not None:
            last_login = parse_tibia_time(char['last_login'])
            now = datetime.now()
            time_diff = now - last_login
            if time_diff.days > last_login_days:
                reply += "\n{he_she} hasn't logged in for **{0}**.".format(get_time_diff(time_diff), **char)
        else:
            reply += "\n{he_she} has never logged in."

        # Insert any highscores this character holds
        for category in highscores_categories:
            if char.get(category, None):
                highscore_string = highscore_format[category].format(char["his_her"], char[category], char[category+'_rank'])
                reply += "\n"+EMOJI[":trophy:"]+" {0}".format(highscore_string)
        return reply

    def get_user_embed(self, ctx, user: discord.Member) -> Optional[discord.Embed]:
        if user is None:
            return None
        embed = discord.Embed()
        if is_private(ctx.message.channel):
            display_name = '@'+user.name
            user_guilds = self.bot.get_user_guilds(ctx.author.id)
            user_tibia_worlds = [world for server, world in tracked_worlds.items() if
                                 server in [s.id for s in user_guilds]]
        else:
            display_name = '@'+user.display_name
            embed.colour = user.colour
            if tracked_worlds.get(ctx.message.guild.id) is None:
                user_tibia_worlds = []
            else:
                user_tibia_worlds = [tracked_worlds[ctx.message.guild.id]]
        if len(user_tibia_worlds) == 0:
            return None
        embed.set_thumbnail(url=user.avatar_url)

        placeholders = ", ".join("?" for w in user_tibia_worlds)
        c = userDatabase.cursor()
        try:
            c.execute("SELECT name, ABS(last_level) as level, vocation "
                      "FROM chars "
                      "WHERE user_id = {0} AND world IN ({1}) ORDER BY level DESC".format(user.id, placeholders),
                      tuple(user_tibia_worlds))
            characters = c.fetchall()
            if not characters:
                embed.description = f"I don't know who **{display_name}** is..."
                return embed
            online_list = [x.split("_", 1)[1] for x in global_online_list]
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
    def get_monster_embed(ctx, monster, long):
        """Gets the monster embeds to show in /mob command
        The message is split in two embeds, the second contains loot only and is only shown if long is True"""
        embed = discord.Embed(title=monster["title"])
        hp = "?" if monster["health"] is None else "{0:,}".format(monster["health"])
        experience = "?" if monster["experience"] is None else "{0:,}".format(monster["experience"])
        if not (monster["experience"] is None or monster["health"] is None or monster["health"] < 0):
            ratio = "{0:.2f}".format(monster['experience'] / monster['health'])
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
                if monster[index] == 0:
                    immune.append(index.title())
                elif monster[index] > 100:
                    weak.append([index.title(), monster[index]-100])
                elif monster[index] < 100:
                    resist.append([index.title(), monster[index]-100])
        # Add paralysis to immunities
        if monster["paralysable"] == 0:
            immune.append("Paralysis")
        if monster["senseinvis"] == 1:
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
                            value="{maxdamage:,}".format(**monster) if monster["maxdamage"] is not None else "???")
            embed.add_field(name="Abilities", value=monster["abilities"], inline=False)
        if monster["loot"] and long:
            loot_string = ""
            for item in monster["loot"]:
                if item["percentage"] is None:
                    item["percentage"] = "??.??%"
                elif item["percentage"] >= 100:
                    item["percentage"] = "Always"
                else:
                    item["percentage"] = "{0:.2f}".format(item['percentage']).zfill(5) + "%"
                if item["max"] > 1:
                    item["count"] = "({min}-{max})".format(**item)
                else:
                    item["count"] = ""
                loot_string += "{percentage} {name} {count}\n".format(**item)
            split_loot = split_message(loot_string, FIELD_VALUE_LIMIT)
            for loot in split_loot:
                if loot == split_loot[0]:
                    name = "Loot"
                else:
                    name = "\u200F"
                embed.add_field(name=name, value="`"+loot+"`")
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

        embed = discord.Embed(title=item["title"], description=item["look_text"])
        if "color" in item:
            embed.colour = item["color"]
        if "ImbueSlots" in item["properties"]:
            embed.add_field(name="Imbuement slots", value=item["properties"]["ImbueSlots"])
        if "imbuements" in item["properties"] and len(item["properties"]["imbuements"]) > 0:
            embed.add_field(name="Used for", value="\n".join(item["properties"]["imbuements"]))
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
                value += "\n"+quest
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item["dropped_by"]) - short_limit)
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
                    creature["percentage"] = "??.??"
                value += "\n{name} ({percentage}%)".format(**creature)
                if count >= short_limit and not long:
                    value += "\n*...And {0} others*".format(len(item["dropped_by"]) - short_limit)
                    drops_too_long = True
                    break
                if long and count >= long_limit:
                    value += "\n*...And {0} others*".format(len(item["dropped_by"]) - long_limit)
                    break

            embed.add_field(name=name, value=value)

        if npcs_too_long or drops_too_long or quests_too_long:
            ask_channel = ctx.bot.get_channel_by_name(ask_channel_name, ctx.message.guild)
            if ask_channel:
                askchannel_string = " or use #" + ask_channel.name
            else:
                askchannel_string = ""
            embed.set_footer(text="To see more, PM me{0}.".format(askchannel_string))

        return embed

    @staticmethod
    def get_house_embed(house):
        """Gets the embed to show in /house command"""
        if type(house) is not dict:
            return
        embed = discord.Embed(title=house["name"])
        house["type"] = "house" if house["guildhall"] == 0 else "guildhall"
        house["_beds"] = "bed" if house["beds"] == 1 else "beds"
        description = "This {type} has **{beds}** {_beds} and has a size of **{sqm}** sqm." \
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

    @staticmethod
    def get_spell_embed(ctx, spell, long):
        """Gets the embed to show in /spell command"""
        short_limit = 5
        too_long = False

        if type(spell) is not dict:
            return
        embed = discord.Embed(title="{name} ({words})".format(**spell))
        spell["premium"] = "**premium** " if spell["premium"] else ""
        if spell["manacost"] < 0:
            spell["manacost"] = "variable"
        if "exani hur" in spell["words"]:
            spell["words"] = "exani hur up/down"
        vocs = list()
        if spell['knight']: vocs.append("knights")
        if spell['paladin']: vocs.append("paladins")
        if spell['druid']: vocs.append("druids")
        if spell['sorcerer']: vocs.append("sorcerers")
        spell["vocs"] = join_list(vocs, ", ", " and ")

        description = "A {premium}spell for level **{levelrequired}** and up. " \
                      "It uses **{manacost}** mana. It can be used by {vocs}".format(**spell)

        if spell["goldcost"] == 0:
            description += "\nIt can be obtained for free."
        else:
            description += "\nIt can be bought for {0:,} gold coins.".format(spell["goldcost"])

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
    bot.add_cog(Tibia(bot))

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
