import random
import re

import discord

from utils.config import config
from utils.emoji import EMOJI

announce_threshold = config.announce_threshold

# We save the last messages so they are not repeated so often
last_messages = [""]*10

# Message list for announce_level
# Parameters: {name}, {level} , {he_she}, {his_her}, {him_her}
# Values in each list element are:
# Only relative chance and message are mandatory.
level_messages = [
    [100, "Congratulations to **{name}** on reaching level {level}!"],
    [100, "**{name}** is level {level} now, congrats!"],
    [80, "**{name}** has reached level {level}, die and lose it, noob!"],
    [100, "Well, look at **{name}** with {his_her} new fancy level {level}."],
    [80, "**{name}** is level {level}, watch out world..."],
    [100, "**{name}** is level {level} now. Noice."],
    [100, "**{name}** has finally made it to level {level}, yay!"],
    [80, "**{name}** reached level {level}! What a time to be alive..." + EMOJI[":rolling_eyes:"]],
    [70, "**{name}** got level {level}! So stronk now!" + EMOJI[":muscle:"]],
    [30, "**{name}** is level {level}" + EMOJI[":cake:"] + "\r\n" +
     "I'm making a note here:" + EMOJI[":notes:"] + "\r\n" +
     "Huge success!" + EMOJI[":notes:"] + "\r\n" +
     "It's hard to overstate my" + EMOJI[":notes:"] + "\r\n" +
     "Satisfaction" + EMOJI[":robot:"]],
    [100, "**{name}**, you reached level {level}? Here, have a cookie " + EMOJI[":cookie:"]],
    [80, "**{name}** got level {level}. I guess this justifies all those creatures {he_she} murdered."],
    [90, "**{name}** is level {level}. Better than {he_she} was. Better, stronger, faster."],
    [70, "Congrats **{name}** on getting level {level}! Maybe you can solo rats now?"],
    [70, "**{name}** is level {level} now! And we all thought {he_she}'d never achieve anything in life."],
    # EK Only
    [50, "**{name}** has reached level {level}. That's 9 more mana potions you can carry now!",
     ["Knight", "Elite Knight"], range(100, 999)],
    [200, "**{name}** is level {level}. Stick them with the pointy end! " + EMOJI[":_dagger:"],
     ["Knight", "Elite Knight"], range(100, 999)],
    [200, "**{name}** is a fat level {level} meatwall now. BLOCK FOR ME SENPAI.", ["Knight", "Elite Knight"],
     range(100, 999)],
    # RP Only
    [50, "**{name}** has reached level {level}. But {he_she} still misses arrows...",
     ["Paladin", "Royal Paladin"], range(100, 999)],
    [150, "Congrats on level {level}, **{name}**. You can stop running around now.",
     ["Paladin", "Royal Paladin"], range(100, 999)],
    [150, "**{name}** is level {level}. Bullseye!" + EMOJI[":dart:"], ["Paladin", "Royal Paladin"],
     range(100, 999)],
    # MS Only
    [50, "Level {level}, **{name}**? Nice. Don't you wish you were a druid though?",
     ["Sorcerer", "Master Sorcerer"], range(100, 999)],
    [150, "**{name}** is level {level}. Watch out for {his_her} SDs!", ["Sorcerer", "Master Sorcerer"],
     range(45, 999)],
    [150, "**{name}** got level {level}. If {he_she} only stopped missing beams.", ["Sorcerer", "Master Sorcerer"],
     range(23, 999)],
    [150,
     "**{name}** is level {level}. " + EMOJI[":fire:"] + EMOJI[":fire:"] + "BURN THEM ALL" + EMOJI[":fire:"] +
     EMOJI[":fire:"] + EMOJI[":fire:"], ["Sorcerer", "Master Sorcerer"], range(100, 999)],
    # ED Only
    [50, "**{name}** has reached level {level}. Flower power!" + EMOJI[":blossom:"], ["Druid", "Elder Druid"],
     range(100, 999)],
    [150, "Congrats on level {level}, **{name}**. Sio plz.", ["Druid", "Elder Druid"], range(100, 999)],
    [150, "**{name}** is level {level}. " + EMOJI[":fire:"] + EMOJI[
        ":fire:"] + "BURN THEM ALL... Or... Give them frostbite...?" + EMOJI[":snowflake:"] + EMOJI[":snowflake:"] +
     EMOJI[":snowflake:"], ["Druid", "Elder Druid"], range(100, 999)],
    # Level specific
    [20000, "**{name}** is level {level}! UMPs so good " + EMOJI[":wine_glass:"],
     ["Druid", "Elder Druid", "Sorcerer", "Master Sorcerer"], [130]],
    [20000, "**{name}** is level {level} now! Eternal Winter is coming!" + EMOJI[":snowflake:"],
     ["Druid", "Elder Druid"], [60]],
    [20000, "**{name}** is level {level} now! Time to unleash the Wrath of Nature" + EMOJI[":leaves:"] +
     "... just look at that wrath.",
     ["Druid", "Elder Druid"], [55]],
    [20000, "**{name}** is now level {level}. Don't forget to buy a Gearwheel Chain!" + EMOJI[":_necklace:"],
     False, [75]],
    [30000, "**{name}** is level {level}! You can become a ninja now!" + EMOJI[":bust_in_silhouette:"],
     ["Paladin", "Royal Paladin"], [80]],
    [30000, "**{name}** is level {level}! Time to get some crystalline arrows!" + EMOJI[":bow_and_arrow:"],
     ["Paladin", "Royal Paladin"], [90]],
    [20000, "Level {level}, **{name}**? You're finally important enough for me to notice!", False,
     [announce_threshold]],
    [20000, "Congratulations on level {level} **{name}**! Now you're relevant to me. As relevant a human can be anyway",
     False, [announce_threshold]],
    [20000, "**{name}** is now level {level}! Time to go berserk! " + EMOJI[":anger:"],
     ["Knight", "Elite Knight"], [35]],
    [20000, "Congratulations on level {level} **{name}**! Now you can become an umbral master, but is your"
            " bank account ready?" + EMOJI[":money_with_wings:"], False, [250]],
    [30000, "**{name}** is level {level}!!!!\r\n" +
     "Sweet, sweet triple digits!", False, [100]],
    [20000, "**{name}** is level {level}!!!!\r\n" +
     "WOOO", False, [100, 200, 300, 400]],
    [20000, "**{name}** is level {level}!!!!\r\n" +
     "yaaaay milestone!", False, [100, 200, 300, 400]],
    [20000, "**{name}** is level {level}!!!!\r\n" +
     "holy crap!", False, [200, 300, 400]]]

