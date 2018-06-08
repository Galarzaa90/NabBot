import discord
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.database import set_server_property
from utils.tibia import tibia_worlds

SETTINGS = {
    "world": {"title": "🌐 World", "check": lambda ctx: ctx.guild.id not in config.lite_servers},
    # "newschannel": {"title": "📰 News channel"},
    # "eventschannel": {"title": "📣 Events channel"},
    # "levelschannel": {"title": "🌟 Levels & Deaths channel"},
    # "prefix": {"title": "❗ Prefix"},
    # "welcomemessage": {"title": "💬 Welcome message"},
    # "askchannel": {"title": "🤖 Command channel"},
}


class Settings:
    """Commands related to server customization."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @staticmethod
    async def __local_check(ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage("Settings can't be modified on private messages.")
        return True

    @checks.is_admin()
    @commands.guild_only()
    @commands.group(invoke_without_command=True, case_insensitive=True, aliases=["config"])
    async def settings(self, ctx):
        """Checks or sets various server-specific settings."""
        embed = discord.Embed(title=f"{ctx.me.display_name} settings", colour=discord.Color.blurple(),
                              description="Use the subcommands to change the settings for this server.")
        for name, info in SETTINGS.items():
            if "check" in info:
                if not info["check"](ctx):
                    continue
            embed.add_field(name=info["title"], value=f"`{ctx.prefix}{ctx.invoked_with} {name}`")

        await ctx.send(embed=embed)

    @checks.is_admin()
    @settings.command(name="world")
    async def settings_world(self, ctx, world: str=None):
        """Changes the world this discord server tracks.

        The tracked world is the Tibia world that this discord server is following.
        Only characters in that world will be registered."""
        if world is None:
            embed = discord.Embed(title=f"{SETTINGS[ctx.command.name]['title']} - {ctx.me.display_name} settings",
                                  description=ctx.command.short_doc, color=discord.Color.blurple())
            embed.add_field(name="Current value", value=ctx.world, inline=False)
            embed.add_field(name="Accepted values", value="Any Tibia world or `none` to disable.", inline=False)
            embed.add_field(name="Edit", value=f"`{ctx.prefix}{ctx.invoked_with} [world/none]`")
            await ctx.send(embed=embed)
            return
        world = world.strip().capitalize()
        if world not in tibia_worlds:
            await ctx.send("There's no world with that name.")
            return
        message = await ctx.send(f"Are you sure you want to assign **{world}** to this server?")
        confirm = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return

        set_server_property("world", ctx.guild.id, world)
        self.bot.reload_worlds()
        await ctx.send(f"{ctx.tick(True)} This server is now tracking **{world}**")


def setup(bot):
    bot.add_cog(Settings(bot))
