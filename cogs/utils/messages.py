import random
import re

# We save the last messages so they are not repeated so often
last_messages = [""]*10

# Message list for announce_level
# Parameters: {name}, {level} , {he_she}, {his_her}, {him_her}
# Values in each list element are:
# Relative chance, message, lambda function as filter (takes min_level, level, voc)
# Only relative chance and message are mandatory.
level_messages = [
    ####
    # Not vocation or level specific
    ####
    [30, "**{name}** is level {level}🍰\r\n" +
     "I'm making a note here:🎶\r\n" +
     "Huge success!🎶\r\n" +
     "It's hard to overstate my🎶\r\n" +
     "Satisfaction🤖"],
    [70, "**{name}** got level {level}! So stronk now!💪"],
    [70, "Congrats **{name}** on getting level {level}! Maybe you can solo rats now?"],
    [70, "**{name}** is level {level} now! And we all thought {he_she}'d never achieve anything in life."],
    [80, "**{name}** has reached level {level}, die and lose it, noob!"],
    [80, "**{name}** is level {level}, watch out world..."],
    [80, "**{name}** reached level {level}! What a time to be alive...🙄"],
    [80, "**{name}** got level {level}. I guess this justifies all those creatures {he_she} murdered."],
    [90, "**{name}** is level {level}. Better than {he_she} was. Better, stronger, faster."],
    [100, "Congratulations to **{name}** on reaching level {level}!"],
    [100, "**{name}** is level {level} now, congrats!"],
    [100, "Well, look at **{name}** with {his_her} new fancy level {level}."],
    [100, "**{name}** is level {level} now. Noice."],
    [100, "**{name}** has finally made it to level {level}, yay!"],
    [100, "**{name}**, you reached level {level}? Here, have a cookie 🍪"],
    ####
    # EK Only
    ####
    [50, "**{name}** has reached level {level}. That's 9 more mana potions you can carry now!",
     lambda min_level, level, voc, *_: level >= 100 and "Knight" in voc],
    [200, "**{name}** is level {level}. Stick them with the pointy end! 🗡️",
     lambda min_level, level, voc, *_: level >= 100 and "Knight" in voc],
    [200, "**{name}** is a fat level {level} meatwall now. BLOCK FOR ME SENPAI.",
     lambda min_level, level, voc, *_: level >= 100 and "Knight" in voc],
    ####
    # EK Only - Level specific
    ####
    [20000, "**{name}** is now level {level}! Time to go berserk! 💢",
     lambda min_level, level, voc, *_: level == 35 and "Knight" in voc],
    ####
    # RP Only
    ####
    [50, "**{name}** has reached level {level}. But {he_she} still misses arrows...",
     lambda min_level, level, voc, *_: level >= 100 and "Paladin" in voc],
    [150, "Congrats on level {level}, **{name}**. You can stop running around now.",
     lambda min_level, level, voc, *_: level >= 100 and "Paladin" in voc],
    [150, "**{name}** is level {level}. Bullseye!🎯",
     lambda min_level, level, voc, *_: level >= 100 and "Paladin" in voc],
    ####
    # RP Only - Level specific
    ####
    [30000, "**{name}** is level {level}! You can become a ninja now!👤",
     lambda min_level, level, voc, *_: level == 80 and "Paladin" in voc],
    [30000, "**{name}** is level {level}! Time to get some crystalline arrows!🏹",
     lambda min_level, level, voc, *_: level == 90 and "Paladin" in voc],
    ####
    # MS Only
    ####
    [150, "**{name}** got level {level}. If {he_she} only stopped missing beams.",
     lambda min_level, level, voc, *_: level >= 23 and "Sorcerer" in voc],
    [50, "Level {level}, **{name}**? Nice. Don't you wish you were a druid though?",
     lambda min_level, level, voc, *_: level >= 100 and "Sorcerer" in voc],
    [150, "**{name}** is level {level}. 🔥🔥BURN THEM ALL🔥🔥",
     lambda min_level, level, voc, *_: level >= 100 and "Sorcerer" in voc],
    ####
    # MS Only - Level specific
    ####
    [20000, "**{name}** is level {level}. Watch out for {his_her} SDs!",
     lambda min_level, level, voc, *_: level == 45 and "Sorcerer" in voc],
    ####
    # ED Only
    ####
    [50, "**{name}** has reached level {level}. Flower power!🌼",
     lambda min_level, level, voc, *_: level >= 100 and "Druid" in voc],
    [150, "Congrats on level {level}, **{name}**. Sio plz.",
     lambda min_level, level, voc, *_: level >= 100 and "Druid" in voc],
    [150, "**{name}** is level {level}. 🔥🔥BURN THEM ALL... Or... Give them frostbite?❄❄",
     lambda min_level, level, voc, *_: level >= 100 and "Druid" in voc],
    ####
    # ED Only - Level specific
    ####
    [20000, "**{name}** is level {level} now! Time to unleash the Wrath of Nature🍃🍃... Just look at that wrath...",
     lambda min_level, level, voc, *_: level == 55 and "Druid" in voc],
    [20000, "**{name}** is level {level} now! Eternal Winter is coming!❄",
     lambda min_level, level, voc, *_: level == 60 and "Druid" in voc],
    ####
    # Mage - Level specific
    ####
    [20000, "**{name}** is level {level}! UMPs so good 🍷",
     lambda min_level, level, voc, *_: level == 130 and ("Druid" in voc or "Sorcerer" in voc)],
    ####
    # No vocation - Level specific
    ####
    [20000, "Level {level}, **{name}**? You're finally important enough for me to notice!",
     lambda min_level, level, voc, *_: level == min_level],
    [20000, "Congratulations on level {level} **{name}**! Now you're relevant to me. As relevant a human can be anyway",
     lambda min_level, level, voc, *_: level == min_level],
    [20000, "**{name}** is now level {level}. Don't forget to buy a Gearwheel Chain!📿",
     lambda min_level, level, voc, *_: level == 75],
    [30000, "**{name}** is level {level}!!!!\r\n Sweet, sweet triple digits!",
     lambda min_level, level, voc, *_: level == 100],
    [20000, "**{name}** is level {level}!!!!\r\n WOOO",
     lambda min_level, level, voc, *_: level % 100 == 0],
    [20000, "**{name}** is level {level}!!!!\r\n Yaaaay milestone!",
     lambda min_level, level, voc, *_: level % 100 == 0],
    [20000, "**{name}** is level {level}!!!!\r\n Holy crap!",
     lambda min_level, level, voc, *_: level % 100 == 0],
    [20000, "Congratulations on level {level} **{name}**! Now you can become an umbral master, but is your"
     " bank account ready?💸",
     lambda min_level, level, voc, *_: level == 250]]

