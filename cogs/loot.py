import io
import logging
import operator
import os
import pickle
import sqlite3
import time
from contextlib import closing
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import discord
import tibiawikisql
from PIL import Image
from discord.ext import commands

from nabbot import NabBot
from .utils import FIELD_VALUE_LIMIT, checks, CogUtils
from .utils.config import config
from .utils.context import NabCtx
from .utils.database import wiki_db
from .utils.messages import split_message

log = logging.getLogger("nabbot")

LOOTDB = "data/loot.db"
DEBUG_FOLDER = "debug/loot"
slot: Dict[str, Image.Image] = {'Normal': Image.open("./images/slot.png"),
                                'Gray': Image.open("./images/slotgray.png"),
                                'Green': Image.open("./images/slotgreen.png"),
                                'Blue': Image.open("./images/slotblue.png"),
                                'Violet': Image.open("./images/slotviolet.png"),
                                'Golden': Image.open("./images/slotgolden.png")}
slot_border = Image.open("./images/slotborder.png").convert("RGBA").getdata()
number_blank: Image.Image = Image.open("./images/numblank.png")
number_blank2: Image.Image = Image.open("./images/numblank2.png")
numbers: List[Image.Image] = [Image.open("./images/0.png"),
                              Image.open("./images/1.png"),
                              Image.open("./images/2.png"),
                              Image.open("./images/3.png"),
                              Image.open("./images/4.png"),
                              Image.open("./images/5.png"),
                              Image.open("./images/6.png"),
                              Image.open("./images/7.png"),
                              Image.open("./images/8.png"),
                              Image.open("./images/9.png"),
                              Image.open("./images/k.png")]

group_images: Dict[str, Image.Image] = {'Green Djinn': Image.open("./images/Green Djinn.png"),
                                        'Blue Djinn': Image.open("./images/Blue Djinn.png"),
                                        'Rashid': Image.open("./images/Rashid.png"),
                                        'Yasir': Image.open("./images/Yasir.png"),
                                        'Tamoril': Image.open("./images/Tamoril.png"),
                                        'Jewels': Image.open("./images/Jewels.png"),
                                        'Gnomission': Image.open("./images/Gnomission.png"),
                                        'Other': Image.open("./images/Other.png"),
                                        'NoValue': Image.open("./images/NoValue.png"),
                                        'Unknown': Image.open("./images/Unknown.png")}

scan_speed = [0.035]*10
MIN_HEIGHT = 27  # Images with a width
MIN_WIDTH = 34   # or height smaller than this are not considered.

Pixel = Tuple[int, ...]


