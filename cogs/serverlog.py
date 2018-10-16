import discord

from cogs.utils import get_user_avatar
from nabbot import NabBot


class ServerLog:
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def on_character_rename(self, old_name, new_name, user_id: int):
        """Called when a character is renamed."""
        user_guilds = self.bot.get_user_guilds(user_id)

        for guild in user_guilds:
            member = guild.get_member(user_id)
            if member is None:
                continue
            embed = discord.Embed(color=discord.Color.blurple(),
                                  description=f"A character of {member.mention} changed name.\n"
                                              f"‣ **{old_name}** -> **{new_name}**")
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=get_user_avatar(member))
            await self.bot.send_log_message(guild, embed=embed)

def setup(bot):
    bot.add_cog(ServerLog(bot))
