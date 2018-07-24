# Messages

One of NabBot's main features is the ability to announce when registered characters level up and ~~make fun~~ announce deaths.

These messages can be found on `utils/messages.py`, in the variables `level_messages`, `death_messages_monster` and `death_messages_player`.

Each list item is made of another list representing each message. The first element, is a number representing the message's weight, or chances to appear.
The second element is the message itself, with some formatting placeholders that are dynamically replaced.
The rest of the elements are conditions that are explained on the following sections.

The chances of each message being selected is based on the first element of the message item, the higher it is, the more likely it is to be selected.


## Level up messages
Level messages have the following parameters that are dynamically replaced, these are enclosed in `{}`:

* name - The name of the character that leveled.
* level - The level the character obtained.
* he_she, his_her, him_her - Pronouns selected based on the character's gender.

Each item of this list is a list with the following items:

* The messages weight.
* The message itself, parameters are enclosed in `{}`.
* Vocations that can get this message. This is a list of vocations. Optional parameter, can be set to `#!py False` to ignore.
* Level range that can get this message. This is a list of levels. `#!py range(min,max)` can be used too. Optional parameter.

??? Summary "Examples"

    * `#!py [50, "Level {level}, **{name}**? Nice. Don't you wish you were a druid though?", ["Sorcerer", "Master Sorcerer"], range(100, 999)],`  
    This message is only for sorcerers between level 100 and 999.
    
    * `#!py [20000, "**{name}** is level {level}!!!!\nyaaaay milestone!", False, [100, 200, 300, 400]]`  
    This message is only for levels 100, 200, 300 and 400.
    

## Death messages
Death messages have the following parameters that are dynamically replaced, these are enclosed in `{}`:

* name - The name of the character that died
* level - The level of the character at the moment of death
* killer - The creature that killed the character.
* killer_article - The article preceding the killer's name. This is empty for bosses.
* he_she, his_her, him_her - Pronouns selected based on the character's gender.

Aditionally, the following syntax is processed too:

* Words surrounded by `\ /` are upper cased.
* Words surrounded by `/ \` are lower cased.
* Words surrounded by `/ /` are title cased.
* Words surrounded by `^ ^` are removed if the next letter is uppercase.

Each item of this list is a list with the following items:

* The messages weight.
* The message itself, parameters are enclosed in `{}`.
* Vocations that can get this message. This is a list of vocations. Optional parameter, can be set to `#!py False` to ignore.
* Level range that can get this message. This is a list of levels. `#!py range(min,max)` can be used too. Optional parameter. 
* Killer that can get this message. This is a list of monsters. Optional parameter, can be set to `#!py False` to ignore.


??? Summary "Examples"

    `#!py [500,"**{name}** ({level}) just died to {killer_article}**{killer}**, why did nobody sio {him_her}!?", ["Knight", "Elite Knight"]]`  
    This message is only for Knights.
    
    `#!py [20000, "**{name}** ({level}) died to {killer_article}**{killer}**! Don't worry, {he_she} didn't have a soul anyway", False, False, ["souleater"]]`  
    This message is for deaths caused by souleaters.


## Pvp death messages
Death messages have the following parameters that are dynamically replaced, these are enclosed in `{}`:

* name - The name of the character that died
* level - The level of the character at the moment of death
* killer - The creature that killed the character.
* he_she, his_her, him_her - Pronouns selected based on the character's gender.

Each item of this list is a list with the following items:

* The messages weight.
* The message itself, parameters are enclosed in `{}`.


??? Summary "Examples"

    `#!py [100, "**{killer}** has killed **{name}** ({level}). What? He had it coming!"]`  
    `#!py [100, "Blood! Blood! Let the blood drip! **{name}** ({level}) was murdered by **{killer}**."]`  
