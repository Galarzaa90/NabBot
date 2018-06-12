import asyncio
import re
from typing import Union

import discord
from discord.ext import commands

from utils.config import config
from utils.database import get_server_property

YES_NO_REACTIONS = ("🇾", "🇳")
CHECK_REACTIONS = ("✅", "❌")
_mention = re.compile(r'<@!?([0-9]{1,19})>')

class NabCtx(commands.Context):
    guild: discord.Guild
    message: discord.Message
    channel: discord.TextChannel
    author: Union[discord.User, discord.Member]
    me: Union[discord.Member, discord.ClientUser]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @staticmethod
    def tick(value: bool, label: str = None):
        """Displays a checkmark or a cross depending on the value."""
        emoji = CHECK_REACTIONS[int(not value)]
        if label:
            return emoji + label
        return emoji

    @property
    def world(self):
        if self.guild is None:
            return None
        else:
            return self.bot.tracked_worlds.get(self.guild.id, None)

    @property
    def long(self) -> bool:
        """Whether the current context allows long replies or not

        Private messages and command channels allow long replies.
        """
        if self.guild is None:
            return True
        return self.is_askchannel

    @property
    def is_askchannel(self):
        """Checks if the current channel is the command channel"""
        ask_channel_id = get_server_property(self.guild.id, "ask_channel", is_int=True)
        ask_channel = self.guild.get_channel(ask_channel_id)
        if ask_channel is None:
            return self.channel.name == config.ask_channel_name
        return ask_channel == self.channel

    @property
    def ask_channel_name(self):
        ask_channel_id = get_server_property(self.guild.id, "ask_channel", is_int=True)
        ask_channel = self.guild.get_channel(ask_channel_id)
        if ask_channel is None:
            return config.ask_channel_name
        return ask_channel.name

    @property
    def clean_prefix(self) -> str:
        m = _mention.match(self.prefix)
        if m:
            user = self.bot.get_user(int(m.group(1)))
            if user:
                return f'@{user.name} '
        return self.prefix

    async def react_confirm(self, message: discord.Message, *, timeout=120.0, delete_after=False,
                            use_checkmark=False):
        """Waits for the command author to reply with a Y or N reaction.

        Returns True if the user reacted with Y
        Returns False if the user reacted with N
        Returns None if the user didn't react at all"""

        if not self.channel.permissions_for(self.me).add_reactions:
            raise RuntimeError('Bot does not have Add Reactions permission.')

        reactions = CHECK_REACTIONS if use_checkmark else YES_NO_REACTIONS
        for emoji in reactions:
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
