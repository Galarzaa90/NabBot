import asyncio
import io
import os
import pickle
from contextlib import closing

import aiohttp
import discord
from PIL import Image
from discord.ext import commands

from config import *
from nabbot import NabBot
from utils import checks
from utils.database import tibiaDatabase, lootDatabase
from utils.discord import FIELD_VALUE_LIMIT, is_private
from utils.messages import EMOJI, split_message
from utils.tibiawiki import get_item

slot = Image.open("./images/slot.png")
slot_border = Image.open("./images/slotborder.png").convert("RGBA").getdata()
numbers = [Image.open("./images/0.png"),
           Image.open("./images/1.png"),
           Image.open("./images/2.png"),
           Image.open("./images/3.png"),
           Image.open("./images/4.png"),
           Image.open("./images/5.png"),
           Image.open("./images/6.png"),
           Image.open("./images/7.png"),
           Image.open("./images/8.png"),
           Image.open("./images/9.png")]


class Loot:
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.parsing_count = 0

    @commands.group(invoke_without_command=True)
    @checks.is_not_lite()
    async def loot(self, ctx):
        """Scans a loot image and returns it's loot value

        The bot will return a list of the items found along with their values, grouped by NPC.
        If the image is compressed or was taken using Tibia's software render, the bot might struggle finding matches."""
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
        file_name = attachment.url.split("/")[len(attachment.url.split("/")) - 1]
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
        progress_bar = await ctx.send(EMOJI[":black_large_square:"] * 10)

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
                            c.execute("SELECT name FROM items, items_attributes "
                                      "WHERE name LIKE ? AND id = item_id AND attribute = 'imbuement'"
                                      " LIMIT 1", (item,))
                            result = c.fetchone()
                        if result:
                            has_marketable = True
                            emoji = EMOJI[":gem:"]
                        else:
                            emoji = ""
                        value += "x{1} {0}{3} \u2192 {2:,}gp total.\n".format(
                            item,
                            loot_list[item]['count'],
                            loot_list[item]['count'] * loot_list[item]['value'],
                            emoji)

                    total_value += loot_list[item]['count'] * loot_list[item]['value']
                    group_value += loot_list[item]['count'] * loot_list[item]['value']
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
    @checks.is_owner()
    @checks.is_not_lite()
    async def loot_show(self, ctx, *, item=None):
        """Shows item info from loot database."""
        result, item = await item_show(item)
        if result is None:
            await ctx.send("There's no item with that name.")
            return
        await ctx.send("Name: {name}, Group: {group}, Priority: {priority}, Value: {value:,}".format(**item),
                       file=discord.File(result, "results.png"))

    @loot.command(name="add")
    @checks.is_owner()
    @checks.is_not_lite()
    async def loot_add(self, ctx, *, item=None):
        """Adds an image to an existing loot item in the database."""
        if len(ctx.message.attachments) == 0:
            await ctx.send("You need to upload the image you want to add to this item.")
            return

        attachment = ctx.message.attachments[0]
        if attachment.width != 32 or attachment.height != 32:
            await ctx.send("Image size has to be 32x32.")
            return

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
            await ctx.send("Image added to item.", file=discord.File(result, "results.png"))
            result, item = await item_show(item)
            if result is not None:
                await ctx.send("Name: {name}, Group: {group}, Priority: {priority}, Value: {value:,}".format(**item),
                               file=discord.File(result, "results.png"))
            return

    @loot.command(name="remove", aliases=["delete", "del"])
    @checks.is_owner()
    @checks.is_not_lite()
    async def loot_remove(self, ctx, *, item=None):
        """Adds an image to an existing loot item in the database."""
        result = await item_remove(item)
        if result is None:
            await ctx.send("Couldn't find an item with that name.")
            return
        else:
            await ctx.send("Item \""+result+"\" removed from loot database.")
            return

    @loot.command(name="new")
    @checks.is_owner()
    @checks.is_not_lite()
    async def loot_new(self, ctx, *, params=None):
        """Adds a new item to the loot database."""
        if len(ctx.message.attachments) == 0:
            await ctx.send("You need to upload the image you want to add to this item.")
            return
        if params is None:
            await ctx.send("Missing parameters (item name,group)")
            return
        params = params.split(",")
        if not len(params) == 2:
            await ctx.send("Wrong parameters (item name,group)")
            return
        item, group = params
        item = get_item(item)
        if item is None or type(item) is list:
            await ctx.send("No item found with that name.")
            return
        if item["value_sell"] is None:
            item["value_sell"] = 0

        attachment = ctx.message.attachments[0]
        if attachment.width != 32 or attachment.height != 32:
            await ctx.send("Image size has to be 32x32.")
            return

        try:
            with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    original_image = await resp.read()
            frame_image = Image.open(io.BytesIO(bytearray(original_image))).convert("RGBA")
        except Exception:
            await ctx.send("Either that wasn't an image or I failed to load it, please try again.")
            return

        result = await item_new(item['title'], frame_image, group, item['value_sell'])
        if result is None:
            await ctx.send("Could not add new item.")
            return
        else:
            await ctx.send("Image added to item.", file=discord.File(result, "results.png"))
            result, item = await item_show(item['title'])
            if result is not None:
                await ctx.send("Name: {name}, Group: {group}, Priority: {priority}, Value: {value}".format(**item),
                               file=discord.File(result, "results.png"))
            return

    @loot.command(name="update")
    @checks.is_owner()
    @checks.is_not_lite()
    async def loot_update(self, ctx, *, item=None):
        """Shows item info from loot database."""
        result = await loot_db_update()
        if result is not None:
            await ctx.send("Added "+str(result)+" items to loot database, check debugimages folder for more info.")
        else:
            await ctx.send("No new items found in tibia_database.")
        return

    @loot.command(name="legend", aliases=["help", "symbols", "symbol"])
    @checks.is_not_lite()
    async def loot_legend(self, ctx):
        """Shows the meaning of the overlayed icons."""
        with open("./images/legend.png", "r+b") as f:
            await ctx.send(file=discord.File(f))
            f.close()


def is_transparent(pixel):
    if len(pixel) < 4:
        return False
    return pixel[3] == 0


def is_number(pixel):
    return is_transparent(pixel) and pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 0


def is_white(pixel):
    return pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 255


def is_background_color(pixel, quality):
    low = max(0, 22 - quality * 2)
    high = min(80, 60 + quality)
    colordiff = min(15, 8 + quality)
    return (pixel[0] >= low and pixel[1] >= low and pixel[2] >= low) \
           and (pixel[0] <= high and pixel[1] <= high and pixel[2] <= high) \
           and max(abs(pixel[0] - pixel[1]), abs(pixel[0] - pixel[2]), abs(pixel[1] - pixel[2])) < colordiff


def is_empty(pixel):
    return is_white(pixel) or is_transparent(pixel) or is_number(pixel)


def pixel_diff(pixel1, pixel2):
    return abs(pixel1[0] - pixel2[0]) + abs(pixel1[1] - pixel2[1]) + abs(pixel1[2] - pixel2[2])


