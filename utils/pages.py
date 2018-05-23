import asyncio
from typing import Union

import discord
from discord.ext import commands

from nabbot import NabBot
from utils.discord import is_private
from utils.tibia import DRUID, SORCERER, PALADIN, KNIGHT


class CannotPaginate(Exception):
    pass


class Pages:
    """Implements a paginator that queries the user for the
    pagination interface.

    Pages are 1-index based, not 0-index based.
    If the user does not reply within 2 minutes then the pagination
    interface exits automatically.

    Based on Rapptz' Paginator: https://github.com/Rapptz/RoboDanny/blob/master/cogs/utils/paginator.py
    Modified for Nab Bot's needs.

    Parameters
    ------------
    ctx: Context
        The context of the command.
    entries: List[str]
        A list of entries to paginate.
    per_page: int
        How many entries show up per page.
    show_entry_count: bool
        Whether to show an entry count in the footer.

    Attributes
    -----------
    embed: discord.Embed
        The embed object that is being used to send pagination info.
        Feel free to modify this externally. Only the description
        and footer fields are internally modified.
    permissions: discord.Permissions
        Our permissions for the channel.
    """
    Empty = discord.Embed.Empty

    def __init__(self, ctx: commands.Context, *, entries, per_page=10, show_entry_count=True, **kwargs):
        self.bot = ctx.bot  # type: NabBot
        self.entries = entries
        self.message = ctx.message  # type: discord.Message
        self.channel = ctx.channel  # type: discord.TextChannel
        self.author = ctx.author  # type: Union[discord.User, discord.Member]
        self.per_page = per_page
        pages, left_over = divmod(len(self.entries), self.per_page)
        if left_over:
            pages += 1
        self.maximum_pages = pages
        self.embed = discord.Embed()
        self.paginating = len(entries) > per_page
        self.show_entry_count = show_entry_count
        self.reaction_emojis = [
            ('\N{BLACK LEFT-POINTING TRIANGLE}', self.previous_page),
            ('\N{BLACK RIGHT-POINTING TRIANGLE}', self.next_page),
            ('\N{BLACK SQUARE FOR STOP}', self.stop_pages)
        ]

        # Added for NabBot
        self.header = kwargs.get("header", "")

        self.current_page = 1
        if ctx.guild is not None:
            self.permissions = self.channel.permissions_for(ctx.guild.me)
        else:
            self.permissions = self.channel.permissions_for(ctx.bot.user)

        if not self.permissions.embed_links:
            raise CannotPaginate('Bot does not have embed links permission.')

        if not self.permissions.send_messages:
            raise CannotPaginate('Bot cannot send messages.')

        if self.paginating:
            if not self.permissions.add_reactions:
                raise CannotPaginate('Bot does not have add reactions permission.')

            if not self.permissions.read_message_history:
                raise CannotPaginate('Bot does not have read message history permission.')

    def get_page(self, page):
        base = (page - 1) * self.per_page
        return self.entries[base:base + self.per_page]

    async def show_page(self, page, *, first=False):
        self.current_page = page
        entries = self.get_page(page)
        p = []
        for index, entry in enumerate(entries, 1 + ((page - 1) * self.per_page)):
            p.append(f'{index}. {entry}')

        if self.maximum_pages > 1:
            if self.show_entry_count:
                text = f'Page {page}/{self.maximum_pages} ({len(self.entries)} entries)'
            else:
                text = f'Page {page}/{self.maximum_pages}'

            self.embed.set_footer(text=text)

        if not self.paginating:
            self.embed.description = '\n'.join(p)
            return await self.channel.send(embed=self.embed)

        if not first:
            self.embed.description = '\n'.join(p)
            await self.message.edit(embed=self.embed)
            return

        # Added for nabBot
        self.embed.description = self.header + "\n" + '\n'.join(p)
        # Original
        # self.embed.description = '\n'.join(p)
        self.message = await self.channel.send(embed=self.embed)
        for (reaction, _) in self.reaction_emojis:
            if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
                # no |<< or >>| buttons if we only have two pages
                # we can't forbid it if someone ends up using it but remove
                # it from the default set
                continue
            # Stop reaction doesn't work on PMs so do not add it
            if is_private(self.message.channel) and reaction == '\N{BLACK SQUARE FOR STOP}':
                continue
            await self.message.add_reaction(reaction)

    async def checked_show_page(self, page):
        if page != 0 and page <= self.maximum_pages:
            await self.show_page(page)

    async def first_page(self):
        """goes to the first page"""
        await self.show_page(1)

    async def last_page(self):
        """goes to the last page"""
        await self.show_page(self.maximum_pages)

    async def next_page(self):
        """goes to the next page"""
        await self.checked_show_page(self.current_page + 1)

    async def previous_page(self):
        """goes to the previous page"""
        await self.checked_show_page(self.current_page - 1)

    async def show_current_page(self):
        if self.paginating:
            await self.show_page(self.current_page)

    async def stop_pages(self):
        """stops the interactive pagination session"""
        # await self.bot.delete_message(self.message)
        try:
            # Can't remove reactions in DMs, so don't even try
            if not is_private(self.message.channel):
                await self.message.clear_reactions()
        except:
            pass
        self.paginating = False

    def react_check(self, reaction: discord.Reaction, user: discord.User):
        if user is None or user.id != self.author.id:
            return False

        if reaction.message.id != self.message.id:
            return False

        for (emoji, func) in self.reaction_emojis:
            if reaction.emoji == emoji:
                self.match = func
                return True
        return False

    async def paginate(self):
        """Actually paginate the entries and run the interactive loop if necessary."""
        first_page = self.show_page(1, first=True)
        if not self.paginating:
            await first_page
        else:
            self.bot.loop.create_task(first_page)

        while self.paginating:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", check=self.react_check, timeout=120.0)
            except asyncio.TimeoutError:
                self.paginating = False
                try:
                    await self.message.clear_reactions()
                except:
                    pass
                finally:
                    break

            try:
                await self.message.remove_reaction(reaction, user)
            except:
                pass

            await self.match()


