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

import discord
from discord.ext import commands

from nabbot import NabBot
from cogs.utils.context import NabCtx
from cogs.utils.tibia import get_guild
from cogs.utils.errors import NetworkError

# This cog has a specific use, and probably has no use for anyone else but me
# This is part of the repository to serve as an example of custom cogs

# /r/TibiaMMO server
GUILD_ID = 140054830252163072
# This is the channel where guilds are advertised
GUILDS_CHANNEL = 449703177000845332
MOD_ROLE = 191848397072891905

# Testing values
# GUILD_ID = 441991938200305674
# GUILDS_CHANNEL = 450740857679642624
# MOD_ROLE = 442005462611656725


class TibiaMMO(commands.Cog):
    """Utilities for /r/TibiaMMO discord server."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def cog_check(self, ctx: NabCtx):
        if ctx.is_private:
            return False
        if ctx.guild.id != GUILD_ID:
            return False
        role = discord.utils.find(lambda r: r.id == MOD_ROLE, ctx.author.roles)
        return role is not None

    @commands.command()
    async def postguild(self, ctx: NabCtx, guild, invite=None, reddit=None, *, member: discord.Member = None):
        """Creates an advertisement post on the reddit guilds channel

        Parameters:
        **guild**: The guild's name, if it has multiple words, surround with quotes.
        **invite**: Invite link to their discord, if available. Type - to ignore.
        **reddit**: The reddit's username of the person to contact. Type - to ignore.
        **member**: The discord's username of the person to contact. Type - or leave blank to omit.
        """
        await ctx.message.delete()
        with ctx.typing():
            try:
                guild = await get_guild(guild)
                if guild is None:
                    await ctx.send(f"I couldn't find any guild named '**{guild}**'. "
                                   f"Please use quotes for names with multiple words.", delete_after=10)
                    return
            except NetworkError:
                await ctx.send("I'm having network issues, please try later.", delete_after=10)
                return

        channel: discord.TextChannel = ctx.guild.get_channel(GUILDS_CHANNEL)
        if channel is None:
            await ctx.send("The channel for reddit guilds seems to have been deleted.")
            return

        embed = discord.Embed(title=f"{guild.name} ({guild.world})", description=guild.description,
                              colour=discord.Colour.blurple(), url=guild.url)
        embed.set_thumbnail(url=guild.logo_url)
        embed.add_field(name="In-game contact", value=f"[{guild.members[0].name}]"
                                                      f"({guild.members[0].url})")
        if member is not None:
            embed.add_field(name="Discord contact", value=member.mention)
        if not invite or invite != "-":
            invite = f"―――――――――――――――――――――\nDiscord Invite: {invite}"
        else:
            invite = "―――――――――――――――――――――"

        if not reddit or reddit != "-":
            embed.add_field(name="Reddit contact", value=f"[u/{reddit}](https://reddit.com/u/{reddit})")
        try:
            await channel.send(invite, embed=embed)
            await ctx.send(ctx.tick(), delete_after=10)
        except discord.Forbidden:
            await ctx.send(f"I don't have permissions to write on {channel.mention}.", delete_after=10)
        except discord.HTTPException:
            await ctx.send("Something went wrong when trying to post the message.", delete_after=10)


def setup(bot):
    bot.add_cog(TibiaMMO(bot))