def crop_item(item_image):
    if item_image is None:
        return item_image, [0, 0]
    # Top
    offsety = 0
    px = 0
    py = 0
    while py < item_image.size[1]:
        item_image_pixel = item_image.getpixel((px, py))
        if not (is_empty(item_image_pixel)):
            offsety = py
            break
        px += 1
        if px == item_image.size[0]:
            py += 1
            px = 0

    # Bottom
    offsety2 = -1
    px = item_image.size[0] - 1
    py = item_image.size[1] - 1
    while py > 0:
        item_image_pixel = item_image.getpixel((px, py))
        if not (is_empty(item_image_pixel)):
            offsety2 = py
            break
        px -= 1
        if px == 0:
            py -= 1
            px = item_image.size[0] - 1

    # Left
    offsetx = 0
    px = 0
    py = 0
    while px < item_image.size[0]:
        item_image_pixel = item_image.getpixel((px, py))
        if not (is_empty(item_image_pixel)):
            offsetx = px
            break
        py += 1
        if py == item_image.size[1]:
            px += 1
            py = 0
    # Right
    offsetx2 = -1
    px = item_image.size[0] - 1
    py = item_image.size[1] - 1
    while px > 0:
        item_image_pixel = item_image.getpixel((px, py))
        if not (is_empty(item_image_pixel)):
            offsetx2 = px
            break
        py -= 1
        if py == 0:
            px -= 1
            py = item_image.size[1] - 1
    if offsetx2 == -1 or offsety2 == -1:
        return None, [0, 0]
    item_image = item_image.crop((offsetx, offsety, offsetx2 + 1, offsety2 + 1))
    return item_image


def number_scan(item_image):
    number1 = item_image.crop((8, 21, 8 + 8, 21 + 10))
    number2 = item_image.crop((16, 21, 16 + 8, 21 + 10))
    number3 = item_image.crop((24, 21, 24 + 8, 21 + 10))
    item_numbers_image = item_image.crop((8, 21, 8 + 8 * 3, 21 + 10))
    item_numbers = [number1, number2, number3]
    number_string = ""
    numbers_image = Image.new("RGBA", (24, 10), (255, 255, 255, 0))
    a = 0
    for item_number in item_numbers:
        i = 0
        for number in numbers:
            px = 0
            py = 0
            while py < item_number.size[1] and py < number.size[1]:
                item_number_pixel = item_number.getpixel((px, py))
                number_pixel = number.getpixel((px, py))
                if not is_transparent(number_pixel):
                    if not pixel_diff(item_number_pixel, number_pixel) == 0:
                        break
                px += 1
                if px == item_number.size[0] or px == number.size[0]:
                    py += 1
                    px = 0
                if py == item_number.size[1]:
                    number_string += str(i)
                    numbers_image.paste(number, (8 * a, 0))
                    i = -1
                    break
            if i == -1:
                break
            i += 1
        a += 1
    px = 0
    py = 0
    while py < numbers_image.size[1]:
        numbers_image_pixel = numbers_image.getpixel((px, py))
        if not is_transparent(numbers_image_pixel):
            item_image.putpixel((px + 8, py + 21), (255, 255, 0, 0))
        px += 1
        if px == numbers_image.size[0]:
            py += 1
            px = 0
    return 1 if number_string == "" else int(number_string), item_image, numbers_image


def clear_background(slot_item, quality=0):
    px = 0
    py = 0
    while py < slot_item.size[1] and py < slot.size[1]:
        slot_item_pixel = slot_item.getpixel((px, py))
        slot_pixel = slot.getpixel((px + 1 + (32 - slot_item.size[0]), py + 1 + (32 - slot_item.size[1])))
        if pixel_diff(slot_item_pixel, slot_pixel) <= quality:
            slot_item.putpixel((px, py), (slot_item_pixel[0], slot_item_pixel[1], slot_item_pixel[2], 0))
        px += 1
        if px == slot_item.size[0] or px == slot.size[0]:
            py += 1
            px = 0
    return slot_item


def get_item_size(item):
    size = item.size[0] * item.size[1]
    empty = 0
    px = 0
    py = 0
    while py < item.size[1]:
        item_pixel = item.getpixel((px, py))
        if not is_empty(item_pixel):
            size -= empty
            empty = 0
            px = 0
            py += 1
        else:
            empty += 1
            px += 1
            if px == item.size[0]:
                size -= empty - 1
                empty = 0
                px = 0
                py += 1

    empty = 0
    px = item.size[0] - 1
    py = 0
    while py < item.size[1]:
        item_pixel = item.getpixel((px, py))
        if not is_empty(item_pixel):
            size -= empty
            empty = 0
            px = item.size[0] - 1
            py += 1
        else:
            empty += 1
            px -= 1
            if px == -1:
                empty = 0
                px = item.size[0] - 1
                py += 1
    return size


def get_item_color(item):
    count = 0
    px = 0
    py = 0
    color = [0, 0, 0]
    while py < item.size[1]:
        item_pixel = item.getpixel((px, py))
        if not (is_empty(item_pixel) or is_background_color(item_pixel, 15)):
            color[0] += item_pixel[0]
            color[1] += item_pixel[1]
            color[2] += item_pixel[2]
            count += 1
        px += 1
        if px == item.size[0]:
            px = 0
            py += 1
    if count == 0:
        return 0, 0, 0
    color[0] /= count
    color[1] /= count
    color[2] /= count
    return int(color[0]) - int(color[1]), int(color[0]) - int(color[2]), int(color[1]) - int(color[2])


async def slot_scan(slot_item, slot_item_size, item_list, group_list, quality):
    if slot_item is None:
        return "Empty"
    if quality < 5:
        quality = 5
    item_list = sorted(item_list, key=lambda k: min(max(k['value'], 1000), 1) + (
    (k['priority'] + group_list.get(k['group'], 0)) / 100), reverse=True)
    non_empty_size = get_item_size(slot_item)
    mismatch_threshold = non_empty_size * (quality * 2)
    silhouette_threshold = non_empty_size * (quality * 0.006)
    for item in item_list:
        await asyncio.sleep(0.0001)
        if item['name'] == "Unknown":
            item_image = item['frame']
        else:
            item_image = pickle.loads(item['frame'])
            item_image = Image.open(io.BytesIO(bytearray(item_image)))
            item_image = crop_item(item_image)
        px = 0
        py = 0
        missmatch = 0
        sillhouette = 0
        while py < slot_item.size[1] and py < item_image.size[1]:
            slot_item_pixel = slot_item.getpixel((px, py))
            item_pixel = item_image.getpixel((px, py))
            if is_empty(item_pixel) == is_empty(slot_item_pixel) is True:
                sillhouette += 0
            elif is_empty(item_pixel) == is_empty(slot_item_pixel) is False:
                pixeldiff = pixel_diff(slot_item_pixel, item_pixel)
                if pixeldiff > quality * 6:
                    missmatch += pixeldiff
            elif is_empty(slot_item_pixel):
                if is_background_color(item_pixel, quality):
                    sillhouette += 0
                elif is_number(slot_item_pixel):
                    sillhouette += 0
                else:
                    sillhouette += 1
            elif is_empty(item_pixel):
                sillhouette += 1

            if missmatch > mismatch_threshold or sillhouette > silhouette_threshold:
                break

            px += 1
            if px == slot_item.size[0] or px == item_image.size[0]:
                py += 1
                px = 0
            if py == slot_item.size[1] or py == item_image.size[1]:
                if item['name'] == "Unknown":
                    return item
                item['priority'] += 400
                return item
    return "Unknown"


