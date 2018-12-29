import asyncio
import functools
import re
from typing import Any, Callable, Optional, Sequence, TypeVar, Union

import aiohttp
import asyncpg
import discord
from discord.ext import commands

import nabbot
from . import config
from .database import get_server_property

_mention = re.compile(r'<@!?([0-9]{1,19})>')

T = TypeVar('T')


class NabCtx(commands.Context):
    """An override of :class:`commands.Context` that provides properties and methods for NabBot."""
    bot: "nabbot.NabBot"
    guild: discord.Guild
    message: discord.Message
    channel: discord.TextChannel
    author: Union[discord.User, discord.Member]
    me: Union[discord.Member, discord.ClientUser]
    command: commands.Command

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pool: asyncpg.pool.Pool = self.bot.pool
        self.session: aiohttp.ClientSession = self.bot.session
        self.yes_no_reactions = ("🇾", "🇳")
        self.check_reactions = (config.true_emoji, config.false_emoji)

    # region Properties
    @property
    def author_permissions(self) -> discord.Permissions:
        """Shortcut to check the command author's permission to the current channel.

        :return: The permissions for the author in the current channel.
        """
        return self.channel.permissions_for(self.author)

    @property
    def bot_permissions(self) -> discord.Permissions:
        """Shortcut to check the bot's permission to the current channel.

        :return: The permissions for the author in the current channel."""
        return self.channel.permissions_for(self.me)

    @property
    def clean_prefix(self) -> str:
        """Gets the clean prefix used in the command invocation.

        This is used to clean mentions into plain text."""
        m = _mention.match(self.prefix)
        if m:
            user = self.bot.get_user(int(m.group(1)))
            if user:
                return f'@{user.name} '
        return self.prefix

    @property
    def is_lite(self) -> bool:
        """Checks if the current context is limited to lite mode.

        If the guild is in the lite_guilds list, the context is in lite mode.
        If the guild is in private message, and the message author is in at least ONE guild that is not in lite_guilds,
        then context is not lite"""
        if self.guild is not None:
            return self.guild.id in config.lite_servers
        if self.is_private:
            for g in self.bot.get_user_guilds(self.author.id):
                if g.id not in config.lite_servers:
                    return False
        return False

    @property
    def is_private(self) -> bool:
        """Whether the current context is a private channel or not."""
        return self.guild is None

    @property
    def usage(self) -> str:
        """Shows the parameters signature of the invoked command"""
        if self.command.usage:
            return self.command.usage

        params = self.command.clean_params
        if not params:
            return ''
        result = []
        for name, param in params.items():
            if param.default is not param.empty:
                # We don't want None or '' to trigger the [name=value] case and instead it should
                # do [name] since [name=None] or [name=] are not exactly useful for the user.
                should_print = param.default if isinstance(param.default, str) else param.default is not None
                if should_print:
                    result.append(f'[{name}={param.default!r}]')
                else:
                    result.append(f'[{name}]')
            elif param.kind == param.VAR_POSITIONAL:
                result.append(f'[{name}...]')
            else:
                result.append(f'<{name}>')

        return ' '.join(result)

    @property
    def world(self) -> Optional[str]:
        """Check the world that is currently being tracked by the guild

        :return: The world that the server is tracking.
        :rtype: str | None
        """
        if self.guild is None:
            return None
        else:
            return self.bot.tracked_worlds.get(self.guild.id, None)

    async def ask_channel_name(self) -> Optional[str]:
        """Gets the name of the ask channel for the current server.

        :return: The name of the ask channel if applicable
        :rtype: str or None"""
        if self.guild is None:
            return None
        ask_channel_id = await get_server_property(self.pool, self.guild.id, "ask_channel")
        ask_channel = self.guild.get_channel(ask_channel_id)
        if ask_channel is None:
            return config.ask_channel_name
        return ask_channel.name

    # endregion
    async def choose(self, matches: Sequence[Any], title="Suggestions", not_found=True):
        if len(matches) == 0:
            raise ValueError('No results found.')

        if len(matches) == 1:
            return matches[0]

        embed = discord.Embed(colour=discord.Colour.blurple(), title=title,
                              description='\n'.join(f'{index}: {item}' for index, item in enumerate(matches, 1)))

        suggestion_text = "Please choose one of the options.\n"
        not_found_text = "I couldn't find what you were looking for, maybe you mean one of these?\n"
        cancel_text = "**Only say the number** (*0 to cancel*)"
        text = not_found_text + cancel_text if not_found else suggestion_text + cancel_text
        msg = await self.send(text, embed=embed)

        def check(m: discord.Message):
            return m.content.isdigit() and m.author.id == self.author.id and m.channel.id == self.channel.id
        message = None
        try:
            message = await self.bot.wait_for('message', check=check, timeout=30.0)
            index = int(message.content)
            if index == 0:
                await self.send("Alright, choosing cancelled.", delete_after=10)
                return None
            try:
                await msg.delete()
                return matches[index - 1]
            except IndexError:
                await self.send(f"{self.tick(False)} That wasn't in the choices.", delete_after=10)
        except asyncio.TimeoutError:
            return None
        finally:
            try:
                if message:
                    await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    # region Methods
    async def error(self, content, *, embed=None, file=None, files=None, delete_after=None):
        """Sends a message prefixed by a cross."""
        content = f"{self.tick(False)} {content}"
        return await self.send(content, embed=embed, file=file, files=files, delete_after=delete_after)

    async def execute_async(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Executes a synchronous function inside an executor.

        :param func: The function to call inside the executor.
        :param args: The function's arguments
        :param kwargs: The function's keyword arguments.
        :return: The value returned by the function, if any.
        """
        ret = await self.bot.loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
        return ret

    async def input(self, *, timeout=60.0, clean=False, delete_response=False) \
            -> Optional[str]:
        """Waits for text input from the author.

        :param timeout: Maximum time to wait for a message.
        :param clean: Whether the content should be cleaned or not.
        :param delete_response: Whether to delete the author's message after.
        :return: The content of the message replied by the author
        """
        def check(_message):
            return _message.channel == self.channel and _message.author == self.author

        try:
            value = await self.bot.wait_for("message", timeout=timeout, check=check)
            if clean:
                ret = value.clean_content
            else:
                ret = value.content
            if delete_response:
                try:
                    await value.delete()
                except discord.HTTPException:
                    pass
            return ret
        except asyncio.TimeoutError:
            return None

    async def is_askchannel(self):
        """Checks if the current channel is the command channel"""
        ask_channel_id = await get_server_property(self.pool, self.guild.id, "ask_channel")
        ask_channel = self.guild.get_channel(ask_channel_id)
        if ask_channel is None:
            return self.channel.name == config.ask_channel_name
        return ask_channel == self.channel

    async def is_long(self) -> bool:
        """Whether the current context allows long replies or not

        Private messages and command channels allow long replies.
        """
        if self.guild is None:
            return True
        return await self.is_askchannel()

    async def react_confirm(self, message: discord.Message, *, timeout=60.0, delete_after=False,
                            use_checkmark=False) -> Optional[bool]:
        """Waits for the command author to reply with a Y or N reaction.

        Returns True if the user reacted with Y
        Returns False if the user reacted with N
        Returns None if the user didn't react at all

        :param message: The message that will contain the reactions.
        :param timeout: The maximum time to wait for reactions
        :param delete_after: Whether to delete or not the message after finishing.
        :param use_checkmark: Whether to use or not checkmarks instead of Y/N
        :return: True if reacted with Y, False if reacted with N, None if timeout.
        """
        if not self.channel.permissions_for(self.me).add_reactions:
            raise RuntimeError('Bot does not have Add Reactions permission.')

        reactions = self.check_reactions if use_checkmark else self.yes_no_reactions
        for emoji in reactions:
            emoji = emoji.replace("<", "").replace(">", "")
            await message.add_reaction(emoji)

        def check_react(reaction: discord.Reaction, user: discord.User):
            if reaction.message.id != message.id:
                return False
            if user.id != self.author.id:
                return False
            if reaction.emoji not in reactions:
                return False
            return True
        try:
            react = await self.bot.wait_for("reaction_add", timeout=timeout, check=check_react)
            if react[0].emoji == reactions[1]:
                return False
        except asyncio.TimeoutError:
            return None
        finally:
            if delete_after:
                await message.delete()
            elif self.guild is not None:
                try:
                    await message.clear_reactions()
                except discord.Forbidden:
                    pass
        return True

    async def success(self, content, *, embed=None, file=None, files=None, delete_after=None):
        """Sends a message prefixed by a checkmark."""
        content = f"{self.tick(True)} {content}"
        return await self.send(content, embed=embed, file=file, files=files, delete_after=delete_after)

    def tick(self, value: bool = True, label: str = None) -> str:
        """Displays a checkmark or a cross depending on the value.

        :param value: The value to evaluate
        :param label: An optional label to display
        :return: A checkmark or cross
        """
        emoji = self.check_reactions[int(not value)]
        if label:
            return emoji + label
        return emoji

    # endregion
