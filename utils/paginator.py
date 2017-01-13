import asyncio
import discord


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
    def __init__(self, bot, *, message, entries, per_page=10, title=None):
        self.bot = bot
        self.entries = entries
        self.message = message
        self.author = message.author
        self.per_page = per_page
        self.current_page = 1
        self.title = title
        pages, left_over = divmod(len(self.entries), self.per_page)
        if left_over:
            pages += 1
        self.maximum_pages = pages
        self.embed = discord.Embed()
        self.paginating = len(entries) > per_page
        self.reaction_emojis = [
            ('\N{BLACK LEFT-POINTING TRIANGLE}', self.previous_page),
            ('\N{BLACK RIGHT-POINTING TRIANGLE}', self.next_page),
        ]
        server = self.message.server
        if server is not None:
            self.permissions = self.message.channel.permissions_for(server.me)
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
        for t in enumerate(entries, 1 + ((page - 1) * self.per_page)):
            p.append('%s. %s' % t)
        self.embed.set_footer(text='Page %s/%s (%s entries)' % (page, self.maximum_pages, len(self.entries)))
        if self.title:
            self.embed.title = self.title

        if not self.paginating:
            self.embed.description = '\n'.join(p)
            ret = yield from self.bot.send_message(self.message.channel, embed=self.embed)
            return ret

        if not first:
            self.embed.description = '\n'.join(p)
            ret = yield from self.bot.edit_message(self.message, embed=self.embed)
            return ret

        # verify we can actually use the pagination session
        if not self.permissions.add_reactions:
            raise CannotPaginate('Bot does not have add reactions permission.')

        self.embed.description = '\n'.join(p)
        self.message = yield from self.bot.send_message(self.message.channel, embed=self.embed)
        for (reaction, _) in self.reaction_emojis:
            if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
                # no |<< or >>| buttons if we only have two pages
                # we can't forbid it if someone ends up using it but remove
                # it from the default set
                continue

            yield from self.bot.add_reaction(self.message, reaction)

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
        yield from self.bot.delete_message(self.message)
        self.paginating = False

    def react_check(self, reaction, user):
        if not self.message.channel.is_private and user.id != self.author.id:
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
            react = yield from self.bot.wait_for_reaction(message=self.message, check=self.react_check, timeout=120.0)
            if react is None:
                yield from self.first_page()
                self.paginating = False
                try:
                    yield from self.bot.clear_reactions(self.message)
                except:
                    pass
                finally:
                    break
            try:
                yield from self.bot.remove_reaction(self.message, react.reaction.emoji, react.user)
            except:
                pass  # can't remove it so don't bother doing so

            yield from self.match()