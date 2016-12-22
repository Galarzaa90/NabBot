from PIL import Image
import asyncio
import io
import pickle
import os
from utils.database import lootDatabase
from utils.messages import EMOJI

slot = Image.open("loot/images/slot.PNG")
slot_border = Image.open("loot/images/slotborder.PNG").convert("RGBA").getdata()
numbers = [Image.open("loot/images/0.PNG"),
           Image.open("loot/images/1.PNG"),
           Image.open("loot/images/2.PNG"),
           Image.open("loot/images/3.PNG"),
           Image.open("loot/images/4.PNG"),
           Image.open("loot/images/5.PNG"),
           Image.open("loot/images/6.PNG"),
           Image.open("loot/images/7.PNG"),
           Image.open("loot/images/8.PNG"),
           Image.open("loot/images/9.PNG")]


def is_transparent(pixel):
    if len(pixel) < 4:
        return False
    return pixel[3] == 0


def is_number(pixel):
    return is_transparent(pixel) and pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 0


def is_white(pixel):
    return pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 255


def is_background_color(pixel, quality):
    low = max(0, 22-quality*2)
    high = min(80, 60+quality)
    colordiff = min(15, 8+quality)
    return (pixel[0] >= low and pixel[1] >= low and pixel[2] >= low) \
           and (pixel[0] <= high and pixel[1] <= high and pixel[2] <= high) \
           and max(abs(pixel[0]-pixel[1]), abs(pixel[0]-pixel[2]), abs(pixel[1]-pixel[2])) < colordiff


def is_empty(pixel):
    return is_white(pixel) or is_transparent(pixel) or is_number(pixel)


def pixel_diff(pixel1, pixel2):
    return abs(pixel1[0]-pixel2[0])+abs(pixel1[1]-pixel2[1])+abs(pixel1[2]-pixel2[2])


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
            offsety2=py
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


def numberScan(itemImage):
    number1 = itemImage.crop((7, 21, 7+8, 21+10))
    number2 = itemImage.crop((15, 21, 15+8, 21+10))
    number3 = itemImage.crop((23, 21, 23+8, 21+10))
    itemNumbersImage = itemImage.crop((7, 21, 7+8*3, 21+10))
    item_numbers = [number1, number2, number3]
    number_string = ""
    numbers_image = Image.new("RGBA", (24, 10), (255, 255, 255, 0))
    a = 0
    for item_number in item_numbers:
        i = 0
        for number in numbers:
            px = 0
            py = 0
            while py<item_number.size[1] and py < number.size[1]:
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
                    numbers_image.paste(number, (8*a, 0))
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
            itemImage.putpixel((px+7, py+21), (255, 255, 0, 0))
        px += 1
        if px == numbers_image.size[0]:
            py += 1
            px = 0
    return 1 if number_string == "" else int(number_string), itemImage, numbers_image


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
    size = item.size[0]*item.size[1]
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
                size -= empty-1
                empty = 0
                px = 0
                py += 1

    empty = 0
    px = item.size[0]-1
    py = 0
    while py < item.size[1]:
        item_pixel = item.getpixel((px, py))
        if not is_empty(item_pixel):
            size -= empty
            empty = 0
            px = item.size[0]-1
            py += 1
        else:
            empty += 1
            px -= 1
            if px == -1:
                empty = 0
                px = item.size[0]-1
                py += 1
    return size


def get_item_color(item):
    count = 0
    px = 0
    py = 0
    color = [0, 0, 0]
    while py < item.size[1]:
        item_pixel = item.getpixel((px,py))
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


@asyncio.coroutine
def slot_scan(slot_item, slot_item_size, item_list, group_list, quality):
    if slot_item is None:
        return "Empty"
    if quality < 5:
        quality = 5
    item_list = sorted(item_list, key=lambda k: min(max(k['value'], 1000), 1) + ((k['priority'] + group_list.get(k['group'], 0)) / 100), reverse=True)
    non_empty_size = get_item_size(slot_item)
    mismatch_threshold = non_empty_size*(quality*2)
    silhouette_threshold = non_empty_size*(quality*0.006)
    for item in item_list:
        yield from asyncio.sleep(0.0001)
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
        while py < slot_item.size[1] and py<item_image.size[1]:
            slot_item_pixel = slot_item.getpixel((px, py))
            item_pixel = item_image.getpixel((px, py))
            if is_empty(item_pixel) == is_empty(slot_item_pixel) is True:
                sillhouette += 0
            elif is_empty(item_pixel) == is_empty(slot_item_pixel) is False:
                pixeldiff = pixel_diff(slot_item_pixel, item_pixel)
                if pixeldiff > quality*6:
                    missmatch += pixeldiff
            elif is_empty(slot_item_pixel):
                if is_background_color(item_pixel, quality+10):
                    sillhouette += 0
                elif is_number(slot_item_pixel):
                    sillhouette += 0
                else:
                    sillhouette += 1
            elif is_empty(item_pixel):
                sillhouette += 1
            
            if missmatch > mismatch_threshold or sillhouette > silhouette_threshold:
                break
            
            px+=1
            if px == slot_item.size[0] or px == item_image.size[0]:
                py+=1
                px=0
            if py == slot_item.size[1] or py == item_image.size[1]:
                if item['name'] == "Unknown":
                    return item
                item['priority'] += 400
                return item
    return "Unknown"


