from PIL import Image
import asyncio
import io
import pickle
import os
from utils.database import lootDatabase
slot = Image.open("loot/images/slot.PNG")
slotborder = Image.open("loot/images/slotborder.PNG").convert("RGBA").getdata()
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

def isTransparent(pixel):
    if len(pixel) < 4:
        return False
    return pixel[3] == 0

def isNumber(pixel):
    return isTransparent(pixel) and pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 0

def isWhite(pixel):
    return pixel[0] == 255 and pixel[1] == 255 and pixel[2] == 255

def isBackgroundColor(pixel,quality):
    low = max(0,22-quality*2)
    high = min(80,60+quality)
    colordiff = min(15,8+quality)
    return (pixel[0] >= low and pixel[1] >= low and pixel[2] >= low) and (pixel[0] <= high and pixel[1] <= high and pixel[2] <= high) and max(abs(pixel[0]-pixel[1]),abs(pixel[0]-pixel[2]),abs(pixel[1]-pixel[2])) < colordiff

def isEmpty(pixel):
    return isWhite(pixel) or isTransparent(pixel) or isNumber(pixel)

def pixelDiff(pixel1,pixel2):
    return abs(pixel1[0]-pixel2[0])+abs(pixel1[1]-pixel2[1])+abs(pixel1[2]-pixel2[2])

def cropItem(itemImage):
    if itemImage is None:
        return itemImage,[0,0]
    #top
    offsety = 0
    px = 0
    py = 0
    while py<itemImage.size[1]:
        itemImagePixel = itemImage.getpixel((px,py))
        if not (isEmpty(itemImagePixel)):
            offsety=py
            break
        px+=1
        if px == itemImage.size[0]:
            py+=1
            px=0
    #bottom
    offsety2 = -1
    px = itemImage.size[0]-1
    py = itemImage.size[1]-1
    while py>0:
        itemImagePixel = itemImage.getpixel((px,py))
        if not (isEmpty(itemImagePixel)):
            offsety2=py
            break
        px-=1
        if px == 0:
            py-=1
            px=itemImage.size[0]-1
    #left
    offsetx = 0
    px = 0
    py = 0
    while px<itemImage.size[0]:
        itemImagePixel = itemImage.getpixel((px,py))
        if not (isEmpty(itemImagePixel)):
            offsetx=px
            break
        py+=1
        if py == itemImage.size[1]:
            px+=1
            py=0
    #right
    offsetx2 = -1
    px = itemImage.size[0]-1
    py = itemImage.size[1]-1
    while px>0:
        itemImagePixel = itemImage.getpixel((px,py))
        if not (isEmpty(itemImagePixel)):
            offsetx2=px
            break
        py-=1
        if py == 0:
            px-=1
            py=itemImage.size[1]-1
    if offsetx2 == -1 or offsety2 == -1:
        return None,[0,0]
    itemImage = itemImage.crop((offsetx,offsety,offsetx2+1,offsety2+1))
    return itemImage

def numberScan(itemImage):
    number1 = itemImage.crop((7,21,7+8,21+10))
    number2 = itemImage.crop((15,21,15+8,21+10))
    number3 = itemImage.crop((23,21,23+8,21+10))
    itemNumbersImage = itemImage.crop((7,21,7+8*3,21+10))
    itemNumbers = [number1,number2,number3]
    numberString = ""
    numbersImage = Image.new("RGBA",(24,10),(255,255,255,0))
    a = 0
    for itemNumber in itemNumbers:
        i = 0
        for number in numbers:
            px = 0
            py = 0
            while py<itemNumber.size[1] and py<number.size[1]:
                itemNumberPixel = itemNumber.getpixel((px,py))
                numberPixel = number.getpixel((px,py))
                if not isTransparent(numberPixel):
                    if not pixelDiff(itemNumberPixel,numberPixel) == 0:
                        break
                px+=1
                if px == itemNumber.size[0] or px == number.size[0]:
                    py+=1
                    px=0
                if py == itemNumber.size[1]:
                    numberString += str(i)
                    numbersImage.paste(number,(8*a,0))
                    i = -1
                    break
            if i == -1:
                break
            i+=1
        a+=1
    px = 0
    py = 0
    while py<numbersImage.size[1]:
        numbersImagePixel = numbersImage.getpixel((px,py))
        if not isTransparent(numbersImagePixel):
            itemImage.putpixel((px+7,py+21),(255,255,0,0))
        px+=1
        if px == numbersImage.size[0]:
            py+=1
            px=0
    return 1 if numberString == "" else int(numberString),itemImage,numbersImage