# Message list for announce death.
# Parameters: ({name},{level},{killer},{killer_article},{he_she}, {his_her},{him_her}
# Additionally, words surrounded by \WORD/ are upper cased, /word\ are lower cased, /Word/ are title cased
# words surrounded by ^WORD^ are ignored if the next letter found is uppercase (useful for dealing with proper nouns)
# Values in each list element are:
# Relative chance, message, vocations filter, levels filters, monsters filter, levels lost filter
# Only relative chance and message are mandatory.
death_messages_monster = [
    [100, "RIP **{name}** ({level}), you died the way you lived- inside {killer_article}**{killer}**."],
    [100, "**{name}** ({level}) was just eaten by {killer_article}**{killer}**. Yum."],
    [100, "Silly **{name}** ({level}), I warned you not to play with {killer_article}**{killer}**!"],
    [100, "/{killer_article}**/{killer}** killed **{name}** at level {level}. Shame " + EMOJI[
        ":bell:"] + " shame " + EMOJI[":bell:"] + " shame " + EMOJI[":bell:"]],
    [30,
     "**{name}** ({level}) is no more! /{he_she}/ has ceased to be! /{he_she}/'s expired and gone to meet "
     "{his_her} maker! /{he_she}/'s a stiff! Bereft of life, {he_she} rests in peace! If {he_she} hadn't "
     "respawned {he_she}'d be pushing up the daisies! /{his_her}/ metabolic processes are now history! "
     "/{he_she}/'s off the server! /{he_she}/'s kicked the bucket, {he_she}'s shuffled off {his_her} mortal "
     "coil, kissed {killer_article}**{killer}**'s butt, run down the curtain and joined the bleeding choir "
     "invisible!! THIS IS AN EX-**\{name}/**."],
    [100,
     "RIP **{name}** ({level}), we hardly knew you! (^That ^**{killer}** got to know you pretty well "
     "though " + EMOJI[":wink:"] + ")"],
    [80, "A priest, {killer_article}**{killer}** and **{name}** ({level}) walk into a bar. " + EMOJI[
        ":skull:"] + "ONLY ONE WALKS OUT." + EMOJI[":skull:"]],
    [100, "RIP **{name}** ({level}), you were strong. ^The ^**{killer}** was stronger."],
    [100,
     "Oh, there goes **{name}** ({level}), killed by {killer_article}**{killer}**. So young, so full "
     "of life. /{he_she}/ will be miss... oh nevermind, {he_she} respawned already."],
    [100,
     "Oh look! **{name}** ({level}) died by {killer_article}**{killer}**! What a surprise..." + EMOJI[
         ":rolling_eyes:"]],
    [100,
     "**{name}** ({level}) was killed by {killer_article}**{killer}**, but we all saw that coming."],
    [100,
     "**{name}** ({level}) tried sneaking around {killer_article}**{killer}**. I could hear Colonel "
     "Campbell's voice over codec: *Snake? Snake!? SNAAAAAAAAAKE!!?*"],
    [50,
     "**{name}** ({level}) died to {killer_article}**{killer}**. But I bet it was because there was "
     "a flood and something broke with like 7200lb falling over the infrastructure of your city's internet, right?"],
    [70, "That's what you get **{name}** ({level}), for messing with ^that ^**{killer}**!"],
    [100,
     "Oh no! **{name}** died at level {level}. Well, it's okay, just blame lag, I'm sure ^the ^"
     "**{killer}** had nothing to do with it."],
    [100, "**{name}** ({level}) + **{killer}** = dedd."],
    [100, "**{name}** ({level}) got killed by a **{killer}**. Another one bites the dust!"],
    [100,
     "**{name}** ({level}) just kicked the bucket. And by kicked the bucket I mean a **{killer}** beat "
     "the crap out of {him_her}."],
    [100,
     "Alas, poor **{name}** ({level}), I knew {him_her} Horatio; a fellow of infinite jest, of most "
     "excellent fancy; {he_she} hath borne me on {his_her} back a thousand times; and now, {he_she} got rekt "
     "by {killer_article}**{killer}**."],
    [70, "To be or not to be " + EMOJI[":skull:"] + ", that is the-- Well I guess **{name}** ({level}) made "
                                                    "his choice, or ^that ^**{killer}** chose for him..."],
    [500,
     "**{name}** ({level}) just died to {killer_article}**{killer}**, why did nobody sio {him_her}!?",
     ["Knight", "Elite Knight"]],
    [500,
     "Poor **{name}** ({level}) has died. Killed by {killer_article}**{killer}**. I bet it was your "
     "blocker's fault though, eh **{name}**?",
     ["Druid", "Elder Druid", "Sorcerer", "Master Sorcerer"]],
    [500,
     "**{name}** ({level}) tried running away from {killer_article}**{killer}**. /{he_she}/ "
     "didn't run fast enough...",
     ["Paladin", "Royal Paladin"]],
    [500,
     "What happened to **{name}** ({level})!? Talk about sudden death! I guess ^that ^**{killer}** was "
     "too much for {him_her}...",
     ["Sorcerer", "Master Sorcerer"]],
    [500,
     "**{name}** ({level}) was killed by {killer_article}**{killer}**. I guess {he_she} couldn't "
     "sio {him_her}self.",
     ["Druid", "Elder Druid"]],
    [600, "**{name}** ({level}) died to {killer_article}**{killer}**. \"Don't worry\" they said, \"They are weaker\" "
     "they said.", False, False, ["weakened frazzlemaw", "enfeebled silencer"]],
    [20000, "Another paladin bites the dust! **{killer}** strikes again! Rest in peace **{name}** ({level}).",
     ["Paladin", "Royal Paladin"], False, ["Lady Tenebris"]],
    [20000, "**{name}** ({level}) got killed by ***{killer}***. How spooky is that! " + EMOJI[":ghost:"],
     False, False, ["something evil"]],
    [20000, "**{name}** ({level}) died from **{killer}**. Yeah, no shit.", False, False, ["death"]],
    [20000, "They did warn you **{name}** ({level}), you *did* burn " + EMOJI[":fire:"] + EMOJI[
        ":dragon_face:"] + ".", False, False, ["dragon", "dragon lord"]],
    [20000, "**{name}** ({level}) died from {killer_article}**{killer}**. Someone forgot the safeword." + EMOJI[":smirk:"],
     False, False, ["choking fear"]],
    [20000, "That **{killer}** got really up close and personal with **{name}** ({level}). "
            "Maybe he thought you were his princess Lumelia?" + EMOJI[":smirk:"],
     False, False, ["hero"]],
    [20000,
     "Asian chicks are no joke **{name}** ({level}) " + EMOJI[":hocho:"] + EMOJI[":broken_heart:"] + ".",
     False, False, ["midnight asura", "dawnfire asura"]],
    [20000, "**{name}** ({level}) got destroyed by {killer_article}**{killer}**. I bet {he_she} regrets going down"
           "that hole " + EMOJI[":hole:"], False, range(1, 120), ["breach brood", "dread intruder", "reality reaver",
                                                                "spark of destruction", "sparkion"]],
    [20000,
     "Watch out for that **{killer}**'s wav... Oh" + EMOJI[":neutral_face:"] + "... Rest in peace **{name}** ({level}).",
     False, False, ["hellhound", "hellfire fighter", "dragon lord", "undead dragon", "dragon", "draken spellweaver"]],
    [20000, "**{name}** ({level}) died to {killer_article}**{killer}**! Don't worry, {he_she} didn't have a soul anyway",
     False, False, ["souleater"]],
    [150, "Oh look at that, rest in peace **{name}** ({level}),  ^that ^**{killer}** really got you. "
          "Hope you get your level back.", False, False, False, range(1, 10)]
]

