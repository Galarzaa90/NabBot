import os
import random

from PIL import Image
from discord.ext import commands
import discord

from config import *
from loot import loot_scan
from utils.database import userDatabase
from utils.general import is_numeric, get_time_diff, join_list, get_brasilia_time_zone
from utils.messages import EMOJI
from utils.discord import get_member_by_name, get_user_color, get_member, get_channel_by_name
from utils.tibia import *

import requests
import io
from loot import *

# Commands
class Tibia:
    """Tibia related commands."""
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.parsing_count = 0

    @commands.group(pass_context=True, invoke_without_command=True)
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
    @asyncio.coroutine
    def loot_legend(self):
        """Shows the meaning of the overlayed icons."""
        with open("loot/images/legend.png", "r+b") as f:
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

        if name.lower() == self.bot.user.name.lower():
            yield from ctx.invoke(self.bot.commands.get('about'))
            return

        char = yield from get_character(name)
        char_string = self.get_char_string(char)
        user = get_member_by_name(self.bot, name)
        user_string = self.get_user_string(name)
        embed = discord.Embed()
        embed.description = ""

        # No user or char with that name
        if char == ERROR_DOESNTEXIST and user is None:
            yield from self.bot.say("I don't see any user or character with that name.")
            return
        # We found an user
        if user is not None:
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
                    embed.description += "\n\nThe character "+char_string
                    yield from self.bot.say(embed=embed)
                    return
                # Not owned by same user, we display a separate embed
                else:
                    char_embed = discord.Embed(description=char_string)
                    char_embed.set_author(name=char["name"],
                                          url=url_character+urllib.parse.quote(char["name"]),
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
                                 url=url_character + urllib.parse.quote(char["name"]),
                                 icon_url="http://static.tibia.com/images/global/general/favicon.ico"
                                 )
                # Char is owned by a discord user
                owner = get_member(self.bot, char["owner_id"])
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

    @commands.command(name="find", aliases=["whereteam", "team", "findteam", "searchteam", "search"], hidden=lite_mode,
                      pass_context=True)
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
        if lite_mode:
            return

        invalid_arguments = "Invalid arguments used, examples:\n" \
                            "```/find vocation,charname\n" \
                            "/find vocation,level\n" \
                            "/find vocation,minlevel,maxlevel```"
        if params is None:
            yield from self.bot.say(invalid_arguments)
            return

        result_limit = 10
        ask_channel_limit = 25
        too_long = False
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
            found = "I found the following {0}s in share range with **{1}** ({2}-{3}):".format(vocation, char["name"],
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
                found = "I found the following {0}s between levels **{1}** and **{2}**:".format(vocation, low, high)
                empty = "I didn't find any {0}s between levels **{1}** and **{2}**".format(vocation, low, high)
            # We only got a level, so we get the share range for it
            else:
                if int(params[1]) <= 0:
                    yield from self.bot.say("You entered an invalid level.")
                    return
                low, high = get_share_range(int(params[1]))
                found = "I found the following {0}s in share range with level **{1}** ({2}-{3}):".format(vocation,
                                                                                                         params[1],
                                                                                                         low, high)
                empty = "I didn't find any {0}s in share range with level **{1}** ({2}-{3})".format(vocation,
                                                                                                    params[1],
                                                                                                    low, high)

        c = userDatabase.cursor()
        try:
            c.execute("SELECT name, user_id, ABS(last_level) as level FROM chars "
                      "WHERE vocation LIKE ? AND level >= ? AND level <= ? "
                      "ORDER by level DESC", ("%"+vocation, low, high))
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
                player["online"] = EMOJI[":small_blue_diamond:"] if player["name"] in online_list else ""
                if count <= result_limit or (count <= ask_channel_limit and ctx.message.channel.name == ask_channel_name):
                    found += "\n\t**{name}** - Level {level} - @**{owner}** {online}".format(**player)
                else:
                    # Check if there's at least one more to suggest using askchannel
                    if c.fetchone() is not None:
                        too_long = True
                    break
            if count < 1:
                yield from self.bot.say(empty)
                return
            ask_channel = get_channel_by_name(self.bot, ask_channel_name, ctx.message.server)
            if ask_channel is not None and too_long:
                found += "\nYou can see more results in " + ask_channel.mention
            yield from self.bot.say(found)
        finally:
            c.close()

    @commands.command(aliases=['guildcheck', 'checkguild'])
    @asyncio.coroutine
    def guild(self, *, name=None):
        """Checks who is online in a guild"""
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
        embed.set_thumbnail(url=guild["logo_url"])
        if len(guild['members']) < 1:
            embed.description = "Nobody is online."
            yield from self.bot.say(embed=embed)
            return

        plural = ""
        if len(guild['members']) > 1:
            plural = "s"
        embed.description = "It has {0} player{1} online:".format(len(guild['members']), plural)
        current_field = ""
        result = ""
        for member in guild['members']:
            if current_field == "":
                current_field = member['rank']
            elif member['rank'] != current_field and member["rank"] != "":
                embed.add_field(name=current_field, value=result, inline=False)
                result = ""
                current_field = member['rank']

            member["title"] = ' (' + member['title'] + ')' if member['title'] != '' else ''
            member["vocation"] = get_voc_abb(member["vocation"])

            result += "{name} {title} -- {level} {vocation}\n".format(**member)
        embed.add_field(name=current_field, value=result, inline=False)
        yield from self.bot.say(embed=embed)

    @commands.command(pass_context=True, aliases=['checkprice', 'item'])
    @asyncio.coroutine
    def itemprice(self, ctx, *, name: str=None):
        """Checks an item's information

        Shows name, picture, npcs that buy and sell and creature drops"""
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
        if permissions.attach_files:
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
        embed, embed_drops = self.get_item_embeds(item, long)
        yield from self.bot.say(embed=embed)
        if embed_drops is not None:
            yield from self.bot.say(embed=embed_drops)
        return

    @commands.command(pass_context=True, aliases=['mon', 'mob', 'creature'])
    @asyncio.coroutine
    def monster(self, ctx, *, name: str=None):
        """Gives information about a monster"""
        if name is None:
            yield from self.bot.say("Tell me the name of the monster you want to search.")
            return
        if name.lower() == self.bot.user.name.lower():
            yield from self.bot.say(random.choice(["**"+self.bot.user.name+"** is too strong for you to hunt!",
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
        if permissions.attach_files:
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
        embed, loot_embed = self.get_monster_embeds(monster, long)

        yield from self.bot.say(embed=embed)
        if loot_embed is not None:
            yield from self.bot.say(embed=loot_embed)

    @commands.command(aliases=['deathlist', 'death'])
    @asyncio.coroutine
    def deaths(self, *, name: str=None):
        """Shows a player's or everyone's recent deaths"""
        if name is None and lite_mode:
            return
        if name is None:
            c = userDatabase.cursor()
            try:
                c.execute("SELECT level, date, name, user_id, byplayer, killer "
                          "FROM char_deaths, chars "
                          "WHERE char_id = id "
                          "ORDER BY date DESC LIMIT 15")
                result = c.fetchall()
                if len(result) < 1:
                    yield from self.bot.say("No one has died recently")
                    return
                now = time.time()
                reply = "Latest deaths:"
                for death in result:
                    timediff = timedelta(seconds=now-death["date"])
                    died = "Killed" if death["byplayer"] else "Died"
                    user = get_member(self.bot, death["user_id"])
                    username = "unknown"
                    if user:
                        username = user.display_name
                    reply += "\n\t{4} (**@{5}**) - {0} at level **{1}** by {2} - *{3} ago*".format(died, death["level"], death["killer"], get_time_diff(timediff), death["name"], username)
                yield from self.bot.say(reply)
                return
            finally:
                c.close()
        if name.lower() == "nab bot":
            yield from self.bot.say("**Nab Bot** never dies.")
            return
        deaths = yield from get_character_deaths(name)
        if deaths == ERROR_DOESNTEXIST:
            yield from self.bot.say("That character doesn't exist!")
            return
        if deaths == ERROR_NETWORK:
            yield from self.bot.say("Sorry, try it again, I'll do it right this time.")
            return
        if len(deaths) == 0:
            yield from self.bot.say(name.title()+" hasn't died recently.")
            return
        tooMany = False
        if len(deaths) > 15:
            tooMany = True
            deaths = deaths[:15]

        reply = name.title()+" recent deaths:"

        for death in deaths:
            diff = get_time_diff(datetime.now() - get_local_time(death['time']))
            died = "Killed" if death['byPlayer'] else "Died"
            reply += "\n\t{0} at level **{1}** by {2} - *{3} ago*".format(died, death['level'], death['killer'], diff)
        if tooMany:
            reply += "\n*This person dies too much, I can't show you all the deaths!*"

        yield from self.bot.say(reply)

    @commands.command(pass_context=True, aliases=['levelups', 'lvl', 'level', 'lvls'], hidden=lite_mode)
    @asyncio.coroutine
    def levels(self, ctx, *, name: str=None):
        """Shows a player's or everoyne's recent level ups

        This only works for characters registered in the bots database, which are the characters owned
        by the users of this discord server."""
        if lite_mode:
            return
        c = userDatabase.cursor()
        limit = 10
        if ctx.message.channel.is_private or ctx.message.channel.name == ask_channel_name:
            limit = 20
        try:
            if name is None:
                c.execute("SELECT level, date, name, user_id "
                          "FROM char_levelups, chars "
                          "WHERE char_id = id AND level >= ? "
                          "ORDER BY date DESC LIMIT ?", (announceTreshold, limit,))
                result = c.fetchall()
                if len(result) < 1:
                    yield from self.bot.say("No one has leveled up recently")
                    return
                now = time.time()
                reply = "Latest level ups:"
                for levelup in result:
                    timediff = timedelta(seconds=now-levelup["date"])
                    user = get_member(self.bot, levelup["user_id"])
                    username = "unkown"
                    if user:
                        username = user.display_name
                    reply += "\n\tLevel **{0}** - {2} (**@{3}**) - *{1} ago*".format(levelup["level"], get_time_diff(timediff), levelup["name"], username)
                if site_Enabled:
                    reply += "\nSee more levels check: <{0}{1}>".format(baseUrl, levelsPage)
                yield from self.bot.say(reply)
                return
            # Checking if character exists in db and get id while we're at it
            c.execute("SELECT id, name FROM chars WHERE name LIKE ?", (name,))
            result = c.fetchone()
            if result is None:
                yield from self.bot.say("I don't have a character with that name registered.")
                return
            # Getting correct capitalization
            name = result["name"]
            id = result["id"]
            c.execute("SELECT level, date FROM char_levelups WHERE char_id = ? ORDER BY date DESC LIMIT ?", (id, limit,))
            result = c.fetchall()
            # Checking number of level ups
            if len(result) < 1:
                yield from self.bot.say("I haven't seen **{0}** level up.".format(name))
                return
            now = time.time()
            reply = "**{0}** latest level ups:".format(name)
            for levelup in result:
                timediff = timedelta(seconds=now-levelup["date"])
                reply += "\n\tLevel **{0}** - *{1} ago*".format(levelup["level"], get_time_diff(timediff))

            reply += "\nSee more levels at: <{0}{1}?name={2}>".format(baseUrl, charactersPage, urllib.parse.quote(name))
            yield from self.bot.say(reply)
        finally:
            c.close()

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
                yield from self.bot.say("**{5}** is a level **{0}** {1}, {6} has:\n\t**{2:,}** HP\n\t**{3:,}** MP\n\t**{4:,}** Capacity".format(level, char["vocation"].lower(), stats["hp"], stats["mp"], stats["cap"], char['name'], pronoun))
            else:
                yield from self.bot.say("A level **{0}** {1} has:\n\t**{2:,}** HP\n\t**{3:,}** MP\n\t**{4:,}** Capacity".format(level, stats["vocation"], stats["hp"], stats["mp"], stats["cap"]))
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

    @commands.command()
    @asyncio.coroutine
    def spell(self, *, name: str= None):
        """Tells you information about a certain spell."""
        if name is None:
            yield from self.bot.say("Tell me the name or words of a spell.")
        spell = get_spell(name)
        if spell is None:
            yield from self.bot.say("I don't know any spell with that name or words.")
            return
        mana = spell["manacost"]
        if mana < 0:
            mana = "variable"
        words = spell["words"]
        if "exani hur" in words:
            words = "exani hur up/down"
        vocs = list()
        if spell['knight']: vocs.append("knights")
        if spell['paladin']: vocs.append("paladins")
        if spell['druid']: vocs.append("druids")
        if spell['sorcerer']: vocs.append("sorcerers")
        voc = join_list(vocs, ", ", " and ")
        reply = "**{0}** (*{1}*) is a {2}spell for level **{3}** and up. It uses **{4}** mana."
        reply = reply.format(spell["name"], words, "premium " if spell["premium"] else "",
                            spell["levelrequired"], mana)
        reply += " It can be used by {0}.".format(voc)
        if spell["goldcost"] == 0:
            reply += "\nIt can be obtained for free."
        else:
            reply += "\nIt can be bought for {0:,} gold coins.".format(spell["goldcost"])
        # Todo: Show which NPCs sell the spell
        """if(len(spell['npcs']) > 0):
            for npc in spell['npcs']:
                vocs = list()
                if(npc['knight']): vocs.append("knights")
                if(npc['paladin']): vocs.append("paladins")
                if(npc['druid']): vocs.append("druids")
                if(npc['sorcerer']): vocs.append("sorcerers")
                voc = ", ".join(vocs)
                print("{0} ({1}) - {2}".format(npc['name'],npc['city'],voc))"""
        yield from self.bot.say(reply)

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
        if char['gender'] == "female":
            pronoun = "She"
        url = url_character + urllib.parse.quote(char["name"])
        reply_format = "[{1}]({9}) is a level {2} __{3}__. {0} resides in __{4}__ in the world __{5}__.{6}{7}{8}"
        guild_format = "\n{0} is __{1}__ of the [{2}]({3})."
        married_format = "\n{0} is married to [{1}]({2})."
        login_format = "\n{0} hasn't logged in for **{1}**."
        guild = ""
        married = ""
        login = "\n{0} has **never** logged in.".format(pronoun)
        if char.get('guild', None):
            guild_url = url_guild+urllib.parse.quote(char["guild"])
            guild = guild_format.format(pronoun, char['rank'], char['guild'], guild_url)
        if char.get('married', None):
            married_url = url_character + urllib.parse.quote(char["married"])
            married = married_format.format(pronoun, char['married'], married_url)

        if char['last_login'] is not None:
            last_login = get_local_time(char['last_login'])
            now = datetime.now()
            time_diff = now - last_login
            if time_diff.days > last_login_days:
                login = login_format.format(pronoun, get_time_diff(time_diff))
            else:
                login = ""

        reply = reply_format.format(pronoun, char['name'], char['level'], char['vocation'], char['residence'],
                                    char['world'], guild, married, login, url)
        return reply

    def get_user_string(self, username: str) -> str:
        user = get_member_by_name(self.bot, username)
        c = userDatabase.cursor()
        if user is None:
            return ERROR_DOESNTEXIST
        try:
            c.execute("SELECT name, ABS(last_level) as level, vocation FROM chars WHERE user_id = ? ORDER BY level DESC",
                      (user.id,))
            result = c.fetchall()
            if result:
                charList = []
                for character in result:
                    try:
                        character["level"] = int(character["level"])
                    except ValueError:
                        character["level"] = ""
                    character["vocation"] = get_voc_abb(character["vocation"])
                    character["url"] = url_character + urllib.parse.quote(character["name"])
                    charList.append("[{name}]({url}) (Lvl {level} {vocation})".format(**character))

                charString = "@**{0.display_name}**'s character{1}: {2}"
                plural = "s are" if len(charList) > 1 else " is"
                reply = charString.format(user, plural, join_list(charList, ", ", " and "))
            else:
                reply = "I don't know who @**{0.display_name}** is...".format(user)
            return reply
        finally:
            c.close()

    @staticmethod
    def get_monster_embeds(monster, long):
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
        embed_loot = None
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
            embed_loot = discord.Embed(title="Loot",description="`"+loot_string+"`")
        if monster["loot"] and not long:
            askchannel_string = " or use #" + ask_channel_name if ask_channel_name is not None else ""
            # Using character U+200F as an invisible space, normal space gets stripped and empty values are not allowed.
            embed.add_field(name="To see more, PM me{0}.".format(askchannel_string), value="\U0000200F", inline=False)
        return embed, embed_loot

    @staticmethod
    def get_item_embeds(item, long):
        """Gets the item embeds to show in /item command
        The message is split in two embeds, the second contains monster drops only and is only shown if long is True"""
        short_limit = 5
        long_limit = 40
        npcs_too_long = False
        drops_too_long = False

        embed = discord.Embed(title=item["title"], description=item["look_text"])
        embed_drops = None
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

        if len(item["dropped_by"]):
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

            if long:
                embed_drops = discord.Embed(title=name, description=value)
                if "color" in item:
                    embed_drops.colour = item["color"]
            else:
                embed.add_field(name=name, value=value)

        if npcs_too_long or drops_too_long:
            askchannel_string = " or use #" + ask_channel_name if ask_channel_name is not None else ""
            # Using character U+200F as an invisible space, normal space gets stripped and empty values are not allowed.
            embed.add_field(name="To see more, PM me{0}.".format(askchannel_string), value="\U0000200F", inline=False)
        return embed, embed_drops


def setup(bot):
    bot.add_cog(Tibia(bot))

if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