async def find_slots(loot_image, progress_bar):
    _lootImage = loot_image.copy()
    loot_bytes = loot_image.tobytes()
    slot_list = []
    if loot_image.size[0] < 34 or loot_image.size[1] < 34:
        return slot_list

    if len(loot_bytes) > 2312:
        progress_percent = 0
        percent_message = ""
        percent_message += EMOJI[":black_square_button:"] * progress_percent
        percent_message += EMOJI[":black_large_square:"] * (10 - progress_percent)
        await progress_bar.edit(content=percent_message)
    x = -1
    y = 0
    skip = False
    for loot_pixel in loot_bytes:
        x += 1
        if x + 34 > _lootImage.size[0]:
            if len(loot_bytes) > 2312:
                if int(y / _lootImage.size[1] * 100 / 10) != progress_percent:
                    progress_percent = int(y / _lootImage.size[1] * 100 / 10)
                    percent_message = ""
                    percent_message += EMOJI[":black_square_button:"] * progress_percent
                    percent_message += EMOJI[":black_large_square:"] * (10 - progress_percent)
                    await progress_bar.edit(content=percent_message)
            y += 1
            x = 0
            await asyncio.sleep(0.0001)
        if y + 34 > _lootImage.size[1]:
            break
        if skip:
            # Skip every other pixel to save time
            skip = False
        else:
            if x + 34 != _lootImage.size[0]:
                # Can't skip the last part of an image
                skip = True
            if pixel_diff(_lootImage.getpixel((x, y)), slot_border[0]) <= 5:
                # If the current pixel looks like a slot
                s = 0
                diff = 0
                diffmax = 132 * 0.3  # 3/4's of the border size
                xs = 0
                ys = 0

                if x != 0 and pixel_diff(_lootImage.getpixel((x - 1, y)), slot_border[0]) <= 5:
                    # Make sure we didnt skip the beggining of a slot
                    # go back if we did
                    x -= 1
                    # We also set the next pixel white to avoid looping here forever if this turns out not to be a slot
                    _lootImage.putpixel((x + 1, y), (255, 255, 255, 255))
                    # and increase the diffmax by one pixel to compensate
                    diffmax += 1
                while diff <= diffmax:
                    if xs == 0 or xs == 33 or ys == 0 or ys == 33:
                        if not pixel_diff(_lootImage.getpixel((x + xs, y + ys)), slot_border[s]) == 0:
                            diff += 1
                    s += 1
                    xs += 1
                    if xs == 34:
                        xs = 0
                        ys += 1
                    if ys == 34:
                        slot_list.append({'image': loot_image.crop((x + 1, y + 1, x + 33, y + 33)), 'x': x, 'y': y})
                        _lootImage.paste(Image.new("RGBA", (34, 34), (255, 255, 255, 255)), (x, y))
                        x += 33
                        break
    return slot_list


async def item_show(item):
    if item is None:
        return None
    c = lootDatabase.cursor()
    c.execute("SELECT * FROM Items WHERE name LIKE ?", (item,))
    item_list = c.fetchall()
    if len(item_list) == 0:
        return None, None
    output_image = Image.new("RGBA", (33 * len(item_list) - 1, 32), (255, 255, 255, 255))
    x = 0
    for i in item_list:
        i_image = pickle.loads(i['frame'])
        i_image = Image.open(io.BytesIO(bytearray(i_image)))
        output_image.paste(i_image, (x * 33, 0))
        x += 1
    img_byte_arr = io.BytesIO()
    output_image.save(img_byte_arr, format='png')
    img_byte_arr = img_byte_arr.getvalue()
    return img_byte_arr, item_list[0]


async def item_remove(item):
    if item is None:
        return None
    c = lootDatabase.cursor()
    c.execute("SELECT * FROM Items WHERE name LIKE ?", (item,))
    item_list = c.fetchall()
    if len(item_list) == 0:
        return None
    c.execute("DELETE FROM Items WHERE name LIKE ?", (item,))
    return item_list[0]["name"]

async def item_add(item, frame):
    if item is None:
        return None
    c = lootDatabase.cursor()
    c.execute("SELECT * FROM Items WHERE name LIKE ?", (item,))
    item_list = c.fetchall()
    if len(item_list) == 0:
        return None
    frame_crop = crop_item(frame)
    frame_color = get_item_color(frame)
    frame_size = get_item_size(frame_crop)
    frame__byte_arr = io.BytesIO()
    frame.save(frame__byte_arr, format='PNG')
    frame__byte_arr = frame__byte_arr.getvalue()
    frame_str = pickle.dumps(frame__byte_arr)
    with lootDatabase as conn:
        conn.execute("INSERT INTO Items(name,`group`,priority,value,frame,sizeX,sizeY,size,red,green,blue) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (item_list[0]["name"], item_list[0]["group"], item_list[0]["priority"], item_list[0]["value"],
                      frame_str, frame_crop.size[0], frame_crop.size[1], frame_size, frame_color[0], frame_color[1],
                      frame_color[2]))

    c.execute("SELECT * FROM Items  WHERE name LIKE ?", (item,))
    item_list = c.fetchall()
    output_image = Image.new("RGBA", (33 * len(item_list) - 1, 32), (255, 255, 255, 255))
    x = 0
    for i in item_list:
        i_image = pickle.loads(i['frame'])
        i_image = Image.open(io.BytesIO(bytearray(i_image)))
        output_image.paste(i_image, (x * 33, 0))
        x += 1
    img_byte_arr = io.BytesIO()
    output_image.save(img_byte_arr, format='png')
    img_byte_arr = img_byte_arr.getvalue()
    return img_byte_arr


async def item_new(item, frame, group, value):
    if item is None or group is None:
        return None

    c = lootDatabase.cursor()
    c.execute("SELECT * FROM Items  WHERE name LIKE ?", (item,))
    item_list = c.fetchall()
    if not len(item_list) == 0:
        return None

    frame_crop = crop_item(frame)
    frame_color = get_item_color(frame)
    frame_size = get_item_size(frame_crop)
    frame__byte_arr = io.BytesIO()
    frame.save(frame__byte_arr, format='PNG')
    frame__byte_arr = frame__byte_arr.getvalue()
    frameStr = pickle.dumps(frame__byte_arr)
    with lootDatabase as conn:
        conn.execute("INSERT INTO Items(name,`group`,priority,value,frame,sizeX,sizeY,size,red,green,blue) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (item, group, 0, value, frameStr, frame_crop.size[0], frame_crop.size[1], frame_size,
                      frame_color[0], frame_color[1], frame_color[2]))

    c.execute("SELECT * FROM Items WHERE name LIKE ?", (item,))
    item_list = c.fetchall()
    output_image = Image.new("RGBA", (33 * len(item_list) - 1, 32), (255, 255, 255, 255))
    x = 0
    for i in item_list:
        i_image = pickle.loads(i['frame'])
        i_image = Image.open(io.BytesIO(bytearray(i_image)))
        output_image.paste(i_image, (x * 33, 0))
        x += 1
    img_byte_arr = io.BytesIO()
    output_image.save(img_byte_arr, format='png')
    img_byte_arr = img_byte_arr.getvalue()
    c.close()
    return img_byte_arr