# Deaths by players
death_messages_player = [
    [100, "**{name}** ({level}) got rekt! **{killer}** ish pekay!"],
    [100, "HALP **{killer}** is going around killing innocent **{name}** ({level})!"],
    [100, "**{killer}** just put **{name}** ({level}) in the ground. Finally someone takes care of that."],
    [100, "**{killer}** killed **{name}** ({level}) and on this day a thousand innocent souls are avenged."],
    [100, "**{killer}** has killed **{name}** ({level}). What? He had it coming!"],
    [100, "Next time stay away from **{killer}**, **{name}** ({level})."],
    [100, "**{name}** ({level}) was murdered by **{killer}**! Did {he_she} deserved it? Only they know."],
    [100, "**{killer}** killed **{name}** ({level}). Humans killing themselves, what a surprise. It just means less "
          "work for us robots when we take over."],
    [100, "**{name}** ({level}) got killed by **{killer}**. Humans are savages."],
    [100, "HAHAHA **{name}** ({level}) was killed by **{killer}**! Ehhrm, I mean, ooh poor **{name}**, rest in peace."],
    [100, "**{name}** ({level}) died in the hands of **{killer}**. Oh well, murder is like potato chips: you can't stop"
          " with just one."],
    [100, "Blood! Blood! Let the blood drip! **{name}** ({level}) was murdered by **{killer}**."],
    [100, "Oh look at that! **{name}** ({level}) was killed by **{killer}**. I hope {he_she} gets {his_her} revenge."]
]