@asyncio.coroutine
def find_slots(bot, loot_image, progress_bar):
    _lootImage = loot_image.copy()
    loot_bytes = loot_image.tobytes()
    slot_list = []
    if loot_image.size[0] < 34 or loot_image.size[1] < 34:
        return slot_list

    if len(loot_bytes) > 2312:
        progress_percent = 0
        percent_message = ""
        percent_message += EMOJI[":black_square_button:"]*progress_percent
        percent_message += EMOJI[":black_large_square:"]*(10-progress_percent)
        yield from bot.edit_message(progress_bar, percent_message)
    x = -1
    y = 0
    skip = False
    for loot_pixel in loot_bytes:
        x+=1
        if x+34 > _lootImage.size[0]:
            if len(loot_bytes) > 2312:
                if int(y/_lootImage.size[1]*100/10) != progress_percent:
                    progress_percent = int(y/_lootImage.size[1]*100/10)
                    percent_message = ""
                    percent_message += EMOJI[":black_square_button:"]*progress_percent
                    percent_message += EMOJI[":black_large_square:"]*(10-progress_percent)
                    yield from bot.edit_message(progress_bar, percent_message)
            y += 1
            x = 0
            yield from asyncio.sleep(0.0001)
        if y+34 > _lootImage.size[1]:
            break
        if skip:
            # Skip every other pixel to save time
            skip = False
        else:
            if x+34 != _lootImage.size[0]:
                # Can't skip the last part of an image
                skip = True
            if pixel_diff(_lootImage.getpixel((x, y)), slot_border[0]) <= 5:
                # If the current pixel looks like a slot
                s = 0
                diff = 0
                diffmax = 132*0.3  # 3/4's of the border size
                xs = 0
                ys = 0
                
                if x != 0 and pixel_diff(_lootImage.getpixel((x-1, y)), slot_border[0]) <= 5:
                    # Make sure we didnt skip the beggining of a slot
                    # go back if we did
                    x-=1
                    # We also set the next pixel white to avoid looping here forever if this turns out not to be a slot
                    _lootImage.putpixel((x+1, y), (255, 255, 255, 255))
                    # and increase the diffmax by one pixel to compensate
                    diffmax += 1
                while diff <= diffmax:
                    if xs == 0 or xs == 33 or ys == 0 or ys == 33:
                        if not pixel_diff(_lootImage.getpixel((x+xs, y+ys)), slot_border[s]) == 0:
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


