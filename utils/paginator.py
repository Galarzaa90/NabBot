import asyncio
import discord

from utils.discord import is_private


class CannotPaginate(Exception):
    pass


class Paginator:
    """Implements a paginator that queries the user for the
    pagination interface.

    Pages are 1-index based, not 0-index based.
    If the user does not reply within 2 minutes then the pagination
    interface exits automatically.

    Based on Rapptz' Paginator: https://github.com/Rapptz/RoboDanny/blob/master/cogs/utils/paginator.py
    Modified for Nab Bot's needs.

    Parameters
    ------------
    bot
        The bot instance.
    message
        The message that initiated this session.
    entries
        A list of entries to paginate.
    per_page
        How many entries show up per page.

    Attributes
    -----------
    embed: discord.Embed
        The embed object that is being used to send pagination info.
        Feel free to modify this externally. Only the description,
        footer fields, and colour are internally modified.
    permissions: discord.Permissions
        Our permissions for the channel.
    """
    def __init__(self, bot: discord.Client, *, message: discord.Message, entries, per_page=10, title=None,
                 description="", numerate=True, color: discord.Colour=None):
        self.bot = bot
        self.entries = entries
        self.message = message
        self.author = message.author
        self.per_page = per_page
        self.current_page = 1
        self.title = title
        self.numerate = numerate
        self.description = description
        pages, left_over = divmod(len(self.entries), self.per_page)
        if left_over:
            pages += 1
        self.maximum_pages = pages
        self.embed = discord.Embed()
        if color is not None:
            self.embed.colour = color
        self.paginating = len(entries) > per_page
        self.reaction_emojis = [
            ('\N{BLACK LEFT-POINTING TRIANGLE}', self.previous_page),
            ('\N{BLACK RIGHT-POINTING TRIANGLE}', self.next_page),
            ('\U000023F9', self.stop_pages)
        ]
        guild = self.message.guild
        if guild is not None:
            self.permissions = self.message.channel.permissions_for(guild.me)
        else:
            self.permissions = self.message.channel.permissions_for(self.bot.user)

        if not self.permissions.embed_links:
            raise CannotPaginate('Bot does not have embed links permission.')

    def get_page(self, page):
        base = (page - 1) * self.per_page
        return self.entries[base:base + self.per_page]

    @asyncio.coroutine
    def show_page(self, page, *, first=False):
        self.current_page = page
        entries = self.get_page(page)
        p = []
        if self.numerate:
            for t in enumerate(entries, 1 + ((page - 1) * self.per_page)):
                p.append('%s. %s' % t)
        else:
            for t in entries:
                p.append(t)
        self.embed.set_footer(text='Page %s/%s (%s entries)' % (page, self.maximum_pages, len(self.entries)))
        if self.title:
            self.embed.title = self.title

        self.embed.description = self.description+"\n"+'\n'.join(p)
        if not self.paginating:
            ret = yield from self.message.channel.send(embed=self.embed)
            return ret

        if not first:
            yield from self.message.edit(embed=self.embed)
            return

        # verify we can actually use the pagination session
        if not self.permissions.add_reactions:
            raise CannotPaginate('Bot does not have add reactions permission.')
        if not self.permissions.read_message_history:
            raise CannotPaginate("Bot does not have read message history permission.")

        self.message = yield from self.message.channel.send(embed=self.embed)
        for (reaction, _) in self.reaction_emojis:
            if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
                # no |<< or >>| buttons if we only have two pages
                # we can't forbid it if someone ends up using it but remove
                # it from the default set
                continue

            yield from self.message.add_reaction(reaction)

    @asyncio.coroutine
    def checked_show_page(self, page):
        if page != 0 and page <= self.maximum_pages:
            yield from self.show_page(page)

    @asyncio.coroutine
    def first_page(self):
        """goes to the first page"""
        yield from self.show_page(1)

    @asyncio.coroutine
    def last_page(self):
        """goes to the last page"""
        yield from self.show_page(self.maximum_pages)

    @asyncio.coroutine
    def next_page(self):
        """goes to the next page"""
        yield from self.checked_show_page(self.current_page + 1)

    @asyncio.coroutine
    def previous_page(self):
        """goes to the previous page"""
        yield from self.checked_show_page(self.current_page - 1)

    @asyncio.coroutine
    def show_current_page(self):
        if self.paginating:
            yield from self.show_page(self.current_page)

    @asyncio.coroutine
    def stop_pages(self):
        """stops the interactive pagination session"""
        # yield from self.bot.delete_message(self.message)
        try:
            yield from self.message.clear_reactions()
        except:
            pass
        yield from self.show_page(1)
        self.paginating = False

    def react_check(self, reaction, user):
        if not is_private(self.message.channel) and user.id != self.author.id:
            return False

        for (emoji, func) in self.reaction_emojis:
            if reaction.emoji == emoji:
                self.match = func
                return True
        return False

    @asyncio.coroutine
    def paginate(self):
        """Actually paginate the entries and run the interactive loop if necessary."""
        yield from self.show_page(1, first=True)

        while self.paginating:
            try:
                react = yield from self.bot.wait_for("reaction_add", check=self.react_check, timeout=120.0)
                try:
                    yield from self.message.remove_reaction(react[0].emoji, react[1])
                except Exception as e:
                    print(e)
                    pass  # can't remove it so don't bother doing so
            except asyncio.TimeoutError:
                yield from self.first_page()
                self.paginating = False
                try:
                    yield from self.message.clear_reactions()
                except:
                    pass
                finally:
                    break

            yield from self.match()