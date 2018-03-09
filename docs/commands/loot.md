## /loot

Scans an image of a container looking for Tibia items and shows an approximate loot value. An image must be attached with the message. The prices used are NPC prices only, images from the flash client don't work

The image requires the following:

* Must be a screenshot of inventory windows (backpacks, depots, etc).
* Have the original size, the image can't be scaled up or down, however it can be cropped.
* Use the regular client, flash client is not supported.
* The image must show the complete slot.
* JPG images are usually not recognized, and PNG images with low compression settings take longer to be scanned or aren't detected at all.

The bot shows the total loot value calculated and a list of the items detected, separated into the NPC that buy them.

??? Summary "Example"

    **/loot** (attached image)  
    ![image](../assets/images/commands/loot_input.png)  
    ![image](../assets/images/commands/loot.png)  

### /loot legend

Shows a legend indicating what the overlayed icons on items mean.

??? Summary "Example"

    **/loot legend**   
    ![image](../assets/images/commands/loot_legend.png)