def dict_factory(cursor, row):
    """Makes values returned by cursor fetch functions return a dictionary instead of a tuple.
    To implement this, the connection's row_factory method must be replaced by this one."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class LootScanException(commands.CommandError):
    pass


class Loot(CogUtils):
    def __init__(self, bot: NabBot):
        self.bot = bot
        self.processing_users = []
        if not os.path.isfile(LOOTDB):
            raise FileNotFoundError("Couldn't find loot database. Can't start cog.")
        self.loot_conn = sqlite3.connect(LOOTDB)
        self.loot_conn.row_factory = dict_factory

    @checks.can_embed()
    @commands.group(invoke_without_command=True, case_insensitive=True)
    async def loot(self, ctx: NabCtx):
        """Scans an image of a container looking for Tibia items and shows an approximate loot value.

        An image must be attached with the message. The prices used are NPC prices only.

        The image requires the following:

        - Must be a screenshot of inventory windows (backpacks, depots, etc).
        - Have the original size, the image can't be scaled up or down, however it can be cropped.
        - The image must show the complete slot.
        - JPG images are usually not recognized.
        - PNG images with low compression settings take longer to be scanned or aren't detected at all.

        The bot shows the total loot value and a list of the items detected, separated into the NPC that buy them.
        """
        if ctx.author.id in self.processing_users and not checks.is_owner_check(ctx):
            await ctx.error("I'm already scanning an image for you! Wait for me to finish that one.")
            return

        if len(ctx.message.attachments) == 0:
            await ctx.error("You need to upload a picture of your loot and type the command in the comment.")
            return

        attachment: discord.Attachment = ctx.message.attachments[0]
        if attachment.height is None:
            await ctx.error("That's not an image!")
            return
        if attachment.size > 2097152:
            await ctx.error("That image was too big! Try splitting it into smaller images, or cropping out anything "
                            "irrelevant.")
            return
        if attachment.height < MIN_HEIGHT or attachment.width < MIN_WIDTH:
            await ctx.error("That image is too small to be a loot image.")
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    loot_image = await resp.read()
        except aiohttp.ClientError:
            log.exception(f"{self.tag} Couldn't parse image")
            await ctx.error("I failed to load your image. Please try again.")
            return

        await ctx.send(f"I've begun parsing your image, **@{ctx.author.display_name}**. "
                       "Please be patient, this may take a few moments.")
        status_msg = await ctx.send("Status: Reading")
        try:
            # Owners are not affected by the limit.
            self.processing_users.append(ctx.author.id)
            start_time = time.time()
            loot_list, loot_image_overlay = await self.loot_scan(ctx, loot_image, status_msg)
            scan_time = time.time() - start_time
        except LootScanException as e:
            await ctx.error(e)
            return
        finally:
            self.processing_users.remove(ctx.author.id)
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_footer(text=f"Loot scanned in {scan_time:,.2f} seconds.")
        long_message = f"These are the results for your image: [{attachment.filename}]({attachment.url})"

        if len(loot_list) == 0:
            await ctx.error(f"Sorry {ctx.author.mention}, I couldn't find any loot in that image. Loot parsing will "
                            f"only work on high quality images, so make sure your image wasn't compressed.")
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
                        value += f"x{loot_list[item]['count']} {item}\n"
                    else:
                        with closing(wiki_db.cursor()) as c:
                            c.execute("""SELECT item.name FROM item
                                         LEFT JOIN item_attribute att on item_id = item.article_id
                                         WHERE item.name LIKE ? AND article_id = item_id AND att.name = 'imbuement'
                                         LIMIT 1""", (item,))
                            result = c.fetchone()
                        if result:
                            has_marketable = True
                            emoji = "💎"
                        else:
                            emoji = ""
                        value += "x{1} {0}{3} \u2192 {2:,}gp total\n".format(
                            item,
                            loot_list[item]['count'],
                            loot_list[item]['count'] * loot_list[item]['value_sell'],
                            emoji)

                    total_value += loot_list[item]['count'] * loot_list[item]['value_sell']
                    group_value += loot_list[item]['count'] * loot_list[item]['value_sell']
            if group == "No Value":
                name = group
            else:
                name = f"{group} - {group_value:,} gold"
            # Split into multiple fields if they exceed field max length
            split_group = split_message(value, FIELD_VALUE_LIMIT)
            for subgroup in split_group:
                if subgroup != split_group[0]:
                    name = "\u200F"
                embed.add_field(name=name, value=subgroup, inline=False)

        if unknown:
            long_message += f"\n**There were {unknown['count']} unknown items.**\n"

        long_message += f"\nThe total loot value is: **{total_value:,}** gold coins."
        if has_marketable:
            long_message += f"\n💎 Items marked with this are used in imbuements and might be worth " \
                            f"more in the market."
        embed.description = long_message
        embed.set_image(url="attachment://results.png")

        # Short message
        short_message = f"I've finished parsing your image {ctx.author.mention}." \
                        f"\nThe total value is {total_value:,} gold coins."
        if not await ctx.is_long():
            short_message += "\nI've also sent you a PM with detailed information."

        # Send on ask_channel or PM
        if await ctx.is_long():
            await ctx.send(short_message, embed=embed, file=discord.File(loot_image_overlay, "results.png"))
        else:
            try:
                await ctx.author.send(file=discord.File(loot_image_overlay, "results.png"), embed=embed)
            except discord.Forbidden:
                await ctx.error(f"{ctx.author.mention}, I tried pming you to send you the results, "
                                f"but you don't allow private messages from this server.\n"
                                f"Enable the option and try again, or try the command channel")
            else:
                await ctx.send(short_message)

    @checks.is_owner()
    @loot.command(name="add")
    async def loot_add(self, ctx: NabCtx, *, item: str):
        """Adds an image to an existing loot item in the database."""
        if len(ctx.message.attachments) == 0:
            return await ctx.error("You need to upload the image you want to add to this item.")

        attachment = ctx.message.attachments[0]
        if attachment.width != 32 or attachment.height != 32:
            return await ctx.send("Image size has to be 32x32.")

        try:
            with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    original_image = await resp.read()
            frame_image = Image.open(io.BytesIO(bytearray(original_image))).convert("RGBA")
        except Exception:
            await ctx.error("Either that wasn't an image or I failed to load it, please try again.")
            return

        result = await self.item_add(item, frame_image)
        if result is None:
            await ctx.error("Couldn't find an item with that name.")
            return
        else:
            await ctx.error("Image added to item.", file=discord.File(result, "results.png"))
            result, item = await self.item_show(item)
            if result is not None:
                await ctx.send("Name: {name}, Group: {group}, Value: {value:,}".format(**item[0]),
                               file=discord.File(result, "results.png"))
            return

    @loot.command(name="legend", aliases=["help", "symbols", "symbol"])
    async def loot_legend(self, ctx: NabCtx):
        """Shows the meaning of the overlayed icons."""
        with open("./images/legend.png", "r+b") as f:
            await ctx.send(file=discord.File(f))
            f.close()

    @checks.is_owner()
    @loot.command(name="new", usage="[item],[group],[id]")
    async def loot_new(self, ctx: NabCtx, *, params=None):
        """Adds a new item to the loot database."""
        if len(ctx.message.attachments) == 0:
            return await ctx.error("You need to upload the image you want to add to this item.")
        if params is None:
            return await ctx.error("Missing parameters (item name,group,id)")
        params = params.split(",")
        if not len(params) == 3:
            return await ctx.error("Wrong parameters (item name,group,id)")
        item, group, id = params
        item: tibiawikisql.models.Item = tibiawikisql.models.Item.get_by_field(wiki_db, "title", item, True)
        if item is None:
            return await ctx.error("No item found with that name.")
        if item.value_buy is None:
            item.value_buy = 0

        attachment = ctx.message.attachments[0]
        if attachment.width != 32 or attachment.height != 32:
            return await ctx.error("Image size has to be 32x32.")

        try:
            with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    original_image = await resp.read()
            frame_image = Image.open(io.BytesIO(bytearray(original_image))).convert("RGBA")
        except Exception:
            return await ctx.error("Either that wasn't an image or I failed to load it, please try again.")

        result = await self.item_new(item.title, frame_image, group, item.value_buy, 0, id)
        if result is None:
            return await ctx.error("Could not add new item.")
        else:
            await ctx.success("Image added to item.", file=discord.File(result, "results.png"))
            result, saved_item = await self.item_show(item.title)
            if result is not None:
                await ctx.send("Name: {name}, Group: {group}, Value: {value}, ID: {id}".format(**saved_item[0]),
                               file=discord.File(result, "results.png"))

    @checks.is_owner()
    @loot.command(name="remove", aliases=["delete", "del"])
    async def loot_remove(self, ctx: NabCtx, *, item: str):
        """Removes an item from the loot database."""
        result = await self.item_remove(item)
        if result is None:
            return await ctx.error("Couldn't find an item with that name.")
        await ctx.send("Item \"" + result + "\" removed from loot database.")

    @checks.is_owner()
    @loot.command(name="show")
    async def loot_show(self, ctx, *, item: str):
        """Shows item info from loot database."""
        result, item_list = await self.item_show(item)

        if not item_list:
            return await ctx.error("There's no item with that name.")
        item = item_list[0]
        embed = discord.Embed(title=item["name"], description=f"Group: {item['group']}")
        content = ""
        for item in item_list:
            content += "ID: {id} | Size: {sizeX}x{sizeY} | {size}px | rgb: {red},{green},{blue} | " \
                       "sell: {value_sell:,} | value_buy: {value_buy:,}\n".format(**item)
        fields = split_message(content, FIELD_VALUE_LIMIT)
        name = "Frame info"
        for i, field in enumerate(fields[:5]):
            if i:
                name = "\u200F"
            embed.add_field(name=name, value=field, inline=False)
        if len(fields) > 5:
            embed.set_footer(text="Too many frames to display all information.")
        embed.set_image(url="attachment://results.png")
        await ctx.send(embed=embed, file=discord.File(result, "results.png"))

    @classmethod
    def load_image(cls, image_bytes: bytes) -> Image.Image:
        """ Loads an image's bytes, into a PIL Image.

        :param image_bytes: The image's byte content.
        :return: Image object.
        """
        return Image.open(io.BytesIO(bytearray(image_bytes))).convert("RGBA")

    @classmethod
    async def update_status(cls, msg: discord.Message, status: str):
        """ Updates the status message.

        :param msg: The message to edit.
        :param status: The new message to set.
        """
        content = f"**Status:** {status}"
        try:
            await msg.edit(content=content)
        except discord.HTTPException:
            pass

    async def loot_scan(self, ctx: NabCtx, image: bytes, status_msg: discord.Message):
        try:
            loot_image = await ctx.execute_async(self.load_image, image)
        except Exception:
            raise LootScanException("Either that wasn't an image or I failed to load it, please try again.")

        await self.update_status(status_msg, "Detecting item slots")

        slot_list = await ctx.execute_async(self.find_slots, loot_image)
        if not slot_list:
            raise LootScanException("I couldn't find any inventory slots in your image."
                                    " Make sure your image is not stretched out or that overscaling is off.")
        loot_list = {}
        await self.update_status(status_msg, f"{len(slot_list)+1:,} slots found.\n"
                                             f"{config.loading_emoji} Identifying items...\n"
                                             f"Estimated time: {(len(slot_list)+1)*(sum(scan_speed)/10):.2f} seconds.")
        start_time = time.time()
        for i, found_slot in enumerate(slot_list):
            found_item = found_slot['image']
            found_item_number, item_number_image = await ctx.execute_async(self.number_scan, found_slot['image'])

            found_item.paste(number_blank, None, number_blank2.convert("RGBA"))
            found_item_clear = await ctx.execute_async(self.clear_background, found_item)
            found_item_clear = self.make_transparent(found_item_clear)

            found_item_crop = await ctx.execute_async(self.crop_item, found_item_clear)

            # Check if the slot is empty
            if found_item_crop is None:
                continue

            found_item_size = await ctx.execute_async(self.get_item_size, found_item_crop)
            found_item_color = await ctx.execute_async(self.get_item_color, found_item_crop)

            results = self.loot_conn.execute(
                "SELECT * FROM Items WHERE sizeX = ? AND sizeY = ?  AND size = ? "
                "AND red = ? AND green = ? AND blue = ?",
                (found_item_crop.size[0], found_item_crop.size[1], found_item_size,
                 found_item_color[0], found_item_color[1], found_item_color[2]))
            item_list = list(results)

            result = await ctx.execute_async(self.scan_item, found_item_clear, item_list)

            if result == "Unknown":
                unknown_image = await ctx.execute_async(self.clear_background, found_slot['image'])
                unknown_image_crop = await ctx.execute_async(self.crop_item, unknown_image, copy=True)
                unknown_image_size = await ctx.execute_async(self.get_item_size, unknown_image_crop)
                result = {'name': "Unknown",
                          'group': "Unknown",
                          'value_sell': 0,
                          'frame': unknown_image_crop,
                          'sizeX': unknown_image_crop.size[0],
                          'sizeY': unknown_image_crop.size[1],
                          'size': unknown_image_size}
                found_item_number = 1
            if isinstance(result, dict):
                if result['name'] in loot_list:
                    loot_list[result['name']]['count'] += found_item_number
                else:
                    loot_list[result['name']] = {'count': found_item_number, 'group': result['group'],
                                                 'value_sell': result['value_sell']}

                if result['group'] != "Unknown":
                    detect = pickle.loads(result['frame'])
                    detect = Image.open(io.BytesIO(bytearray(detect)))
                    loot_image.paste(slot['Normal'], (found_slot['x'], found_slot['y']))
                    detect = Image.alpha_composite(loot_image.crop(
                        (found_slot['x'] + 1, found_slot['y'] + 1, found_slot['x'] + 33, found_slot['y'] + 33)), detect)
                    if found_item_number > 1:
                        num = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
                        num.paste(item_number_image, (0, 20))
                        detect = Image.alpha_composite(detect, num)
                    loot_image.paste(detect, (found_slot['x'] + 1, found_slot['y'] + 1))

                overlay = Image.alpha_composite(
                    loot_image.crop((found_slot['x'], found_slot['y'], found_slot['x'] + 34, found_slot['y'] + 34)),
                    group_images.get(result['group'], group_images['Other']) if result['value_sell'] > 0 or result[
                        'group'] == "Unknown" else
                    group_images['NoValue'])
                loot_image.paste(overlay, (found_slot['x'], found_slot['y']))
        total_time = time.time() - start_time
        scan_speed.pop()
        scan_speed.insert(0, total_time/(len(slot_list)+1))
        await self.update_status(status_msg, "Complete!")
        img_byte_arr = io.BytesIO()
        await ctx.execute_async(loot_image.save, img_byte_arr, format="png")
        img_byte_arr = img_byte_arr.getvalue()
        return loot_list, img_byte_arr

    @classmethod
    def is_transparent(cls, pixel: Pixel) -> bool:
        """Checks if a pixel is transparent."""
        if len(pixel) < 4:
            return False
        return pixel[3] == 0

    @classmethod
    def is_number(cls, pixel: Pixel) -> bool:
        """Checks if a pixel is a number."""
        return cls.is_transparent(pixel) and pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 0

    @classmethod
    def is_white(cls, pixel: Pixel) -> bool:
        """Checks if a pixel is white"""
        return pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 255

    @classmethod
    def is_background_color(cls, pixel: Pixel) -> bool:
        low = 22
        high = 60
        color_diff = 15
        return (pixel[0] >= low and pixel[1] >= low and pixel[2] >= low) \
            and (pixel[0] <= high and pixel[1] <= high and pixel[2] <= high) \
            and max(abs(pixel[0] - pixel[1]), abs(pixel[0] - pixel[2]), abs(pixel[1] - pixel[2])) < color_diff

    @classmethod
    def is_empty(cls, pixel: Pixel):
        """Checks if a pixel can be considered empty."""
        return cls.is_white(pixel) or cls.is_transparent(pixel) or cls.is_number(pixel)

    @classmethod
    def crop_item(cls, item_image: Image.Image, *, copy=False) -> Optional[Image.Image]:
        """Removes the transparent border around item images.

        :param item_image: The item's image, with no slot background.
        :param copy: Whether to return a copy or alter the original
        :return: The cropped's item's image.
        """
        if item_image is None:
            return item_image
        # Top
        offset_top = 0
        px = 0
        py = 0
        # Clear reference to previous item
        if copy:
            item_image = item_image.copy()
        while py < item_image.size[1]:
            item_image_pixel = item_image.getpixel((px, py))
            if not (cls.is_empty(item_image_pixel)):
                offset_top = py
                break
            px += 1
            if px == item_image.size[0]:
                py += 1
                px = 0

        # Bottom
        offset_bottom = -1
        px = item_image.size[0] - 1
        py = item_image.size[1] - 1
        while py > 0:
            item_image_pixel = item_image.getpixel((px, py))
            if not (cls.is_empty(item_image_pixel)):
                offset_bottom = py
                break
            px -= 1
            if px == 0:
                py -= 1
                px = item_image.size[0] - 1

        # Left
        offset_left = 0
        px = 0
        py = 0
        while px < item_image.size[0]:
            item_image_pixel = item_image.getpixel((px, py))
            if not (cls.is_empty(item_image_pixel)):
                offset_left = px
                break
            py += 1
            if py == item_image.size[1]:
                px += 1
                py = 0
        # Right
        offset_right = -1
        px = item_image.size[0] - 1
        py = item_image.size[1] - 1
        while px > 0:
            item_image_pixel = item_image.getpixel((px, py))
            if not (cls.is_empty(item_image_pixel)):
                offset_right = px
                break
            py -= 1
            if py == 0:
                px -= 1
                py = item_image.size[1] - 1
        if offset_right == -1 or offset_bottom == -1:
            return None
        item_image = item_image.crop((offset_left, offset_top, offset_right + 1, offset_bottom + 1))
        return item_image

    @classmethod
    def number_scan(cls, slot_image: Image.Image) -> Tuple[int, Any]:
        """Scans a slot's image looking for amount digits

        :param slot_image: The image of an inventory slot.
        :return: A tuple containing the number parsed, the slot's image and the number's image.
        """
        digit_thousands = slot_image.crop((0, 20, 0 + 8, 20 + 7))
        digit_hundreds = slot_image.crop((8, 20, 8 + 8, 20 + 7))
        digit_tens = slot_image.crop((16, 20, 16 + 8, 20 + 7))
        digit_units = slot_image.crop((24, 20, 24 + 8, 20 + 7))
        item_numbers = [digit_thousands, digit_hundreds, digit_tens, digit_units]
        number_string = ""
        numbers_image = Image.new("RGBA", (32, 11), (255, 255, 255, 0))
        a = 0
        for item_number in item_numbers:
            i = 0
            for number in numbers:
                px = 0
                py = 0
                while py < item_number.size[1] and py < number.size[1]:
                    item_number_pixel = item_number.getpixel((px, py))
                    number_pixel = number.getpixel((px, py))
                    if not cls.is_transparent(number_pixel) and not item_number_pixel == number_pixel:
                        break
                    px += 1
                    if px == item_number.size[0] or px == number.size[0]:
                        py += 1
                        px = 0
                    if py == item_number.size[1]:
                        if i > 9:
                            i = "k"
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
            if not cls.is_transparent(numbers_image_pixel):
                slot_image.putpixel((px, py + 20), (255, 255, 0, 0))
            px += 1
            if px == numbers_image.size[0]:
                py += 1
                px = 0
        return 1 if number_string == "" else int(number_string.replace("k", "000")), numbers_image

    @classmethod
    def make_transparent(cls, slot_item: Image.Image):
        px = 0
        py = 0
        while py < slot_item.size[1] and py < 34:
            slot_item_pixel = slot_item.getpixel((px, py))
            if slot_item_pixel == (255, 0, 255, 255):
                slot_item.putpixel((px, py), (255, 0, 255, 0))
            px += 1
            if px == slot_item.size[0] or px == 34:
                py += 1
                px = 0
        return slot_item

    @classmethod
    def get_background_type(cls, lum):
        """Guesses background color based on a pixels luminosity
        """
        if 24 < lum < 52:
            return 'Normal'
        elif 89 < lum < 94:
            return 'Green'
        elif 98 < lum < 101:
            return 'Blue'
        elif 110 < lum < 113:
            return 'Violet'
        elif 114 < lum < 124:
            return 'Golden'
        elif 126 < lum < 131:
            return 'Gray'
        return 'Other'

    @classmethod
    def clear_background(cls, slot_item: Image.Image, *, copy=False) -> Image.Image:
        """Clears the slot's background of an image.

        :param slot_item: The slot's image.
        :param copy: Whether to create a copy or alter the original.

        :returns: The item's image without the slot's background.
        """
        px = 0
        py = 0
        if copy:
            slot_item = slot_item.copy()

        background = {'Normal': 0, 'Gray': 0, 'Green': 0, 'Blue': 0, 'Violet': 0, 'Golden': 0, 'Other': -255}
        for i in range(0, 32):
            pixel = slot_item.getpixel((i, 0))
            lum = (0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2])
            background[cls.get_background_type(lum)] += 1
        for i in range(0, 32):
            pixel = slot_item.getpixel((0, i))
            lum = (0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2])
            background[cls.get_background_type(lum)] += 1
        for i in range(0, 32):
            pixel = slot_item.getpixel((31, i))
            lum = (0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2])
            background[cls.get_background_type(lum)] += 1
        # no point checking the last row since its always blanked out
        # for i in range(0, 32):
        #     pixel = slot_item.getpixel((i, 31))
        #     lum = (0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2])
        #     background[get_background_type(lum)]+=1
        background_type = max(background.items(), key=operator.itemgetter(1))[0]
        while py < slot_item.size[1] and py < slot[background_type].size[1]:
            slot_item_pixel = slot_item.getpixel((px, py))
            slot_pixel = slot[background_type].getpixel((px + 1, py + 1))
            if slot_item_pixel[:3] == slot_pixel[:3]:
                slot_item.putpixel((px, py), (255, 0, 255, 0))
            px += 1
            if px == slot_item.size[0] or px == slot[background_type].size[0]:
                py += 1
                px = 0
        return slot_item

    @classmethod
    def get_item_size(cls, item: Image.Image) -> int:
        """Gets the actual size of an item in pixels."""
        size = item.size[0] * item.size[1]
        empty = 0
        px = 0
        py = 0
        while py < item.size[1]:
            item_pixel = item.getpixel((px, py))
            if not cls.is_empty(item_pixel):
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
            if not cls.is_empty(item_pixel):
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

    @classmethod
    def get_item_color(cls, item: Image.Image) -> Tuple[int, int, int]:
        """Gets the average color of an item.

        :param item: The item's image
        :return: The item's colors
        """
        count = 0
        px = 0
        py = 0
        color = [0, 0, 0]
        while py < item.size[1]:
            item_pixel = item.getpixel((px, py))
            if not (cls.is_empty(item_pixel) or cls.is_background_color(item_pixel)):
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
        return int(color[0]), int(color[1]), int(color[2])

    @classmethod
    def scan_item(cls, slot_item: Image.Image, item_list: List[Dict[str, Any]]) -> \
            Union[Dict[str, Union[str, int]], str]:
        """Scans an item's image, and looks for it among similar items in the database.

        :param slot_item: The item's cropped image.
        :param item_list: The list of similar items.
        :return: The matched item, represented in a dictionary.
        """
        results = {}
        if slot_item is None:
            return "Empty"
        for item in item_list:
            if item['id'] in results:
                continue
            item_image = pickle.loads(item['frame'])
            item_image = Image.open(io.BytesIO(bytearray(item_image)))
            px = 0
            py = 0
            while py < slot_item.size[1] and py < item_image.size[1]:
                slot_item_pixel = slot_item.getpixel((px, py))
                item_pixel = item_image.getpixel((px, py))
                if cls.is_empty(item_pixel) == cls.is_empty(slot_item_pixel):
                    pass
                elif cls.is_empty(slot_item_pixel):
                    if not cls.is_number(slot_item_pixel):
                        break
                elif cls.is_empty(item_pixel) or item_pixel != slot_item_pixel:
                    break

                px += 1
                if px == slot_item.size[0] or px == item_image.size[0]:
                    py += 1
                    px = 0
                if py == slot_item.size[1] or py == item_image.size[1]:
                    return item

        return "Unknown"

    @classmethod
    def find_slots(cls, loot_image: Image) -> List[Dict[str, Any]]:
        """Scans through an image, looking for inventory slots

        :param loot_image: An inventory screenshot
        :return: A list of dictionaries, containing the images and coordinates for every slot.
        """
        image_copy = loot_image.copy()
        loot_bytes = loot_image.tobytes()
        slot_list = []
        if loot_image.size[0] < 34 or loot_image.size[1] < 27:
            return slot_list

        x = -1
        y = 0
        skip = False
        for _ in loot_bytes:
            x += 1
            if x + 34 > image_copy.size[0]:
                y += 1
                x = 0
            if y + 27 > image_copy.size[1]:
                break
            if skip:
                # Skip every other pixel to save time
                skip = False
            else:
                if x + 34 != image_copy.size[0]:
                    # Can't skip the last part of an image
                    skip = True
                if image_copy.getpixel((x, y)) == slot_border[0]:
                    # If the current pixel looks like a slot
                    s = 0
                    diff = 0
                    diffmax = 1  # 3/4's of the border size
                    xs = 0
                    ys = 0

                    if x != 0 and image_copy.getpixel((x - 1, y)) == slot_border[0]:
                        # Make sure we didnt skip the beggining of a slot
                        # go back if we did
                        x -= 1
                        # We also flag the next pixel to avoid looping here forever if this turns out not to be a slot
                        image_copy.putpixel((x + 1, y), (255, 0, 255, 0))
                    while diff < diffmax:
                        if xs == 0 or xs == 33 or ys == 0 or ys == 33:
                            if not image_copy.getpixel((x + xs, y + ys)) == slot_border[s] \
                                and image_copy.getpixel((x + xs, y + ys)) not in [(24, 24, 24, 255),
                                                                                  (55, 55, 55, 255),
                                                                                  (57, 57, 57, 255),
                                                                                  (75, 76, 76, 255),
                                                                                  (255, 0, 255, 0)]:
                                # ^ This is a workaround to ignore the bottom-left border of containers
                                # as well as make the skipping work correctly
                                    break
                        s += 1
                        xs += 1
                        if xs == 34:
                            xs = 0
                            ys += 1
                        if ys == 28:
                            slot_list.append({'image': loot_image.crop((x + 1, y + 1, x + 33, y + 33)), 'x': x, 'y': y})
                            image_copy.paste(Image.new("RGBA", (34, 34), (255, 255, 255, 255)), (x, y))
                            x += 33
                            break
        return slot_list

    async def item_show(self, item: str) -> Tuple[bytes, list]:
        c = self.loot_conn.execute("SELECT * FROM Items WHERE name LIKE ?", (item,))
        item_list = c.fetchall()
        if len(item_list) == 0:
            return b'', []
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
        return img_byte_arr, item_list

    async def item_remove(self, item):
        c = self.loot_conn.execute("SELECT * FROM Items WHERE name LIKE ?", (item,))
        item_list = c.fetchall()
        if len(item_list) == 0:
            return None
        c.execute("DELETE FROM Items WHERE name LIKE ?", (item,))
        return item_list[0]["name"]

    async def item_add(self, item, frame):
        c = self.loot_conn.execute("SELECT * FROM Items WHERE name LIKE ?", (item,))
        item_list = c.fetchall()
        if len(item_list) == 0:
            return None
        frame_crop = self.crop_item(frame)
        frame_color = self.get_item_color(frame)
        frame_size = self.get_item_size(frame_crop)
        frame__byte_arr = io.BytesIO()
        frame.save(frame__byte_arr, format='PNG')
        frame__byte_arr = frame__byte_arr.getvalue()
        frame_str = pickle.dumps(frame__byte_arr)
        with self.loot_conn as conn:
            conn.execute("INSERT INTO Items(name,`group`,id,\
                                            value_sell,value_buy,frame,\
                                            sizeX,sizeY,size,\
                                            red,green,blue) "
                         "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (item_list[0]["name"], item_list[0]["group"], item_list[0]["id"],
                          item_list[0]["value_sell"], item_list[0]["value_buy"], frame_str,
                          frame_crop.size[0], frame_crop.size[1], frame_size,
                          frame_color[0], frame_color[1], frame_color[2]))

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

    async def item_new(self, item, frame, group, value_sell, value_buy, item_id):
        if item is None or group is None:
            return None

        c = self.loot_conn.execute("SELECT * FROM Items  WHERE name LIKE ?", (item,))
        item_list = c.fetchall()
        if not len(item_list) == 0:
            return None

        frame_crop = self.crop_item(frame)
        frame_color = self.get_item_color(frame)
        frame_size = self.get_item_size(frame_crop)
        frame__byte_arr = io.BytesIO()
        frame.save(frame__byte_arr, format='PNG')
        frame__byte_arr = frame__byte_arr.getvalue()
        frame_str = pickle.dumps(frame__byte_arr)
        with self.loot_conn as conn:
            conn.execute("INSERT INTO Items(name,`group`,id,\
                                            value_sell,value_buy,frame,\
                                            sizeX,sizeY,size,\
                                            red,green,blue) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (item, group, item_id,
                          value_sell, value_buy, frame_str,
                          frame_crop.size[0], frame_crop.size[1], frame_size,
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


def setup(bot):
    bot.add_cog(Loot(bot))
