from typing import List

import discord
from discord.ext import commands

from nabbot import NabBot
from .utils import checks, join_list, log, get_user_avatar
from .utils.config import config
from .utils.context import NabCtx
from .utils.tibia import get_character, NetworkError, Character


class Admin:
    """Commands for server owners and admins.

    Admins are members with the `Administrator` permission."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    @checks.is_owner()
    @checks.is_tracking_world()
    @commands.command(name="addaccount", aliases=["addacc"], usage="<user>,<character>")
    async def add_account(self, ctx: NabCtx, *, params):
        """Register a character and all other visible characters to a discord user.

        If a character is hidden, only that character will be added. Characters in other worlds are skipped."""
        params = params.split(",")
        if len(params) != 2:
            raise commands.BadArgument()
        target_name, char_name = params

        user = ctx.author
        world = ctx.world

        target = self.bot.get_member(target_name, ctx.guild)
        if target is None:
            return await ctx.send(f"{ctx.tick(False)} I couldn't find any users named @{target_name}")
        if target.bot:
            return await ctx.send(f"{ctx.tick(False)} You can't register characters to discord bots!")

        # Get list of the user's shared servers with the bot
        target_guilds = self.bot.get_user_guilds(target.id)
        # Filter only the servers that follow the same as the current context
        target_guilds = list(filter(lambda x: self.bot.tracked_worlds.get(x.id) == world, target_guilds))

        msg = await ctx.send(f"{config.loading_emoji} Fetching characters...")
        try:
            char = await get_character(ctx.bot, char_name)
            if char is None:
                return await msg.edit(content="That character doesn't exist.")
        except NetworkError:
            return await msg.edit(content="I couldn't fetch the character, please try again.")
        chars = char.other_characters
        # If the char is hidden,we still add the searched character, if we have just one, we replace it with the
        # searched char, so we don't have to look him up again
        if len(chars) == 0 or len(chars) == 1:
            chars = [char]
        skipped = []
        updated = []
        added: List[Character] = []
        existent = []
        for char in chars:
            # Skip chars in non-tracked worlds
            if char.world != world:
                skipped.append(char)
                continue
            db_char = await ctx.pool.fetchrow("""SELECT id, name, guild, user_id as owner, abs(level) as level, vocation
                                                 FROM "character"
                                                 WHERE name = $1""", char.name)
            if db_char is not None:
                owner = self.bot.get_member(db_char["owner"])
                # Previous owner doesn't exist anymore
                if owner is None:
                    updated.append({'name': char.name, 'world': char.world, 'prevowner': db_char["owner"],
                                    'vocation': db_char["vocation"], 'level': db_char['level'],
                                    'guild': db_char['guild'], 'id': db_char['id']})
                    continue
                # Char already registered to this user
                elif owner.id == target.id:
                    existent.append("{0.name} ({0.world})".format(char))
                    continue
                # Character is registered to another user, we stop the whole process
                else:
                    reply = "A character in that account ({0}) is already registered to **{1.display_name}**"
                    await ctx.send(reply.format(db_char["name"], owner))
                    return
            # If we only have one char, it already contains full data
            if len(chars) > 1:
                try:
                    await ctx.channel.trigger_typing()
                    char = await get_character(ctx.bot, char.name)
                except NetworkError:
                    await ctx.send("I'm having network troubles, please try again.")
                    return
            if char.deleted is not None:
                skipped.append(char)
                continue
            added.append(char)

        if len(skipped) == len(chars):
            await ctx.send(f"Sorry, I couldn't find any characters in **{world}**.")
            return

        reply = ""
        if len(existent) > 0:
            reply += "\nThe following characters were already registered to @{1}: {0}" \
                .format(join_list(existent, ", ", " and "), target.display_name)

        if len(added) > 0:
            reply += "\nThe following characters were added to @{1.display_name}: {0}" \
                .format(join_list(["{0.name} ({0.world})".format(c) for c in added], ", ", " and "), target)
            for char in added:
                log.info("{2.display_name} registered character {0} was assigned to {1.display_name} (ID: {1.id})"
                         .format(char.name, target, user))

        if len(updated) > 0:
            reply += "\nThe following characters were reassigned to @{1.display_name}: {0}" \
                .format(join_list(["{name} ({world})".format(**c) for c in updated], ", ", " and "), target)
            for char in updated:
                log.info("{2.display_name} reassigned character {0} to {1.display_name} (ID: {1.id})"
                         .format(char['name'], target, user))

        async with ctx.pool.acquire() as conn:
            for char in updated:
                await conn.execute('UPDATE "character" SET user_id = $1 WHERE id = $2', target.id, char["id"])
            for char in added:
                await conn.execute("""INSERT INTO "character"(name, level, vocation, user_id, world, guild)
                                      VALUES($1, $2, $3, $4, $5, $6) ON CONFLICT(name) DO NOTHING""",
                                   char.name, -char.level, char.vocation, target.id, char.world, char.guild_name)

        await ctx.send(reply)
        self.bot.dispatch("characters_registered", target, added, updated, ctx.author)

    @checks.is_admin()
    @checks.is_tracking_world()
    @commands.command(name="addchar", aliases=["registerchar"], usage="<user>,<character>")
    async def add_char(self, ctx: NabCtx, *, params):
        """Registers a character to a user.

        The character must be in the world you're tracking.
        If the desired character is already assigned to someone else, the user must use `claim`."""
        params = params.split(",")
        if len(params) != 2:
            raise commands.BadArgument()

        user = self.bot.get_member(params[0], ctx.guild)
        if user is None:
            return await ctx.send(f"{ctx.tick(False)} I don't see any user named **{params[0]}** in this server.")
        if user.bot:
            return await ctx.send(f"{ctx.tick(False)} You can't register characters to discord bots!")
        with ctx.typing():
            try:
                char = await get_character(ctx.bot, params[1])
                if char is None:
                    await ctx.send("That character doesn't exist")
                    return
            except NetworkError:
                await ctx.send("I couldn't fetch the character, please try again.")
                return
            if char.world != ctx.world:
                await ctx.send("**{0.name}** ({0.world}) is not in a world you can manage.".format(char))
                return
            if char.deleted is not None:
                await ctx.send("**{0.name}** ({0.world}) is scheduled for deletion and can't be added.".format(char))
                return
            embed = discord.Embed()
            embed.set_author(name=f"{user.name}#{user.discriminator}", icon_url=get_user_avatar(user))
            embed.colour = discord.Colour.dark_teal()
            icon_url = get_user_avatar(ctx.author)
            embed.set_footer(text="{0.name}#{0.discriminator}".format(ctx.author), icon_url=icon_url)
            async with ctx.pool.acquire() as conn:
                result = await conn.fetchrow('SELECT id, name, user_id FROM "character" WHERE name = $1', char.name)
                if result is not None:
                    # Registered to a different user
                    if result["user_id"] != user.id:
                        current_user = self.bot.get_member(result["user_id"])
                        # User registered to someone else
                        if current_user is not None:
                            await ctx.send("This character is already registered to  **{0.name}#{0.discriminator}**"
                                           .format(current_user))
                            return
                        # User no longer in any servers
                        await conn.execute('UPDATE "character" SET user_id = $1 WHERE id = $2', user.id, result["id"])
                        await ctx.send("This character was reassigned to this user successfully.")
                        char_dict = {"name": char.name, "level": char.level, "vocation": char.vocation,
                                     "guild": char.guild_name, "world": char.world}
                        self.bot.dispatch("characters_registered", user, [], [char_dict], ctx.author)
                    else:
                        await ctx.send("This character is already registered to this user.")
                    return
                await conn.execute("""INSERT INTO "character"(name, level, vocation, user_id, world, guild)
                                      VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT(name) DO NOTHING""",
                                   char.name, -char.level, char.vocation, user.id, char.world, char.guild_name)
                await ctx.send("**{0}** was registered successfully to this user.".format(char.name))
                char_dict = {"name": char.name, "level": char.level, "vocation": char.vocation,
                             "guild": char.guild_name, "world": char.world}
                self.bot.dispatch("characters_registered", user, [char_dict], [], ctx.author)

    @checks.is_admin()
    @commands.guild_only()
    @commands.command()
    async def checkchannel(self, ctx: NabCtx, *, channel: discord.TextChannel = None):
        """Checks the channel's permissions.

        Makes sure that the bot has all the required permissions to work properly.
        If no channel is specified, the current one is checked."""
        if channel is None:
            channel = ctx.channel
        permissions = channel.permissions_for(ctx.me)
        content = f"**Checking {channel.mention}:**"
        if permissions.administrator:
            content += f"\n{ctx.tick(True)} I have `Administrator` permission."
            await ctx.send(content)
            return
        perm_dict = dict(permissions)
        check_permissions = {
            "read_messages": ["error", "I won't be able to see commands in here."],
            "send_messages": ["error", "I won't be able to respond in here."],
            "add_reactions": ["error", "Pagination or commands that require emoji confirmation won't work."],
            "external_emojis": ["warn", "I won't be able to show my emojis in some commands."],
            "read_message_history": ["error", "I won't be able to see your reactions in commands."],
            "manage_messages": ["warn", "Command pagination won't work well and I won't be able to delete messages "
                                        "in the ask channel."],
            "embed_links": ["error", "I won't be able to show many of my commands."],
            "attach_files": ["warn", "I won't be able to show images in some of my commands."]
        }
        ok = True
        for k, v in check_permissions.items():
            level, explain = v
            if not perm_dict[k]:
                ok = False
                perm_name = k.replace("_", " ").title()
                icon = ctx.tick(False) if level == "error" else config.warn_emoji
                content += f"\nMissing `{perm_name}` permission"
                content += f"\n\t{icon} {explain}"
        if ok:
            content += f"\n{ctx.tick(True)} All permissions are correct!"
        await ctx.send(content)

    @checks.is_admin()
    @checks.is_tracking_world()
    @commands.command(name="removechar", aliases=["deletechar", "unregisterchar"])
    async def remove_char(self, ctx: NabCtx, *, name):
        """Removes a registered character.

        Note that you can only remove chars if they are from users exclusively in your server.
        You can't remove any characters that would alter other servers NabBot is in."""
        # This could be used to remove deleted chars so we don't need to check anything
        # Except if the char exists in the database...
        result = await ctx.pool.fetchrow("""SELECT name, user_id, world, guild, abs(level) as level, vocation
                                            FROM "character" WHERE lower(name) = $1""", name.lower())
        if result is None or result["user_id"] == 0:
            return await ctx.send("There's no character with that name registered.")
        if result["world"] != ctx.world:
            return await ctx.send(f"{ctx.tick(False)} The character **{result['name']}** is in a different world.")

        user = self.bot.get_user(result["user_id"])
        if user is not None:
            user_guilds = self.bot.get_user_guilds(user.id)
            for guild in user_guilds:
                if guild == ctx.guild:
                    continue
                if self.bot.tracked_worlds.get(guild.id, None) != ctx.world:
                    continue
                author: discord.Member = guild.get_member(ctx.author.id)
                if author is None or not author.guild_permissions.manage_guild:
                    await ctx.send(f"{ctx.tick(False)} The user of this server is also in another server tracking "
                                   f"**{ctx.world}**, where you are not an admin. You can't alter other servers.")
                    return
        username = "unknown" if user is None else user.display_name
        await ctx.pool.execute('UPDATE "character" SET user_id = 0 WHERE name = $1', result["name"])
        await ctx.send("**{0}** was removed successfully from **@{1}**.".format(result["name"], username))
        self.bot.dispatch("character_unregistered", user, result, ctx.author)


def setup(bot):
    bot.add_cog(Admin(bot))