# Message list for announce death.
# Parameters: ({name},{level},{killer},{killer_article},{he_she}, {his_her},{him_her}
# Additionally, words surrounded by \WORD/ are upper cased, /word\ are lower cased, /Word/ are title cased
# words surrounded by ^WORD^ are ignored if the next letter found is uppercase (useful for dealing with proper nouns)
# Values in each list element are:
# Relative chance, message, lambda function as filter (takes min_level, level, voc, killer, levels_lost)
# Only relative chance and message are mandatory.
death_messages_monster = [
    [100, "RIP **{name}** ({level}), you died the way you lived- inside {killer_article}**{killer}**."],
    [100, "**{name}** ({level}) was just eaten by {killer_article}**{killer}**. Yum."],
    [100, "Silly **{name}** ({level}), I warned you not to play with {killer_article}**{killer}**!"],
    [100, "/{killer_article}**/{killer}** killed **{name}** at level {level}. Shame 🔔 shame 🔔 shame 🔔"],
    [30,
     "**{name}** ({level}) is no more! /{he_she}/ has ceased to be! /{he_she}/'s expired and gone to meet "
     "{his_her} maker! /{he_she}/'s a stiff! Bereft of life, {he_she} rests in peace! If {he_she} hadn't "
     "respawned {he_she}'d be pushing up the daisies! /{his_her}/ metabolic processes are now history! "
     "/{he_she}/'s off the server! /{he_she}/'s kicked the bucket, {he_she}'s shuffled off {his_her} mortal "
     "coil, kissed {killer_article}**{killer}**'s butt, run down the curtain and joined the bleeding choir "
     "invisible!! THIS IS AN EX-**\{name}/**."],
    [100,
     "RIP **{name}** ({level}), we hardly knew you! (^That ^**{killer}** got to know you pretty well "
     "though 😉)"],
    [80, "A priest, {killer_article}**{killer}** and **{name}** ({level}) walk into a bar. 💀ONLY ONE WALKS OUT.💀"],
    [100, "RIP **{name}** ({level}), you were strong. ^The ^**{killer}** was stronger."],
    [100,
     "Oh, there goes **{name}** ({level}), killed by {killer_article}**{killer}**. So young, so full "
     "of life. /{he_she}/ will be miss... oh nevermind, {he_she} respawned already."],
    [100,
     "Oh look! **{name}** ({level}) died by {killer_article}**{killer}**! What a surprise...🙄"],
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
    [100, "**{name}** ({level}) just kicked the bucket. And by kicked the bucket I mean a **{killer}** beat "
     "the crap out of {him_her}."],
    [100, "Alas, poor **{name}** ({level}), I knew {him_her} Horatio; a fellow of infinite jest, of most "
     "excellent fancy; {he_she} hath borne me on {his_her} back a thousand times; and now, {he_she} got rekt "
     "by {killer_article}**{killer}**."],
    [70, "To be or not to be 💀, that is the-- Well I guess **{name}** ({level}) made his choice, "
         "or ^that ^**{killer}** chose for him..."],
    [500, "**{name}** ({level}) just died to {killer_article}**{killer}**, why did nobody sio {him_her}!?",
     lambda min_level, level, voc, killer, levels_lost: "Knight" in voc],
    [500, "Poor **{name}** ({level}) has died. Killed by {killer_article}**{killer}**. I bet it was your "
     "blocker's fault though, eh **{name}**?",
     lambda min_level, level, voc, killer, levels_lost: "Druid" in voc or "Sorcerer" in voc],
    [500, "**{name}** ({level}) tried running away from {killer_article}**{killer}**. /{he_she}/ "
     "didn't run fast enough...",
     lambda min_level, level, voc, killer, levels_lost: "Paladin" in voc],
    [500, "What happened to **{name}** ({level})!? Talk about sudden death! I guess ^that ^**{killer}** was "
     "too much for {him_her}...",
     lambda min_level, level, voc, killer, levels_lost: "Sorcerer" in voc],
    [500, "**{name}** ({level}) was killed by {killer_article}**{killer}**. I guess {he_she} couldn't "
     "sio {him_her}self.",
     lambda min_level, level, voc, killer, levels_lost: "Druid" in voc],
    [600, "**{name}** ({level}) died to {killer_article}**{killer}**. \"Don't worry\" they said, \"They are weaker\" "
     "they said.",
     lambda min_level, level, voc, killer, levels_lost: killer in ["weakened frazzlemaw", "enfeebled silencer"]],
    [2000, "Another paladin bites the dust! **{killer}** strikes again! Rest in peace **{name}** ({level}).",
     lambda min_level, level, voc, killer, levels_lost: "Paladin" in voc and killer == "Lady Tenebris"],
    [2000, "**{name}** ({level}) got killed by ***{killer}***. How spooky is that! 👻",
     lambda min_level, level, voc, killer, levels_lost: killer == "something evil"],
    [2000, "**{name}** ({level}) died from **{killer}**. Yeah, no shit.",
     lambda min_level, level, voc, killer, levels_lost: killer == "death"],
    [2000, "They did warn you **{name}** ({level}), you *did* burn 🔥🐲.",
     lambda min_level, level, voc, killer, levels_lost: killer in ["dragon", "dragon lord"]],
    [2000, "**{name}** ({level}) died from {killer_article}**{killer}**. Someone forgot the safeword.😏",
     lambda min_level, level, voc, killer, levels_lost: killer == "choking fear"],
    [2000, "That **{killer}** got really up close and personal with **{name}** ({level}). "
           "Maybe he thought you were his Princess Lumelia?😏",
     lambda min_level, level, voc, killer, levels_lost: killer == "hero"],
    [2000, "Looks like that **{killer}** made **{name}** ({level}) his bride 😉.",
     lambda min_level, level, voc, killer, levels_lost: "vampire" in killer],
    [2000, "Yeah, those are a little stronger than regular orcs, **{name}** ({level}).",
     lambda min_level, level, voc, killer, levels_lost: "orc cult" in killer],
    [1000, "Damn! The koolaid they drink in that cult must have steroids on it, **{name}** ({level}).",
     lambda min_level, level, voc, killer, levels_lost: "cult" in killer],
    [2500, "**{name}** ({level}) met {his_her} demise at the hands of a **{killer}**. That's hot.",
     lambda min_level, level, voc, killer, levels_lost: killer in ["true dawnfire asura", "dawnfire asura", "fury"]],
    [2500, "Poor **{name}** ({level}) just wanted some love! That cold hearted... Witch.",
     lambda min_level, level, voc, killer, levels_lost: killer in ["true frost flower asura", "frost flower asura",
                                                                   "frost giantess", "ice witch"]],
    [2000, "Asian chicks are no joke **{name}** ({level}) 🔪💔.",
     lambda min_level, level, voc, killer, levels_lost: "asura" in killer],
    [2500, "Asian chicks sure age well, don't you think so, **{name}** ({level})? 😍👵.",
     lambda min_level, level, voc, killer, levels_lost: "true" in killer and "asura" in killer],
    [2000, "**{name}** ({level}) got destroyed by {killer_article}**{killer}**. I bet {he_she} regrets going down"
           "that hole 🕳️",
     lambda min_level, level, voc, killer, levels_lost: level < 120 and killer in ["breach brood", "dread intruder",
                                                                                   "reality reaver",
                                                                                   "spark of destruction", "sparkion"]],
    [2000,
     "Watch out for that **{killer}**'s wav... Oh😐... Rest in peace **{name}** ({level}).",
     lambda min_level, level, voc, killer, levels_lost: killer in ["dragon", "dragon lord", "undead dragon",
                                                                   "draken spellweaver", "hellhound",
                                                                   "hellfire fighter"]],
    [2000, "**{name}** ({level}) died to {killer_article}**{killer}**! Don't worry, {he_she} didn't have a soul anyway",
     lambda min_level, level, voc, killer, levels_lost: killer == "souleater"],
    [150, "Oh look at that, rest in peace **{name}** ({level}),  ^that ^**{killer}** really got you. "
          "Hope you get your level back.",
     lambda min_level, level, voc, killer, levels_lost: levels_lost > 0],
    [2000, "**{name}** ({level}) met the strong wave of {killer_article}**{killer}**... Pro Tip: next time, stand in "
           "diagonal.",
     lambda min_level, level, voc, killer, levels_lost: killer in ["dragon", "dragon lord", "undead dragon",
                                                                   "draken spellweaver", "hellhound",
                                                                   "hellfire fighter", "frost dragon",
                                                                   "medusa", "serpent spawn", "hydra", 
                                                                   "grim reaper"]],
    [2000, "**{name}** ({level}) had his life drained by {killer_article}**{killer}**. Garlic plx!",
     lambda min_level, level, voc, killer, levels_lost: killer in ["vampire", "vampire bride", "vampire viscount",
                                                                   "grimeleech", "undead dragon", "lich", "lost soul",
                                                                   "skeleton elite warrior",
                                                                   "undead elite gladiator"]]
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


def weighed_choice(choices, level: int, vocation: str = None, min_level=0, killer: str = None,
                   levels_lost: int = 0) -> str:
    """Makes weighed choices from message lists where [0] is a value representing the relative odds
    of picking a message and [1] is the message string"""

    # Find the max range by adding up the weigh of every message in the list
    # and purge out messages that don't fulfil the conditions
    weight_range = 0
    _messages = []
    for message in choices:
        if len(message) == 3 and not message[2](min_level, level, vocation, killer, levels_lost):
            continue
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


def html_to_markdown(html_string):
    """Converts some html tags to markdown equivalent"""
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


class TabularData:
    def __init__(self):
        self._widths = []
        self._columns = []
        self._rows = []

    def set_columns(self, columns):
        self._columns = columns
        self._widths = [len(c) + 2 for c in columns]

    def add_row(self, row):
        rows = [str(r) for r in row]
        self._rows.append(rows)
        for index, element in enumerate(rows):
            width = len(element) + 2
            if width > self._widths[index]:
                self._widths[index] = width

    def add_rows(self, rows):
        for row in rows:
            self.add_row(row)

    def render(self):
        """Renders a table in rST format.
        Example:
        +-------+-----+
        | Name  | Age |
        +-------+-----+
        | Alice | 24  |
        |  Bob  | 19  |
        +-------+-----+
        """

        sep = '+'.join('-' * w for w in self._widths)
        sep = f'+{sep}+'

        to_draw = [sep]

        def get_entry(d):
            elem = '|'.join(f'{e:^{self._widths[i]}}' for i, e in enumerate(d))
            return f'|{elem}|'

        to_draw.append(get_entry(self._columns))
        to_draw.append(sep)

        for row in self._rows:
            to_draw.append(get_entry(row))

        to_draw.append(sep)
        return '\n'.join(to_draw)