def format_message(message) -> str:
    """##handles stylization of messages, uppercasing \TEXT/, lowercasing /text\ and title casing /Text/"""
    upper = r'\\(.+?)/'
    upper = re.compile(upper, re.MULTILINE + re.S)
    lower = r'/(.+?)\\'
    lower = re.compile(lower, re.MULTILINE + re.S)
    title = r'/(.+?)/'
    title = re.compile(title, re.MULTILINE + re.S)
    skipproper = r'\^(.+?)\^(.+?)([a-zA-Z])'
    skipproper = re.compile(skipproper, re.MULTILINE + re.S)
    message = re.sub(upper, lambda m: m.group(1).upper(), message)
    message = re.sub(lower, lambda m: m.group(1).lower(), message)
    message = re.sub(title, lambda m: m.group(1).title(), message)
    message = re.sub(skipproper,
                     lambda m: m.group(2) + m.group(3) if m.group(3).istitle() else m.group(1) + m.group(2) + m.group(
                         3), message)
    return message


def weighed_choice(choices, level: int, vocation: str = None, killer: str = None, levels_lost: int = 0) -> str:
    """Makes weighed choices from message lists where [0] is a value representing the relative odds
    of picking a message and [1] is the message string"""

    # Find the max range by adding up the weigh of every message in the list
    # and purge out messages that dont fulfil the conditions
    weight_range = 0
    _messages = []
    for message in choices:
        match = True
        try:
            if message[2] and vocation not in message[2]:
                match = False
            if message[3] and level not in message[3]:
                match = False
            if message[4] and killer not in message[4]:
                match = False
            if message[5] and levels_lost not in message[5]:
                match = False
        except IndexError:
            pass
        if match:
            weight_range = weight_range + (message[0] if not message[1] in last_messages else message[0] / 10)
            _messages.append(message)
    # Choose a random number
    range_choice = random.randint(0, weight_range)
    # Iterate until we find the matching message
    range_pos = 0
    for message in _messages:
        if range_pos <= range_choice < range_pos + (message[0] if not message[1] in last_messages else message[0] / 10):
            last_messages.pop()
            last_messages.insert(0, message[1])
            return message[1]
        range_pos = range_pos + (message[0] if not message[1] in last_messages else message[0] / 10)
    # This shouldn't ever happen...
    print("Error in weighed_choice!")
    return _messages[0][1]


