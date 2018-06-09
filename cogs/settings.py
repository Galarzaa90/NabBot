import discord
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.database import set_server_property, get_server_property
from utils.tibia import tibia_worlds

SETTINGS = {
    "world": {"title": "🌐 World", "check": lambda ctx: ctx.guild.id not in config.lite_servers},
    # "newschannel": {"title": "📰 News channel"},
    # "eventschannel": {"title": "📣 Events channel"},
    "levelschannel": {"title": "🌟☠ Levels & Deaths channel", "check":
        lambda ctx: ctx.guild.id not in config.lite_servers},
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

    @staticmethod
    async def show_info_embed(ctx, current_value, accepted_values, edit_params):
        embed = discord.Embed(title=f"{SETTINGS[ctx.command.name]['title']} - {ctx.me.display_name} settings",
                              description=ctx.command.short_doc, color=discord.Color.blurple())
        embed.add_field(name="📄 Current value", value=current_value, inline=False)
        embed.add_field(name="☑ Accepted values", value=accepted_values, inline=False)
        embed.add_field(name="📝 Edit", inline=False,
                        value=f"`{ctx.prefix}{ctx.command.full_parent_name} {ctx.invoked_with} [{edit_params}]`")
        embed.set_footer(text=f'Use "{ctx.prefix}help {ctx.command.full_parent_name} {ctx.invoked_with}" for more info')
        await ctx.send(embed=embed)

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
            await self.show_info_embed(ctx, ctx.world, "Any Tibia world or `none` to disable.", "world/none")
            return
        world = world.strip().capitalize()
        if world == "None":
            if ctx.world is None:
                await ctx.send("This server is already not tracking any world.")
                return
            message = await ctx.send(f"Are you sure you want to unassign **{ctx.world}** from this server?")
            world = None
        else:
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
        if world is None:
            await ctx.send(f"{ctx.tick(True)} This server is no longer tracking any world.")
        else:
            await ctx.send(f"{ctx.tick(True)} This server is now tracking **{world}**")

    @checks.is_admin()
    @settings.command(name="levelschannel", aliases=["deathschannel"])
    async def settings_levelschannel(self, ctx, channel: str=None):
        """Changes the channel where levelup and deaths are announced.

        This is were all level ups and deaths of registered characters will be announced.
        By default, I will use the highest channel on the list where I can send messages.
        If the channel you assign is deleted, I will go back to using the top channel."""
        current_channel_id = get_server_property("levels_channel", ctx.guild.id, is_int=True)
        current_channel = ctx.guild.get_channel(current_channel_id)
        print(current_channel_id)
        if channel is None:
            top_channel = self.bot.get_top_channel(ctx.guild, True)
            if current_channel:
                perms = current_channel.permissions_for(ctx.me)
            else:
                perms = discord.Permissions()
            ok = False
            if current_channel_id is None:
                current_value = "None."
            elif current_channel is None:
                current_value = "None, previous channel was deleted."
            elif not perms.read_messages or not perms.send_messages:
                current_value = f"{current_channel.mention}, but I can't use the channel."
            else:
                current_value = f"{current_channel.mention}"
                ok = True

            if not ok:
                # This condition should be impossible to meet, because if the bot can't send messages on any channel,
                # it wouldn't be able to reply to this command in the first place ¯\_(ツ)_/¯
                if top_channel is None:
                    current_value += " I have no channel to announce."
                else:
                    current_value += f" I will use {top_channel.mention} meanwhile."

            await self.show_info_embed(ctx, current_value, "A channel's name or ID.", "channel/none")
            return
        if channel.lower() == "none":
            if current_channel_id is None:
                await ctx.send("There wasn't any levels and deaths channel set.")
                return
            message = await ctx.send(f"Are you sure you want to remove <#{current_channel_id}> "
                                     f"as the level & deaths channel?")
            new_value = None
        else:
            try:
                new_channel = await commands.TextChannelConverter().convert(ctx, channel)
            except commands.BadArgument:
                await ctx.send("I couldn't find that channel, are you sure it exists?")
                return
            perms = new_channel.permissions_for(ctx.me)
            if not perms.read_messages or not perms.send_messages:
                await ctx.send(f"I don't have permission to use {new_channel.mention}.")
                return
            message = await ctx.send(f"Are you sure you want {new_channel.mention} as the new level & deaths channel?")
            new_value = new_channel.id
        confirm = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return

        set_server_property("levels_channel", ctx.guild.id, new_value)
        self.bot.reload_worlds()
        if new_value is None:
            await ctx.send(f"{ctx.tick(True)} The level & deaths channel has been disabled.")
        else:
            await ctx.send(f"{ctx.tick(True)} <#{new_value}> will now be used.")


def setup(bot):
    bot.add_cog(Settings(bot))