def is_black(pixel):
    return not(pixel[0] >= 55 or pixel[1] >= 55 or pixel[2] >= 55)

def clear_black_lines(itemImage):
    if itemImage is None:
        return itemImage
    #horizontal
    px = 0
    py = 0
    while py<itemImage.size[1]:
        itemImagePixel = itemImage.getpixel((px,py))
        if not is_black(itemImagePixel):
            py+=1
            px=0
            continue
        px+=1
        if px == itemImage.size[0]:
            px=0
            for lx in range(0,itemImage.size[0]):
                itemImage.putpixel((lx,py),(0,0,0,0))
            py+=1
    #vertical
    px = 0
    py = 0
    while px<itemImage.size[0]:
        itemImagePixel = itemImage.getpixel((px,py))
        if not is_black(itemImagePixel):
            px+=1
            py=0
            continue
        py+=1
        if py == itemImage.size[1]:
            py=0
            for ly in range(0,itemImage.size[1]):
                itemImage.putpixel((px,ly),(0,0,0,0))
            px+=1
    return itemImage

async def loot_db_update():
    itemSkipFilters = ["Abacus (Replica)","Airtight Cloth","Almanac of Magic","Amulet of Life","Animal Fetish","Annihilation Bear","Antler Talisman","Areca Palm","Armor Rack","Arrow (Weak)","Artist's Easel (with Canvas)","Artist's Easel","Avalanche Rune (Weak)","Baby Dragon","Badger Fur (Decoration)","Badly Made Piece of Cloth","Bag (Ahmet)","Bag of Screws","Bag with Stolen Gold","Baking Tray (with Garlic Dough)","Bale of White Cloth","Bale of Yellowed Cloth","Bamboo Drawer","Bamboo Shelf","Bamboo Table","Barrel (Brown)","Barrel of Beer","Barrel","Beer Bottle","Belongings of a Deceased","Big Table","Birdcage (Dead)","Birdcage","Blessed Ankh","Blue Powder","Blue Spell Wand","Bolt (Weak)","Bookcase (Ab'Dendriel)","Bookcase (Venore)","Bookcase","Boots of Homecoming (Used)","Boots of Waterwalking","Botanist's Container (Bells)","Botanist's Container (Cauldron)","Botanist's Container (Empty)","Botanist's Container (Orchid)","Botanist's Container (Rose)","Bottle of Bug Milk","Bottle of Whisper Beer","Bowl (Gold)","Bowl (Green)","Bowl (Silver)","Bowl of Tea Leaves","Bowl with Sacred Water","Box (Brown)","Box (Pies)","Branch","Brandon's Wedding Ring","Bricklayers' Kit","Broken Wooden Shield","Bucket Full of Mortar","Bucket of Bog Water","Bundle of Rags","Burst Arrow (Weak)","Butterfly Conservation Kit (Blue)","Butterfly Conservation Kit (Empty)","Butterfly Conservation Kit (Purple)","Butterfly Conservation Kit (Red)","Cabinet (Venorean)","Cabinet","Cake Cabinet","Carafe of Water Binding","Carved Stone Table","Case of Rust Bugs","Cask of Brown Ale (Item)","Cat in a Basket","Chaos Matter","Chest of Drawers","Chimney (Lit)","Chimney","Christmas Branch","Christmas Present Bag","Christmas Tree Package","Christmas Tree","Club of the Fury","Compromising Letter","Conjurer Wand","Crate (Swapped)","Crate (Wine)","Crate Full of Coral","Crumpled Paper","Crystal Ring (Eleonore)","Cups of Honour","Damaged Logbook","Dead Bog Frog (Quest)","Dead Rat (Oramond)","Deed of Ownership","Deep Crystal","Delany's Golden Bug Trophy","Dinky Moss Floret Garland","Djinn's Lamp","Document of the Follower","Document of the Leader","Double Loot Week","Dragha's Spellbook","Dragon Eye (Replica)","Dragon Statue (Item)","Dragon Throne","Drawer","Dream Junk","Dresser","Drowned Seaman's Skull","Dung Ball (Quest)","Dwarven Pickaxe","Easily Inflammable Sulphur","Eclesius' Sandals","Eerie Song Book","Eggs of a Sacred Snake","Elane's Crossbow","Elven Brooch","Elven Wand","Empty Beer Bottle","Empty Jug","Energy Net","Enigmatic Voodoo Skull","Envelope from the Wizards","Envenom Rune","Exploding Cookie","Explosion Rune (Weak)","Exquisite Silk","Exquisite Wood","Fake Dwarven Beard","Fake Rabbit's Foot","Faked Label","Family Brooch (Dwarven)","Family Brooch","Family Signet Ring","Fan Doll of King Tibianus","Farmer's Avenger","Ferocious Cabinet","Ferocious Chair","Ferocious Table","Ferocious Trunk","Ferumbras' Mana Keg (Used)","Filigree Statue","Filled Carrying Device","Filled Cup","Fine Sulphur","Fireball Rune (Weak)","Fishnapped Goldfish","Flask of Cough Syrup","Flask of Warrior's Sweat","Flexible Dragon Scale","Food Crate","Friendship Amulet (Replica)","Frozen Heart (Replica)","Full Gas Bag","Funeral Urn","Fungus Powder","Garlic Bread","Garlic Cookie","Gas Bag","Gemmed Lamp (Fa'hradin's)","Ghost Duster","Ghost Residue","Giant Screwdriver","Giant Smithhammer","Glob of Grease","Globe","Glooth Vinegar","Glutton's Mace","Gnomish Crystal Package","Gnomish Spore Gatherer (Blue)","Gnomish Spore Gatherer (Complete)","Gnomish Spore Gatherer (Green)","Gnomish Spore Gatherer (Red)","Gnomish Spore Gatherer (Yellow)","Goblets","Goblin Statue","Golden Goblet (15th Anniversary)","Golden Quartz Powder","Golden Wand","Golem Disassembler","Gooey Substance","Great Fireball Rune (Weak)","Green Balloons","Green Cushioned Chair","Green Powder","Green Power Core","Green Spell Wand","Griffinclaw Container","Grodrik's Favourite Axe","Guardcatcher","Hamster in a Wheel","Harp","Headache Pill","Heated Worm Punisher","Heavy Magic Missile Rune (Weak)","Heavy Metal T-Shirt","Helmet of Nature","Holy Missile Rune (Weak)","Hopgoblin's Broken Staff","Hourglass","House Silversun's Signet Ring","Ice Cream Cone (Venorean Dream)","Icicle (Item)","Icicle Rune (Weak)","Incantation Fragment","Incredible Mumpiz Slayer","Indoor Plant","Intense Healing Rune (Item Weak)","Iriana's Chest","Ivory Chair","Jerom's Family Necklace","Key of Numerous Locks (Replica)","Key Ring","Kidney Table","Large Amphora","Large Trunk","Leaf Basket","Letter to Chantalle","Letter to Eremo","Letter to Markwin","Lettuce","Light Magic Missile Rune (Weak)","Lightest Magic Missile Rune","Lit Protectress Lamp","Lizard Weapon Rack","Locker","Lump of Garlic Dough","Lump of Holy Water Dough","Machine Crate","Magic Crystal","Magical Inkwell","Magical Watch","Magnificent Cabinet","Magnificent Chair","Magnificent Table","Magnificent Trunk","Mago Mechanic Core","Mailbox (Furniture)","Masterpiece of a Gozzler","Masterpiece of a Muse","Matrix Crystal","Mean Knight Sword","Mean Paladin Spear","Meat Shield","Memory Box (Activated)","Memory Stone","Mighty Helm of Green Sparks","Milking Fork","Miniature House","Mining Helmet (Budrik)","Minotaur Statue","Molten Wax","Monk's Diary","Musician's Bow","Mysterious Package","Mysterious Scroll","Mystic Root","Nature Magic Spellbook","Noble Sword (Activated)","Noble Sword (Replica)","Nomad Parchment","Norseman Doll (Replica)","Note from the Thieves Guild","Odd Hat","Ogre Rune Stone","Ogre Rune Stones (Corner)","Ogre Rune Stones (Right)","Ogre Rune Stones (Two)","Ogre Rune Stones (Up)","Old and Used Backpack","Old Encrypted Text","Old Iron","Old Nasty","Old Piece of Paper","Old Power Core","Omrabas' Heart","Omrabas' Talking Skull","Orc Tusk","Orc's Jaw Shredder (Replica)","Orichalcum Pearl","Ornamented Stone Table","Ornate Mailbox","Oven (Lit)","Oven","Painting of a Gozzler","Painting of a Muse","Pet Pig","Pharaoh Rares","Phoenix Statue (Replica)","Piano","Piercing Bolt (Weak)","Pile of Bones","Pinch of Crystal Dust","Pirates Surprise","Poet's Fencing Quill","Pointed Rabbitslayer","Potted Plant","Power Arrow","Power Bolt (Weak)","Precious Necklace","Prepared Bucket","Present (Explosive)","Present (Postman)","Protectress Lamp","Quagmire Rod","Red Cushioned Chair","Red Powder","Red Power Core","Red Spell Wand","Replica of the Sceptre","Rerun's Ring","Resonance Crystal","Reward Box","Ring of Wishes","Ritual Wand","Rocking Chair","Rocking Horse","Rolling Pin (Rookgaard)","Roshamuul Prison Keys","Sacred Bowl of Purification","Sacred Bowl","Sacred Earth","Scum Bag","Secret Agent Tools","Shadow Orb","Shaggy Ogre Bag","Shapechanger","Shield of Care","Shield of the White Knight","Silver Key (Outpost)","Simon the Beggar's Favorite Staff","Simple Arrow (Weak)","Siramal's Golden Bug Trophy","Skeleton (Item)","Skull (Item)","Skull of Ratha","Small Bamboo Shelf","Small Enchanted Amethyst","Small Enchanted Emerald","Small Enchanted Ruby","Small Enchanted Sapphire","Small Golden Taboret","Small Round Table","Small Table","Snake Destroyer","Sneaky Stabber of Eliteness (Jammed)","Sniper Arrow (Weak)","Snowman Package","Sofa Chair","Soft Piece of Cloth","Some Mushrooms (Brown)","Some Special Leaves","Sorc and Druid Staff","Soul Contract","Spare Part","Special Flask (Fools Guild)","Special Flask (Quara)","Special Flask (Slime)","Special Polish","Spectral Cloth","Spectral Dress","Spectral Stone","Spool of Steel Silk Yarn","Square Table","Squeezing Gear of Girlpower (Jammed)","Stabilizer","Stalagmite Rune (Weak)","Stale Bread of Ancientness","Standing Mirror","Steel Spider Silk","Stolen Golden Goblet","Stone Shower Rune (Weak)","Stool","Strange Powder (Hive)","Strong Sinew","Sudden Death Rune (Weak)","Sugar","Sugatrap's Obsidian Lance","Suspicious Documents","Suspicious Surprise Bag","Swarmer Drum","Sweet and Sugary Substance","Taboret","Tainted Blood Essence","Tea Spoon","Telescope","Tempest Rod","Test Voodoo Doll","The Alchemists' Formulas","The Carrot of Doom","The Crossbow of Swordfish","The Dust of Arthei","The Dust of Boreth","The Dust of Lersatio","The Dust of Marziel","The Dwarven Emperor's Beard","The Famous Mina Losa Painting","The Horn of Sundering","The Mexcalibur (Replica)","The Rain Coat","The Ring of the Count","The Shield Nevermourn","The Tail of the Keeper","Thick Trunk","Throwing Cake","Thunderstorm Rune (Weak)","Tibia Coins","Timber Chair","Time Compass","Tome","Torn Incantation Fragment","Torn Log Book","Torn Magic Cape","Tortoise Egg from Nargor","Trashed Draken Boots","Treasure Digging","Treasure Map (Pirate)","Trough for Mortar","Trough","Trousers of the Ancients","Trunkhammer","Tusk Chair","Tusk Table","Ultimate Healing Rune (Item Weak)","Unholy Shield","Unworked Sacred Wood","V-Belt","Valuable Vase","Venorean Chair","Venorean Stool","Very Noble-Looking Watch","Volcanic Rod","Waldo's Post Horn","Wand of Might","Wand of Plague","War Wolf Skin","Wardrobe (Venorean)","Water Pipe (Deluxe)","Weapon Rack","Weapons Crate (Set)","Weapons Crate","Whacking Driller of Fate (Jammed)","Whisper Moss","Whoopee Cushion","Witchesbroom","Wooden Chair","Wooden Ties","Wooden Trunk","Wooden Wand","Worm Punisher","Xodet's First Wand","Yalahari Gear Wheel","Yellow Pillow (Supersoft)","Yellow Powder","Yellow Spell Wand","Amazon Disguise Kit","Armor Rack Kit","Bamboo Drawer Kit","Bamboo Table Kit","Barrel Kit","Big Table Kit","Birdcage Kit","Blue Bed Kit","Cake Cabinet Kit","Canopy Bed Kit","Chimney Kit","Coal Basin Kit","Crystal Table Kit","Dragon Statue Kit","Dragon Throne Kit","Drawer Kit","Dresser Kit","Dwarf Disguise Kit","Easel Kit","Globe Kit","Goblin Statue Kit","Green Bed Kit","Green Cushioned Chair Kit","Harp Kit","Heavy Package","Indoor Plant Kit","Ivory Chair Kit","Knight Statue Kit","Large Amphora Kit","Large Used Amphora Kit","Lizard Weapon Rack Kit","Locker Kit","Minotaur Statue Kit","Monkey Statue 'Hear' Kit","Monkey Statue 'See' Kit","Monkey Statue 'Speak' Kit","Oven Kit","Pendulum Clock Kit","Piano Kit","Red Bed Kit","Red Cushioned Chair Kit","Rocking Chair Kit","Rocking Horse Kit","Round Table Kit","Small Table Kit","Sofa Chair Kit","Square Table Kit","Stone Table Kit","Table Lamp Kit","Telescope Kit","Trough Kit","Trunk Chair Kit","Trunk Kit","Trunk Table Kit","Tusk Chair Kit","Tusk Table Kit","Used Globe Kit","Used Red Chair Kit","Used Rocking Horse Kit","Used Telescope Kit","Venorean Cabinet Kit","Venorean Drawer Kit","Venorean Wardrobe Kit","Weapon Rack Kit","Wooden Chair Kit","Yellow Bed Kit","Goblin Bone Key","Green Key","Key 0000","Key 0001","Key 0004","Key 0005","Key 0006","Key 0007","Key 0008","Key 0009","Key 0010","Key 0020","Key 0021","Key 0555","Key 3001","Key 3002","Key 3003","Key 3004","Key 3005","Key 3006","Key 3007","Key 3008","Key 3012","Key 3033","Key 3100","Key 3142","Key 3301","Key 3302","Key 3303","Key 3304","Key 3350","Key 3520","Key 3600","Key 3610","Key 3620","Key 3650","Key 3666","Key 3667","Key 3700","Key 3701","Key 3702","Key 3703","Key 3800","Key 3801","Key 3802","Key 3899","Key 3900","Key 3901","Key 3909","Key 3910","Key 3911","Key 3912","Key 3913","Key 3914","Key 3915","Key 3916","Key 3917","Key 3923","Key 3925","Key 3930","Key 3931","Key 3932","Key 3933","Key 3934","Key 3935","Key 3936","Key 3937","Key 3938","Key 3940","Key 3950","Key 3960","Key 3970","Key 3980","Key 3988","Key 4001","Key 4009","Key 4022","Key 4023","Key 4033","Key 4037","Key 4055","Key 4210","Key 4501","Key 4502","Key 4503","Key 4600","Key 4601","Key 4602","Key 4603","Key 5000","Key 5002","Key 5010","Key 5050","Key 6010","Magical Key","Omrabas' Bone Key","Omrabas' Copper Key","Prison Cell Key","Theodore Loveless' Key","Rusty Armor (Common)","Rusty Armor (Rare)","Rusty Armor (Semi-Rare)","Rusty Helmet (Common)","Rusty Helmet (Rare)","Rusty Helmet (Semi-Rare)","Rusty Legs (Common)","Rusty Legs (Rare)","Rusty Legs (Semi-Rare)","Rusty Shield (Common)","Rusty Shield (Rare)","Rusty Shield (Semi-Rare)","Golden Rune Emblem (Animate Dead)","Golden Rune Emblem (Avalanche)","Golden Rune Emblem (Chameleon)","Golden Rune Emblem (Desintegrate)","Golden Rune Emblem (Destroy Field)","Golden Rune Emblem (Energy Bomb)","Golden Rune Emblem (Energy Wall)","Golden Rune Emblem (Explosion)","Golden Rune Emblem (Fire Bomb)","Golden Rune Emblem (Fire Field)","Golden Rune Emblem (Fireball)","Golden Rune Emblem (Great Fireball)","Golden Rune Emblem (Heavy Magic Missile)","Golden Rune Emblem (Holy Missile)","Golden Rune Emblem (Icicle)","Golden Rune Emblem (Light Magic Missile)","Golden Rune Emblem (Magic Wall)","Golden Rune Emblem (Paralyze)","Golden Rune Emblem (Poison Bomb)","Golden Rune Emblem (Soulfire)","Golden Rune Emblem (Sudden Death)","Golden Rune Emblem (Thunderstorm)","Golden Rune Emblem (Ultimate Healing)","Golden Rune Emblem (Wild Growth)","Monkey Statue (No Hearing)","Monkey Statue (No Seeing)","Monkey Statue (No Speaking)","Silver Rune Emblem (Animate Dead)","Silver Rune Emblem (Avalanche)","Silver Rune Emblem (Chameleon)","Silver Rune Emblem (Desintegrate)","Silver Rune Emblem (Destroy Field)","Silver Rune Emblem (Energy Bomb)","Silver Rune Emblem (Energy Wall)","Silver Rune Emblem (Explosion)","Silver Rune Emblem (Fire Bomb)","Silver Rune Emblem (Fire Field)","Silver Rune Emblem (Fireball)","Silver Rune Emblem (Great Fireball)","Silver Rune Emblem (Heavy Magic Missile)","Silver Rune Emblem (Holy Missile)","Silver Rune Emblem (Icicle)","Silver Rune Emblem (Light Magic Missile)","Silver Rune Emblem (Magic Wall)","Silver Rune Emblem (Paralyze)","Silver Rune Emblem (Poison Bomb)","Silver Rune Emblem (Soulfire)","Silver Rune Emblem (Sudden Death)","Silver Rune Emblem (Thunderstorm)","Silver Rune Emblem (Ultimate Healing)","Silver Rune Emblem (Wild Growth)","Aggressive Fluid","Animal Cure","Beer","Blood Vial (Necromancer)","Blood Vial (Vampire)","Blood Vial","Blood","Bottle of Airtight Gloo","Bottle of Gloo","Bottle with Rat Urine","Coconut Milk","Flask Mushroom Fertilizer","Flask of Chitin Dissolver","Flask of Crown Polisher","Flask of Dissolved Chitin","Flask of Greasy Red Oil","Flask of Plant Poison","Flask of Poison","Flask of Wasp Poison","Flask with Beaver Bait","Flask with Magical Oil","Flask with Oil and Blood","Flask with Paint","Fruit Juice","Glooth Plasma","Lemonade","Lifefluid","Manafluid","Mead","Milk","Mud","Oil","Pink Gloud Essence","Reagent Flask","Rum","Slime (Liquid)","Special Flask (Holy Water)","Special Flask (Padreia)","Special Flask (Stalker)","Special Flask (Vascalir)","Tea","Urine","Vial of Elemental Water","Vial of Medusa Blood","Water (Liquid)","Wine","Wonder Glue","Amarie's Favourite Book","Ancient Map","Baby Rotworm","Bag of Oriental Spices (Replica)","Bill","Blank Poetry Parchment","Blob Bomb","Blood Crystal (Charged)","Blue Pollen","Book (Atlas)","Book (Black)","Book (Blue)","Book (Brown Square)","Book (Brown Thin)","Book (Brown)","Book (CGB)","Book (Draconia)","Book (Fat Green)","Book (Green)","Book (Grey)","Book (Orange)","Book (Red)","Boots of Renewal","Botany Almanach","Carrying Device","Combustion Rune","Contract","Document (Certificate)","Document of the Officer","Dog House","Doll of Durin The Almighty (Replica)","Emergency Kit","Encyclopedia (Replica)","Ewer (Blue)","Ewer (Golden)","Ewer (Green)","Ewer (Silver)","Ewer with Holy Water","Faded Last Will","Fan Club Membership Card","File AH-X17L89","Fish Tank","Gingerbread Recipe","Gnomish Voucher Type CA1","Gnomish Voucher Type CA2","Gnomish Voucher Type CB","Gnomish Voucher Type MA1","Gnomish Voucher Type MA2","Gnomish Voucher Type MB","Golden Newspaper (Replica)","Golem Blueprint","Hand Puppets (Replica)","Helmet of Ultimate Terror","Imortus (Replica)","Intelligence Reports","Interwoven Moss Florets","Invitation","Julius' Map","Map (Brown)","Map (Colour)","Map to the Unknown","Medusa Skull (Replica)","Music Box (Replica)","Music Sheet (First Verse)","Music Sheet (Fourth Verse)","Music Sheet (Second Verse)","Music Sheet (Third Verse)","Nautical Map","Notes and Coordinates","Old Parchment (Brown)","Old Parchment (Omrabas)","Old Parchment","Package of Potions","Paper","Parcel (Watchtower)","Parchment (Gnomes)","Parchment (Poetry)","Parchment (Questionnaire)","Parchment (White)","Parchment (Yellow Rewritable)","Parchment (Yellow)","Picture (Landscape)","Picture (Portrait)","Picture (Still Life)","Plans for a Strange Device","Purple Powder","Scribbled Sheet of Paper","Scroll (Brown)","Scroll (TBI)","Secret Letter","Sheet of Tracing Paper (Blank)","Sheet of Tracing Paper (Full)","Signed Contract","Spellbook (Alternative)","Statue (Knight)","Stone (Small)","Strange Amulet","Strange Good Night Songs","Strong Cloth","Strong Health Potion","Tactical Map","Tea Cup","The Lower Left Part of a Map","The Lower Right Part of a Map","The Top Left Part of a Map","The Top Right Part of a Map","Translation Scroll","Treasure Chest (Item)","Very Old Piece of Paper","Voodoo Doll (Quest)","Wrinkled Parchment","Your Student Book","Giant Shimmering Pearl (Brown)","Giant Shimmering Pearl (Green)","Belongings of a Deceased (Death Priest Shargon)","Belongings of a Deceased (The Ravager)","Gleaming Starlight Vial (Quest)","Golden Goblet (Level 999)","Voodoo Doll (5261)","Voodoo Doll (3613)","Voodoo Doll (2543)","Very Noble-Looking Watch (Broken)","TibiaHispano Emblem (Replica)","Strange Blue Powder (Used)","Strange Yellow Powder (Used)","Strange Red Powder (Used)","Staff (Simon)","Icy Crystal Mace","Icy Crystal Mace Replica"]
    # Reading item database
    c = tibiaDatabase.cursor()
    c2 = lootDatabase.cursor()
    # Search query
    c.execute("SELECT DISTINCT Items.title,Items.type"+
    " FROM Items",())
    itemList = c.fetchall()
    newitems = 0
    for item in itemList:
        if item['title'] in itemSkipFilters:
            continue
        c2.execute("SELECT * FROM Items WHERE name LIKE ?", (item['title'],))
        item_list = c2.fetchall()
        if not len(item_list) == 0:
            continue
        
        get = get_item(item['title'])
        if get is None:
            item['value'] = 0
            item['buyers'] = []
            item['type'] = "Other"
        else:
            get['type'] = item['type']
            item = get
            if item['title'] == "Crystal Coin":
                item['value'] = 10000
                item['buyers'] = [{'name':"Bank"}]
            elif item['title'] == "Platinum Coin":
                item['value'] = 100
                item['buyers'] = [{'name':"Bank"}]
            elif item['title'] == "Gold Coin":
                item['value'] = 1
                item['buyers'] = [{'name':"Bank"}]
        
        group = item['type']
        if item['value'] is None or len(item['buyers']) == 0:
            item['value'] = 0
            group = 'No Value'
        elif group not in ["Creature Products","Containers"]:
            group = 'Valuables'
        for npc in item['buyers']:
            if npc['name'] == 'Alesar' or npc['name'] == 'Yaman':
                group = 'Green Djinn'
                break
            elif npc['name'] == 'Nah\'Bob' or npc['name'] == 'Haroun':
                group = 'Blue Djinn'
                break
            elif npc['name'] == 'Rashid':
                group = 'Rashid'
                break
            elif npc['name'] == 'Yasir':
                group = 'Yasir'
                break
            elif npc['name'] == 'Gnomission':
                group = 'Gnomission'
                break
            elif npc['name'] == 'Jessica':
                group = 'Jewels'
                break
            elif npc['name'] == 'Tamoril':
                group = 'Dragon'
            elif npc['name'] == 'Alaistar' or npc['name'] == 'Flint':
                group = 'Oramond'
                break
                
        frames = []
        try:
            imagegif = Image.open(io.BytesIO(bytearray(item['image'])))
            ## v    to save .gif images correctly     v ##
            with open("debugimages/"+item["title"]+"/"+item["title"]+'.gif', 'wb') as w:
                w.write(item['image'])
            ##############################################
            nframes = 0
            while imagegif:
                itemImageFrame = clear_black_lines(imagegif.convert("RGBA"))
                itemImageFrameCrop = crop_item(itemImageFrame)
                itemColor = get_item_color(itemImageFrameCrop)
                if itemImageFrame is not None and itemImageFrameCrop is not None:
                    #frames.append(itemImageFrame.tobytes())
                    imgByteArr = io.BytesIO()
                    itemImageFrame.save(imgByteArr, format='PNG')
                    imgByteArr = imgByteArr.getvalue() 
                    frames.append([imgByteArr,itemImageFrameCrop.size,itemColor])
                nframes += 1
                try:
                    imagegif.seek( nframes )
                except EOFError:
                    break;
        except Exception as e:
            imagegif = None
        
        print("Creating new item: "+item['title'])
        fn = 0
        if not os.path.exists("debugimages/"+item['title']):
            os.makedirs("debugimages/"+item['title'])
        for frame in frames:
            frameStr = pickle.dumps(frame[0])
            frameImg = Image.open(io.BytesIO(frame[0]))
            c2.execute("INSERT INTO Items(name,`group`,value,frame,sizeX,sizeY,size,red,green,blue) VALUES (?,?,?,?,?,?,?,?,?,?)",(item["title"],group,item["value"],frameStr,frame[1][0],frame[1][1],get_item_size(frameImg),frame[2][0],frame[2][1],frame[2][2]))
            frameImg.save("debugimages/"+item['title']+"/"+item['title']+str(fn)+".png", "PNG")
            fn+=1
        newitems+=1
        
    c.close()
    c2.close()
    lootDatabase.commit()
    return newitems or None

