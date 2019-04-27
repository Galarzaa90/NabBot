#  Copyright 2019 Allan Galarza
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import logging
import random
from typing import List, Optional

import discord
from discord.ext import commands

from nabbot import NabBot
from .utils import CogUtils, checks, get_user_avatar, is_numeric, parse_message_link
from .utils.context import NabCtx

log = logging.getLogger("nabbot")


class General(commands.Cog, CogUtils):
    """General use commands."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    def cog_unload(self):
        log.info(f"{self.tag} Unloading cog")

    # region Commands
    @commands.command(aliases=["checkdm"])
    async def checkpm(self, ctx: NabCtx):
        """Checks if you can receive PMs from the bot.

        If you can't receive PMs, 'Allow direct messages from server members.' must be enabled in the Privacy Settings
         of any server where NabBot is in."""
        if ctx.guild is None:
            return await ctx.success("This is a private message, so yes... PMs are working.")
        try:
            await ctx.author.send("Testing PMs...")
            await ctx.success("You can receive PMs.")
        except discord.Forbidden:
            await ctx.error("You can't receive my PMs.\n"
                            "To enable, go to Server > Privacy Settings and enable the checkbox in any server I'm in.")

    @commands.command(usage="<choices...>")
    async def choose(self, ctx, *choices: str):
        """Chooses between multiple choices.

        Each choice is separated by spaces. For choices that contain spaces surround it with quotes.
        e.g. "Choice A" ChoiceB "Choice C"
        """
        if not choices:
            await ctx.error(f"I can't tell you what to choose if you don't give me choices")
            return
        user = ctx.author
        await ctx.send('Alright, **@{0}**, I choose: "{1}"'.format(user.display_name, random.choice(choices)))

    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @checks.can_embed()
    @commands.command(nam="permissions", aliases=["perms"])
    async def permissions(self, ctx: NabCtx, member: discord.Member = None, channel: discord.TextChannel = None):
        """Shows a member's permissions in the current channel.

        If no member is provided, it will show your permissions.
        Optionally, a channel can be provided as the second parameter, to check permissions in said channel."""
        member = member or ctx.author
        channel = channel or ctx.channel
        guild_permissions = channel.permissions_for(member)
        embed = discord.Embed(title=f"Permissions in #{channel.name}", colour=member.colour)
        embed.set_author(name=member.display_name, icon_url=get_user_avatar(member))
        allowed = []
        denied = []
        for name, value in guild_permissions:
            name = name.replace('_', ' ').replace('guild', 'server').title()
            if value:
                allowed.append(name)
            else:
                denied.append(name)
        if allowed:
            embed.add_field(name=f"{ctx.tick()}Allowed", value="\n".join(allowed))
        if denied:
            embed.add_field(name=f"{ctx.tick(False)}Denied", value="\n".join(denied))
        await ctx.send(embed=embed)

    @commands.guild_only()
    @checks.can_embed()
    @commands.command(usage="<message>")
    async def quote(self, ctx: NabCtx, message_id: str):
        """Shows a messages by its ID or link.

        In order to get the message's link, you can right click and select **Copy Link**.

        In order to get a message's id, you need to enable Developer Mode.
        Developer mode is found in `User Settings > Appearance`.
        Once enabled, you can right click a message and select **Copy ID**.

        Using a message link is faster than using an Id.

        Note that the bot won't attempt to search in channels you can't read.
        Additionally, messages in NSFW channels can't be quoted in regular channels."""
        message = None
        if is_numeric(message_id):
            message = await self.search_message(ctx, int(message_id))
        else:
            guild_id, channel_id, message_id = parse_message_link(message_id)
            if message_id is None or channel_id is None:
                return await ctx.error("That's not a valid message link or message id.")
            if guild_id is None:
                return await ctx.error("I can't quote private messages.")
            if guild_id != ctx.guild.id:
                return await ctx.error("I can't quote messages from other servers.")
            channel: discord.TextChannel = ctx.guild.get_channel(channel_id)
            bot_perm = channel.permissions_for(ctx.me)
            auth_perm = channel.permissions_for(ctx.author)
            # Both bot and members must be able to read the channel.
            if channel is not None and bot_perm.read_message_history and bot_perm.read_messages and \
                    auth_perm.read_message_history and auth_perm.read_messages:
                try:
                    message = await channel.fetch_message(message_id)
                except discord.HTTPException:
                    pass
        if message is None:
            await ctx.error("I can't find that message, or it is in a channel you can't access.")
            return
        if not message.content and not message.attachments:
            await ctx.error("I can't quote embed messages.")
            return
        if message.channel.nsfw and not ctx.channel.nsfw:
            await ctx.error("I can't quote messages from NSFW channels in regular channels.")
            return
        embed = discord.Embed(description=f"{message.content}\n\n[Jump to original]({message.jump_url})",
                              timestamp=message.created_at)
        try:
            embed.colour = message.author.colour
        except AttributeError:
            pass
        embed.set_author(name=message.author.display_name, icon_url=get_user_avatar(message.author))
        embed.set_footer(text=f"In #{message.channel.name}")
        if len(message.attachments) >= 1:
            attachment: discord.Attachment = message.attachments[0]
            if attachment.height is not None:
                embed.set_image(url=message.attachments[0].url)
            else:
                embed.add_field(name="Attached file",
                                value=f"[{attachment.filename}]({attachment.url}) ({attachment.size:,} bytes)")
        await ctx.send(embed=embed)

    @commands.command(aliases=["dice"], usage="[times][d[sides]]")
    async def roll(self, ctx: NabCtx, params=None):
        """Rolls a die.

        By default, it rolls a 6-sided die once.
        You can specify how many times you want the die to be rolled.

        You can also specify the number of sides of the die, using the format `TdS` where T is times and S is sides."""
        sides = 6
        if params is None:
            times = 1
        elif is_numeric(params):
            times = int(params)
        else:
            try:
                times, sides = map(int, params.split('d'))
            except ValueError:
                await ctx.error("Invalid parameter! I'm expecting `<times>d<rolls>`.")
                return
        if times == 0:
            await ctx.send("You want me to roll the die zero times? Ok... There, done.")
            return
        if times < 0:
            await ctx.error("It's impossible to roll negative times!")
            return
        if sides <= 0:
            await ctx.error("There's no dice with zero or less sides!")
            return
        if times > 20:
            await ctx.error("I can't roll the die that many times. Only up to 20.")
            return
        if sides > 100:
            await ctx.error("I don't have dice with more than 100 sides.")
            return
        time_plural = "times" if times > 1 else "time"
        results = [str(random.randint(1, sides)) for _ in range(times)]
        result = f"You rolled a **{sides}**-sided die **{times}** {time_plural} and got:\n\t{', '.join(results)}"
        if sides == 1:
            result += "\nWho would have thought? 🙄"
        await ctx.send(result)
    # endregion

    # region Auxiliary methods
    @classmethod
    async def search_message(cls, ctx: NabCtx, message_id: int):
        """Searches for a message with a specific id in the current context."""
        channels: List[discord.TextChannel] = ctx.guild.text_channels
        message: Optional[discord.Message] = None
        with ctx.typing():
            for channel in channels:
                bot_perm = ctx.bot_permissions
                auth_perm = ctx.author_permissions
                # Both bot and members must be able to read the channel.
                if not (bot_perm.read_message_history and bot_perm.read_messages and
                        auth_perm.read_message_history and auth_perm.read_messages):
                    continue
                try:
                    message = await channel.fetch_message(message_id)
                except discord.HTTPException:
                    continue
                if message is not None:
                    break
        return message
    # endregion

def setup(bot):
    bot.add_cog(General(bot))
