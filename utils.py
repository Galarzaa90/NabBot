import discord
import logging
from discord.ext import commands
import re
import math
import random
import asyncio
import urllib.request
import urllib
import sqlite3
import os
import platform
import time
from datetime import datetime, timedelta, date
from calendar import timegm
import sys
import aiohttp

# Command list (populated automatically, used to check if a message is(n't) a command invocation)
command_list = []
# Emoji code
# Emoji :shortname: list
EMOJI = {":_hotdog:": chr(0x1F32D),
         ":_robot:": chr(0x1F916),
         ":_necklace:": chr(0x1F4FF),
         ":_snowflake:": chr(0x2744),
         ":_dagger:": chr(0x1F5E1),
         ":_upsidedown:": chr(0x1F643),
         ":_eyeroll:": chr(0x1F644),
         ":+1:": chr(0x1F44D),
         ":-1:": chr(0x1F44E),
         ":100:": chr(0x1F4AF),
         ":1234:": chr(0x1F522),
         ":8ball:": chr(0x1F3B1),
         ":a:": chr(0x1F170),
         ":ab:": chr(0x1F18E),
         ":abc:": chr(0x1F524),
         ":abcd:": chr(0x1F521),
         ":accept:": chr(0x1F251),
         ":aerial_tramway:": chr(0x1F6A1),
         ":airplane:": chr(0x02708),
         ":alarm_clock:": chr(0x023F0),
         ":alien:": chr(0x1F47D),
         ":ambulance:": chr(0x1F691),
         ":anchor:": chr(0x02693),
         ":angel:": chr(0x1F47C),
         ":anger:": chr(0x1F4A2),
         ":angry:": chr(0x1F620),
         ":anguished:": chr(0x1F627),
         ":ant:": chr(0x1F41C),
         ":apple:": chr(0x1F34E),
         ":aquarius:": chr(0x02652),
         ":aries:": chr(0x02648),
         ":arrow_backward:": chr(0x025C0),
         ":arrow_double_down:": chr(0x023EC),
         ":arrow_double_up:": chr(0x023EB),
         ":arrow_down:": chr(0x02B07),
         ":arrow_down_small:": chr(0x1F53D),
         ":arrow_forward:": chr(0x025B6),
         ":arrow_heading_down:": chr(0x02935),
         ":arrow_heading_up:": chr(0x02934),
         ":arrow_left:": chr(0x02B05),
         ":arrow_lower_left:": chr(0x02199),
         ":arrow_lower_right:": chr(0x02198),
         ":arrow_right:": chr(0x027A1),
         ":arrow_right_hook:": chr(0x021AA),
         ":arrow_up:": chr(0x02B06),
         ":arrow_up_down:": chr(0x02195),
         ":arrow_up_small:": chr(0x1F53C),
         ":arrow_upper_left:": chr(0x02196),
         ":arrow_upper_right:": chr(0x02197),
         ":arrows_clockwise:": chr(0x1F503),
         ":arrows_counterclockwise:": chr(0x1F504),
         ":art:": chr(0x1F3A8),
         ":articulated_lorry:": chr(0x1F69B),
         ":astonished:": chr(0x1F632),
         ":athletic_shoe:": chr(0x1F45F),
         ":atm:": chr(0x1F3E7),
         ":b:": chr(0x1F171),
         ":baby:": chr(0x1F476),
         ":baby_bottle:": chr(0x1F37C),
         ":baby_chick:": chr(0x1F424),
         ":baby_symbol:": chr(0x1F6BC),
         ":back:": chr(0x1F519),
         ":baggage_claim:": chr(0x1F6C4),
         ":balloon:": chr(0x1F388),
         ":ballot_box_with_check:": chr(0x02611),
         ":bamboo:": chr(0x1F38D),
         ":banana:": chr(0x1F34C),
         ":bangbang:": chr(0x0203C),
         ":bank:": chr(0x1F3E6),
         ":bar_chart:": chr(0x1F4CA),
         ":barber:": chr(0x1F488),
         ":baseball:": chr(0x026BE),
         ":basketball:": chr(0x1F3C0),
         ":bath:": chr(0x1F6C0),
         ":bathtub:": chr(0x1F6C1),
         ":battery:": chr(0x1F50B),
         ":bear:": chr(0x1F43B),
         ":bee:": chr(0x1F41D),
         ":beer:": chr(0x1F37A),
         ":beers:": chr(0x1F37B),
         ":beetle:": chr(0x1F41E),
         ":beginner:": chr(0x1F530),
         ":bell:": chr(0x1F514),
         ":bento:": chr(0x1F371),
         ":bicyclist:": chr(0x1F6B4),
         ":bike:": chr(0x1F6B2),
         ":bikini:": chr(0x1F459),
         ":bird:": chr(0x1F426),
         ":birthday:": chr(0x1F382),
         ":black_circle:": chr(0x026AB),
         ":black_joker:": chr(0x1F0CF),
         ":black_large_square:": chr(0x02B1B),
         ":black_medium_small_square:": chr(0x025FE),
         ":black_medium_square:": chr(0x025FC),
         ":black_nib:": chr(0x02712),
         ":black_small_square:": chr(0x025AA),
         ":black_square_button:": chr(0x1F532),
         ":blossom:": chr(0x1F33C),
         ":blowfish:": chr(0x1F421),
         ":blue_book:": chr(0x1F4D8),
         ":blue_car:": chr(0x1F699),
         ":blue_heart:": chr(0x1F499),
         ":blush:": chr(0x1F60A),
         ":boar:": chr(0x1F417),
         ":boat:": chr(0x026F5),
         ":bomb:": chr(0x1F4A3),
         ":book:": chr(0x1F4D6),
         ":bookmark:": chr(0x1F516),
         ":bookmark_tabs:": chr(0x1F4D1),
         ":books:": chr(0x1F4DA),
         ":boom:": chr(0x1F4A5),
         ":boot:": chr(0x1F462),
         ":bouquet:": chr(0x1F490),
         ":bow:": chr(0x1F647),
         ":bowling:": chr(0x1F3B3),
         ":boy:": chr(0x1F466),
         ":bread:": chr(0x1F35E),
         ":bride_with_veil:": chr(0x1F470),
         ":bridge_at_night:": chr(0x1F309),
         ":briefcase:": chr(0x1F4BC),
         ":broken_heart:": chr(0x1F494),
         ":bug:": chr(0x1F41B),
         ":bulb:": chr(0x1F4A1),
         ":bullettrain_front:": chr(0x1F685),
         ":bullettrain_side:": chr(0x1F684),
         ":bus:": chr(0x1F68C),
         ":busstop:": chr(0x1F68F),
         ":bust_in_silhouette:": chr(0x1F464),
         ":busts_in_silhouette:": chr(0x1F465),
         ":cactus:": chr(0x1F335),
         ":cake:": chr(0x1F370),
         ":calendar:": chr(0x1F4C6),
         ":calling:": chr(0x1F4F2),
         ":camel:": chr(0x1F42B),
         ":camera:": chr(0x1F4F7),
         ":cancer:": chr(0x0264B),
         ":candy:": chr(0x1F36C),
         ":capital_abcd:": chr(0x1F520),
         ":capricorn:": chr(0x02651),
         ":car:": chr(0x1F697),
         ":card_index:": chr(0x1F4C7),
         ":carousel_horse:": chr(0x1F3A0),
         ":cat:": chr(0x1F431),
         ":cat2:": chr(0x1F408),
         ":cd:": chr(0x1F4BF),
         ":chart:": chr(0x1F4B9),
         ":chart_with_downwards_trend:": chr(0x1F4C9),
         ":chart_with_upwards_trend:": chr(0x1F4C8),
         ":checkered_flag:": chr(0x1F3C1),
         ":cherries:": chr(0x1F352),
         ":cherry_blossom:": chr(0x1F338),
         ":chestnut:": chr(0x1F330),
         ":chicken:": chr(0x1F414),
         ":children_crossing:": chr(0x1F6B8),
         ":chocolate_bar:": chr(0x1F36B),
         ":christmas_tree:": chr(0x1F384),
         ":church:": chr(0x026EA),
         ":cinema:": chr(0x1F3A6),
         ":circus_tent:": chr(0x1F3AA),
         ":city_sunrise:": chr(0x1F307),
         ":city_sunset:": chr(0x1F306),
         ":cl:": chr(0x1F191),
         ":clap:": chr(0x1F44F),
         ":clapper:": chr(0x1F3AC),
         ":clipboard:": chr(0x1F4CB),
         ":clock1:": chr(0x1F550),
         ":clock10:": chr(0x1F559),
         ":clock1030:": chr(0x1F565),
         ":clock11:": chr(0x1F55A),
         ":clock1130:": chr(0x1F566),
         ":clock12:": chr(0x1F55B),
         ":clock1230:": chr(0x1F567),
         ":clock130:": chr(0x1F55C),
         ":clock2:": chr(0x1F551),
         ":clock230:": chr(0x1F55D),
         ":clock3:": chr(0x1F552),
         ":clock330:": chr(0x1F55E),
         ":clock4:": chr(0x1F553),
         ":clock430:": chr(0x1F55F),
         ":clock5:": chr(0x1F554),
         ":clock530:": chr(0x1F560),
         ":clock6:": chr(0x1F555),
         ":clock630:": chr(0x1F561),
         ":clock7:": chr(0x1F556),
         ":clock730:": chr(0x1F562),
         ":clock8:": chr(0x1F557),
         ":clock830:": chr(0x1F563),
         ":clock9:": chr(0x1F558),
         ":clock930:": chr(0x1F564),
         ":closed_book:": chr(0x1F4D5),
         ":closed_lock_with_key:": chr(0x1F510),
         ":closed_umbrella:": chr(0x1F302),
         ":cloud:": chr(0x02601),
         ":clubs:": chr(0x02663),
         ":cocktail:": chr(0x1F378),
         ":coffee:": chr(0x02615),
         ":cold_sweat:": chr(0x1F630),
         ":collision:": chr(0x1F4A5),
         ":computer:": chr(0x1F4BB),
         ":confetti_ball:": chr(0x1F38A),
         ":confounded:": chr(0x1F616),
         ":confused:": chr(0x1F615),
         ":congratulations:": chr(0x03297),
         ":construction:": chr(0x1F6A7),
         ":construction_worker:": chr(0x1F477),
         ":convenience_store:": chr(0x1F3EA),
         ":cookie:": chr(0x1F36A),
         ":cool:": chr(0x1F192),
         ":cop:": chr(0x1F46E),
         ":copyright:": chr(0xA9),
         ":corn:": chr(0x1F33D),
         ":couple:": chr(0x1F46B),
         ":couple_with_heart:": chr(0x1F491),
         ":couplekiss:": chr(0x1F48F),
         ":cow:": chr(0x1F42E),
         ":cow2:": chr(0x1F404),
         ":credit_card:": chr(0x1F4B3),
         ":crescent_moon:": chr(0x1F319),
         ":crocodile:": chr(0x1F40A),
         ":crossed_flags:": chr(0x1F38C),
         ":crown:": chr(0x1F451),
         ":cry:": chr(0x1F622),
         ":crying_cat_face:": chr(0x1F63F),
         ":crystal_ball:": chr(0x1F52E),
         ":cupid:": chr(0x1F498),
         ":curly_loop:": chr(0x027B0),
         ":currency_exchange:": chr(0x1F4B1),
         ":curry:": chr(0x1F35B),
         ":custard:": chr(0x1F36E),
         ":customs:": chr(0x1F6C3),
         ":cyclone:": chr(0x1F300),
         ":dancer:": chr(0x1F483),
         ":dancers:": chr(0x1F46F),
         ":dango:": chr(0x1F361),
         ":dart:": chr(0x1F3AF),
         ":dash:": chr(0x1F4A8),
         ":date:": chr(0x1F4C5),
         ":deciduous_tree:": chr(0x1F333),
         ":department_store:": chr(0x1F3EC),
         ":diamond_shape_with_a_dot_inside:": chr(0x1F4A0),
         ":diamonds:": chr(0x02666),
         ":disappointed:": chr(0x1F61E),
         ":disappointed_relieved:": chr(0x1F625),
         ":dizzy:": chr(0x1F4AB),
         ":dizzy_face:": chr(0x1F635),
         ":do_not_litter:": chr(0x1F6AF),
         ":dog:": chr(0x1F436),
         ":dog2:": chr(0x1F415),
         ":dollar:": chr(0x1F4B5),
         ":dolls:": chr(0x1F38E),
         ":dolphin:": chr(0x1F42C),
         ":door:": chr(0x1F6AA),
         ":doughnut:": chr(0x1F369),
         ":dragon:": chr(0x1F409),
         ":dragon_face:": chr(0x1F432),
         ":dress:": chr(0x1F457),
         ":dromedary_camel:": chr(0x1F42A),
         ":droplet:": chr(0x1F4A7),
         ":dvd:": chr(0x1F4C0),
         ":e-mail:": chr(0x1F4E7),
         ":ear:": chr(0x1F442),
         ":ear_of_rice:": chr(0x1F33E),
         ":earth_africa:": chr(0x1F30D),
         ":earth_americas:": chr(0x1F30E),
         ":earth_asia:": chr(0x1F30F),
         ":egg:": chr(0x1F373),
         ":eggplant:": chr(0x1F346),
         ":eight_pointed_black_star:": chr(0x02734),
         ":eight_spoked_asterisk:": chr(0x02733),
         ":electric_plug:": chr(0x1F50C),
         ":elephant:": chr(0x1F418),
         ":email:": chr(0x02709),
         ":end:": chr(0x1F51A),
         ":envelope:": chr(0x02709),
         ":envelope_with_arrow:": chr(0x1F4E9),
         ":euro:": chr(0x1F4B6),
         ":european_castle:": chr(0x1F3F0),
         ":european_post_office:": chr(0x1F3E4),
         ":evergreen_tree:": chr(0x1F332),
         ":exclamation:": chr(0x02757),
         ":expressionless:": chr(0x1F611),
         ":eyeglasses:": chr(0x1F453),
         ":eyes:": chr(0x1F440),
         ":facepunch:": chr(0x1F44A),
         ":factory:": chr(0x1F3ED),
         ":fallen_leaf:": chr(0x1F342),
         ":family:": chr(0x1F46A),
         ":fast_forward:": chr(0x023E9),
         ":fax:": chr(0x1F4E0),
         ":fearful:": chr(0x1F628),
         ":feet:": chr(0x1F43E),
         ":ferris_wheel:": chr(0x1F3A1),
         ":file_folder:": chr(0x1F4C1),
         ":fire:": chr(0x1F525),
         ":fire_engine:": chr(0x1F692),
         ":fireworks:": chr(0x1F386),
         ":first_quarter_moon:": chr(0x1F313),
         ":first_quarter_moon_with_face:": chr(0x1F31B),
         ":fish:": chr(0x1F41F),
         ":fish_cake:": chr(0x1F365),
         ":fishing_pole_and_fish:": chr(0x1F3A3),
         ":fist:": chr(0x0270A),
         ":flags:": chr(0x1F38F),
         ":flashlight:": chr(0x1F526),
         ":flipper:": chr(0x1F42C),
         ":floppy_disk:": chr(0x1F4BE),
         ":flower_playing_cards:": chr(0x1F3B4),
         ":flushed:": chr(0x1F633),
         ":foggy:": chr(0x1F301),
         ":football:": chr(0x1F3C8),
         ":footprints:": chr(0x1F463),
         ":fork_and_knife:": chr(0x1F374),
         ":fountain:": chr(0x026F2),
         ":four_leaf_clover:": chr(0x1F340),
         ":free:": chr(0x1F193),
         ":fried_shrimp:": chr(0x1F364),
         ":fries:": chr(0x1F35F),
         ":frog:": chr(0x1F438),
         ":frowning:": chr(0x1F626),
         ":fuelpump:": chr(0x026FD),
         ":full_moon:": chr(0x1F315),
         ":full_moon_with_face:": chr(0x1F31D),
         ":game_die:": chr(0x1F3B2),
         ":gem:": chr(0x1F48E),
         ":gemini:": chr(0x0264A),
         ":ghost:": chr(0x1F47B),
         ":gift:": chr(0x1F381),
         ":gift_heart:": chr(0x1F49D),
         ":girl:": chr(0x1F467),
         ":globe_with_meridians:": chr(0x1F310),
         ":goat:": chr(0x1F410),
         ":golf:": chr(0x026F3),
         ":grapes:": chr(0x1F347),
         ":green_apple:": chr(0x1F34F),
         ":green_book:": chr(0x1F4D7),
         ":green_heart:": chr(0x1F49A),
         ":grey_exclamation:": chr(0x02755),
         ":grey_question:": chr(0x02754),
         ":grimacing:": chr(0x1F62C),
         ":grin:": chr(0x1F601),
         ":grinning:": chr(0x1F600),
         ":guardsman:": chr(0x1F482),
         ":guitar:": chr(0x1F3B8),
         ":gun:": chr(0x1F52B),
         ":haircut:": chr(0x1F487),
         ":hamburger:": chr(0x1F354),
         ":hammer:": chr(0x1F528),
         ":hamster:": chr(0x1F439),
         ":hand:": chr(0x0270B),
         ":handbag:": chr(0x1F45C),
         ":hankey:": chr(0x1F4A9),
         ":hatched_chick:": chr(0x1F425),
         ":hatching_chick:": chr(0x1F423),
         ":headphones:": chr(0x1F3A7),
         ":hear_no_evil:": chr(0x1F649),
         ":heart:": chr(0x02764),
         ":heart_decoration:": chr(0x1F49F),
         ":heart_eyes:": chr(0x1F60D),
         ":heart_eyes_cat:": chr(0x1F63B),
         ":heartbeat:": chr(0x1F493),
         ":heartpulse:": chr(0x1F497),
         ":hearts:": chr(0x02665),
         ":heavy_check_mark:": chr(0x02714),
         ":heavy_division_sign:": chr(0x02797),
         ":heavy_dollar_sign:": chr(0x1F4B2),
         ":heavy_exclamation_mark:": chr(0x02757),
         ":heavy_minus_sign:": chr(0x02796),
         ":heavy_multiplication_x:": chr(0x02716),
         ":heavy_plus_sign:": chr(0x02795),
         ":helicopter:": chr(0x1F681),
         ":herb:": chr(0x1F33F),
         ":hibiscus:": chr(0x1F33A),
         ":high_brightness:": chr(0x1F506),
         ":high_heel:": chr(0x1F460),
         ":hocho:": chr(0x1F52A),
         ":honey_pot:": chr(0x1F36F),
         ":honeybee:": chr(0x1F41D),
         ":horse:": chr(0x1F434),
         ":horse_racing:": chr(0x1F3C7),
         ":hospital:": chr(0x1F3E5),
         ":hotel:": chr(0x1F3E8),
         ":hotsprings:": chr(0x02668),
         ":hourglass:": chr(0x0231B),
         ":hourglass_flowing_sand:": chr(0x023F3),
         ":house:": chr(0x1F3E0),
         ":house_with_garden:": chr(0x1F3E1),
         ":hushed:": chr(0x1F62F),
         ":ice_cream:": chr(0x1F368),
         ":icecream:": chr(0x1F366),
         ":id:": chr(0x1F194),
         ":ideograph_advantage:": chr(0x1F250),
         ":imp:": chr(0x1F47F),
         ":inbox_tray:": chr(0x1F4E5),
         ":incoming_envelope:": chr(0x1F4E8),
         ":information_desk_person:": chr(0x1F481),
         ":information_source:": chr(0x02139),
         ":innocent:": chr(0x1F607),
         ":interrobang:": chr(0x02049),
         ":iphone:": chr(0x1F4F1),
         ":izakaya_lantern:": chr(0x1F3EE),
         ":jack_o_lantern:": chr(0x1F383),
         ":japan:": chr(0x1F5FE),
         ":japanese_castle:": chr(0x1F3EF),
         ":japanese_goblin:": chr(0x1F47A),
         ":japanese_ogre:": chr(0x1F479),
         ":jeans:": chr(0x1F456),
         ":joy:": chr(0x1F602),
         ":joy_cat:": chr(0x1F639),
         ":key:": chr(0x1F511),
         ":keycap_ten:": chr(0x1F51F),
         ":kimono:": chr(0x1F458),
         ":kiss:": chr(0x1F48B),
         ":kissing:": chr(0x1F617),
         ":kissing_cat:": chr(0x1F63D),
         ":kissing_closed_eyes:": chr(0x1F61A),
         ":kissing_heart:": chr(0x1F618),
         ":kissing_smiling_eyes:": chr(0x1F619),
         ":koala:": chr(0x1F428),
         ":koko:": chr(0x1F201),
         ":lantern:": chr(0x1F3EE),
         ":large_blue_circle:": chr(0x1F535),
         ":large_blue_diamond:": chr(0x1F537),
         ":large_orange_diamond:": chr(0x1F536),
         ":last_quarter_moon:": chr(0x1F317),
         ":last_quarter_moon_with_face:": chr(0x1F31C),
         ":laughing:": chr(0x1F606),
         ":leaves:": chr(0x1F343),
         ":ledger:": chr(0x1F4D2),
         ":left_luggage:": chr(0x1F6C5),
         ":left_right_arrow:": chr(0x02194),
         ":leftwards_arrow_with_hook:": chr(0x021A9),
         ":lemon:": chr(0x1F34B),
         ":leo:": chr(0x0264C),
         ":leopard:": chr(0x1F406),
         ":libra:": chr(0x0264E),
         ":light_rail:": chr(0x1F688),
         ":link:": chr(0x1F517),
         ":lips:": chr(0x1F444),
         ":lipstick:": chr(0x1F484),
         ":lock:": chr(0x1F512),
         ":lock_with_ink_pen:": chr(0x1F50F),
         ":lollipop:": chr(0x1F36D),
         ":loop:": chr(0x027BF),
         ":loudspeaker:": chr(0x1F4E2),
         ":love_hotel:": chr(0x1F3E9),
         ":love_letter:": chr(0x1F48C),
         ":low_brightness:": chr(0x1F505),
         ":m:": chr(0x024C2),
         ":mag:": chr(0x1F50D),
         ":mag_right:": chr(0x1F50E),
         ":mahjong:": chr(0x1F004),
         ":mailbox:": chr(0x1F4EB),
         ":mailbox_closed:": chr(0x1F4EA),
         ":mailbox_with_mail:": chr(0x1F4EC),
         ":mailbox_with_no_mail:": chr(0x1F4ED),
         ":man:": chr(0x1F468),
         ":man_with_gua_pi_mao:": chr(0x1F472),
         ":man_with_turban:": chr(0x1F473),
         ":mans_shoe:": chr(0x1F45E),
         ":maple_leaf:": chr(0x1F341),
         ":mask:": chr(0x1F637),
         ":massage:": chr(0x1F486),
         ":meat_on_bone:": chr(0x1F356),
         ":mega:": chr(0x1F4E3),
         ":melon:": chr(0x1F348),
         ":memo:": chr(0x1F4DD),
         ":mens:": chr(0x1F6B9),
         ":metro:": chr(0x1F687),
         ":microphone:": chr(0x1F3A4),
         ":microscope:": chr(0x1F52C),
         ":milky_way:": chr(0x1F30C),
         ":minibus:": chr(0x1F690),
         ":minidisc:": chr(0x1F4BD),
         ":mobile_phone_off:": chr(0x1F4F4),
         ":money_with_wings:": chr(0x1F4B8),
         ":moneybag:": chr(0x1F4B0),
         ":monkey:": chr(0x1F412),
         ":monkey_face:": chr(0x1F435),
         ":monorail:": chr(0x1F69D),
         ":moon:": chr(0x1F314),
         ":mortar_board:": chr(0x1F393),
         ":mount_fuji:": chr(0x1F5FB),
         ":mountain_bicyclist:": chr(0x1F6B5),
         ":mountain_cableway:": chr(0x1F6A0),
         ":mountain_railway:": chr(0x1F69E),
         ":mouse:": chr(0x1F42D),
         ":mouse2:": chr(0x1F401),
         ":movie_camera:": chr(0x1F3A5),
         ":moyai:": chr(0x1F5FF),
         ":muscle:": chr(0x1F4AA),
         ":mushroom:": chr(0x1F344),
         ":musical_keyboard:": chr(0x1F3B9),
         ":musical_note:": chr(0x1F3B5),
         ":musical_score:": chr(0x1F3BC),
         ":mute:": chr(0x1F507),
         ":nail_care:": chr(0x1F485),
         ":name_badge:": chr(0x1F4DB),
         ":necktie:": chr(0x1F454),
         ":negative_squared_cross_mark:": chr(0x0274E),
         ":neutral_face:": chr(0x1F610),
         ":new:": chr(0x1F195),
         ":new_moon:": chr(0x1F311),
         ":new_moon_with_face:": chr(0x1F31A),
         ":newspaper:": chr(0x1F4F0),
         ":ng:": chr(0x1F196),
         ":no_bell:": chr(0x1F515),
         ":no_bicycles:": chr(0x1F6B3),
         ":no_entry:": chr(0x026D4),
         ":no_entry_sign:": chr(0x1F6AB),
         ":no_good:": chr(0x1F645),
         ":no_mobile_phones:": chr(0x1F4F5),
         ":no_mouth:": chr(0x1F636),
         ":no_pedestrians:": chr(0x1F6B7),
         ":no_smoking:": chr(0x1F6AD),
         ":non-potable_water:": chr(0x1F6B1),
         ":nose:": chr(0x1F443),
         ":notebook:": chr(0x1F4D3),
         ":notebook_with_decorative_cover:": chr(0x1F4D4),
         ":notes:": chr(0x1F3B6),
         ":nut_and_bolt:": chr(0x1F529),
         ":o:": chr(0x02B55),
         ":o2:": chr(0x1F17E),
         ":ocean:": chr(0x1F30A),
         ":octopus:": chr(0x1F419),
         ":oden:": chr(0x1F362),
         ":office:": chr(0x1F3E2),
         ":ok:": chr(0x1F197),
         ":ok_hand:": chr(0x1F44C),
         ":ok_woman:": chr(0x1F646),
         ":older_man:": chr(0x1F474),
         ":older_woman:": chr(0x1F475),
         ":on:": chr(0x1F51B),
         ":oncoming_automobile:": chr(0x1F698),
         ":oncoming_bus:": chr(0x1F68D),
         ":oncoming_police_car:": chr(0x1F694),
         ":oncoming_taxi:": chr(0x1F696),
         ":open_book:": chr(0x1F4D6),
         ":open_file_folder:": chr(0x1F4C2),
         ":open_hands:": chr(0x1F450),
         ":open_mouth:": chr(0x1F62E),
         ":ophiuchus:": chr(0x026CE),
         ":orange_book:": chr(0x1F4D9),
         ":outbox_tray:": chr(0x1F4E4),
         ":ox:": chr(0x1F402),
         ":package:": chr(0x1F4E6),
         ":page_facing_up:": chr(0x1F4C4),
         ":page_with_curl:": chr(0x1F4C3),
         ":pager:": chr(0x1F4DF),
         ":palm_tree:": chr(0x1F334),
         ":panda_face:": chr(0x1F43C),
         ":paperclip:": chr(0x1F4CE),
         ":parking:": chr(0x1F17F),
         ":part_alternation_mark:": chr(0x0303D),
         ":partly_sunny:": chr(0x026C5),
         ":passport_control:": chr(0x1F6C2),
         ":paw_prints:": chr(0x1F43E),
         ":peach:": chr(0x1F351),
         ":pear:": chr(0x1F350),
         ":pencil:": chr(0x1F4DD),
         ":pencil2:": chr(0x0270F),
         ":penguin:": chr(0x1F427),
         ":pensive:": chr(0x1F614),
         ":performing_arts:": chr(0x1F3AD),
         ":persevere:": chr(0x1F623),
         ":person_frowning:": chr(0x1F64D),
         ":person_with_blond_hair:": chr(0x1F471),
         ":person_with_pouting_face:": chr(0x1F64E),
         ":phone:": chr(0x0260E),
         ":pig:": chr(0x1F437),
         ":pig2:": chr(0x1F416),
         ":pig_nose:": chr(0x1F43D),
         ":pill:": chr(0x1F48A),
         ":pineapple:": chr(0x1F34D),
         ":pisces:": chr(0x02653),
         ":pizza:": chr(0x1F355),
         ":point_down:": chr(0x1F447),
         ":point_left:": chr(0x1F448),
         ":point_right:": chr(0x1F449),
         ":point_up:": chr(0x0261D),
         ":point_up_2:": chr(0x1F446),
         ":police_car:": chr(0x1F693),
         ":poodle:": chr(0x1F429),
         ":poop:": chr(0x1F4A9),
         ":post_office:": chr(0x1F3E3),
         ":postal_horn:": chr(0x1F4EF),
         ":postbox:": chr(0x1F4EE),
         ":potable_water:": chr(0x1F6B0),
         ":pouch:": chr(0x1F45D),
         ":poultry_leg:": chr(0x1F357),
         ":pound:": chr(0x1F4B7),
         ":pouting_cat:": chr(0x1F63E),
         ":pray:": chr(0x1F64F),
         ":princess:": chr(0x1F478),
         ":punch:": chr(0x1F44A),
         ":purple_heart:": chr(0x1F49C),
         ":purse:": chr(0x1F45B),
         ":pushpin:": chr(0x1F4CC),
         ":put_litter_in_its_place:": chr(0x1F6AE),
         ":question:": chr(0x02753),
         ":rabbit:": chr(0x1F430),
         ":rabbit2:": chr(0x1F407),
         ":racehorse:": chr(0x1F40E),
         ":radio:": chr(0x1F4FB),
         ":radio_button:": chr(0x1F518),
         ":rage:": chr(0x1F621),
         ":railway_car:": chr(0x1F683),
         ":rainbow:": chr(0x1F308),
         ":raised_hand:": chr(0x0270B),
         ":raised_hands:": chr(0x1F64C),
         ":raising_hand:": chr(0x1F64B),
         ":ram:": chr(0x1F40F),
         ":ramen:": chr(0x1F35C),
         ":rat:": chr(0x1F400),
         ":recycle:": chr(0x0267B),
         ":red_car:": chr(0x1F697),
         ":red_circle:": chr(0x1F534),
         ":registered:": chr(0xAE),
         ":relaxed:": chr(0x0263A),
         ":relieved:": chr(0x1F60C),
         ":repeat:": chr(0x1F501),
         ":repeat_one:": chr(0x1F502),
         ":restroom:": chr(0x1F6BB),
         ":revolving_hearts:": chr(0x1F49E),
         ":rewind:": chr(0x023EA),
         ":ribbon:": chr(0x1F380),
         ":rice:": chr(0x1F35A),
         ":rice_ball:": chr(0x1F359),
         ":rice_cracker:": chr(0x1F358),
         ":rice_scene:": chr(0x1F391),
         ":ring:": chr(0x1F48D),
         ":rocket:": chr(0x1F680),
         ":roller_coaster:": chr(0x1F3A2),
         ":rooster:": chr(0x1F413),
         ":rose:": chr(0x1F339),
         ":rotating_light:": chr(0x1F6A8),
         ":round_pushpin:": chr(0x1F4CD),
         ":rowboat:": chr(0x1F6A3),
         ":rugby_football:": chr(0x1F3C9),
         ":runner:": chr(0x1F3C3),
         ":running:": chr(0x1F3C3),
         ":running_shirt_with_sash:": chr(0x1F3BD),
         ":sa:": chr(0x1F202),
         ":sagittarius:": chr(0x02650),
         ":sailboat:": chr(0x026F5),
         ":sake:": chr(0x1F376),
         ":sandal:": chr(0x1F461),
         ":santa:": chr(0x1F385),
         ":satellite:": chr(0x1F4E1),
         ":satisfied:": chr(0x1F606),
         ":saxophone:": chr(0x1F3B7),
         ":school:": chr(0x1F3EB),
         ":school_satchel:": chr(0x1F392),
         ":scissors:": chr(0x02702),
         ":scorpius:": chr(0x0264F),
         ":scream:": chr(0x1F631),
         ":scream_cat:": chr(0x1F640),
         ":scroll:": chr(0x1F4DC),
         ":seat:": chr(0x1F4BA),
         ":secret:": chr(0x03299),
         ":see_no_evil:": chr(0x1F648),
         ":seedling:": chr(0x1F331),
         ":shaved_ice:": chr(0x1F367),
         ":sheep:": chr(0x1F411),
         ":shell:": chr(0x1F41A),
         ":ship:": chr(0x1F6A2),
         ":shirt:": chr(0x1F455),
         ":shit:": chr(0x1F4A9),
         ":shoe:": chr(0x1F45E),
         ":shower:": chr(0x1F6BF),
         ":signal_strength:": chr(0x1F4F6),
         ":six_pointed_star:": chr(0x1F52F),
         ":ski:": chr(0x1F3BF),
         ":skull:": chr(0x1F480),
         ":sleeping:": chr(0x1F634),
         ":sleepy:": chr(0x1F62A),
         ":slot_machine:": chr(0x1F3B0),
         ":small_blue_diamond:": chr(0x1F539),
         ":small_orange_diamond:": chr(0x1F538),
         ":small_red_triangle:": chr(0x1F53A),
         ":small_red_triangle_down:": chr(0x1F53B),
         ":smile:": chr(0x1F604),
         ":smile_cat:": chr(0x1F638),
         ":smiley:": chr(0x1F603),
         ":smiley_cat:": chr(0x1F63A),
         ":smiling_imp:": chr(0x1F608),
         ":smirk:": chr(0x1F60F),
         ":smirk_cat:": chr(0x1F63C),
         ":smoking:": chr(0x1F6AC),
         ":snail:": chr(0x1F40C),
         ":snake:": chr(0x1F40D),
         ":snowboarder:": chr(0x1F3C2),
         ":snowflake:": chr(0x02744),
         ":snowman:": chr(0x026C4),
         ":sob:": chr(0x1F62D),
         ":soccer:": chr(0x026BD),
         ":soon:": chr(0x1F51C),
         ":sos:": chr(0x1F198),
         ":sound:": chr(0x1F509),
         ":space_invader:": chr(0x1F47E),
         ":spades:": chr(0x02660),
         ":spaghetti:": chr(0x1F35D),
         ":sparkle:": chr(0x02747),
         ":sparkler:": chr(0x1F387),
         ":sparkles:": chr(0x02728),
         ":sparkling_heart:": chr(0x1F496),
         ":speak_no_evil:": chr(0x1F64A),
         ":speaker:": chr(0x1F50A),
         ":speech_balloon:": chr(0x1F4AC),
         ":speedboat:": chr(0x1F6A4),
         ":star:": chr(0x02B50),
         ":star2:": chr(0x1F31F),
         ":stars:": chr(0x1F303),
         ":station:": chr(0x1F689),
         ":statue_of_liberty:": chr(0x1F5FD),
         ":steam_locomotive:": chr(0x1F682),
         ":stew:": chr(0x1F372),
         ":straight_ruler:": chr(0x1F4CF),
         ":strawberry:": chr(0x1F353),
         ":stuck_out_tongue:": chr(0x1F61B),
         ":stuck_out_tongue_closed_eyes:": chr(0x1F61D),
         ":stuck_out_tongue_winking_eye:": chr(0x1F61C),
         ":sun_with_face:": chr(0x1F31E),
         ":sunflower:": chr(0x1F33B),
         ":sunglasses:": chr(0x1F60E),
         ":sunny:": chr(0x02600),
         ":sunrise:": chr(0x1F305),
         ":sunrise_over_mountains:": chr(0x1F304),
         ":surfer:": chr(0x1F3C4),
         ":sushi:": chr(0x1F363),
         ":suspension_railway:": chr(0x1F69F),
         ":sweat:": chr(0x1F613),
         ":sweat_drops:": chr(0x1F4A6),
         ":sweat_smile:": chr(0x1F605),
         ":sweet_potato:": chr(0x1F360),
         ":swimmer:": chr(0x1F3CA),
         ":symbols:": chr(0x1F523),
         ":syringe:": chr(0x1F489),
         ":tada:": chr(0x1F389),
         ":tanabata_tree:": chr(0x1F38B),
         ":tangerine:": chr(0x1F34A),
         ":taurus:": chr(0x02649),
         ":taxi:": chr(0x1F695),
         ":tea:": chr(0x1F375),
         ":telephone:": chr(0x0260E),
         ":telephone_receiver:": chr(0x1F4DE),
         ":telescope:": chr(0x1F52D),
         ":tennis:": chr(0x1F3BE),
         ":tent:": chr(0x026FA),
         ":thought_balloon:": chr(0x1F4AD),
         ":thumbsdown:": chr(0x1F44E),
         ":thumbsup:": chr(0x1F44D),
         ":ticket:": chr(0x1F3AB),
         ":tiger:": chr(0x1F42F),
         ":tiger2:": chr(0x1F405),
         ":tired_face:": chr(0x1F62B),
         ":tm:": chr(0x02122),
         ":toilet:": chr(0x1F6BD),
         ":tokyo_tower:": chr(0x1F5FC),
         ":tomato:": chr(0x1F345),
         ":tongue:": chr(0x1F445),
         ":top:": chr(0x1F51D),
         ":tophat:": chr(0x1F3A9),
         ":tractor:": chr(0x1F69C),
         ":traffic_light:": chr(0x1F6A5),
         ":train:": chr(0x1F683),
         ":train2:": chr(0x1F686),
         ":tram:": chr(0x1F68A),
         ":triangular_flag_on_post:": chr(0x1F6A9),
         ":triangular_ruler:": chr(0x1F4D0),
         ":trident:": chr(0x1F531),
         ":triumph:": chr(0x1F624),
         ":trolleybus:": chr(0x1F68E),
         ":trophy:": chr(0x1F3C6),
         ":tropical_drink:": chr(0x1F379),
         ":tropical_fish:": chr(0x1F420),
         ":truck:": chr(0x1F69A),
         ":trumpet:": chr(0x1F3BA),
         ":tshirt:": chr(0x1F455),
         ":tulip:": chr(0x1F337),
         ":turtle:": chr(0x1F422),
         ":tv:": chr(0x1F4FA),
         ":twisted_rightwards_arrows:": chr(0x1F500),
         ":two_hearts:": chr(0x1F495),
         ":two_men_holding_hands:": chr(0x1F46C),
         ":two_women_holding_hands:": chr(0x1F46D),
         ":u5272:": chr(0x1F239),
         ":u5408:": chr(0x1F234),
         ":u55b6:": chr(0x1F23A),
         ":u6307:": chr(0x1F22F),
         ":u6708:": chr(0x1F237),
         ":u6709:": chr(0x1F236),
         ":u6e80:": chr(0x1F235),
         ":u7121:": chr(0x1F21A),
         ":u7533:": chr(0x1F238),
         ":u7981:": chr(0x1F232),
         ":u7a7a:": chr(0x1F233),
         ":umbrella:": chr(0x02614),
         ":unamused:": chr(0x1F612),
         ":underage:": chr(0x1F51E),
         ":unlock:": chr(0x1F513),
         ":up:": chr(0x1F199),
         ":v:": chr(0x0270C),
         ":vertical_traffic_light:": chr(0x1F6A6),
         ":vhs:": chr(0x1F4FC),
         ":vibration_mode:": chr(0x1F4F3),
         ":video_camera:": chr(0x1F4F9),
         ":video_game:": chr(0x1F3AE),
         ":violin:": chr(0x1F3BB),
         ":virgo:": chr(0x0264D),
         ":volcano:": chr(0x1F30B),
         ":vs:": chr(0x1F19A),
         ":walking:": chr(0x1F6B6),
         ":waning_crescent_moon:": chr(0x1F318),
         ":waning_gibbous_moon:": chr(0x1F316),
         ":warning:": chr(0x026A0),
         ":watch:": chr(0x0231A),
         ":water_buffalo:": chr(0x1F403),
         ":watermelon:": chr(0x1F349),
         ":wave:": chr(0x1F44B),
         ":wavy_dash:": chr(0x03030),
         ":waxing_crescent_moon:": chr(0x1F312),
         ":waxing_gibbous_moon:": chr(0x1F314),
         ":wc:": chr(0x1F6BE),
         ":weary:": chr(0x1F629),
         ":wedding:": chr(0x1F492),
         ":whale:": chr(0x1F433),
         ":whale2:": chr(0x1F40B),
         ":wheelchair:": chr(0x0267F),
         ":white_check_mark:": chr(0x02705),
         ":white_circle:": chr(0x026AA),
         ":white_flower:": chr(0x1F4AE),
         ":white_large_square:": chr(0x02B1C),
         ":white_medium_small_square:": chr(0x025FD),
         ":white_medium_square:": chr(0x025FB),
         ":white_small_square:": chr(0x025AB),
         ":white_square_button:": chr(0x1F533),
         ":wind_chime:": chr(0x1F390),
         ":wine_glass:": chr(0x1F377),
         ":wink:": chr(0x1F609),
         ":wolf:": chr(0x1F43A),
         ":woman:": chr(0x1F469),
         ":womans_clothes:": chr(0x1F45A),
         ":womans_hat:": chr(0x1F452),
         ":womens:": chr(0x1F6BA),
         ":worried:": chr(0x1F61F),
         ":wrench:": chr(0x1F527),
         ":x:": chr(0x0274C),
         ":yellow_heart:": chr(0x1F49B),
         ":yen:": chr(0x1F4B4),
         ":yum:": chr(0x1F60B),
         ":zap:": chr(0x026A1),
         ":zzz:": chr(0x1F4A4)}


