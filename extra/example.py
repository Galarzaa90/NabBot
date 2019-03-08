from discord.ext import commands

from nabbot import NabBot
from cogs.utils import checks
from cogs.utils.config import config
from cogs.utils.tibia import get_share_range


class Example(commands.Cog):
    """Example cog"""
    def __init__(self, bot: NabBot):
        self.bot = bot

    def cog_unload(self):
        """This will be called every time this cog is unloaded

        Used for cleaning up tasks and other stuff"""
        pass

    def bot_check(self, ctx):
        """This check is called for ANY command, in any cog

        Use this with caution as this will affect all the other commands."""
        return True

    async def cog_check(self, ctx):
        """This check is called before running any command from this cog.

        If this returns true, the command can be run, otherwise it can't.

        This is also called when you /help is called, to check if the command is available to the user."""
        # Only the bot owner can use the commands in this cog
        return await checks.is_owner(ctx)

    @commands.command()
    async def example(self, ctx):
        output = "Using methods from `nabbot.py`:"
        member = self.bot.get_member(ctx.author.id)
        output += f"\n```py\nself.bot.get_member({ctx.author.id})\n> {member}```"

        output += "\nUsing methods from `utils/tibia.py`:"
        share_range = get_share_range(300)
        output += f"\n```py\nfrom utils.tibia import get_share_range\nget_share_range(300)" \
                  f"\n> {share_range!r}```"

        output += "\nUsing values from `utils/config.py` (values in `config.yml`):"
        prefixes = config.command_prefix
        output += f"\n```py\nfrom utils.config import config\nconfig.command_prefix\n> {prefixes!r}```"

        await ctx.send(output)


# This is necessary for NabBot to load our cog
def setup(bot):
    bot.add_cog(Example(bot))
