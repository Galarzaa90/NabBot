import asyncio
import discord
from discord.ext import commands
import re

from config import log_channel_name, owner_ids
from utils.database import tracked_worlds, announce_channels
from .messages import EMOJI

# Discord length limit
CONTENT_LIMIT = 2000
DESCRIPTION_LIMIT = 2048
FIELD_NAME_LIMIT = 256
FIELD_VALUE_LIMIT = 1024
FIELD_AMOUNT = 25

def get_channel_by_name(bot: discord.Client, channel_name: str, guild: discord.Guild = None,
                        guild_id: str = None, guild_name: str = None) -> discord.TextChannel:
    """Finds a channel by name on all the channels visible by the bot.

    If server, server_id or server_name is specified, only channels in that server will be searched"""
    if guild is None and guild_id is not None:
        guild = bot.get_guild(guild_id)
    if guild is None and guild_name is not None:
        guild = get_server_by_name(bot, guild_name)
    if guild is None:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     bot.get_all_channels())
    else:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     guild.channels)
    return channel


def get_server_by_name(bot: discord.Client, guild_name: str) -> discord.Guild:
    """Returns a guild by its name"""
    guild = discord.utils.find(lambda m: m.name.lower() == guild_name.lower(), bot.guilds)
    return guild


def get_member_by_name(bot: discord.Client, name: str, guild: discord.Guild=None, guild_list=None) -> discord.Member:
    """Returns a member matching the name

    If no server is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    If server_list is defined, only members within that server list will be searched for
    User functions remain the same, regardless of server"""
    if guild_list is not None and len(guild_list) > 0:
        members = [m for ml in [g.members for g in guild_list] for m in ml]
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), members)
    if guild is not None:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), guild.members)
    else:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), bot.get_all_members())


def get_member(bot: discord.Client, user_id: int, guild: discord.Guild = None, guild_list=None) -> discord.Member:
    """Returns a member matching the id

    If no server_id is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    User functions remain the same, regardless of server"""
    if guild_list is not None and len(guild_list) > 0:
        members = [m for ml in [g.members for g in guild_list] for m in ml]
        return discord.utils.find(lambda m: m.id == user_id, members)
    if guild is not None:
        return guild.get_member(user_id)
    else:
        return discord.utils.get(bot.get_all_members(), id=user_id)


def get_user_servers(bot: discord.Client, user_id):
    """Returns a list of the user's shared servers with the bot"""
    return [m.guild for m in bot.get_all_members() if m.id == str(user_id)]


def get_user_admin_servers(bot: discord.Client, user_id):
    """Returns a list of the servers the user is and admin of and the bot is a member of

    If the user is a bot owner, returns all the servers the bot is in"""
    if user_id in owner_ids:
        return list(bot.guilds)
    guiilds = get_user_servers(bot, user_id)
    ret = []
    for guild in guiilds:
        member = guild.get_member(str(user_id))   # type: discord.Member
        if member.guild_permissions.administrator:
            ret.append(guild)
    return ret


def get_user_worlds(bot: discord.Client, user_id, guild_list=None):
    """Returns a list of all the tibia worlds the user is tracked in.

    This is based on the tracked world of each server the user belongs to.
    server_list can be passed to search in a specific set of servers. Note that the user may not belong to them."""
    if guild_list is None:
        guild_list = get_user_servers(bot, user_id)
    return list(set([world for guild, world in tracked_worlds.items() if guild in [g.id for g in guild_list]]))


@asyncio.coroutine
def send_log_message(bot: discord.Client, guild: discord.Guild, content=None, embed: discord.Embed = None):
    """Sends a message on the server-log channel

    If the channel doesn't exist, it doesn't send anything or give of any warnings as it meant to be an optional
    feature"""
    channel = get_channel_by_name(bot, log_channel_name, guild)
    if channel is None:
        return
    yield from channel.send(content=content, embed=embed)


def get_role(server: discord.Guild, role_id) -> discord.Role:
    """Returns a role matching the id in a server"""
    if server is not None:
        for role in server.roles:
            if role.id == str(role_id):
                return role
    return None


def get_role_list(server: discord.Guild):
    """Lists all role within the discord server and returns to caller."""
    roles = []
    for role in server.roles:
        # Ignore @everyone and NabBot
        if role.name not in ["@everyone", "Nab Bot"]:
            roles.append(role)

    return roles


def get_user_color(user: discord.User, guild: discord.Guild) -> discord.Colour:
    """Gets the user's color based on the highest role with a color"""
    # If it's a PM, server will be none
    if guild is None:
        return discord.Colour.default()
    member = guild.get_member(user.id)  # type: discord.Member
    if member is not None:
        return member.colour
    return discord.Colour.default()


def get_region_string(region: discord.GuildRegion) -> str:
    """Returns a formatted string for a given ServerRegion"""
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


def get_announce_channel(bot: discord.Client, server: discord.Guild) -> discord.TextChannel:
    """Returns this world's announcements channel. If no channel is set, the default channel is returned.

    It also checks if the bot has permissions on that channel, if not, it will return the default channel too."""
    channel_name = announce_channels.get(server.id, None)
    if channel_name is None:
        return server.default_channel
    channel = get_channel_by_name(bot, channel_name, server)
    if channel is None:
        return server.default_channel
    permissions = channel.permissions_for(get_member(bot, bot.user.id, server))
    if not permissions.read_messages or not permissions.send_messages:
        return server.default_channel
    return channel


def clean_string(ctx: commands.Context, string: str) -> str:
    """Turns mentions into plain text

    For message object, there's already a property that odes this: message.clean_content"""
    def repl_channel(match):
        channel_id = match.group(0).replace("<", "").replace("#", "").replace(">", "")
        channel = ctx.message.server.get_channel(str(channel_id))
        return "#deleted_channel" if channel is None else "#"+channel.name

    def repl_role(match):
        role_id = match.group(0).replace("<", "").replace("@", "").replace("&", "").replace(">", "")
        role = get_role(ctx.message.server, role_id)
        return "@deleted_role" if role is None else "@"+role.name

    def repl_user(match):
        user_id = match.group(0).replace("<", "").replace("@", "").replace("!", "").replace(">", "")
        user = ctx.message.server.get_member(user_id)
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
