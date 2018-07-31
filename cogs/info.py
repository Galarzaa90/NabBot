import platform
import re
import time
from collections import Counter, OrderedDict
from contextlib import closing
from typing import List

import discord
import psutil
from discord.ext import commands

from nabbot import NabBot
from utils import checks
from utils.config import config
from utils.context import NabCtx
from utils.database import get_server_property, userDatabase
from utils.general import parse_uptime, FIELD_VALUE_LIMIT, get_region_string, get_user_avatar
from utils.messages import split_message
from utils.pages import HelpPaginator, _can_run
from utils.tibia import tibia_worlds


class Info:
    def __init__(self, bot: NabBot):
        self.bot = bot

    @checks.can_embed()
    @commands.command()
    async def about(self, ctx: NabCtx):
        """Shows basic information about the bot."""
        embed = discord.Embed(description=ctx.bot.description, colour=discord.Colour.blurple())
        embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                         icon_url="https://github.com/fluidicon.png")
        prefixes = list(config.command_prefix)
        if ctx.guild:
            prefixes = get_server_property(ctx.guild.id, "prefixes", deserialize=True, default=prefixes)
        prefixes_str = "\n".join(f"- `{p}`" for p in prefixes)
        embed.add_field(name="Prefixes", value=prefixes_str, inline=False)
        embed.add_field(name="Authors", value="\u2023 [Galarzaa90](https://github.com/Galarzaa90)\n"
                                              "\u2023 [Nezune](https://github.com/Nezune)")
        embed.add_field(name="Created", value="March 30th 2016")
        embed.add_field(name="Version", value=f"v{self.bot.__version__}")
        embed.add_field(name="Platform", value="Python "
                                               "([discord.py](https://github.com/Rapptz/discord.py/tree/rewrite))")
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}")
        embed.add_field(name="Users", value=f"{len(self.bot.users):,}")
        embed.add_field(name="Links", inline=False,
                        value=f"[Add to your server](https://discordbots.org/bot/178966653982212096)  |  "
                              f"[Support Server](https://discord.me/nabbot)  |  "
                              f"[Docs](https://galarzaa90.github.io/NabBot)  |  "
                              f"[Donate](https://www.paypal.com/cgi-bin/webscr?"
                              f"cmd=_s-xclick&hosted_button_id=B33DCPZ9D3GMJ)")
        embed.set_footer(text=f"Uptime | {parse_uptime(self.bot.start_time, True)}")
        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command(name="botinfo")
    async def bot_info(self, ctx: NabCtx):
        """Shows advanced information about the bot."""
        char_count = 0
        deaths_count = 0
        levels_count = 0
        with closing(userDatabase.cursor()) as c:
            c.execute("SELECT COUNT(*) as count FROM chars")
            result = c.fetchone()
            if result is not None:
                char_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_deaths")
            result = c.fetchone()
            if result is not None:
                deaths_count = result["count"]
            c.execute("SELECT COUNT(*) as count FROM char_levelups")
            result = c.fetchone()
            if result is not None:
                levels_count = result["count"]

        used_ram = psutil.Process().memory_full_info().uss / 1024 ** 2
        total_ram = psutil.virtual_memory().total / 1024 ** 2
        percentage_ram = psutil.Process().memory_percent()

        def ram(value):
            if value >= 1024:
                return f"{value/1024:.2f}GB"
            else:
                return f"{value:.2f}MB"

        # Calculate ping
        t1 = time.perf_counter()
        await ctx.trigger_typing()
        t2 = time.perf_counter()
        ping = round((t2 - t1) * 1000)

        embed = discord.Embed()
        embed.set_author(name="NabBot", url="https://github.com/Galarzaa90/NabBot",
                         icon_url="https://github.com/fluidicon.png")
        embed.description = f"🔰 Version: **{self.bot.__version__}**\n" \
                            f"⏱ ️Uptime **{parse_uptime(self.bot.start_time)}**\n" \
                            f"🖥️ OS: **{platform.system()} {platform.release()}**\n" \
                            f"📉 RAM: **{ram(used_ram)}/{ram(total_ram)} ({percentage_ram:.2f}%)**\n"
        try:
            embed.description += f"⚙️ CPU: **{psutil.cpu_count()} @ {psutil.cpu_freq().max} MHz**\n"
        except AttributeError:
            pass
        embed.description += f"🏓 Ping: **{ping} ms**\n" \
                             f"👾 Servers: **{len(self.bot.guilds):,}**\n" \
                             f"💬 Channels: **{len(list(self.bot.get_all_channels())):,}**\n" \
                             f"👨 Users: **{len(self.bot.users):,}** \n" \
                             f"👤 Characters: **{char_count:,}**\n" \
                             f"🌐 Tracked worlds: **{len(self.bot.tracked_worlds_list)}/{len(tibia_worlds)}**\n" \
                             f"{config.levelup_emoji} Level ups: **{levels_count:,}**\n" \
                             f"{config.death_emoji} Deaths: **{deaths_count:,}**"
        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command(name="commands", aliases=["commandlist"])
    async def _commands(self, ctx: NabCtx):
        """Shows a simple list of all commands.

        This displays all the commands you can use, with no description or subcommand information.
        Note that different commands might show up in server channels and in private messages.

        For more details, use `help`."""
        embed = discord.Embed(title=f"{ctx.me.display_name} commands")
        embed.set_footer(text=f"For a more detailed list, try '{ctx.clean_prefix}help' or "
                              f"'{ctx.clean_prefix}help [command_name]'")
        _commands: List[commands.Command] = [c for c in self.bot.commands if not c.hidden and await _can_run(c, ctx)]
        categories = {}
        for command in _commands:
            if command.cog_name not in categories:
                categories[command.cog_name] = []
            categories[command.cog_name].append(command.name)

        for k in sorted(categories):
            embed.add_field(name=k, value=", ".join(f"`{c}`" for c in sorted(categories[k])), inline=False)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(name="emojiinfo")
    async def emoji_info(self, ctx: NabCtx, *, emoji: discord.Emoji=None):
        """Shows information about an emoji, or shows all emojis.

        If the command is used with no arguments, all the server emojis are shown.

        If a emoji, its id or name is provided, it will show more information about it.

        Only emojis in the current servers can be checked."""
        if emoji is not None:
            embed = discord.Embed(title=emoji.name, timestamp=emoji.created_at, color=discord.Color.blurple())
            embed.set_thumbnail(url=emoji.url)
            embed.set_footer(text="Created at")
            embed.add_field(name="ID", value=emoji.id)
            embed.add_field(name="Usage", value=f"`{emoji}`")
            embed.add_field(name="Attributes", inline=False,
                            value=f"{ctx.tick(emoji.managed)} Twitch managed\n"
                                  f"{ctx.tick(emoji.require_colons)} Requires colons\n"
                                  f"{ctx.tick(len(emoji.roles) > 0)} Role limited")
        else:
            emojis: List[discord.Emoji] = ctx.guild.emojis
            if not emojis:
                return await ctx.send("This server has no custom emojis.")
            normal = [str(e) for e in emojis if not e.animated]
            animated = [str(e) for e in emojis if e.animated]
            embed = discord.Embed(title="Custom Emojis", color=discord.Color.blurple())
            if normal:
                emojis_str = "\n".join(normal)
                fields = split_message(emojis_str, FIELD_VALUE_LIMIT)
                for i, value in enumerate(fields):
                    if i == 0:
                        name = f"Regular ({len(normal)})"
                    else:
                        name = "\u200F"
                    embed.add_field(name=name, value=value.replace("\n", ""))
            if animated:
                emojis_str = "\n".join(animated)
                fields = split_message(emojis_str, FIELD_VALUE_LIMIT)
                for i, value in enumerate(fields):
                    if i == 0:
                        name = f"Animated (Nitro required) ({len(animated)})"
                    else:
                        name = "\u200F"
                    embed.add_field(name=name, value=value.replace("\n", ""))
        await ctx.send(embed=embed)

    @checks.can_embed()
    @commands.command(name='help')
    async def _help(self, ctx, *, command: str = None):
        """Shows help about a command or the bot.

        - If no command is specified, it will list all available commands
        - If a command is specified, it will show further info, and its subcommands if applicable.
        - If a category is specified, it will show only commands in that category.

        Various symbols are used to represent a command's signature and/or show further info.
        **<argument>**
        This means the argument is __**required**__.

        **[argument]**
        This means the argument is __**optional**__.

        **[A|B]**
        This means the it can be __**either A or B**__.

        **[argument...]**
        This means you can have __**multiple arguments**__.

        🔸
        This means the command has subcommands.
        Check the command's help to see them."""
        try:
            if command is None:
                p = await HelpPaginator.from_bot(ctx)
            else:
                entity = self.bot.get_cog(command) or self.bot.get_command(command)

                if entity is None:
                    clean = command.replace('@', '@\u200b')
                    return await ctx.send(f'Command or category "{clean}" not found.')
                elif isinstance(entity, commands.Command):
                    p = await HelpPaginator.from_command(ctx, entity)
                else:
                    p = await HelpPaginator.from_cog(ctx, entity)
            await p.paginate()
        except Exception as e:
            await ctx.send(e)

    @commands.command(name="oldhelp", hidden=True)
    async def oldhelp(self, ctx, *commands: str):
        """Shows this message."""
        _mentions_transforms = {
            '@everyone': '@\u200beveryone',
            '@here': '@\u200bhere'
        }
        _mention_pattern = re.compile('|'.join(_mentions_transforms.keys()))

        bot = ctx.bot
        destination = ctx.channel if ctx.long else ctx.author

        def repl(obj):
            return _mentions_transforms.get(obj.group(0), '')

        # help by itself just lists our own commands.
        if len(commands) == 0:
            pages = await bot.formatter.format_help_for(ctx, bot)
        elif len(commands) == 1:
            # try to see if it is a cog name
            name = _mention_pattern.sub(repl, commands[0])
            command = None
            if name in bot.cogs:
                command = bot.cogs[name]
            else:
                command = bot.all_commands.get(name)
                destination = ctx.channel
                if command is None:
                    await destination.send(bot.command_not_found.format(name))
                    return

            pages = await bot.formatter.format_help_for(ctx, command)
        else:
            name = _mention_pattern.sub(repl, commands[0])
            command = bot.all_commands.get(name)
            destination = ctx.channel
            if command is None:
                await destination.send(bot.command_not_found.format(name))
                return

            for key in commands[1:]:
                try:
                    key = _mention_pattern.sub(repl, key)
                    command = command.all_commands.get(key)
                    if command is None:
                        await destination.send(bot.command_not_found.format(key))
                        return
                except AttributeError:
                    await destination.send(bot.command_has_no_subcommands.format(command, key))
                    return

            pages = await bot.formatter.format_help_for(ctx, command)

        for page in pages:
            await destination.send(page)

    @commands.guild_only()
    @commands.command()
    @checks.can_embed()
    async def serverinfo(self, ctx: NabCtx, server=None):
        """Shows the server's information.

        The bot owner can additionally check the information of a specific server where the bot is.
        """
        if await checks.is_owner_check(ctx) and server is not None:
            try:
                guild = self.bot.get_guild(int(server))
                if guild is None:
                    return await ctx.send(f"{ctx.tick(False)} I'm not in any server with ID {server}.")
            except ValueError:
                return await ctx.send(f"{ctx.tick(False)} That is not a valid id.")
        else:
            guild = ctx.guild
        embed = discord.Embed(title=guild.name, timestamp=guild.created_at, color=discord.Color.blurple())
        embed.set_footer(text="Created on")
        embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="ID", value=str(guild.id), inline=False)
        if ctx.guild != guild:
            embed.add_field(name="Owner", value=str(guild.owner))
        else:
            embed.add_field(name="Owner", value=guild.owner.mention)
        embed.add_field(name="Voice Region", value=get_region_string(guild.region))
        embed.add_field(name=f"Channels ({len(guild.text_channels)+len(guild.voice_channels):,})",
                        value=f"📄 Text: **{len(guild.text_channels):,}**\n"
                              f"🎙 Voice: **{len(guild.voice_channels):,}**\n"
                              f"🗂 Categories: **{len(guild.categories):,}**")
        status_count = Counter(str(m.status) for m in guild.members)
        bot_count = len(list(filter(lambda m: m.bot, guild.members)))
        if config.use_status_emojis:
            embed.add_field(name=f"Members ({len(guild.members):,})",
                            value=f"**{status_count['online']:,}**{config.status_emojis['online']} "
                                  f"**{status_count['idle']:,}**{config.status_emojis['idle']} "
                                  f"**{status_count['dnd']:,}**{config.status_emojis['dnd']} "
                                  f"**{status_count['offline']:,}**{config.status_emojis['offline']}\n"
                                  f"👨 Humans: **{len(guild.members)-bot_count:,}**\n"
                                  f"🤖 Bots: **{bot_count:,}**"
                            )
        else:
            embed.add_field(name=f"Members ({len(guild.members):,})",
                            value=f"Online: **{status_count['online']:,}**\n"
                                  f"Idle: **{status_count['idle']:,}**\n"
                                  f"Busy: **{status_count['dnd']:,}**\n"
                                  f"Offline: **{status_count['offline']:,}**\n"
                                  f"Humans: **{len(guild.members)-bot_count:,}**\n"
                                  f"Bots: **{bot_count:,}**"
                            )
        embed.add_field(name="Roles", value=f"{len(guild.roles):,}")
        embed.add_field(name="Emojis", value=f"{len(guild.emojis):,}")
        if self.bot.tracked_worlds.get(guild.id):
            embed.add_field(name="Tracked world", value=self.bot.tracked_worlds.get(guild.id))
        if guild.splash_url:
            embed.add_field(name="Splash screen", value="\u200F", inline=True)
            embed.set_image(url=guild.splash_url)
        await ctx.send(embed=embed)

    @commands.command()
    async def uptime(self, ctx):
        """Shows how long the bot has been running."""
        await ctx.send("I have been running for {0}.".format(parse_uptime(self.bot.start_time, True)))

    @commands.guild_only()
    @checks.can_embed()
    @commands.command(aliases=["memberinfo"])
    async def userinfo(self, ctx, *, user: str = None):
        """Shows a user's information.

        If no user is provided, it shows your own information.

        About user statuses:

        - Server Owner: Owner of the server
        - Server Admin: User with `Administrator` permission
        - Server Moderator: User with `Manage Server` permissions.
        - Channel Moderator: User with `Manage Channels` permissions in at least one channel."""
        if user is None:
            user = ctx.author
        else:
            _user = self.bot.get_member(user, ctx.guild)
            if _user is None:
                await ctx.send(f"Could not find user `{user}`")
                return
            user = _user
        embed = discord.Embed(title=f"{user.name}#{user.discriminator}", timestamp=user.joined_at, colour=user.colour)
        if config.use_status_emojis:
            embed.title += config.status_emojis[str(user.status)]
        embed.set_thumbnail(url=get_user_avatar(user))
        embed.set_footer(text="Member since")
        embed.add_field(name="ID", value=user.id)
        embed.add_field(name="Created", value=user.created_at)
        status = []
        if ctx.guild.owner == user:
            status.append("Server Owner")
        if user.guild_permissions.administrator:
            status.append("Server Admin")
        if user.guild_permissions.manage_guild:
            status.append("Server Moderator")
        if any(c.permissions_for(user).manage_channels for c in ctx.guild.text_channels):
            status.append("Channel Moderator")
        if user.bot:
            status.append("Bot")
        if not status:
            status.append("Regular User")
        embed.add_field(name="User Status", value=", ".join(status), inline=False)

        embed.add_field(name="Servers", value=f"{len(self.bot.get_user_guilds(user.id))} shared")
        embed.add_field(name="Roles", value=f"{len(user.roles):,}")
        embed.add_field(name="Highest role", value=f"{user.top_role.mention}")

        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Info(bot))