async def loot_scan(loot_image, image_name, progress_msg, progress_bar):
    debug_output = image_name
    debug_outputex = 0
    while os.path.exists("loot/debug/" + str(debug_outputex) + "_" + debug_output):
        debug_outputex += 1
    debug_output = str(debug_outputex) + "_" + debug_output

    loot_image_original = loot_image.copy()
    group_images = {'Green Djinn': Image.open("./images/Green Djinn.png"),
                    'Blue Djinn': Image.open("./images/Blue Djinn.png"),
                    'Rashid': Image.open("./images/Rashid.png"),
                    'Yasir': Image.open("./images/Yasir.png"),
                    'Tamoril': Image.open("./images/Tamoril.png"),
                    'Jewels': Image.open("./images/Jewels.png"),
                    'Gnomission': Image.open("./images/Gnomission.png"),
                    'Other': Image.open("./images/Other.png"),
                    'NoValue': Image.open("./images/NoValue.png"),
                    'Unknown': Image.open("./images/Unknown.png")}

    await progress_msg.edit(content="Status: Detecting item slots.")
    slot_list = await find_slots(loot_image, progress_bar)
    c = lootDatabase.cursor()
    group_list = {}
    loot_list = {}
    unknown_items_list = []
    lq_items_list = []
    progress = 0
    progress_percent = 0
    percent_message = ""
    quality_warning = 0
    percent_message += EMOJI[":black_square_button:"] * progress_percent
    percent_message += EMOJI[":black_large_square:"] * (10 - progress_percent)
    await progress_msg.edit(content="Status: Scanning items.")
    await progress_bar.edit(content=percent_message)
    for found_slot in slot_list:
        found_item_number, found_item, item_number_image = number_scan(found_slot['image'])
        result = "Unknown"
        quality = 0
        qz_item = clear_background(found_item.copy())
        qz_item_crop = crop_item(qz_item)
        while result == "Unknown" and quality < 30:
            found_item_clear = clear_background(found_item, quality)
            found_item_crop = crop_item(found_item_clear)
            # Check if the slot is empty
            if type(found_item_crop) is tuple:
                result = "Empty"
                quality = 30
                continue
            found_item_size = get_item_size(found_item_crop)
            found_item_color = get_item_color(found_item_crop)
            c.execute("SELECT * FROM Items "
                      "WHERE ((ABS(sizeX - ?) <= 3 AND ABS(sizeY - ?) <= 3) OR ABS(size - ?) <= ?) AND "
                      "(ABS(red - ?)+ABS(green - ?)+ABS(blue - ?) <= ?)",
                      (found_item_crop.size[0], found_item_crop.size[1], found_item_size, 10, found_item_color[0],
                       found_item_color[1], found_item_color[2], 60 + quality * 2,))

            item_list = c.fetchall()
            for unknownItem in unknown_items_list:
                if abs(unknownItem['sizeX'] - found_item_crop.size[0]) <= 3 and abs(
                                unknownItem['sizeY'] - found_item_crop.size[1]) <= 3:
                    item_list.append(unknownItem)
            if quality == 0:
                for lq_item in lq_items_list:
                    if abs(lq_item['sizeX'] - found_item_crop.size[0]) <= 3 and abs(
                                    lq_item['sizeY'] - found_item_crop.size[1]) <= 3:
                        item_list.append(lq_item)
            result = await slot_scan(found_item_crop, found_item_crop.size, item_list, group_list, quality)
            quality += max(2, int(quality / 2))

        if result == "Unknown":
            unknown_image = clear_background(found_slot['image'])
            unknown_image_crop = crop_item(clear_background(found_slot['image']))
            unknown_image_size = get_item_size(unknown_image_crop)
            result = {'name': "Unknown",
                      'group': "Unknown",
                      'value': 0,
                      'priority': 10000000,
                      'frame': unknown_image_crop,
                      'sizeX': unknown_image_crop.size[0],
                      'sizeY': unknown_image_crop.size[1],
                      'size': unknown_image_size}
            found_item_number = 1
            unknown_items_list.append(result)
            # Save the loot image and the cropped item that couldn't be recognize
            if not os.path.exists("loot/debug/" + debug_output):
                os.makedirs("loot/debug/" + debug_output)
                loot_image_original.save("loot/debug/" + debug_output + "/" + image_name, "png")
            filename = "Unknown"
            filenameex = 0
            while os.path.isfile("loot/debug/" + debug_output + "/" + str(filenameex) + "_" + filename + ".png"):
                filenameex += 1
            # Save with background
            loot_image.crop(
                (found_slot['x'] + 1, found_slot['y'] + 1, found_slot['x'] + 33, found_slot['y'] + 33)).save(
                "loot/debug/" + debug_output + "/" + str(filenameex) + "_" + filename + ".png", "png")
            # Save without background
            unknown_image.save("loot/debug/" + debug_output + "/" + str(filenameex) + "_" + filename + "-clean.png",
                               "png")
        if type(result) == dict:
            if quality > 2 and not result in unknown_items_list and not result in lq_items_list:
                quality_warning += 1
                if quality_warning == 5:
                    await progress_bar.channel.send("WARNING: You seem to be using a low quality image, or a "
                                                    "screenshot taken using Tibia's **software** renderer. Some "
                                                    "items may not be recognized correctly, and overall scanning "
                                                    "speed will be slower!")
                lq_item = result
                img_byte_arr = io.BytesIO()
                qz_item.save(img_byte_arr, format='png')
                img_byte_arr = img_byte_arr.getvalue()
                lq_item['original'] = result['frame']
                lq_item['frame'] = pickle.dumps(img_byte_arr)
                lq_item['sizeX'] = qz_item_crop.size[0]
                lq_item['sizeY'] = qz_item_crop.size[1]
                lq_items_list.append(lq_item)

            if result['name'] in loot_list:
                loot_list[result['name']]['count'] += found_item_number
            else:
                loot_list[result['name']] = {'count': found_item_number, 'group': result['group'],
                                             'value': result['value']}

            if result['group'] != "Unknown":
                group_list[result['group']] = group_list.get(result['group'], 0) + 100
                c.execute("UPDATE Items SET priority = priority+4 WHERE `name` = ?", (result['name'],))
                c.execute("UPDATE Items SET priority = priority+1 WHERE `group` = ?", (result['group'],))

            if result['group'] != "Unknown":
                if result not in lq_items_list:
                    detect = pickle.loads(result['frame'])
                else:
                    detect = pickle.loads(result['original'])
                detect = Image.open(io.BytesIO(bytearray(detect)))
                loot_image.paste(slot, (found_slot['x'], found_slot['y']))
                detect = Image.alpha_composite(loot_image.crop(
                    (found_slot['x'] + 1, found_slot['y'] + 1, found_slot['x'] + 33, found_slot['y'] + 33)), detect)
                if found_item_number > 1:
                    num = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
                    num.paste(item_number_image, (7, 21))
                    detect = Image.alpha_composite(detect, num)
                loot_image.paste(detect, (found_slot['x'] + 1, found_slot['y'] + 1))

            overlay = Image.alpha_composite(
                loot_image.crop((found_slot['x'], found_slot['y'], found_slot['x'] + 34, found_slot['y'] + 34)),
                group_images.get(result['group'], group_images['Other']) if result['value'] > 0 or result[
                                                                                                     'group'] == "Unknown" else
                group_images['NoValue'])
            loot_image.paste(overlay, (found_slot['x'], found_slot['y']))

        progress += 1
        if int(progress / len(slot_list) * 100 / 10) != progress_percent:
            progress_percent = int(progress / len(slot_list) * 100 / 10)
            percent_message = ""
            percent_message += EMOJI[":black_square_button:"] * progress_percent
            percent_message += EMOJI[":black_large_square:"] * (10 - progress_percent)
            await progress_msg.edit(
                content="Status: Scanning items (" + str(progress) + "/" + str(len(slot_list)) + ").")
            await progress_bar.edit(content=percent_message)
        await asyncio.sleep(0.005)
    await progress_msg.edit(content="Status: Complete!")
    c.close()
    lootDatabase.commit()
    img_byte_arr = io.BytesIO()
    loot_image.save(img_byte_arr, format='png')
    img_byte_arr = img_byte_arr.getvalue()
    return loot_list, img_byte_arr


def setup(bot):
    bot.add_cog(Loot(bot))