def clearBackground(slotItem,quality=0):
    px = 0
    py = 0
    while py<slotItem.size[1] and py<slot.size[1]:
        slotItemPixel = slotItem.getpixel((px,py))
        slotPixel = slot.getpixel((px+1+(32-slotItem.size[0]),py+1+(32-slotItem.size[1])))
        if pixelDiff(slotItemPixel,slotPixel) <= quality:
            slotItem.putpixel((px,py),(slotItemPixel[0],slotItemPixel[1],slotItemPixel[2],0))
        px+=1
        if px == slotItem.size[0] or px == slot.size[0]:
            py+=1
            px=0
    return slotItem
def getItemSize(item):
    size = item.size[0]*item.size[1]
    empty = 0
    px = 0
    py = 0
    while py<item.size[1]:
        itemPixel = item.getpixel((px,py))
        if not isEmpty(itemPixel):
            size-=empty
            empty=0
            px=0
            py+=1
        else:
            empty+=1
            px+=1
            if px == item.size[0]:
                size-=empty-1
                empty=0
                px=0
                py+=1

    empty = 0
    px = item.size[0]-1
    py = 0
    while py<item.size[1]:
        itemPixel = item.getpixel((px,py))
        if not isEmpty(itemPixel):
            size-=empty
            empty=0
            px=item.size[0]-1
            py+=1
        else:
            empty+=1
            px-=1
            if px == -1:
                empty=0
                px=item.size[0]-1
                py+=1
    return size
    
def getItemColor(item):
    count = 0
    px = 0
    py = 0
    color = [0,0,0]
    while py<item.size[1]:
        itemPixel = item.getpixel((px,py))
        if not (isEmpty(itemPixel) or isBackgroundColor(itemPixel,15)):
            color[0]+=itemPixel[0]
            color[1]+=itemPixel[1]
            color[2]+=itemPixel[2]
            count+=1
        px+=1
        if px == item.size[0]:
            px=0
            py+=1
    if count == 0:
        return (0,0,0)
    color[0]/=count
    color[1]/=count
    color[2]/=count
    return (int(color[0])-int(color[1]),int(color[0])-int(color[2]),int(color[1])-int(color[2]))

@asyncio.coroutine
def slotScan(slotItem,slotItemSize,itemList,groupList,quality):
    if slotItem is None:
        return "Empty"
    if quality < 5:
        quality = 5
    itemList = sorted(itemList, key=lambda k: min(max(k['value'],1000),1)+((k['priority']+groupList.get(k['group'],0))/100),reverse=True)
    nonEmptySize = getItemSize(slotItem)
    missmatch_threshold = nonEmptySize*(quality*2)
    sillhouette_threshold = nonEmptySize*(quality*0.006)
    for item in itemList:
        yield from asyncio.sleep(0.0001)
        if item['name'] == "Unknown":
            itemImage = item['frame']
        else:
            itemImage = pickle.loads(item['frame'])
            itemImage = Image.open(io.BytesIO(bytearray(itemImage)))
            itemImage = cropItem(itemImage)
        px = 0
        py = 0
        missmatch = 0
        sillhouette = 0
        while py<slotItem.size[1] and py<itemImage.size[1]:
            slotItemPixel = slotItem.getpixel((px,py))
            itemPixel = itemImage.getpixel((px,py))
            if isEmpty(itemPixel) == isEmpty(slotItemPixel) == True:
                sillhouette+=0
            elif isEmpty(itemPixel) == isEmpty(slotItemPixel) == False:
                pixeldiff = pixelDiff(slotItemPixel,itemPixel)
                if pixeldiff > quality*6:
                    missmatch+=pixeldiff
            elif isEmpty(slotItemPixel):
                if isBackgroundColor(itemPixel,quality+10):
                    sillhouette+=0
                elif isNumber(slotItemPixel):
                    sillhouette+=0
                else:
                    sillhouette+=1
            elif isEmpty(itemPixel):
                sillhouette+=1
            
            if missmatch > missmatch_threshold or sillhouette > sillhouette_threshold:
                break
            
            px+=1
            if px == slotItem.size[0] or px == itemImage.size[0]:
                py+=1
                px=0
            if py == slotItem.size[1] or py == itemImage.size[1]:
                if item['name'] == "Unknown":
                    return item
                item['priority']+=400
                return item
    return "Unknown"