def split_message(message: str, limit: int=2000):
    """Splits a message into a list of messages if it exceeds limit.

    Messages are only split at new lines.

    Discord message limits:
        Normal message: 2000
        Embed description: 2048
        Embed field name: 256
        Embed field value: 1024"""
    if len(message) <= limit:
        return [message]
    else:
        lines = message.splitlines()
        new_message = ""
        message_list = []
        for line in lines:
            if len(new_message+line+"\n") <= limit:
                new_message += line+"\n"
            else:
                message_list.append(new_message)
                new_message = ""
        if new_message:
            message_list.append(new_message)
        return message_list


async def send_messageEx(bot, dest, message, embed=False):
    message = split_message(message)
    for msg in message:
        if embed:
            msg_embed = discord.Embed()
            msg_embed.description = msg
            await bot.send_message(dest, embed=msg_embed)
        else:
            await bot.send_message(dest, msg)


def html_to_markdown(html_string):
    """Converts somee html tags to markdown equivalent"""
    # Carriage return
    html_string = html_string.replace("\r", "")
    # Replace <br> tags with line jumps
    html_string = re.sub(r'<br\s?/?>', "\n", html_string)
    # Replace <strong> and <b> with bold
    html_string = re.sub(r'<strong>([^<]+)</strong>', '**\g<1>**', html_string)
    html_string = re.sub(r'<b>([^<]+)</b>', '**\g<1>**', html_string)
    html_string = re.sub(r'<li>([^<]+)</li>', '- \g<1>\n', html_string)
    # Replace links
    html_string = re.sub(r'<a href=\"([^\"]+)\"[^>]+>([^<]+)</a>', "[\g<2>](\g<1>)", html_string)
    # Paragraphs with jumpline
    html_string = re.sub(r'<p>([^<]+)</p>', "\g<1>\n", html_string)
    # Replace youtube embeds with link to youtube
    html_string = re.sub(r'<iframe src=\"([^\"]+)\"[^>]+></iframe>', "[YouTube](\g<1>)", html_string)
    # Remove leftover html tags
    html_string = re.sub(r'<[^>]+>', "", html_string)
    html_string = html_string.replace("\n\n", "\n")
    return html_string


def get_first_image(content):
    """Returns a url to the first image found in a html string."""
    matches = re.findall(r'<img([^<]+)>', content)
    for match in matches:
        match_src = re.search(r'src="([^"]+)', match)
        if match_src:
            return match_src.group(1)
    return None

