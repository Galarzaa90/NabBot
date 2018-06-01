import asyncio

import discord
from discord.ext import commands

YES_NO_REACTIONS = ('\U0001f1fe', '\U0001f1f3')
CHECK_REACTIONS = ('\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}')


class Context(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def world(self):
        if self.guild is None:
            return None
        else:
            return self.bot.tracked_worlds.get(self.guild.id, None)

    @staticmethod
    def tick(value: bool, label: str=None):
        """Displays a checkmark or a cross depending on the value."""
        emoji = CHECK_REACTIONS[int(not value)]
        if label:
            return emoji+label
        return emoji

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
            if self.guild is not None:
                try:
                    await message.clear_reactions()
                except discord.Forbidden:
                    pass
        return True