class VocationPages(Pages):
    def __init__(self, ctx: commands.Context, *, entries, vocations, **kwargs):
        super().__init__(ctx, entries=entries, **kwargs)
        present_vocations = []
        # Only add vocation filters for the vocations present
        if any(v.lower() in DRUID for v in vocations):
            present_vocations.append(('\U00002744', self.filter_druids))
        if any(v.lower() in SORCERER for v in vocations):
            present_vocations.append(('\U0001F525', self.filter_sorcerers))
        if any(v.lower() in PALADIN for v in vocations):
            present_vocations.append(('\U0001F3F9', self.filter_paladins))
        if any(v.lower() in KNIGHT for v in vocations):
            present_vocations.append(('\U0001F6E1', self.filter_knights))

        # Only add filters if there's more than one different vocation
        if len(present_vocations) > 1:
            self.reaction_emojis.extend(present_vocations)

        # Copies the entry list without reference
        self.original_entries = entries[:]
        self.vocations = vocations
        self.filters = [DRUID, SORCERER, PALADIN, KNIGHT]
        self.current_filter = -1

    async def filter_druids(self):
        await self.filter_vocation(0)

    async def filter_knights(self):
        await self.filter_vocation(3)

    async def filter_paladins(self):
        await self.filter_vocation(2)

    async def filter_sorcerers(self):
        await self.filter_vocation(1)

    async def filter_vocation(self, vocation):
        if vocation != self.current_filter:
            self.current_filter = vocation
            self.entries = [c for c, v in zip(self.original_entries, self.vocations) if v.lower() in self.filters[vocation]]
        else:
            self.current_filter = -1
            self.entries = self.original_entries[:]
        pages, left_over = divmod(len(self.entries), self.per_page)
        if left_over:
            pages += 1
        self.maximum_pages = pages
        await self.show_page(1)

