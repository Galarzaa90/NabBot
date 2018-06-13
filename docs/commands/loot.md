# Loot commands

!!! info
    Parameters are enclosed with `< >`.   
    Optional parameters are enclosed in brackets `[]`.

## loot

Scans an image of a container looking for Tibia items and shows an approximate loot value.

An image must be attached with the message. The prices used are NPC prices only.

The image requires the following:

- Must be a screenshot of inventory windows (backpacks, depots, etc).
- Have the original size, the image can't be scaled up or down, however it can be cropped.
- The image must show the complete slot.
- JPG images are usually not recognized.
- PNG images with low compression settings take longer to be scanned or aren't detected at all.

The bot shows the total loot value and a list of the items detected, separated into the NPC that buy them.

??? Summary "Example"

    **/loot** (attached image)  
    ![image](../assets/images/commands/loot_input.png)  
    ![image](../assets/images/commands/loot.png)  

---- 

### loot add
**Syntax:** `loot add <item>`

Adds an image to an existing loot item in the database.

----

### loot new
**Syntax:** `loot new <item>,<group>`

Adds a new item to the loot database.

----

### loot legend

Shows the meaning of the overlayed icons.

??? Summary "Example"

    **/loot legend**   
    ![image](../assets/images/commands/loot_legend.png)

----

### loot remove
**Syntax:** `loot remove <item>`

Adds an image to an existing loot item in the database.

----

### loot show
**Syntax:** `loot show <item>`

Shows item info from the loot database.

----

### loot update

Updates the entire loot database.

----