@asyncio.coroutine
def findSlots(bot,lootImage,progressBar):
    _lootImage = lootImage.copy()
    lootbytes = lootImage.tobytes()
    slotList = []
    if lootImage.size[0] < 34 or lootImage.size[1] < 34:
        return slotList

    if len(lootbytes) > 2312:
        progress_percent = 0
        percentmessage = ""
        for _p in range(0,progress_percent): percentmessage+=":black_square_button:"
        for _p in range(0,10-progress_percent): percentmessage+=":black_large_square:"
        yield from bot.edit_message(progressBar,percentmessage)
    x = -1
    y = 0
    skip = False
    for loot_pixel in lootbytes:
        x+=1
        if x+34 > _lootImage.size[0]:
            if len(lootbytes) > 2312:
                if int(y/_lootImage.size[1]*100/10) != progress_percent:
                    progress_percent = int(y/_lootImage.size[1]*100/10)
                    percentmessage = ""
                    for _p in range(0,progress_percent): percentmessage+=":black_square_button:"
                    for _p in range(0,10-progress_percent): percentmessage+=":black_large_square:"
                    yield from bot.edit_message(progressBar,percentmessage)
            y+=1
            x=0
            yield from asyncio.sleep(0.0001)
        if y+34 > _lootImage.size[1]:
            break
        if skip:
            #skip every other pixel to save time
            skip = False
        else:
            if x+34 != _lootImage.size[0]:
                #cant skip the last part of an image
                skip = True
            if pixelDiff(_lootImage.getpixel((x,y)),slotborder[0]) <= 5:
                #if the current pixel looks like a slot
                s = 0
                diff = 0
                diffmax = 132*0.3 #3/4's of the border size
                xs = 0
                ys = 0
                
                if x != 0 and pixelDiff(_lootImage.getpixel((x-1,y)),slotborder[0]) <= 5:
                    #make sure we didnt skip the beggining of a slot
                    #go back if we did
                    x-=1
                    #we also set the next pixel as white to avoid looping here forever if this turns out not to be a slot
                    _lootImage.putpixel((x+1,y),(255,255,255,255))
                    #and increase the diffmax by one pixel to compensate
                    diffmax+=1
                while diff <= diffmax:
                    if xs == 0 or xs == 33 or ys == 0 or ys == 33:
                        if not pixelDiff(_lootImage.getpixel((x+xs,y+ys)),slotborder[s]) == 0:
                            diff+=1
                    s+=1
                    xs+=1
                    if xs == 34:
                        xs = 0
                        ys+=1
                    if ys == 34:
                        slotList.append({'image': lootImage.crop((x+1,y+1,x+33,y+33)),'x': x,'y': y})
                        _lootImage.paste(Image.new("RGBA",(34,34),(255,255,255,255)),(x,y))
                        x+=33
                        break
    return slotList