def decode_emoji(message):
    """Replaces unicode emojis with shortnames for logging"""
    for shortname_emoji, u_emoji in EMOJI.items():
        message = message.replace(u_emoji, shortname_emoji)
    return message


from config import *

bot = ""

# Global constants
ERROR_NETWORK = 0
ERROR_DOESNTEXIST = 1

# Start logging
# Create logs folder
os.makedirs('logs/', exist_ok=True)
# discord.py log
discord_log = logging.getLogger('discord')
discord_log.setLevel(logging.INFO)
handler = logging.FileHandler(filename='logs/discord.log', encoding='utf-8', mode='a')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
discord_log.addHandler(handler)
# NabBot log
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
# Save log to file (info level)
fileHandler = logging.FileHandler(filename='logs/nabbot.log', encoding='utf-8', mode='a')
fileHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
fileHandler.setLevel(logging.INFO)
log.addHandler(fileHandler)
# Print output to console too (debug level)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s: %(message)s'))
consoleHandler.setLevel(logging.DEBUG)
log.addHandler(consoleHandler)

# Database global connections
userDatabase = sqlite3.connect(USERDB)
tibiaDatabase = sqlite3.connect(TIBIADB)

DB_LASTVERSION = 5


def initDatabase():
    """Initializes and/or updates the database to the current version"""

    # Database file is automatically created with connect, now we have to check if it has tables
    print("Checking database version...")
    db_version = 0
    try:
        c = userDatabase.cursor()
        c.execute("SELECT COUNT(*) as count FROM sqlite_master WHERE type = 'table'")
        result = c.fetchone()
        # Database is empty
        if result is None or result["count"] == 0:
            c.execute("""CREATE TABLE discord_users (
                      id INTEGER NOT NULL,
                      weight INTEGER DEFAULT 5,
                      PRIMARY KEY(id)
                      )""")
            c.execute("""CREATE TABLE chars (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      name TEXT,
                      last_level INTEGER DEFAULT -1,
                      last_death_time TEXT
                      )""")
            c.execute("""CREATE TABLE char_levelups (
                      char_id INTEGER,
                      level INTEGER,
                      date INTEGER
                      )""")
        c.execute("SELECT tbl_name FROM sqlite_master WHERE type = 'table' AND name LIKE 'db_info'")
        result = c.fetchone()
        # If there's no version value, version 1 is assumed
        if (result is None):
            c.execute("""CREATE TABLE db_info (
                      key TEXT,
                      value TEXT
                      )""")
            c.execute("INSERT INTO db_info(key,value) VALUES('version','1')")
            db_version = 1
            print("No version found, version 1 assumed")
        else:
            c.execute("SELECT value FROM db_info WHERE key LIKE 'version'")
            db_version = int(c.fetchone()["value"])
            print("Version {0}".format(db_version))
        if db_version == DB_LASTVERSION:
            print("Database is up to date.")
            return
        # Code to patch database changes
        if db_version == 1:
            # Added 'vocation' column to chars table, used to display vocations when /check'ing users among other things.
            # Changed how the last_level flagging system works a little, a character of unknown level is now flagged as level 0 instead of -1, negative levels are now used to flag of characters never seen online before.
            c.execute("ALTER TABLE chars ADD vocation TEXT")
            c.execute("UPDATE chars SET last_level = 0 WHERE last_level = -1")
            db_version += 1
        if db_version == 2:
            # Added 'events' table
            c.execute("""CREATE TABLE events (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      creator INTEGER,
                      name TEXT,
                      start INTEGER,
                      duration INTEGER,
                      active INTEGER DEFAULT 1
                      )""")
            db_version += 1
        if db_version == 3:
            # Added 'char_deaths' table
            # Added 'status column' to events (for event announces)
            c.execute("""CREATE TABLE char_deaths (
                      char_id INTEGER,
                      level INTEGER,
                      killer TEXT,
                      date INTEGER,
                      byplayer BOOLEAN
                      )""")
            c.execute("ALTER TABLE events ADD COLUMN status DEFAULT 4")
            db_version += 1
        if db_version == 4:
            # Added 'name' column to 'discord_users' table to save their names for external use
            c.execute("ALTER TABLE discord_users ADD name TEXT")
            db_version += 1
        print("Updated database to version {0}".format(db_version))
        c.execute("UPDATE db_info SET value = ? WHERE key LIKE 'version'", (db_version,))

    finally:
        userDatabase.commit()


