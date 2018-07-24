import discord
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.context import NabCtx
from utils.database import set_server_property, get_server_property
from utils.tibia import tibia_worlds

SETTINGS = {
    "world": {"title": "🌐 World", "check": lambda ctx: ctx.guild.id not in config.lite_servers},
    "newschannel": {"title": "📰 News channel"},
    "eventschannel": {"title": "📣 Events channel"},
    "levelschannel": {"title": "🌟☠ Tracking channel", "check": lambda ctx: ctx.guild.id not in config.lite_servers},
    "minlevel": {"title": "📏 Min Announce Level", "check": lambda ctx: ctx.guild.id not in config.lite_servers},
    "prefix": {"title": "❗ Prefix"},
    "welcome": {"title": "👋 Welcome message"},
    "welcomechannel": {"title": "💬 Welcome channel"},
    "askchannel": {"title": "🤖 Command channel"},
    "commandsonly": {"title": "🗑 Command channel - Delete other"},
}


class PrefixConverter(commands.Converter):
    async def convert(self, ctx, argument):
        user_id = ctx.bot.user.id
        if argument.startswith((f'<@{user_id}>', f'<@!{user_id}>')):
            raise commands.BadArgument("You can't remove this prefix.")
        if len(argument) > 20:
            raise commands.BadArgument("The prefix can't be longer than 20 characters.")
        return argument


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
    async def show_info_embed(ctx: NabCtx, current_value, accepted_values, edit_params):
        embed = discord.Embed(title=f"{SETTINGS[ctx.command.name]['title']} - Settings",
                              description=ctx.command.short_doc, color=discord.Color.blurple())
        embed.add_field(name="📄 Current value", value=current_value, inline=False)
        embed.add_field(name="📝 Edit", inline=False,
                        value=f"`{ctx.clean_prefix}{ctx.command.full_parent_name} {ctx.invoked_with} [{edit_params}]`")
        embed.add_field(name="☑ Accepted values", value=accepted_values, inline=False)
        embed.set_footer(text=f'Use "{ctx.clean_prefix}help {ctx.command.full_parent_name} {ctx.invoked_with}" '
                              f'for more info')
        await ctx.send(embed=embed)

    @checks.is_admin()
    @commands.guild_only()
    @commands.group(invoke_without_command=True, case_insensitive=True, aliases=["config"])
    async def settings(self, ctx: NabCtx):
        """Checks or sets various server-specific settings."""
        embed = discord.Embed(title=f"{ctx.me.display_name} settings", colour=discord.Color.blurple(),
                              description="Use the subcommands to change the settings for this server.")
        for name, info in SETTINGS.items():
            if "check" in info:
                if not info["check"](ctx):
                    continue
            embed.add_field(name=info["title"], value=f"`{ctx.clean_prefix}{ctx.invoked_with} {name}`")
        await ctx.send(embed=embed)

    @checks.is_admin()
    @settings.command(name="askchannel", aliases=["commandchannel"])
    async def settings_askchannel(self, ctx: NabCtx, channel: str=None):
        """Changes the channel where longer replies for commands are given.

        In this channel, pagination commands show more entries at once and command replies in general are longer."""
        current_channel_id = get_server_property(ctx.guild.id, "ask_channel", is_int=True)
        current_channel = ctx.guild.get_channel(current_channel_id)
        if channel is None:
            if current_channel:
                perms = current_channel.permissions_for(ctx.me)
            else:
                perms = discord.Permissions()
            ok = False
            if current_channel_id is None:
                current_value = f"None."
            elif current_channel is None:
                current_value = "Previous channel was deleted."
            elif not perms.read_messages or not perms.send_messages:
                current_value = f"{current_channel.mention}, but I can't use the channel."
            else:
                current_value = current_channel.mention
                ok = True

            if not ok:
                current_value += f" By default, I'll use any channel named {config.ask_channel_name}."
            await self.show_info_embed(ctx, current_value, "A channel's name or id, or `none`.", "channel/none")
            return

        if channel.lower() == "none":
            if current_channel_id is None:
                await ctx.send("There's no command channel set.")
                return
            message = await ctx.send(f"Are you sure you want to delete the set command channel?")
            new_value = 0
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
            message = await ctx.send(f"Are you sure you want {new_channel.mention} as the new commands channel?")
            new_value = new_channel.id
        confirm = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return

        set_server_property(ctx.guild.id, "ask_channel", new_value)
        if new_value is 0:
            await ctx.send(f"{ctx.tick(True)} The command channel was deleted."
                           f"I will still use any channel named **{config.ask_channel_name}**.")
        else:
            await ctx.send(f"{ctx.tick(True)} <#{new_value}> will now be used as a command channel.")

    @checks.is_admin()
    @settings.command(name="commandsonly")
    async def settings_commandsonly(self, ctx: NabCtx, option: str=None):
        """Sets whether only commands are allowed in the command channel.

        If this is enabled, everything that is not a message will be deleted from the command channel.
        This allows the channel to be used exclusively for commands.

        If the channel is shared with other command bots, this should be off.

        Note that the bot needs `Manage Messages` permission to delete messages."""
        def yes_no(choice: bool):
            return "Yes" if choice else "No"
        if option is None:
            current = get_server_property(ctx.guild.id, "commandsonly", is_int=True)
            if current is None:
                current_value = f"{yes_no(config.ask_channel_delete)} (Global default)"
            else:
                current_value = yes_no(current)
            await self.show_info_embed(ctx, current_value, "yes/no", "yes/no")
            return
        if option.lower() == "yes":
            set_server_property(ctx.guild.id, "commandsonly", True)
            await ctx.send(f"{ctx.tick(True)} I will delete non-commands in the command channel from now on.")
        elif option.lower() == "no":
            set_server_property(ctx.guild.id, "commandsonly", False)
            await ctx.send(f"{ctx.tick(True)} I won't delete non-commands in the command channel from now on.")
        else:
            await ctx.send("That's not a valid option, try **yes** or **no**.")

    @checks.is_admin()
    @settings.command(name="eventschannel")
    async def settings_eventschannel(self, ctx: NabCtx, channel: str=None):
        """Changes the channel where upcoming events are announced.

        This is where announcements of events about to happen will be made.
        If the assigned channel is deleted or forbidden, the top channel will be used.

        If this is disabled, users that subscribed to the event will still receive notifications via PM.
        """
        current_channel_id = get_server_property(ctx.guild.id, "events_channel", is_int=True, default=0)
        if channel is None:
            current_value = self.get_current_channel(ctx, current_channel_id)
            await self.show_info_embed(ctx, current_value, "A channel's name or ID, or `disable`.", "channel/disable")
            return
        if channel.lower() == "disable":
            if current_channel_id is 0:
                await ctx.send("Event announcements are already disabled.")
                return
            message = await ctx.send(f"Are you sure you want to disable events announcements?")
            new_value = 0
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
            message = await ctx.send(f"Are you sure you want {new_channel.mention} as the new events channel?")
            new_value = new_channel.id
        confirm = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return

        set_server_property(ctx.guild.id, "events_channel", new_value)
        if new_value is 0:
            await ctx.send(f"{ctx.tick(True)} The events channel has been disabled.")
        else:
            await ctx.send(f"{ctx.tick(True)} <#{new_value}> will now be used for events.")

    @checks.is_admin()
    @settings.command(name="levelschannel", aliases=["deathschannel", "trackingchannel"])
    async def settings_levelschannel(self, ctx: NabCtx, channel: str=None):
        """Changes the channel where levelup and deaths are announced.

        This is were all level ups and deaths of registered characters will be announced.
        By default, the highest channel on the list where the bot can send messages will be used.
        If the assigned channel is deleted or forbidden, the top channel will be used again.

        If this is disabled, Announcements won't be made, but there will still be tracking.
        """
        current_channel_id = get_server_property(ctx.guild.id, "levels_channel", is_int=True)
        if channel is None:
            current_value = self.get_current_channel(ctx, current_channel_id)
            await self.show_info_embed(ctx, current_value, "A channel's name or ID, or `disable`.", "channel/disable")
            return
        if channel.lower() == "disable":
            if current_channel_id is 0:
                await ctx.send("Level and deaths announcements are already disabled.")
                return
            message = await ctx.send(f"Are you sure you want to disable the level & deaths channel?")
            new_value = 0
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

        set_server_property(ctx.guild.id, "levels_channel", new_value)
        if new_value is 0:
            await ctx.send(f"{ctx.tick(True)} The level & deaths channel has been disabled.")
        else:
            await ctx.send(f"{ctx.tick(True)} <#{new_value}> will now be used.")

    @checks.is_admin()
    @settings.command(name="minlevel", aliases=["announcelevel"])
    async def settings_minlevel(self, ctx: NabCtx, level: int=None):
        """Sets the minimum level for death and level up announcements.

        Level ups and deaths under the minimum level are still and can be seen by checking the character directly."""
        current_level = get_server_property(ctx.guild.id, "announce_level", is_int=True)
        if level is None:
            if current_level is None:
                current_value = f"`{config.announce_threshold}` (global default)"
            else:
                current_value = f"`{current_level}`"
            return await self.show_info_embed(ctx, current_value, "Any number greater than 1", "level")
        if level < 1:
            return await ctx.send(f"{ctx.tick(False)} Level can't be lower than 1.")

        set_server_property(ctx.guild.id, "announce_level", level)
        await ctx.send(f"{ctx.tick()} Minimum announce level has been set to `{level}`.")

    @checks.is_admin()
    @settings.command(name="newschannel")
    async def settings_newschannel(self, ctx: NabCtx, channel: str=None):
        """Changes the channel where Tibia news are announced.

        This is where all news and articles posted in Tibia.com will be announced.
        If the assigned channel is deleted or forbidden, the top channel will be used.
        """
        current_channel_id = get_server_property(ctx.guild.id, "news_channel", is_int=True, default=0)
        if channel is None:
            current_value = self.get_current_channel(ctx, current_channel_id)
            await self.show_info_embed(ctx, current_value, "A channel's name or ID, or `disable`.", "channel/disable")
            return
        if channel.lower() == "disable":
            if current_channel_id is 0:
                await ctx.send("News announcements are already disabled.")
                return
            message = await ctx.send(f"Are you sure you want to disable news announcements?")
            new_value = 0
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
            message = await ctx.send(f"Are you sure you want {new_channel.mention} as the new news channel?")
            new_value = new_channel.id
        confirm = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return

        set_server_property(ctx.guild.id, "news_channel", new_value)
        if new_value is 0:
            await ctx.send(f"{ctx.tick(True)} The news channel has been disabled.")
        else:
            await ctx.send(f"{ctx.tick(True)} <#{new_value}> will now be used for Tibia news.")

    @checks.is_admin()
    @settings.command(name="prefix")
    async def settings_prefix(self, ctx: NabCtx, prefix: PrefixConverter=None):
        """Changes the command prefix for this server.

        The prefix are the characters that go before a command's name, in order for the bot to recognize the command.
        A maximum of 5 prefixes can be set per server.

        To remove an existing prefix, use it as a parameter.

        If you want to have a space at the end, such as: `nabbot help`, you have to use double quotes "nabbot ".
        Multiple words also require using quotes.

        Mentioning the bot is always a valid command and can't be changed."""
        prefixes = get_server_property(ctx.guild.id, "prefixes", deserialize=True, default=list(config.command_prefix))
        if prefix is None:
            current_value = ", ".join(f"`{p}`" for p in prefixes) if len(prefixes) > 0 else "Mentions only"
            await self.show_info_embed(ctx, current_value, "Any text", "prefix")
            return
        remove = False
        if prefix in prefixes:
            message = await ctx.send(f"Do you want to remove `{prefix}` as a prefix?")
            remove = True
        else:
            if len(prefixes) >= 5:
                await ctx.send("You can't have more than 5 command prefixes.")
                return
            message = await ctx.send(f"Do you want to add `{prefix}` as a prefix?")
        confirm = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return

        if remove:
            prefixes.remove(prefix)
            await ctx.send(f"{ctx.tick(True)} The prefix `{prefix}` was removed.")
        else:
            prefixes.append(prefix)
            await ctx.send(f"{ctx.tick(True)} The prefix `{prefix}` was added.")
        set_server_property(ctx.guild.id, "prefixes", sorted(prefixes, reverse=True), serialize=True)

    @checks.is_admin()
    @settings.command(name="welcome")
    async def settings_welcome(self, ctx: NabCtx, *, message: str = None):
        """Changes the message new members receive when joining.

        This is initially disabled.

        You can use formatting to show dynamic values:
        - {server} -> The server's name.
        - {server.owner} -> The server's owner name
        - {server.owner.mention} -> Mention to the server's owner.
        - {owner} -> The name of the server owner
        - {owner.mention} -> Mention the server owner.
        - {user} -> The name of the user that joined.
        - {user.mention} -> Mention the user that joined.
        - {bot} -> The name of the bot
        - {bot.mention} -> Mention the bot.

        Be sure to change the welcome channel too."""
        current_message = get_server_property(ctx.guild.id, "welcome")
        if message is None:
            await self.show_info_embed(ctx, current_message, "Any text", "message/disable")
            return
        if message.lower() == "disable":
            if current_message is None:
                await ctx.send("Welcome messages are already disabled.")
                return
            msg = await ctx.send("Are you sure you want to disable welcome messages?")
            new_value = None
        else:
            try:
                if len(message) > 1000:
                    await ctx.send(f"{ctx.tick(False)} This message is too long! {len(message):,}/1000 characters.")
                    return
                formatted = message.format(server=ctx.guild, bot=self.bot, owner=ctx.guild.owner, user=ctx.author)
                msg = await ctx.send("Do you want to set this as the new message?\n"
                                     "*This is how your message would look if **you** joined.*",
                                     embed=discord.Embed(title="Message Preview", colour=discord.Colour.blurple(),
                                                         description=formatted))
                new_value = message
            except KeyError as e:
                await ctx.send(f"{ctx.tick(False)} Unknown keyword {e}.")
                return
        confirm = await ctx.react_confirm(msg, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return
        set_server_property(ctx.guild.id, "welcome", new_value)
        if new_value is None:
            await ctx.send(f"{ctx.tick(True)} The welcome message has been disabled.")
        else:
            await ctx.send(f"{ctx.tick(True)} Welcome message updated.")

    @checks.is_admin()
    @settings.command(name="welcomechannel")
    async def settings_welcomechannel(self, ctx: NabCtx, channel: str = None):
        """Changes the channel where new members are welcomed.

        A welcome message must be set for this setting to work.
        If the channel becomes unavailable, private messages will be used.

        Note that private messages are not reliable since new users can have them disabled before joining.
        To disable this, you must disable welcome messages using `settings welcome`.
        """
        current_channel_id = get_server_property(ctx.guild.id, "welcome_channel", is_int=True)
        if channel is None:
            current_value = self.get_current_channel(ctx, current_channel_id, pm_fallback=True)
            await self.show_info_embed(ctx, current_value, "A channel's name or ID, or `private`.", "channel/private")
            return
        if channel.lower() == "private":
            if current_channel_id is None:
                await ctx.send("Welcome messages are already private.")
                return
            message = await ctx.send(f"Are you sure you want to make welcome messages private?")
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
            message = await ctx.send(f"Are you sure you want {new_channel.mention} as the new welcome channel?")
            new_value = new_channel.id
        confirm = await ctx.react_confirm(message, timeout=60, delete_after=True)
        if not confirm:
            await ctx.message.delete()
            return

        set_server_property(ctx.guild.id, "welcome_channel", new_value)
        if new_value is None:
            await ctx.send(f"{ctx.tick(True)} Welcome messages will be sent privately.")
        else:
            await ctx.send(f"{ctx.tick(True)} <#{new_value}> will now be used for welcome messages.")

    @checks.is_admin()
    @checks.is_not_lite()
    @settings.command(name="world")
    async def settings_world(self, ctx: NabCtx, world: str=None):
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

        set_server_property(ctx.guild.id, "world", world)
        self.bot.reload_worlds()
        if world is None:
            await ctx.send(f"{ctx.tick(True)} This server is no longer tracking any world.")
        else:
            await ctx.send(f"{ctx.tick(True)} This server is now tracking **{world}**")

    @settings_prefix.error
    async def prefix_error(self, ctx: NabCtx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error))

    def get_current_channel(self, ctx: NabCtx, current_channel_id, pm_fallback=False):
        top_channel = self.bot.get_top_channel(ctx.guild, True)
        current_channel = ctx.guild.get_channel(current_channel_id)
        if current_channel:
            perms = current_channel.permissions_for(ctx.me)
        else:
            perms = discord.Permissions()
        ok = False
        if current_channel_id is None and pm_fallback:
            current_value = "Private Messages"
            ok = True
        elif current_channel_id == 0:
            current_value = "Disabled."
            ok = True
        elif current_channel_id is None:
            current_value = "None,"
        elif current_channel is None:
            current_value = "None, previous channel was deleted."
        elif not perms.read_messages or not perms.send_messages:
            current_value = f"{current_channel.mention}, but I can't use the channel."
        else:
            current_value = f"{current_channel.mention}"
            ok = True

        if not ok:
            if pm_fallback:
                current_value += " I will send direct messages meanwhile."
            # This condition should be impossible to meet, because if the bot can't send messages on any channel,
            # it wouldn't be able to reply to this command in the first place ¯\_(ツ)_/¯
            elif top_channel is None:
                current_value += " I have no channel to use."
            else:
                current_value += f" I will use {top_channel.mention} meanwhile."
        return current_value


def setup(bot):
    bot.add_cog(Settings(bot))