@asyncio.coroutine
def loot_scan(bot, loot_image, image_name, progress_msg, progress_bar):
    debug_output = image_name
    debug_outputex = 0
    while os.path.exists("loot/debug/"+str(debug_outputex)+"_"+debug_output):
        debug_outputex += 1
    debug_output = str(debug_outputex)+"_"+debug_output
    
    loot_image_original = loot_image.copy()
    groupimages = {'Green Djinn':Image.open("loot/images/Green Djinn.PNG"),
                   'Blue Djinn':Image.open("loot/images/Blue Djinn.PNG"),
                   'Rashid': Image.open("loot/images/Rashid.PNG"),
                   'Yasir': Image.open("loot/images/Yasir.PNG"),
                   'Tamoril': Image.open("loot/images/Tamoril.PNG"),
                   'Jewels': Image.open("loot/images/Jewels.PNG"),
                   'Gnomission': Image.open("loot/images/Gnomission.PNG"),
                   'Other': Image.open("loot/images/Other.PNG"),
                   'NoValue': Image.open("loot/images/NoValue.PNG"),
                   'Unknown': Image.open("loot/images/Unknown.PNG")}

    yield from bot.edit_message(progress_msg, "Status: Detecting item slots.")
    slot_list = yield from find_slots(bot, loot_image, progress_bar)
    c = lootDatabase.cursor()
    group_list = {}
    loot_list = {}
    unknown_items_list = []
    lq_items_list = []
    progress = 0
    progress_percent = 0
    percent_message = ""
    quality_warning = 0
    percent_message += EMOJI[":black_square_button:"]*progress_percent
    percent_message += EMOJI[":black_large_square:"]*(10-progress_percent)
    yield from bot.edit_message(progress_msg, "Status: Scanning items.")
    yield from bot.edit_message(progress_bar, percent_message)
    for found_slot in slot_list:
        found_item_number, found_item, item_number_image = numberScan(found_slot['image'])
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
                      (found_item_crop.size[0], found_item_crop.size[1], found_item_size, 10, found_item_color[0], found_item_color[1], found_item_color[2], 60+quality*2,))
            
            item_list = c.fetchall()
            for unknownItem in unknown_items_list:
                if abs(unknownItem['sizeX'] - found_item_crop.size[0]) <= 3 and abs(unknownItem['sizeY'] - found_item_crop.size[1]) <= 3:
                    item_list.append(unknownItem)
            if quality == 0:
                for lq_item in lq_items_list:
                    if abs(lq_item['sizeX'] - found_item_crop.size[0]) <= 3 and abs(lq_item['sizeY'] - found_item_crop.size[1]) <= 3:
                        item_list.append(lq_item)
            result = yield from slot_scan(found_item_crop, found_item_crop.size, item_list, group_list, quality)
            quality += max(2, int(quality/2))

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
            if not os.path.exists("loot/debug/"+debug_output):
                os.makedirs("loot/debug/"+debug_output)
                loot_image_original.save("loot/debug/" + debug_output +"/" + image_name, "PNG")
            filename = "Unknown"
            filenameex = 0
            while os.path.isfile("loot/debug/"+debug_output+"/"+str(filenameex)+"_"+filename+".png"):
                filenameex += 1
            # Save with background
            loot_image.crop((found_slot['x'] + 1, found_slot['y'] + 1, found_slot['x'] + 33, found_slot['y'] + 33)).save("loot/debug/" + debug_output + "/" + str(filenameex) + "_" + filename + ".png", "PNG")
            # Save without background
            unknown_image.save("loot/debug/"+debug_output+"/"+str(filenameex)+"_"+filename+"-clean.png","PNG")
        if type(result) == dict:
            if quality > 2 and not result in unknown_items_list and not result in lq_items_list:
                quality_warning += 1
                if quality_warning == 5:
                    yield from bot.send_message(progress_bar.channel,"WARNING: You seem to be using a low quality image, or a screenshot taken using Tibia's **software** renderer. Some items may not be recognized correctly, and overall scanning speed will be slower!")
                lq_item = result
                img_byte_arr = io.BytesIO()
                qz_item.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                lq_item['original'] = result['frame']
                lq_item['frame'] = pickle.dumps(img_byte_arr)
                lq_item['sizeX'] = qz_item_crop.size[0]
                lq_item['sizeY'] = qz_item_crop.size[1]
                lq_items_list.append(lq_item)
            
            if result['name'] in loot_list:
                loot_list[result['name']]['count']+= found_item_number
            else:
                loot_list[result['name']] = {'count':found_item_number,'group':result['group'],'value':result['value']}
            
            if result['group'] != "Unknown":
                group_list[result['group']] = group_list.get(result['group'],0)+100
                c.execute("UPDATE Items SET priority = priority+4 WHERE `name` = ?",(result['name'],))
                c.execute("UPDATE Items SET priority = priority+1 WHERE `group` = ?",(result['group'],))
            
            if result['group'] != "Unknown":
                if result not in lq_items_list:
                    detect = pickle.loads(result['frame'])
                else:
                    detect = pickle.loads(result['original'])
                detect = Image.open(io.BytesIO(bytearray(detect)))
                loot_image.paste(slot, (found_slot['x'], found_slot['y']))
                detect = Image.alpha_composite(loot_image.crop((found_slot['x'] + 1, found_slot['y'] + 1, found_slot['x'] + 33, found_slot['y'] + 33)), detect)
                if found_item_number > 1:
                    num = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
                    num.paste(item_number_image, (7, 21))
                    detect = Image.alpha_composite(detect, num)
                loot_image.paste(detect, (found_slot['x'] + 1, found_slot['y'] + 1))
            
            overlay = Image.alpha_composite(loot_image.crop((found_slot['x'], found_slot['y'], found_slot['x'] + 34, found_slot['y'] + 34)), groupimages.get(result['group'], groupimages['Other']) if result['value'] > 0 or result['group'] == "Unknown" else groupimages['NoValue'])
            loot_image.paste(overlay, (found_slot['x'], found_slot['y']))
            
        
        progress += 1
        if int(progress/len(slot_list)*100/10) != progress_percent:
            progress_percent = int(progress/len(slot_list)*100/10)
            percent_message = ""
            percent_message += EMOJI[":black_square_button:"] * progress_percent
            percent_message += EMOJI[":black_large_square:"] * (10 - progress_percent)
            yield from bot.edit_message(progress_msg, "Status: Scanning items (" + str(progress) + "/" + str(len(slot_list)) + ").")
            yield from bot.edit_message(progress_bar, percent_message)
        yield from asyncio.sleep(0.005)
    yield from bot.edit_message(progress_msg, "Status: Complete!")
    c.close()
    lootDatabase.commit()
    img_byte_arr = io.BytesIO()
    loot_image.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()
    return loot_list, img_byte_arr