def dict_factory(cursor, row):
    """Makes values returned by cursor fetch functions return a dictionary instead of a tuple.

    To implement this, the connection's row_factory method must be replaced by this one."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

userDatabase.row_factory = dict_factory
tibiaDatabase.row_factory = dict_factory


def vocAbb(vocation):
    """Given a vocation name, it returns an abbreviated string """
    abbrev = {'None': 'N', 'Druid': 'D', 'Sorcerer': 'S', 'Paladin': 'P', 'Knight': 'K', 'Elder Druid': 'ED',
              'Master Sorcerer': 'MS', 'Royal Paladin': 'RP', 'Elite Knight': 'EK'}
    try:
        return abbrev[vocation]
    except KeyError:
        return 'N'


def getLogin():
    """When the bot is run without a login.py file, it prompts the user for login info"""
    if not os.path.isfile("login.py"):
        print("This seems to be the first time NabBot is ran (or login.py is missing)")
        print("To run your own instance of NabBot you need to create a new bot account to get a bot token")
        print("https://discordapp.com/developers/applications/me")
        print("Alternatively, you can use a regular discord account for your bot, although this is not recommended")
        print("Insert a bot token OR an e-mail address for a regular account to be used as a bot")
        login = input(">>")
        email = ""
        password = ""
        token = ""
        if "@" in login:
            email = login
            password = input("Enter password: >>")
        elif len(login) >= 50:
            token = login
        else:
            input("What you entered isn't a token or an e-mail. Restart NabBot to retry.")
            quit()
        f = open("login.py", "w+")
        f.write("#Token always has priority, if token is defined it will always attempt to login using a token\n")
        f.write("#Comment the token line or set it empty to use email login\n")
        f.write("token = '{0}'\nemail = '{1}'\npassword = '{2}'\n".format(token, email, password))
        f.close()
        print("Login data has been saved correctly. You can change this later by editing login.py")
        input("Press any key to start NabBot now...")
        quit()
    return __import__("login")


def utilsGetBot(_bot):
    global bot
    bot = _bot


def formatMessage(message):
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


def weighedChoice(messages, condition1=False, condition2=False, condition3=False, condition4=False):
    """Makes weighed choices from message lists where [0] is a value representing the relative odds
    of picking a message and [1] is the message string"""

    # Find the max range by adding up the weigh of every message in the list
    # and purge out messages that dont fulfil the conditions
    range = 0
    _messages = []
    for message in messages:
        if len(message) == 6:
            if (not message[2] or condition1 in message[2]) and (not message[3] or condition2 in message[3]) and (
                not message[4] or condition3 in message[4]) and (not message[5] or condition4 in message[5]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        elif len(message) == 5:
            if (not message[2] or condition1 in message[2]) and (not message[3] or condition2 in message[3]) and (
                not message[4] or condition3 in message[4]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        elif len(message) == 4:
            if (not message[2] or condition1 in message[2]) and (not message[3] or condition2 in message[3]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        elif len(message) == 3:
            if (not message[2] or condition1 in message[2]):
                range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
                _messages.append(message)
        else:
            range = range + (message[0] if not message[1] in lastmessages else message[0] / 10)
            _messages.append(message)
    # Choose a random number
    rangechoice = random.randint(0, range)
    # Iterate until we find the matching message
    rangepos = 0
    for message in _messages:
        if rangepos <= rangechoice < rangepos + (message[0] if not message[1] in lastmessages else message[0] / 10):
            currentChar = lastmessages.pop()
            lastmessages.insert(0, message[1])
            return message[1]
        rangepos = rangepos + (message[0] if not message[1] in lastmessages else message[0] / 10)
    # This shouldnt ever happen...
    print("Error in weighedChoice!")
    return _messages[0][1]


def getChannelByServerAndName(server_name: str, channel_name: str):
    """Returns a channel within a server
    
    If server_name is left blank, it will search on all servers the bot can see"""
    if server_name == "":
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     bot.get_all_channels())
    else:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     getServerByName(server_name).channels)
    return channel


def getChannelByName(channel_name: str):
    """Alias for getChannelByServerAndName
    
    mainserver is searched first, then all visible servers"""
    channel = getChannelByServerAndName(mainserver, channel_name)
    if channel is None:
        return getChannelByServerAndName("", channel_name)
    return channel


def getServerByName(server_name: str):
    """Returns a server by its name"""
    server = discord.utils.find(lambda m: m.name == server_name, bot.servers)
    return server


def getUserByName(userName, search_pm=True) -> discord.User:
    """Returns a discord user by its name
    
    If there's duplicate usernames, it will return the first user found
    Users are searched on mainserver first, then on all visible channel and finally private channels."""
    user = None
    _mainserver = getServerByName(mainserver)
    if _mainserver is not None:
        user = discord.utils.find(lambda m: m.display_name.lower() == userName.lower(), _mainserver.members)
    if user is None:
        user = discord.utils.find(lambda m: m.display_name.lower() == userName.lower(), bot.get_all_members())
    if user is None and search_pm:
        private = discord.utils.find(lambda m: m.user.display_name.lower() == userName.lower(), bot.private_channels)
        if private is not None:
            user = private.user
    return user


def getUserById(userId, search_pm=True) -> discord.User:
    """Returns a discord user by its id

    If search_pm is False, only users in servers the bot can see will be searched."""
    user = discord.utils.find(lambda m: m.id == str(userId), bot.get_all_members())
    if user is None and search_pm:
        private = discord.utils.find(lambda m: m.user.id == str(userId), bot.private_channels)
        if private is not None:
            user = private.user
    return user


def getTimeDiff(time):
    """Returns a string showing the time difference of a timedelta"""
    if not isinstance(time, timedelta):
        return None
    hours = time.seconds // 3600
    minutes = (time.seconds // 60) % 60
    if time.days > 1:
        return "{0} days".format(time.days)
    if time.days == 1:
        return "1 day"
    if hours > 1:
        return "{0} hours".format(hours)
    if hours == 1:
        return "1 hour"
    if minutes > 1:
        return "{0} minutes".format(minutes)
    else:
        return "moments"


def getLocalTimezone():
    """Returns the server's local time zone"""
    # Getting local time and GMT
    t = time.localtime()
    u = time.gmtime(time.mktime(t))
    # UTC Offset
    return (timegm(t) - timegm(u)) / 60 / 60