@asyncio.coroutine
def lootScan(bot,lootImage,imageName,progressMsg,progressBar):
    debug_output = imageName
    debug_outputex = 0
    while os.path.exists("loot/debug/"+str(debug_outputex)+"_"+debug_output):
        debug_outputex+=1
    debug_output = str(debug_outputex)+"_"+debug_output
    
    lootImageOriginal = lootImage.copy()
    groupimages = {'Green Djinn':Image.open("loot/images/Green Djinn.PNG"),
                    'Blue Djinn':Image.open("loot/images/Blue Djinn.PNG"),
                    'Rashid':Image.open("loot/images/Rashid.PNG"),
                    'Yasir':Image.open("loot/images/Yasir.PNG"),
                    'Tamoril':Image.open("loot/images/Tamoril.PNG"),
                    'Jewels':Image.open("loot/images/Jewels.PNG"),
                    'Gnomission':Image.open("loot/images/Gnomission.PNG"),
                    'Other':Image.open("loot/images/Other.PNG"),
                    'NoValue':Image.open("loot/images/NoValue.PNG"),
                    'Unknown':Image.open("loot/images/Unknown.PNG")}

    yield from bot.edit_message(progressMsg,"Status: Detecting item slots.")
    slotList = yield from findSlots(bot,lootImage,progressBar)
    c = lootDatabase.cursor()
    groupList = {}
    lootList = {}
    unknownItemsList = []
    lqItemsList = []
    progress = 0
    progress_percent = 0
    percentmessage = ""
    quality_warning = 0
    for _p in range(0,progress_percent): percentmessage+=":black_square_button:"
    for _p in range(0,10-progress_percent): percentmessage+=":black_large_square:"
    yield from bot.edit_message(progressMsg,"Status: Scanning items.")
    yield from bot.edit_message(progressBar,percentmessage)
    for foundSlot in slotList:
        foundItemNumber,foundItem,itemNumberImage = numberScan(foundSlot['image'])
        result = "Unknown"
        quality = 0
        qzItem = clearBackground(foundItem.copy())
        qzItemCrop = cropItem(qzItem)
        while result == "Unknown" and quality < 30:
            foundItemClear = clearBackground(foundItem,quality)
            foundItemCrop = cropItem(foundItemClear)
            #check if the slot is empty
            if type(foundItemCrop) is tuple:
                result = "Empty"
                quality = 30
                continue
            foundItemSize = getItemSize(foundItemCrop)
            foundItemColor = getItemColor(foundItemCrop)
            c.execute("SELECT *"+
            " FROM Items WHERE ((ABS(sizeX - ?) <= 3 AND ABS(sizeY - ?) <= 3) OR ABS(size - ?) <= ?) AND (ABS(red - ?)+ABS(green - ?)+ABS(blue - ?) <= ?)",(foundItemCrop.size[0],foundItemCrop.size[1],foundItemSize,10,foundItemColor[0],foundItemColor[1],foundItemColor[2],60+quality*2,))
            
            itemList = c.fetchall()
            for unknownItem in unknownItemsList:
                if abs(unknownItem['sizeX'] - foundItemCrop.size[0]) <= 3 and abs(unknownItem['sizeY'] - foundItemCrop.size[1]) <= 3:
                    itemList.append(unknownItem)
            if quality == 0:
                for lqItem in lqItemsList:
                    if abs(lqItem['sizeX'] - foundItemCrop.size[0]) <= 3 and abs(lqItem['sizeY'] - foundItemCrop.size[1]) <= 3:
                        itemList.append(lqItem)
            result = yield from slotScan(foundItemCrop,foundItemCrop.size,itemList,groupList,quality)
            quality+=max(2,int(quality/2))
        if result == "Unknown":
            unknownImage = clearBackground(foundSlot['image'])
            unknownImageCrop = cropItem(clearBackground(foundSlot['image']))
            unknownImageSize = getItemSize(unknownImageCrop)
            result = {'name':"Unknown",'group':"Unknown",'value':0,'priority':10000000,'frame':unknownImageCrop,'sizeX':unknownImageCrop.size[0],'sizeY':unknownImageCrop.size[1],'size':unknownImageSize}
            foundItemNumber = 1
            unknownItemsList.append(result)
            #save the loot image and the cropped item that couldn't be recognize
            if not os.path.exists("loot/debug/"+debug_output):
                os.makedirs("loot/debug/"+debug_output)
                lootImageOriginal.save("loot/debug/"+debug_output+"/"+imageName,"PNG")
            filename = "Unknown"
            filenameex = 0
            while os.path.isfile("loot/debug/"+debug_output+"/"+str(filenameex)+"_"+filename+".png"):
                filenameex+=1
            #save with background
            lootImage.crop((foundSlot['x']+1,foundSlot['y']+1,foundSlot['x']+33,foundSlot['y']+33)).save("loot/debug/"+debug_output+"/"+str(filenameex)+"_"+filename+".png","PNG")
            #save without background
            unknownImage.save("loot/debug/"+debug_output+"/"+str(filenameex)+"_"+filename+"-clean.png","PNG")
        if type(result) == dict:
            if quality > 2 and not result in unknownItemsList and not result in lqItemsList:
                quality_warning+=1
                if quality_warning == 5:
                    yield from bot.send_message(progressBar.channel,"WARNING: You seem to be using a low quality image, or a screenshot taken using Tibia's **software** renderer. Some items may not be recognized correctly, and overall scanning speed will be slower!")
                lqItem = result
                imgByteArr = io.BytesIO()
                qzItem.save(imgByteArr, format='PNG')
                imgByteArr = imgByteArr.getvalue() 
                lqItem['frame'] = pickle.dumps(imgByteArr)
                lqItem['original'] = result['frame']
                lqItem['sizeX'] = qzItemCrop.size[0]
                lqItem['sizeY'] = qzItemCrop.size[1]
                lqItemsList.append(lqItem)
            
            if result['name'] in lootList:
                lootList[result['name']]['count']+= foundItemNumber
            else:
                lootList[result['name']] = {'count':foundItemNumber,'group':result['group'],'value':result['value']}
            
            if result['group'] != "Unknown":
                groupList[result['group']] = groupList.get(result['group'],0)+100
                c.execute("UPDATE Items SET priority = priority+4 WHERE `name` = ?",(result['name'],))
                c.execute("UPDATE Items SET priority = priority+1 WHERE `group` = ?",(result['group'],))
            
            if result['group'] != "Unknown":
                if not result in unknownItemsList and not result in lqItemsList:
                    detect = pickle.loads(result['frame'])
                else:
                    detect = pickle.loads(result['original'])
                detect = Image.open(io.BytesIO(bytearray(detect)))
                lootImage.paste(slot,(foundSlot['x'],foundSlot['y']))
                detect = Image.alpha_composite(lootImage.crop((foundSlot['x']+1,foundSlot['y']+1,foundSlot['x']+33,foundSlot['y']+33)),detect)
                if foundItemNumber > 1:
                    num = Image.new("RGBA",(32,32),(255,255,255,0))
                    num.paste(itemNumberImage,(7,21))
                    detect = Image.alpha_composite(detect,num)
                lootImage.paste(detect,(foundSlot['x']+1,foundSlot['y']+1))
            
            overlay = Image.alpha_composite(lootImage.crop((foundSlot['x'],foundSlot['y'],foundSlot['x']+34,foundSlot['y']+34)),groupimages.get(result['group'],groupimages['Other']) if result['value'] > 0 or result['group'] == "Unknown" else groupimages['NoValue'])
            lootImage.paste(overlay,(foundSlot['x'],foundSlot['y']))
            
        
        progress+=1
        if int(progress/len(slotList)*100/10) != progress_percent:
            progress_percent = int(progress/len(slotList)*100/10)
            percentmessage = ""
            for _p in range(0,progress_percent): percentmessage+=":black_square_button:"
            for _p in range(0,10-progress_percent): percentmessage+=":black_large_square:"
            yield from bot.edit_message(progressMsg,"Status: Scanning items ("+str(progress)+"/"+str(len(slotList))+").")
            yield from bot.edit_message(progressBar,percentmessage)
        yield from asyncio.sleep(0.005)
    yield from bot.edit_message(progressMsg,"Status: Complete!")
    c.close()
    lootDatabase.commit();
    imgByteArr = io.BytesIO()
    lootImage.save(imgByteArr, format='PNG')
    imgByteArr = imgByteArr.getvalue()
    return lootList,imgByteArr
