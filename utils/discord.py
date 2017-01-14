import asyncio
import discord
from discord.ext import commands
import re

from config import log_channel_name
from utils.database import tracked_worlds
from .messages import EMOJI


def get_channel_by_name(bot: discord.Client, channel_name: str, server: discord.Server = None,
                        server_id: str = None, server_name: str = None) -> discord.Channel:
    """Finds a channel by name on all the channels visible by the bot.

    If server, server_id or server_name is specified, only channels in that server will be searched"""
    if server is None and server_id is not None:
        server = bot.get_server(server_id)
    if server is None and server_name is not None:
        server = get_server_by_name(bot, server_name)
    if server is None:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     bot.get_all_channels())
    else:
        channel = discord.utils.find(lambda m: m.name == channel_name and not m.type == discord.ChannelType.voice,
                                     server.channels)
    return channel


def get_server_by_name(bot: discord.Client, server_name: str) -> discord.Server:
    """Returns a server by its name"""
    server = discord.utils.find(lambda m: m.name.lower() == server_name.lower(), bot.servers)
    return server


def get_member_by_name(bot: discord.Client, name: str, server: discord.Server=None, server_list=None) -> discord.Member:
    """Returns a member matching the name

    If no server is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    If server_list is defined, only members within that server list will be searched for
    User functions remain the same, regardless of server"""
    if server_list is not None and len(server_list) > 0:
        members = [m for ml in [s.members for s in server_list] for m in ml]
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), members)
    if server is not None:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), server.members)
    else:
        return discord.utils.find(lambda m: m.display_name.lower() == name.lower(), bot.get_all_members())


def get_member(bot: discord.Client, user_id, server: discord.Server = None) -> discord.Member:
    """Returns a member matching the id

    If no server_id is specified, the first member matching the id will be returned, meaning that the server he
    belongs to will be unknown, so member-only functions may be inaccurate.
    User functions remain the same, regardless of server"""
    if server is not None:
        return server.get_member(str(user_id))
    else:
        return discord.utils.get(bot.get_all_members(), id=str(user_id))


def get_user_servers(bot: discord.Client, user_id):
    """Returns a list of the user's shared servers with the bot"""
    return [m.server for m in bot.get_all_members() if m.id == str(user_id)]


def get_user_admin_servers(bot: discord.Client, user_id):
    """Returns a list of the servers the user is and admin of and the bot is a member of"""
    servers = get_user_servers(bot, user_id)
    ret = []
    for server in servers:
        member = server.get_member(str(user_id))   # type: discord.Member
        if member.server_permissions.administrator:
            ret.append(server)
    return ret


def get_user_worlds(bot: discord.Client, user_id, server_list=None):
    """Returns a list of all the tibia worlds the user is tracked in.

    This is based on the tracked world of each server the user belongs to.
    server_list can be passed to search in a specific set of servers. Note that the user may not belong to them."""
    if server_list is None:
        server_list = get_user_servers(bot, user_id)
    return [world for server, world in tracked_worlds.items() if server in [s.id for s in server_list]]


@asyncio.coroutine
def send_log_message(bot: discord.Client, server: discord.Server, content=None, embed: discord.Embed = None):
    """Sends a message on the server-log channel

    If the channel doesn't exist, it doesn't send anything or give of any warnings as it meant to be an optional
    feature"""
    channel = get_channel_by_name(bot, log_channel_name, server)
    if channel is None:
        return
    yield from bot.send_message(channel, content=content, embed=embed)


def get_role(server: discord.Server, role_id) -> discord.Role:
    """Returns a role matching the id in a server"""
    if server is not None:
        for role in server.roles:
            if role.id == str(role_id):
                return role
    return None


def get_role_list(server: discord.Server):
    """Lists all role within the discord server and returns to caller."""
    roles = []
    for role in server.roles:
        # Ignore @everyone and NabBot
        if role.name not in ["@everyone", "Nab Bot"]:
            roles.append(role)

    return roles


def get_user_color(user: discord.User, server: discord.Server) -> discord.Colour:
    """Gets the user's color based on the highest role with a color"""
    # If it's a PM, server will be none
    if server is None:
        return discord.Colour.default()
    member = server.get_member(user.id)  # type: discord.Member
    if member is not None:
        return member.colour
    return discord.Colour.default()


def get_region_string(region: discord.ServerRegion) -> str:
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