def getTibiaTimeZone():
    """Returns Germany's timezone, considering their daylight saving time dates"""
    # Find date in Germany
    gt = datetime.utcnow() + timedelta(hours=1)
    germany_date = date(gt.year, gt.month, gt.day)
    dst_start = date(gt.year, 3, (31 - (int(((5 * gt.year) / 4) + 4) % int(7))))
    dst_end = date(gt.year, 10, (31 - (int(((5 * gt.year) / 4) + 1) % int(7))))
    if dst_start < germany_date < dst_end:
        return 2
    return 1


def getBrasiliaTimeZone():
    """Returns Brasilia's timezone, considering their daylight saving time dates"""
    # Find date in Brasilia
    bt = datetime.utcnow() - timedelta(hours=3)
    brasilia_date = date(bt.year, bt.month, bt.day)
    # These are the dates for the 2016/2017 time change, they vary yearly but ¯\0/¯, good enough
    dst_start = date(bt.year, 10, 16)
    dst_end = date(bt.year + 1, 2, 21)
    if dst_start < brasilia_date < dst_end:
        return -2
    return -3


start_time = datetime.utcnow()


def getUptime():
    """Returns a string with the time the bot has been running for.

    Start time is saved when this module is loaded, not when the bot actually logs in,
    so it is a couple seconds off."""
    now = datetime.utcnow()
    delta = now - start_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    days, hours = divmod(hours, 24)
    if days:
        fmt = '{d} days, {h} hours, {m} minutes, and {s} seconds'
    else:
        fmt = '{h} hours, {m} minutes, and {s} seconds'

    return fmt.format(d=days, h=hours, m=minutes, s=seconds)


