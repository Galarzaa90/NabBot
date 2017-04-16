from typing import List, Optional, Dict

import discord
from discord.abc import PrivateChannel, Messageable
from discord.ext import commands
import re

from config import log_channel_name, owner_ids, lite_servers
from nabbot import NabBot
from utils.database import tracked_worlds, announce_channels
from .messages import EMOJI

# Discord length limit
CONTENT_LIMIT = 2000
DESCRIPTION_LIMIT = 2048
FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
FIELD_AMOUNT = 25


def get_member_by_name(bot: discord.Client, name: str, guild: discord.Guild=None, guild_list=None) -> discord.Member:
    """Returns a member matching the name

    If no guild is specified, the first member matching the id will be returned, meaning that the guild he
    belongs to will be unknown, so member-only functions may be inaccurate.
    If server_list is defined, only members within that guild list will be searched for
    User functions remain the same, regardless of guild"""
    if guild_list is not None and len(guild_list) > 0:
        members = [m for ml in [g.members for g in guild_list] for m in ml]
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), members)
    if guild is not None:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), guild.members)
    else:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), bot.get_all_members())


def get_member(bot: discord.Client, user_id: int, guild: discord.Guild = None, guild_list=None) -> discord.Member:
    """Returns a member matching the id

    If no guild_id is specified, the first member matching the id will be returned, meaning that the guild he
    belongs to will be unknown, so member-only functions may be inaccurate.
    User functions remain the same, regardless of guild"""
    if guild_list is not None and len(guild_list) > 0:
        members = [m for ml in [g.members for g in guild_list] for m in ml]
        return discord.utils.find(lambda m: m.id == user_id, members)
    if guild is not None:
        return guild.get_member(user_id)
    else:
        return discord.utils.get(bot.get_all_members(), id=user_id)


def get_user_guilds(bot: NabBot, user_id: int) -> List[discord.Guild]:
    """Returns a list of the user's shared guilds with the bot"""
    return [bot.get_guild(gid) for gid in bot.members[user_id]]


def get_user_admin_guilds(bot: discord.Client, user_id):
    """Returns a list of the guilds the user is and admin of and the bot is a member of

    If the user is a bot owner, returns all the guilds the bot is in"""
    if user_id in owner_ids:
        return list(bot.guilds)
    guilds = get_user_guilds(bot, user_id)
    ret = []
    for guild in guilds:
        member = guild.get_member(user_id)   # type: discord.Member
        if member.guild_permissions.administrator:
            ret.append(guild)
    return ret


def get_user_worlds(bot: discord.Client, user_id: int, guild_list=None) -> List[Dict[int, str]]:
    """Returns a list of all the tibia worlds the user is tracked in.

    This is based on the tracked world of each guild the user belongs to.
    guild_list can be passed to search in a specific set of guilds. Note that the user may not belong to them."""
    if guild_list is None:
        guild_list = get_user_guilds(bot, user_id)
    return list(set([world for guild, world in tracked_worlds.items() if guild in [g.id for g in guild_list]]))


def get_role(guild: discord.Guild, role_id: int = None, role_name: str = None) -> Optional[discord.Role]:
    """Returns a role matching the id in a server"""
    if guild is None:
        raise ValueError("guild is None")
    if role_id is None and role_name is None:
        raise ValueError("Either role_id or role_name must be specified")
    for role in guild.roles:
        if role.id == role_id or role.name.lower() == role_name.lower():
            return role
    return None


def get_role_list(guild: discord.Guild) -> List[discord.Role]:
    """Lists all role within the discord server and returns to caller."""
    roles = []
    for role in guild.roles:
        # Ignore @everyone and NabBot
        if role.name not in ["@everyone", "Nab Bot"]:
            roles.append(role)
    return roles


def get_user_color(user: discord.Member, guild: discord.Guild) -> discord.Colour:
    """Gets the user's color based on the highest role with a color"""
    # If it's a PM, server will be none
    if guild is None:
        return discord.Colour.default()
    member = guild.get_member(user.id)  # type: discord.Member
    if member is not None:
        return member.colour
    return discord.Colour.default()


def get_region_string(region: discord.GuildRegion) -> str:
    """Returns a formatted string for a given GuildRegion"""
    regions = {"us-west": EMOJI[":flag_us:"]+"US West",
               "us-east": EMOJI[":flag_us:"]+"US East",
               "us-central": EMOJI[":flag_us:"]+"US Central",
               "us-south": EMOJI[":flag_us:"]+"US South",
               "eu-west": EMOJI[":flag_eu:"]+"West Europe",
               "eu-central": EMOJI[":flag_eu:"]+"Central Europe",
               "singapore": EMOJI[":flag_sg:"]+"Singapore",
               "london": EMOJI[":flag_gb:"]+"London",
               "sydney": EMOJI[":flag_au:"]+"Sydney",
               "amsterdam": EMOJI[":flag_nl:"]+"Amsterdam",
               "frankfurt": EMOJI[":flag_de:"]+"Frankfurt",
               "brazil": EMOJI[":flag_br:"]+"Brazil"
               }
    return regions.get(str(region), str(region))


def is_private(channel: Messageable) -> bool:
    return isinstance(channel, PrivateChannel)


def get_announce_channel(bot: discord.Client, guild: discord.Guild) -> discord.TextChannel:
    """Returns this world's announcements channel. If no channel is set, the default channel is returned.

    It also checks if the bot has permissions on that channel, if not, it will return the default channel too."""
    channel_name = announce_channels.get(guild.id, None)
    if channel_name is None:
        return guild.default_channel
    channel = bot.get_channel_by_name(channel_name, guild)
    if channel is None:
        return guild.default_channel
    permissions = channel.permissions_for(get_member(bot, bot.user.id, guild))
    if not permissions.read_messages or not permissions.send_messages:
        return guild.default_channel
    return channel


def clean_string(ctx: commands.Context, string: str) -> str:
    """Turns mentions into plain text

    For message object, there's already a property that odes this: message.clean_content"""
    def repl_channel(match):
        channel_id = match.group(0).replace("<", "").replace("#", "").replace(">", "")
        channel = ctx.message.guild.get_channel(channel_id)
        return "#deleted_channel" if channel is None else "#"+channel.name

    def repl_role(match):
        role_id = match.group(0).replace("<", "").replace("@", "").replace("&", "").replace(">", "")
        role = get_role(ctx.message.guild, role_id)
        return "@deleted_role" if role is None else "@"+role.name

    def repl_user(match):
        user_id = match.group(0).replace("<", "").replace("@", "").replace("!", "").replace(">", "")
        user = ctx.message.guild.get_member(user_id)
        return "@deleted_role" if user is None else "@" + user.display_name
    # Find channel mentions:
    string = re.sub(r"<#\d+>", repl_channel, string)
    # Find role mentions
    string = re.sub(r"<@&\d+>", repl_role, string)
    # Find user mentions
    string = re.sub(r"<@!\d+>", repl_user, string)
    string = re.sub(r"<@\d+>", repl_user, string)
    # Clean @everyone and @here
    return string.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")


def is_lite_mode(ctx: commands.Context) -> bool:
    """Checks if the current command context is limited to lite mode.
    
    If the guild is in the lite_guilds list, the context is in lite mode.
    If the guild is in private message, and the message author is in at least ONE guild that is not in lite_guilds, 
    then context is not lite"""
    if is_private(ctx.message.channel):
        for g in get_user_guilds(ctx.bot, ctx.message.author.id):
            if g.id not in lite_servers:
                return False
    else:
        return ctx.message.guild in lite_servers
