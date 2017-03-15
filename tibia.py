import discord
from discord.ext import commands
from PIL import Image
import os
import random
import requests
import io

from config import *
from utils import checks
from utils.database import tracked_worlds
from utils.general import is_numeric, get_time_diff, join_list, get_brasilia_time_zone
from utils.loot import loot_scan
from utils.messages import EMOJI, split_message
from utils.discord import get_member_by_name, get_user_color, get_member, get_channel_by_name, get_user_servers, \
    FIELD_VALUE_LIMIT, get_user_worlds
from utils.paginator import Paginator, CannotPaginate
from utils.tibia import *


# Commands
class Tibia:
    """Tibia related commands."""
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.parsing_count = 0

    @commands.group(pass_context=True, invoke_without_command=True)
    @checks.is_not_lite()
    @asyncio.coroutine
    def loot(self, ctx):
        """Scans a loot image and returns it's loot value

        The bot will return a list of the items found along with their values, grouped by NPC.
        If the image is compressed or was taken using Tibia's software render, the bot might struggle finding matches.

        The bot can only scan 3 images simultaneously."""
        author = ctx.message.author
        if self.parsing_count >= loot_max:
            yield from self.bot.say("Sorry, I am already parsing too many loot images, "
                                    "please wait a couple of minutes and try again.")
            return

        if len(ctx.message.attachments) == 0:
            yield from self.bot.say("You need to upload a picture of your loot and type the command in the comment.")
            return

        attachment = ctx.message.attachments[0]
        if attachment['size'] > 2097152:
            yield from self.bot.say("That image was too big! Try splitting it into smaller images, or cropping out anything irrelevant.")
            return
        file_name = attachment['url'].split("/")[len(attachment['url'].split("/"))-1]
        file_url = attachment['url']
        r = requests.get(attachment['url'])
        try:
            lootImage = Image.open(io.BytesIO(bytearray(r.content))).convert("RGBA")
        except Exception:
            yield from self.bot.say("Either that wasn't an image or I failed to load it, please try again.")
            return

        self.parsing_count += 1
        yield from self.bot.say("I've begun parsing your image, **@{0.display_name}**. "
                                "Please be patient, this may take a few moments.".format(author))
        progress_msg = yield from self.bot.say("Status: ...")
        progress_bar = yield from self.bot.say(EMOJI[":black_large_square:"]*10)

        loot_list, loot_image_overlay = yield from loot_scan(self.bot, lootImage, file_name, progress_msg, progress_bar)
        self.parsing_count -= 1
        embed = discord.Embed()
        long_message = "These are the results for your image: [{0}]({1})".format(file_name, file_url)

        if len(loot_list) == 0:
            message = "Sorry {0.mention}, I couldn't find any loot in that image. Loot parsing will only work on " \
                      "high quality images, so make sure your image wasn't compressed."
            yield from self.bot.say(message.format(author))
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

        for group in groups:
            value = ""
            group_value = 0
            for item in loot_list:
                if loot_list[item]['group'] == group and loot_list[item]['group'] != "Unknown":
                    if group == "No Value":
                        value += "x{1} {0}\n".format(item, loot_list[item]['count'])
                    else:
                        value += "x{1} {0} \u2192 {2:,}gp total.\n".format(
                            item, loot_list[item]['count'], loot_list[item]['count']*loot_list[item]['value'])

                    total_value += loot_list[item]['count']*loot_list[item]['value']
                    group_value += loot_list[item]['count']*loot_list[item]['value']
            if group == "No Value":
                name = group
            else:
                name = "{0} - {1:,} gold".format(group, group_value)
            embed.add_field(name=name, value=value, inline=False)

        if unknown:
            long_message += "\n*There were {0} unknown items.*\n".format(unknown['count'])

        long_message += "\nThe total loot value is: **{0:,}** gold coins.".format(total_value)
        embed.description = long_message

        # Short message
        short_message = "I've finished parsing your image {0.mention}.\nThe total value is {1:,} gold coins."
        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if not ctx.message.channel.is_private and ctx.message.channel != ask_channel:
            short_message += "\nI've also sent you a PM with detailed information."
        yield from self.bot.say(short_message.format(author, total_value))

        # Send on ask_channel or PM
        if ctx.message.channel == ask_channel:
            destination = ctx.message.channel
        else:
            destination = ctx.message.author

        yield from self.bot.send_file(destination, loot_image_overlay, filename=file_name+".png")
        yield from self.bot.send_message(destination, embed=embed)

    @loot.command(name="legend", aliases=["help", "symbols", "symbol"])
    @checks.is_not_lite()
    @asyncio.coroutine
    def loot_legend(self):
        """Shows the meaning of the overlayed icons."""
        with open("./images/legend.png", "r+b") as f:
            yield from self.bot.upload(f)
            f.close()

    @commands.command(aliases=['check', 'player', 'checkplayer', 'char', 'character'], pass_context=True)
    @asyncio.coroutine
    def whois(self, ctx, *, name=None):
        """Tells you a character's or a discord user's information

        If it matches a discord user, it displays its registered users
        If it matches a character, it displays its information.

        Note that the bot has no way to know the characters of a member that just joined.
        The bot has to be taught about the character's of an user."""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return
        if name is None:
            yield from self.bot.say("Tell me which character or user you want to check.")
            return

        if lite_mode:
            char = yield from get_character(name)
            if char == ERROR_DOESNTEXIST:
                yield from self.bot.say("I couldn't find a character with that name")
            elif char == ERROR_NETWORK:
                yield from self.bot.say("Sorry, I couldn't fetch the character's info, maybe you should try again...")
            else:
                embed = discord.Embed(description=self.get_char_string(char))
                embed.set_author(name=char["name"],
                                 url=url_character + urllib.parse.quote(char["name"]),
                                 icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                 )
                yield from self.bot.say(embed=embed)
            return
        if ctx.message.channel.is_private:
            bot_member = self.bot.user
        else:
            bot_member = get_member(self.bot, self.bot.user.id, ctx.message.server)
        if name.lower() == bot_member.display_name.lower():
            yield from ctx.invoke(self.bot.commands.get('about'))
            return

        char = yield from get_character(name)
        char_string = self.get_char_string(char)
        user = get_member_by_name(self.bot, name, ctx.message.server)
        user_string = self.get_user_string(ctx, name)
        embed = discord.Embed()
        embed.description = ""

        # No user or char with that name
        if char == ERROR_DOESNTEXIST and (user is None or user_string == ERROR_DOESNTEXIST):
            yield from self.bot.say("I don't see any user or character with that name.")
            return
        # We found an user
        if user is not None and user_string != ERROR_DOESNTEXIST:
            embed.description = user_string
            color = get_user_color(user, ctx.message.server)
            if color is not discord.Colour.default():
                embed.colour = color
            if "I don't know" not in user_string:
                embed.set_thumbnail(url=user.avatar_url)
            # Check if we found a char too
            if type(char) is dict:
                # If it's owned by the user, we append it to the same embed.
                if char["owner_id"] == int(user.id):
                    embed.add_field(name="Character", value=char_string, inline=False)
                    yield from self.bot.say(embed=embed)
                    return
                # Not owned by same user, we display a separate embed
                else:
                    char_embed = discord.Embed(description=char_string)
                    char_embed.set_author(name=char["name"],
                                          url=get_character_url(char["name"]),
                                          icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                          )
                    yield from self.bot.say(embed=embed)
                    yield from self.bot.say(embed=char_embed)
            else:
                yield from self.bot.say(embed=embed)
                if char == ERROR_NETWORK:
                    yield from self.bot.say("I failed to do a character search for some reason "+EMOJI[":astonished:"])
        else:
            if char == ERROR_NETWORK:
                yield from self.bot.say("I failed to do a character search for some reason " + EMOJI[":astonished:"])
            elif type(char) is dict:
                embed.set_author(name=char["name"],
                                 url=get_character_url(char["name"]),
                                 icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                 )
                # Char is owned by a discord user
                owner = get_member(self.bot, char["owner_id"], ctx.message.server)
                if owner is not None:
                    embed.set_thumbnail(url=owner.avatar_url)
                    color = get_user_color(owner, ctx.message.server)
                    if color is not discord.Colour.default():
                        embed.colour = color
                    embed.description += "A character of @**{1.display_name}**\n".format(char["name"], owner)

                embed.description += char_string

            yield from self.bot.say(embed=embed)

    @commands.command(aliases=['expshare', 'party'])
    @asyncio.coroutine
    def share(self, *, param: str=None):
        """Shows the sharing range for that level or character

        There's two ways to use this command:
        /share level
        /share char_name"""
        if param is None:
            yield from self.bot.say("You need to tell me a level or a character's name.")
            return
        name = ""
        # Check if param is numeric
        try:
            level = int(param)
        # If it's not numeric, then it must be a char's name
        except ValueError:
            char = yield from get_character(param)
            if type(char) is dict:
                level = int(char['level'])
                name = char['name']
            else:
                yield from self.bot.say('There is no character with that name.')
                return
        if level <= 0:
            replies = ["Invalid level.",
                       "I don't think that's a valid level.",
                       "You're doing it wrong!",
                       "Nope, you can't share with anyone.",
                       "You probably need a couple more levels"
                       ]
            yield from self.bot.say(random.choice(replies))
            return
        low, high = get_share_range(level)
        if name == "":
            reply = "A level {0} can share experience with levels **{1}** to **{2}**.".format(level, low, high)
        else:
            reply = "**{0}** ({1}) can share experience with levels **{2}** to **{3}**.".format(name, level, low, high)
        yield from self.bot.say(reply)

    @commands.command(name="find", aliases=["whereteam", "team", "findteam", "searchteam", "search"], no_pm=True,
                      pass_context=True)
    @checks.is_not_lite()
    @asyncio.coroutine
    def find_team(self, ctx, *, params=None):
        """Searches for a registered character that meets the criteria

        There are 3 ways to use this command:
        -Find a character of a certain vocation in share range with another character:
        /find vocation,charname

        -Find a character of a certain vocation in share range with a certain level
        /find vocation,level

        -Find a character of a certain vocation between a level range
        /find vocation,min_level,max_level"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        invalid_arguments = "Invalid arguments used, examples:\n" \
                            "```/find vocation,charname\n" \
                            "/find vocation,level\n" \
                            "/find vocation,minlevel,maxlevel```"

        tracked_world = tracked_worlds.get(ctx.message.server.id)
        if tracked_world is None:
            yield from self.bot.say("This server is not tracking any tibia worlds.")
            return

        if params is None:
            yield from self.bot.say(invalid_arguments)
            return

        entries = []
        online_entries = []

        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        char = None
        params = params.split(",")
        if len(params) < 2 or len(params) > 3:
            yield from self.bot.say(invalid_arguments)
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
            yield from self.bot.say(invalid_arguments)
            return

        # params[1] could be a character's name, a character's level or one of the level ranges
        # If it's not a number, it should be a player's name
        if not is_numeric(params[1]):
            # We shouldn't have another parameter if a character name was specified
            if len(params) == 3:
                yield from self.bot.say(invalid_arguments)
                return
            char = yield from get_character(params[1])
            if type(char) is not dict:
                yield from self.bot.say("I couldn't find a character with that name.")
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
                    yield from self.bot.say(invalid_arguments)
                    return
                if level1 <= 0 or level2 <= 0:
                    yield from self.bot.say("You entered an invalid level.")
                    return
                low = min(level1, level2)
                high = max(level1, level2)
                title = "I found the following {0}s between levels {1} and {2}".format(vocation, low, high)
                empty = "I didn't find any {0}s between levels **{1}** and **{2}**".format(vocation, low, high)
            # We only got a level, so we get the share range for it
            else:
                if int(params[1]) <= 0:
                    yield from self.bot.say("You entered an invalid level.")
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
                owner = get_member(self.bot, player["user_id"], ctx.message.server)
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
                yield from self.bot.say(empty)
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
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @commands.command(pass_context=True, aliases=['guildcheck', 'checkguild'])
    @asyncio.coroutine
    def guild(self, ctx, *, name=None):
        """Checks who is online in a guild"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return
        if name is None:
            yield from self.bot.say("Tell me the guild you want me to check.")
            return

        guild = yield from get_guild_online(name)
        if guild == ERROR_DOESNTEXIST:
            yield from self.bot.say("The guild {0} doesn't exist.".format(name))
            return
        if guild == ERROR_NETWORK:
            yield from self.bot.say("Can you repeat that? I had some trouble communicating.")
            return

        embed = discord.Embed()
        embed.set_author(name="{name} ({world})".format(**guild),
                         url=url_guild + urllib.parse.quote(guild["name"]),
                         icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                         )
        embed.description = ""
        embed.set_thumbnail(url=guild["logo_url"])
        if guild.get("guildhall") is not None:
            guildhouse = yield from get_house(guild["guildhall"])
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
            yield from self.bot.say(embed=embed)
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
        yield from self.bot.say(embed=embed)

    @commands.command(pass_context=True, aliases=['checkprice', 'itemprice'])
    @asyncio.coroutine
    def item(self, ctx, *, name: str=None):
        """Checks an item's information

        Shows name, picture, npcs that buy and sell and creature drops"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("Tell me the name of the item you want to search.")
            return
        item = get_item(name)
        if item is None:
            yield from self.bot.say("I couldn't find an item with that name.")
            return

        if type(item) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(item))
            yield from self.bot.say("I couldn't find that item, maybe you meant one of these?", embed=embed)
            return

        # Attach item's image only if the bot has permissions
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if permissions.attach_files and item["image"] != 0:
            filename = item['name'] + ".png"
            while os.path.isfile(filename):
                filename = "_" + filename
            with open(filename, "w+b") as f:
                f.write(bytearray(item['image']))
                f.close()

            with open(filename, "r+b") as f:
                yield from self.bot.upload(f)
                f.close()
            os.remove(filename)

        long = ctx.message.channel.is_private or ctx.message.channel.name == ask_channel_name
        embed = self.get_item_embed(ctx, item, long)
        yield from self.bot.say(embed=embed)

    @commands.command(pass_context=True, aliases=['mon', 'mob', 'creature'])
    @asyncio.coroutine
    def monster(self, ctx, *, name: str=None):
        """Gives information about a monster"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("Tell me the name of the monster you want to search.")
            return
        if ctx.message.channel.is_private:
            bot_member = self.bot.user
        else:
            bot_member = get_member(self.bot, self.bot.user.id, ctx.message.server)
        if name.lower() == bot_member.display_name.lower():
            yield from self.bot.say(random.choice(["**"+bot_member.display_name+"** is too strong for you to hunt!",
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
            yield from self.bot.say("I couldn't find a monster with that name.")
            return

        if type(monster) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(monster))
            yield from self.bot.say("I couldn't find that creature, maybe you meant one of these?", embed=embed)
            return

        # Attach item's image only if the bot has permissions
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if permissions.attach_files and monster["image"] != 0:
            filename = monster['name'] + ".png"
            while os.path.isfile(filename):
                filename = "_" + filename
            with open(filename, "w+b") as f:
                f.write(bytearray(monster['image']))
                f.close()
            # Send monster's image
            with open(filename, "r+b") as f:
                yield from self.bot.upload(f)
                f.close()
            os.remove(filename)

        long = ctx.message.channel.is_private or ctx.message.channel.name == ask_channel_name
        embed = self.get_monster_embed(ctx, monster, long)

        yield from self.bot.say(embed=embed)

    @commands.group(aliases=['deathlist', 'death'], pass_context=True, invoke_without_command=True)
    @asyncio.coroutine
    def deaths(self, ctx, *, name: str = None):
        """Shows a player's or everyone's recent deaths"""
        if name is None and lite_mode:
            return
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if ctx.message.channel.is_private:
            user_servers = get_user_servers(self.bot, ctx.message.author.id)
            user_worlds = get_user_worlds(self.bot, ctx.message.author.id)
        else:
            user_servers = [ctx.message.server]
            user_worlds = [tracked_worlds.get(ctx.message.server.id)]
            if user_worlds[0] is None and name is None:
                yield from self.bot.say("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        count = 0
        now = time.time()
        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        try:
            if name is None:
                title = "Latest deaths"
                c.execute("SELECT level, date, name, user_id, byplayer, killer, world "
                          "FROM char_deaths, chars "
                          "WHERE char_id = id "
                          "ORDER BY date DESC")
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    user = get_member(self.bot, row["user_id"], guild_list=user_servers)
                    if user is None:
                        continue
                    if row["world"] not in user_worlds:
                        continue
                    count += 1
                    row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
                    row["user"] = user.display_name
                    entries.append("{name} (**@{user}**) - At level **{level}** by {killer} - *{time} ago*".format(**row))
                    if count >= 100:
                        break
            else:
                char = yield from get_character(name)
                if char == ERROR_DOESNTEXIST:
                    yield from self.bot.say("That character doesn't exist.")
                    return
                elif char == ERROR_NETWORK:
                    yield from self.bot.say("Sorry, I had trouble checking that character, try it again.")
                    return
                deaths = char["deaths"]
                last_time = now
                name = char["name"]
                title = "{0} latest deaths:".format(name)
                for death in deaths:
                    last_time = parse_tibia_time(death["time"]).timestamp()
                    death["time"] = get_time_diff(datetime.now() - parse_tibia_time(death['time']))
                    entries.append("At level **{level}** by {killer} - *{time} ago*".format(**death))
                    count += 1

                c.execute("SELECT id, name FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is not None and not lite_mode:
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
                yield from self.bot.say("There are no registered deaths.")
                return
        finally:
            c.close()

        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @deaths.command(pass_context=True, name="monster", aliases=["mob", "killer"])
    @checks.is_not_lite()
    @asyncio.coroutine
    def deaths_monsters(self, ctx, *, name: str=None):
        """Returns a list of the latest kills by that monster"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("You must tell me a monster's name to look for its kills.")
            return
        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()
        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        if name[:1] in ["a", "e", "i", "o", "u"]:
            name_with_article = "an "+name
        else:
            name_with_article = "a "+name
        try:
            c.execute("SELECT level, date, name, user_id, byplayer, killer "
                      "FROM char_deaths, chars "
                      "WHERE char_id = id AND (killer LIKE ? OR killer LIKE ?) "
                      "ORDER BY date DESC", (name, name_with_article))
            while True:
                row = c.fetchone()
                if row is None:
                    break
                user = get_member(self.bot, row["user_id"], ctx.message.server)
                if user is None:
                    continue
                count += 1
                row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
                row["user"] = user.display_name
                entries.append("{name} (**@{user}**) - At level **{level}** - *{time} ago*".format(**row))
                if count >= 100:
                    break
            if count == 0:
                yield from self.bot.say("There are no registered deaths by that killer.")
                return
        finally:
            c.close()

        title = "{0} latest kills".format(name.title())
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @deaths.command(pass_context=True,name="user")
    @checks.is_not_lite()
    @asyncio.coroutine
    def deaths_user(self, ctx, *, name: str=None):
        """Shows an user's recent deaths on his/her registered characters"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("You must tell me an user's name to look for his/her deaths.")
            return

        if ctx.message.channel.is_private:
            user_servers = get_user_servers(self.bot, ctx.message.author.id)
            user_worlds = get_user_worlds(self.bot, ctx.message.author.id)
        else:
            user_servers = [ctx.message.server]
            user_worlds = [tracked_worlds.get(ctx.message.server.id)]
            if user_worlds[0] is None:
                yield from self.bot.say("This server is not tracking any tibia worlds.")
                return

        user = get_member_by_name(self.bot, name, guild_list=user_servers)
        if user is None:
            yield from self.bot.say("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()

        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5

        try:
            c.execute("SELECT name, world, level, killer, byplayer, date "
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
                entries.append("{name} - At level **{level}** by {killer} - *{time} ago*".format(**row))

                if count >= 100:
                    break
            if count == 0:
                yield from self.bot.say("There are not registered deaths by this user.")
                return
        finally:
            c.close()

        title = "@{0} latest kills".format(user.display_name)
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @commands.group(pass_context=True, aliases=['levelups', 'lvl', 'level', 'lvls'], invoke_without_command=True)
    @checks.is_not_lite()
    @asyncio.coroutine
    def levels(self, ctx, *, name: str=None):
        """Shows a player's or everoyne's recent level ups

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if ctx.message.channel.is_private:
            user_servers = get_user_servers(self.bot, ctx.message.author.id)
            user_worlds = get_user_worlds(self.bot, ctx.message.author.id)
        else:
            user_servers = [ctx.message.server]
            user_worlds = [tracked_worlds.get(ctx.message.server.id)]
            if user_worlds[0] is None:
                yield from self.bot.say("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        count = 0
        now = time.time()
        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        yield from self.bot.send_typing(ctx.message.channel)
        try:
            if name is None:
                title = "Latest level ups"
                c.execute("SELECT level, date, name, user_id, world "
                          "FROM char_levelups, chars "
                          "WHERE char_id = id AND level >= ? "
                          "ORDER BY date DESC", (announce_threshold, ))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    user = get_member(self.bot, row["user_id"], guild_list=user_servers)
                    if user is None:
                        continue
                    if row["world"] not in user_worlds:
                        continue
                    count += 1
                    row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
                    row["user"] = user.display_name
                    entries.append("Level **{level}** - {name} (**@{user}**) - *{time} ago*".format(**row))
                    if count >= 100:
                        break
            else:
                c.execute("SELECT id, name, user_id FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is None:
                    yield from self.bot.say("I don't have a character with that name registered.")
                    return
                # If user doesn't share a server with the owner, don't display it
                owner = get_member(self.bot, result["user_id"], guild_list=user_servers)
                if owner is None:
                    yield from self.bot.say("I don't have a character with that name registered.")
                    return
                name = result["name"]
                title = "**{0}** latest level ups:".format(name)
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
            yield from self.bot.say("There are no registered levels.")
            return

        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @levels.command(pass_context=True, name="user")
    @checks.is_not_lite()
    @asyncio.coroutine
    def levels_user(self, ctx, *, name: str = None):
        """Shows an user's recent level ups on his/her registered characters"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("You must tell me an user's name to look for his/her level ups.")
            return

        if ctx.message.channel.is_private:
            user_servers = get_user_servers(self.bot, ctx.message.author.id)
            user_worlds = get_user_worlds(self.bot, ctx.message.author.id)
        else:
            user_servers = [ctx.message.server]
            user_worlds = [tracked_worlds.get(ctx.message.server.id)]
            if user_worlds[0] is None:
                yield from self.bot.say("This server is not tracking any tibia worlds.")
                return

        user = get_member_by_name(self.bot, name, guild_list=user_servers)
        if user is None:
            yield from self.bot.say("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        count = 0
        entries = []
        now = time.time()

        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
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
                entries.append("{name} - Level **{level}** - *{time} ago*".format(**row))
                if count >= 100:
                    break
            if count == 0:
                yield from self.bot.say("There are not registered level ups by this user.")
                return
        finally:
            c.close()

        title = "@{0} latest level ups".format(user.display_name)
        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @commands.group(pass_context=True, aliases=["story"], invoke_without_command=True)
    @checks.is_not_lite()
    @asyncio.coroutine
    def timeline(self, ctx, *, name: str = None):
        """Shows a player's recent level ups and deaths"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if ctx.message.channel.is_private:
            user_servers = get_user_servers(self.bot, ctx.message.author.id)
            user_worlds = get_user_worlds(self.bot, ctx.message.author.id)
        else:
            user_servers = [ctx.message.server]
            user_worlds = [tracked_worlds.get(ctx.message.server.id)]
            if user_worlds[0] is None:
                yield from self.bot.say("This server is not tracking any tibia worlds.")
                return

        c = userDatabase.cursor()
        entries = []
        count = 0
        now = time.time()
        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        yield from self.bot.send_typing(ctx.message.channel)
        try:
            if name is None:
                title = "Timeline"
                c.execute("SELECT name, user_id, world, level, killer, 'death' AS `type`, date "
                          "FROM char_deaths, chars WHERE char_id = id AND level >= ? "
                          "UNION "
                          "SELECT name, user_id, world, level, null, 'levelup' AS `type`, date "
                          "FROM char_levelups, chars WHERE char_id = id AND level >= ? "
                          "ORDER BY date DESC", (announce_threshold, announce_threshold))
                while True:
                    row = c.fetchone()
                    if row is None:
                        break
                    user = get_member(self.bot, row["user_id"], guild_list=user_servers)
                    if user is None:
                        continue
                    if row["world"] not in user_worlds:
                        continue
                    count += 1
                    row["time"] = get_time_diff(timedelta(seconds=now - row["date"]))
                    row["user"] = user.display_name
                    if row["type"] == "death":
                        row["emoji"] = EMOJI[":skull:"]
                        entries.append("{emoji} {name} (**@{user}**) - At level **{level}** by {killer} - *{time} ago*"
                                       .format(**row)
                                       )
                    else:
                        row["emoji"] = EMOJI[":star2:"]
                        entries.append("{emoji} {name} (**@{user}**) - Level **{level}** - *{time} ago*".format(**row))
                    if count >= 200:
                        break
            else:
                c.execute("SELECT id, name, user_id FROM chars WHERE name LIKE ?", (name,))
                result = c.fetchone()
                if result is None:
                    yield from self.bot.say("I don't have a character with that name registered.")
                    return
                # If user doesn't share a server with the owner, don't display it
                owner = get_member(self.bot, result["user_id"], guild_list=user_servers)
                if owner is None:
                    yield from self.bot.say("I don't have a character with that name registered.")
                    return
                name = result["name"]
                title = "**{0}** timeline".format(name)
                c.execute("SELECT name, user_id, world, level, killer, 'death' AS `type`, date "
                          "FROM char_deaths, chars WHERE char_id = id AND level >= ? AND name LIKE ?"
                          "UNION "
                          "SELECT name, user_id, world, level, null, 'levelup' AS `type`, date "
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
            yield from self.bot.say("There are no registered events.")
            return

        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @timeline.command(pass_context=True, name="user")
    @checks.is_not_lite()
    @asyncio.coroutine
    def timeline_user(self, ctx, *, name: str = None):
        """Shows an users's recent level ups and deaths on his/her characters"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("You must tell me an user's name to look for his/her story.")
            return

        if ctx.message.channel.is_private:
            user_servers = get_user_servers(self.bot, ctx.message.author.id)
            user_worlds = get_user_worlds(self.bot, ctx.message.author.id)
        else:
            user_servers = [ctx.message.server]
            user_worlds = [tracked_worlds.get(ctx.message.server.id)]
            if user_worlds[0] is None:
                yield from self.bot.say("This server is not tracking any tibia worlds.")
                return

        user = get_member_by_name(self.bot, name, guild_list=user_servers)
        if user is None:
            yield from self.bot.say("I don't see any users with that name.")
            return

        c = userDatabase.cursor()
        entries = []
        count = 0
        now = time.time()

        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if ctx.message.channel.is_private or ctx.message.channel == ask_channel:
            per_page = 20
        else:
            per_page = 5
        yield from self.bot.send_typing(ctx.message.channel)
        try:
            title = "@{0} timeline".format(user.display_name)
            c.execute("SELECT name, user_id, world, level, killer, 'death' AS `type`, date "
                      "FROM char_deaths, chars WHERE char_id = id AND level >= ? AND user_id = ? "
                      "UNION "
                      "SELECT name, user_id, world, level, null, 'levelup' AS `type`, date "
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
                if row["type"] == "death":
                    row["emoji"] = EMOJI[":skull:"]
                    entries.append("{emoji} {name} - At level **{level}** by {killer} - *{time} ago*"
                                   .format(**row)
                                   )
                else:
                    row["emoji"] = EMOJI[":star2:"]
                    entries.append("{emoji} {name} - Level **{level}** - *{time} ago*".format(**row))
                if count >= 200:
                    break
        finally:
            c.close()

        if count == 0:
            yield from self.bot.say("There are no registered events.")
            return

        pages = Paginator(self.bot, message=ctx.message, entries=entries, per_page=per_page, title=title)
        try:
            yield from pages.paginate()
        except CannotPaginate as e:
            yield from self.bot.say(e)

    @commands.command()
    @asyncio.coroutine
    def stats(self, *, params: str=None):
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
            yield from self.bot.say(invalid_arguments)
            return
        params = params.split(",")
        char = None
        if len(params) == 1:
            _digits = re.compile('\d')
            if _digits.search(params[0]) is not None:
                yield from self.bot.say(invalid_arguments)
                return
            else:
                char = yield from get_character(params[0])
                if char == ERROR_NETWORK:
                    yield from self.bot.say("Sorry, can you try it again?")
                    return
                if char == ERROR_DOESNTEXIST:
                    yield from self.bot.say("Character **{0}** doesn't exist!".format(params[0]))
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
                    yield from self.bot.say(invalid_arguments)
                    return
        else:
            yield from self.bot.say(invalid_arguments)
            return
        stats = get_stats(level, vocation)
        if stats == "low level":
            yield from self.bot.say("Not even *you* can go down so low!")
        elif stats == "high level":
            yield from self.bot.say("Why do you care? You will __**never**__ reach this level "+str(chr(0x1f644)))
        elif stats == "bad vocation":
            yield from self.bot.say("I don't know what vocation that is...")
        elif stats == "bad level":
            yield from self.bot.say("Level needs to be a number!")
        elif isinstance(stats, dict):
            if stats["vocation"] == "no vocation":
                stats["vocation"] = "with no vocation"
            if char:
                pronoun = "he" if char['gender'] == "male" else "she"
                yield from self.bot.say("**{5}** is a level **{0}** {1}, {6} has:"
                                        "\n\t**{2:,}** HP"
                                        "\n\t**{3:,}** MP"
                                        "\n\t**{4:,}** Capacity"
                                        "\n\t**{7:,}** Total experience"
                                        "\n\t**{8:,}** to next level"
                                        .format(level, char["vocation"].lower(), stats["hp"], stats["mp"], stats["cap"],
                                                char['name'], pronoun, stats["exp"], stats["exp_tnl"]))
            else:
                yield from self.bot.say("A level **{0}** {1} has:"
                                        "\n\t**{2:,}** HP"
                                        "\n\t**{3:,}** MP"
                                        "\n\t**{4:,}** Capacity"
                                        "\n\t**{5:,}** Experience"
                                        "\n\t**{6:,}** to next level"
                                        .format(level, stats["vocation"], stats["hp"], stats["mp"], stats["cap"],
                                                stats["exp"], stats["exp_tnl"]))
        else:
            yield from self.bot.say("Are you sure that is correct?")

    @commands.command(aliases=['bless'])
    @asyncio.coroutine
    def blessings(self, level: int = None):
        """Calculates the price of blessings at a specific level"""
        if level is None:
            yield from self.bot.say("I need a level to tell you blessings's prices")
            return
        if level < 1:
            yield from self.bot.say("Very funny... Now tell me a valid level.")
            return
        price = 200 * (level - 20)
        if level <= 30:
            price = 2000
        if level >= 120:
            price = 20000
        inquisition = ""
        if level >= 100:
            inquisition = "\nBlessing of the Inquisition costs **{0:,}** gold coins.".format(int(price*5*1.1))
        yield from self.bot.say(
                "At that level, you will pay **{0:,}** gold coins per blessing for a total of **{1:,}** gold coins.{2}"
                .format(price, price*5, inquisition))

    @commands.command(pass_context=True)
    @asyncio.coroutine
    def spell(self, ctx, *, name: str= None):
        """Tells you information about a certain spell."""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("Tell me the name or words of a spell.")
            return

        spell = get_spell(name)

        if spell is None:
            yield from self.bot.say("I don't know any spell with that name or words.")
            return

        if type(spell) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(spell))
            yield from self.bot.say("I couldn't find that spell, maybe you meant one of these?", embed=embed)
            return

        # Attach item's image only if the bot has permissions
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if permissions.attach_files and spell["image"] != 0:
            filename = spell['name'] + ".png"
            while os.path.isfile(filename):
                filename = "_" + filename
            with open(filename, "w+b") as f:
                f.write(bytearray(spell['image']))
                f.close()

            with open(filename, "r+b") as f:
                yield from self.bot.upload(f)
                f.close()
            os.remove(filename)
        long = ctx.message.channel.is_private or ctx.message.channel.name == ask_channel_name
        embed = self.get_spell_embed(ctx, spell, long)
        yield from self.bot.say(embed=embed)

    @commands.command(pass_context=True, aliases=["houses", "guildhall", "gh"])
    @asyncio.coroutine
    def house(self, ctx, *, name: str=None):
        """Shows info for a house or guildhall"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("Tell me the name of the house or guildhall you want to check.")
            return
        world = None
        if ctx.message.server is not None:
            world = tracked_worlds.get(ctx.message.server.id)

        house = yield from get_house(name, world)
        if house is None:
            yield from self.bot.say("I couldn't find a house with that name.")
            return

        if type(house) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(house))
            yield from self.bot.say("I couldn't find that house, maybe you meant one of these?", embed=embed)
            return

        # Attach image only if the bot has permissions
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if permissions.attach_files:
            filename = house['name'] + ".png"
            while os.path.isfile(filename):
                filename = "_" + filename
            with open(filename, "w+b") as f:
                image = get_map_area(house["x"], house["y"], house["z"])
                f.write(bytearray(image))
                f.close()
            # Send image
            with open(filename, "r+b") as f:
                yield from self.bot.upload(f)
                f.close()
            os.remove(filename)
        yield from self.bot.say(embed=self.get_house_embed(house))

    @commands.command(pass_context=True, aliases=["achiev"])
    @asyncio.coroutine
    def achievement(self, ctx, *, name: str=None):
        """Shows an achievement's information

        Spoilers are only shown on ask channel and private messages"""
        permissions = ctx.message.channel.permissions_for(get_member(self.bot, self.bot.user.id, ctx.message.server))
        if not permissions.embed_links:
            yield from self.bot.say("Sorry, I need `Embed Links` permission for this command.")
            return

        if name is None:
            yield from self.bot.say("Tell me the name of the achievement you want to check.")
            return
        achievement = get_achievement(name)

        if type(achievement) is list:
            embed = discord.Embed(title="Suggestions", description="\n".join(achievement))
            yield from self.bot.say("I couldn't find that house, maybe you meant one of these?", embed=embed)
            return

        ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
        if not (ask_channel == ctx.message.channel or ctx.message.channel.is_private):
            achievement["spoiler"] = "*To see spoilers, pm me"
            if ask_channel is not None:
                achievement["spoiler"] += " or use "+ask_channel.mention
            achievement["spoiler"] += ".*"

        embed = discord.Embed(title=achievement["name"], description=achievement["description"])
        embed.add_field(name="Grade", value=EMOJI[":star:"]*int(achievement["grade"]))
        embed.add_field(name="Points", value=achievement["points"])
        embed.add_field(name="Spoiler", value=achievement["spoiler"], inline=True)

        yield from self.bot.say(embed=embed)

    @commands.command(aliases=['serversave','ss'])
    @asyncio.coroutine
    def time(self):
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
        yield from self.bot.say(reply)

    @staticmethod
    def get_char_string(char) -> str:
        """Returns a formatted string containing a character's info."""
        if char == ERROR_NETWORK or char == ERROR_DOESNTEXIST:
            return char
        pronoun = "He"
        pronoun2 = "His"
        if char['gender'] == "female":
            pronoun = "She"
            pronoun2 = "Her"
        url = url_character + urllib.parse.quote(char["name"].encode('iso-8859-1'))
        reply_format = "[{1}]({9}) is a level {2} __{3}__. {0} resides in __{4}__ in the world __{5}__.{6}{7}{8}{10}"
        guild_format = "\n{0} is __{1}__ of the [{2}]({3})."
        married_format = "\n{0} is married to [{1}]({2})."
        login_format = "\n{0} hasn't logged in for **{1}**."
        house_format = "\n{0} owns [{1}]({2}) in {3}."
        guild = ""
        married = ""
        house = ""
        login = "\n{0} has **never** logged in.".format(pronoun)
        if "guild" in char:
            guild_url = url_guild+urllib.parse.quote(char["guild"])
            guild = guild_format.format(pronoun, char['rank'], char['guild'], guild_url)
        if "married" in char:
            married_url = url_character + urllib.parse.quote(char["married"].encode('iso-8859-1'))
            married = married_format.format(pronoun, char['married'], married_url)
        if "house" in char:
            house_url = url_house.format(id=char["house_id"], world=char["world"])
            house = house_format.format(pronoun, char["house"], house_url, char["house_town"])
        if char['last_login'] is not None:
            last_login = parse_tibia_time(char['last_login'])
            now = datetime.now()
            time_diff = now - last_login
            if time_diff.days > last_login_days:
                login = login_format.format(pronoun, get_time_diff(time_diff))
            else:
                login = ""

        reply = reply_format.format(pronoun, char['name'], char['level'], char['vocation'], char['residence'],
                                    char['world'], guild, married, login, url, house)
        if lite_mode:
            return reply
        # Insert any highscores this character holds
        for category in highscores_categories:
            if char.get(category, None):
                highscore_string = highscore_format[category].format(pronoun2, char[category], char[category+'_rank'])
                reply += "\n"+EMOJI[":trophy:"]+" {0}".format(highscore_string)
        return reply

    def get_user_string(self, ctx, username: str) -> str:
        user = get_member_by_name(self.bot, username, ctx.message.server)
        if user is None:
            return ERROR_DOESNTEXIST
        # List of servers the user shares with the bot
        user_servers = get_user_servers(self.bot, user.id)
        # List of Tibia worlds tracked in the servers the user is
        if ctx.message.channel.is_private:
            user_tibia_worlds = [world for server, world in tracked_worlds.items() if
                                 server in [s.id for s in user_servers]]
        else:
            if tracked_worlds.get(ctx.message.server.id) is None:
                user_tibia_worlds = []
            else:
                user_tibia_worlds = [tracked_worlds[ctx.message.server.id]]
        # If server tracks no worlds, do not display owned chars
        if len(user_tibia_worlds) == 0:
            return "I don't know who @**{0.display_name}** is...".format(user)

        placeholders = ", ".join("?" for w in user_tibia_worlds)

        c = userDatabase.cursor()
        try:
            c.execute("SELECT name, ABS(last_level) as level, vocation "
                      "FROM chars "
                      "WHERE user_id = {0} AND world IN ({1}) ORDER BY level DESC".format(user.id, placeholders),
                      tuple(user_tibia_worlds))
            result = c.fetchall()
            if result:
                charList = []
                online_list = [x.split("_", 1)[1] for x in global_online_list]
                for character in result:
                    character["online"] = ""
                    if character["name"] in online_list:
                        character["online"] = EMOJI[":small_blue_diamond:"]
                    try:
                        character["level"] = int(character["level"])
                    except ValueError:
                        character["level"] = ""
                    character["vocation"] = get_voc_abb(character["vocation"])
                    character["url"] = url_character + urllib.parse.quote(character["name"].encode('iso-8859-1'))
                    charList.append("[{name}]({url}){online} (Lvl {level} {vocation})".format(**character))

                char_string = "@**{0.display_name}**'s character{1}: {2}"
                plural = "s are" if len(charList) > 1 else " is"
                reply = char_string.format(user, plural, join_list(charList, ", ", " and "))
            else:
                reply = "I don't know who @**{0.display_name}** is...".format(user)
            return reply
        finally:
            c.close()

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
            ask_channel = get_channel_by_name(ctx.bot, ask_channel_name, ctx.message.server)
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
            ask_channel = get_channel_by_name(ctx.bot, ask_channel_name, ctx.message.server)
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
            if house["status"] == "rented":
                house["owner_url"] = get_character_url(house["owner"])
                description += "\nIn **{world}**, this {type} is rented by [{owner}]({owner_url}).".format(**house)
            elif house["status"] == "transferred":
                house["owner_url"] = get_character_url(house["owner"])
                house["transferee_url"] = get_character_url(house["transferee"])
                description += "\nIn **{world}**, this {type} is rented by [{owner}]({owner_url}).\n" \
                               "It will be transferred to [{transferee}]({transferee_url}) for **{transfer_price:,}** " \
                               "gold on **{transfer_date}**".format(**house)

            elif house["status"] == "empty":
                description += "\nIn **{world}**, this {type} is unoccupied.".format(**house)
            elif house["status"] == "auctioned":
                house["bidder_url"] = get_character_url(house["top_bidder"])
                description += "\nIn **{world}**, this {type} is being auctioned. " \
                               "The top bid is **{top_bid:,}** gold, by [{top_bidder}]({bidder_url}).\n" \
                               "The auction ends at **{auction_end}**".format(**house)

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
                      "It uses **{manacost:,}** mana. It can be used by {vocs}".format(**spell)

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
            ask_channel = get_channel_by_name(ctx.bot, ask_channel_name, ctx.message.server)
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