def joinList(list, separator, endseparator):
    """Joins elements in a list with a separator between all elements and a different separator for the last element."""
    size = len(list)
    if size == 0:
        return ""
    if size == 1:
        return list[0]
    return separator.join(list[:size - 1]) + endseparator + str(list[size - 1])


def getAboutContent():
    """Returns a formatted string with general information about the bot.
    
    Used in /about and /whois Nab Bot"""
    user_count = 0
    char_count = 0
    try:
        c = userDatabase.cursor()
        c.execute("SELECT COUNT(*) FROM discord_users")
        result = c.fetchone()
        if result is not None:
            user_count = result[0]
        c.execute("SELECT COUNT(*) FROM chars")
        result = c.fetchone()
        if result is not None:
            char_count = result[0]
    finally:
        c.close()

    reply = "*Beep boop beep boop*. I'm just a bot!\n"
    reply += "\t- Authors: @Galarzaa#8515, @Nezune#2269\n"
    reply += "\t- Platform: Python " + EMOJI[":snake:"] + "\n"
    reply += "\t- Created: March 30th 2016\n"
    reply += "\t- Uptime: " + getUptime() + "\n"
    reply += "\t- Tracked users: " + str(user_count) + "\n"
    reply += "\t- Tracked chars: " + str(char_count)
    return reply


def getListRoles(server):
    """Lists all role within the discord server and returns to caller."""

    roles = []

    for role in server.roles:
        # Ignore @everyone and NabBot
        if role.name not in ["@everyone", "Nab Bot"]:
            roles.append(role)

    return roles


if __name__ == "__main__":
    input("To run NabBot, run nabbot.py")
