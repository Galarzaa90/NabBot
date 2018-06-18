import asyncio
from typing import List

import discord
from discord.ext import commands

from nabbot import NabBot
from utils import checks, context
from utils.config import config
from utils.context import NabCtx
from utils.database import *
from utils.discord import get_user_avatar
from utils.general import join_list, log
from utils.tibia import get_character, NetworkError, Character, get_voc_abb_and_emoji


class Admin:
    """Commands for server owners and admins.

    Admins are members with the `Administrator` permission."""
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def __error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            if not error.args:
                await ctx.send(f"{ctx.tick(False)} The correct syntax is: "
                               f"`{ctx.clean_prefix}{ctx.invoked_with} {ctx.usage}`")
            else:
                await ctx.send(error)

    @commands.guild_only()
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
            await ctx.send(f"{ctx.tick(False)} I couldn't find any users named @{target_name}")
            return
        if target.bot:
            await ctx.send(f"{ctx.tick(False)} You can't register characters to discord bots!")
            return
        target_guilds = self.bot.get_user_guilds(target.id)
        target_guilds = list(filter(lambda x: self.bot.tracked_worlds.get(x.id) == world, target_guilds))

        await ctx.trigger_typing()
        try:
            char = await get_character(char_name)
            if char is None:
                await ctx.send("That character doesn't exist.")
                return
        except NetworkError:
            await ctx.send("I couldn't fetch the character, please try again.")
            return
        chars = char.other_characters
        # If the char is hidden,we still add the searched character, if we have just one, we replace it with the
        # searched char, so we don't have to look him up again
        if len(chars) == 0 or len(chars) == 1:
            chars = [char]
        skipped = []
        updated = []
        added = []  # type: List[Character]
        existent = []
        for char in chars:
            # Skip chars in non-tracked worlds
            if char.world != world:
                skipped.append(char)
                continue
            with closing(userDatabase.cursor()) as c:
                c.execute("SELECT name, guild, user_id as owner, abs(level) as level FROM chars WHERE name LIKE ?",
                          (char.name,))
                db_char = c.fetchone()
            if db_char is not None:
                owner = self.bot.get_member(db_char["owner"])
                # Previous owner doesn't exist anymore
                if owner is None:
                    updated.append({'name': char.name, 'world': char.world, 'prevowner': db_char["owner"],
                                    'vocation': db_char["vocation"], 'level': db_char['level'],
                                    'guild': db_char['guild']
                                    })
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
                    char = await get_character(char.name)
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
        log_reply = dict().fromkeys([server.id for server in target_guilds], "")
        if len(existent) > 0:
            reply += "\nThe following characters were already registered to @{1}: {0}" \
                .format(join_list(existent, ", ", " and "), target.display_name)

        if len(added) > 0:
            reply += "\nThe following characters were added to @{1.display_name}: {0}" \
                .format(join_list(["{0.name} ({0.world})".format(c) for c in added], ", ", " and "), target)
            for char in added:
                log.info("{2.display_name} registered character {0} was assigned to {1.display_name} (ID: {1.id})"
                         .format(char.name, target, user))
                # Announce on server log of each server
                for guild in target_guilds:
                    _guild = "No guild" if char.guild is None else char.guild_name
                    voc = get_voc_abb_and_emoji(char.vocation)
                    log_reply[guild.id] += "\n\u2023 {1.name} - Level {1.level} {2} - **{0}**" \
                        .format(_guild, char, voc)

        if len(updated) > 0:
            reply += "\nThe following characters were reassigned to @{1.display_name}: {0}" \
                .format(join_list(["{name} ({world})".format(**c) for c in updated], ", ", " and "), target)
            for char in updated:
                log.info("{2.display_name} reassigned character {0} to {1.display_name} (ID: {1.id})"
                         .format(char['name'], target, user))
                # Announce on server log of each server
                for guild in target_guilds:
                    char["voc"] = get_voc_abb_and_emoji(char["vocation"])
                    if char["guild"] is None:
                        char["guild"] = "No guild"
                    log_reply[guild.id] += "\n\u2023 {name} - Level {level} {voc} - **{guild}** (Reassigned)". \
                        format(**char)

        for char in updated:
            with userDatabase as conn:
                conn.execute("UPDATE chars SET user_id = ? WHERE name LIKE ?", (target.id, char['name']))
        for char in added:
            with userDatabase as conn:
                conn.execute("INSERT INTO chars (name,level,vocation,user_id, world, guild) VALUES (?,?,?,?,?,?)",
                             (char.name, char.level * -1, char.vocation, target.id, char.world,
                              char.guild_name)
                             )

        with userDatabase as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (target.id, target.display_name,))
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (target.display_name, target.id,))

        await ctx.send(reply)
        print(log_reply)
        for server_id, message in log_reply.items():
            if message:
                message = f"{target.mention} registered:" + message
                embed = discord.Embed(description=message)
                embed.set_author(name=f"{target.name}#{target.discriminator}", icon_url=get_user_avatar(target))
                embed.colour = discord.Colour.dark_teal()
                icon_url = get_user_avatar(user)
                embed.set_footer(text="{0.name}#{0.discriminator}".format(user), icon_url=icon_url)
                await self.bot.send_log_message(self.bot.get_guild(server_id), embed=embed)

    @commands.command(name="addchar", aliases=["registerchar"], usage="<user>,<character>")
    @checks.is_admin()
    @commands.guild_only()
    async def add_char(self, ctx: NabCtx, *, params):
        """Registers a character to a user."""
        params = params.split(",")
        if len(params) != 2:
            raise commands.BadArgument()

        if ctx.world is None:
            await ctx.send("This server is not tracking any worlds.")
            return

        user = self.bot.get_member(params[0], ctx.guild)
        if user is None:
            await ctx.send("I don't see any user named **{0}** in this server.".format(params[0]))
        user_servers = self.bot.get_user_guilds(user.id)

        with ctx.typing():
            try:
                char = await get_character(params[1])
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

            with closing(userDatabase.cursor()) as c:
                c.execute("SELECT id, name, user_id FROM chars WHERE name LIKE ?", (char.name,))
                result = c.fetchone()
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
                        c.execute("UPDATE chars SET user_id = ? WHERE id = ?", (user.id, result["id"],))
                        await ctx.send("This character was reassigned to this user successfully.")
                        userDatabase.commit()
                        for server in user_servers:
                            world = self.bot.tracked_worlds.get(server.id, None)
                            if world == char.world:
                                guild = "No guild" if char.guild is None else char.guild_name
                                embed.description = "{0.mention} registered:\n\u2023 {1} - Level {2} {3} - **{4}**"\
                                    .format(user, char.name, char.level, get_voc_abb_and_emoji(char.vocation), guild)
                                await self.bot.send_log_message(server, embed=embed)
                    else:
                        await ctx.send("This character is already registered to this user.")
                    return
                c.execute("INSERT INTO chars (name,level,vocation,user_id, world, guild) VALUES (?,?,?,?,?,?)",
                          (char.name, char.level * -1, char.vocation, user.id, char.world, char.guild_name))
                # Check if user is already registered
                c.execute("SELECT id from users WHERE id = ?", (user.id,))
                result = c.fetchone()
                if result is None:
                    c.execute("INSERT INTO users(id,name) VALUES (?,?)", (user.id, user.display_name,))
                await ctx.send("**{0}** was registered successfully to this user.".format(char.name))
                # Log on relevant servers
                for server in user_servers:
                    world = self.bot.tracked_worlds.get(server.id, None)
                    if world == char.world:
                        guild = "No guild" if char.guild is None else char.guild_name
                        embed.description = "{0.mention} registered:\n\u2023 {1}  - Level {2} {3} - **{4}**"\
                            .format(user, char.name, char.level, get_voc_abb_and_emoji(char.vocation), guild)
                        await self.bot.send_log_message(server, embed=embed)
                userDatabase.commit()

    @commands.command()
    @checks.is_admin()
    @commands.guild_only()
    async def checkchannel(self, ctx: NabCtx, *, channel: discord.TextChannel = None):
        """Checks the channel's permissions.

        Makes sure that the bot has all the required permissions to work properly.
        If no channel is specified, the current one is checked."""
        if channel is None:
            channel = ctx.channel
        permissions = channel.permissions_for(ctx.me)  # type: discord.Permissions
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
                icon = ctx.tick(False) if level == "error" else "⚠"
                content += f"\nMissing `{perm_name}` permission"
                content += f"\n\t{icon} {explain}"
        if ok:
            content += f"\n{ctx.tick(True)} All permissions are correct!"
        await ctx.send(content)

    @commands.guild_only()
    @checks.is_admin()
    @checks.is_not_lite()
    @commands.command(name="setwelcome")
    async def set_welcome(self, ctx, *, message: str = None):
        """Set the messages members get PMed when joining.

        A part of the message is already fixed and cannot be changed, but the message can be extended.

        Say "clear" to clear the current message.

        The following can be used to get dynamically replaced:
        {user.name} - The joining user's name
        {user.mention} - The joining user's mention
        {server.name} - The name of the server the member joined.
        {owner.name} - The name of the owner of the server.
        {owner.mention} - A mention to the owner of the server.
        {bot.name} - The name of the bot
        {bot.mention} - The name of the bot."""

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        if message is None:
            current_message = get_server_property(ctx.guild.id, "welcome")
            if current_message is None:
                current_message = config.welcome_pm.format(ctx.author, self.bot)
                await ctx.send(f"This server has no custom message, joining members get the default message:\n"
                               f"----------\n{current_message}")
            else:
                unformatted_message = f"{config.welcome_pm}\n{current_message}"
                complete_message = unformatted_message.format(user=ctx.author, server=ctx.guild, bot=self.bot.user,
                                                              owner=ctx.guild.owner)
                await ctx.send(f"This server has the following welcome message:\n"
                               f"----------\n``The first two lines can't be changed``\n{complete_message}")
            return
        if message.lower() in ["clear", "none", "delete", "remove"]:
            await ctx.send("Are you sure you want to delete this server's welcome message? `yes/no`\n"
                           "The default welcome message will still be shown.")
            try:
                reply = await self.bot.wait_for("message", timeout=50.0, check=check)
                if reply.content.lower() not in ["yes", "y"]:
                    await ctx.send("No changes were made then.")
                    return
            except asyncio.TimeoutError:
                await ctx.send("I guess you changed your mind...")
                return

            set_server_property(ctx.guild.id, "welcome", None)
            await ctx.send("This server's welcome message was removed.")
            return

        if len(message) > 1200:
            await ctx.send("This message exceeds the character limit! ({0}/{1}".format(len(message), 1200))
            return
        try:
            unformatted_message = f"{config.welcome_pm}\n{message}"
            complete_message = unformatted_message.format(user=ctx.author, server=ctx.guild, bot=self.bot.user,
                                                          owner=ctx.guild.owner)
        except Exception as e:
            await ctx.send("There is something wrong with your message.\n```{0}```".format(e))
            return

        await ctx.send("Are you sure you want this as your private welcome message?\n"
                       "----------\n``The first two lines can't be changed``\n{0}"
                       .format(complete_message))
        try:
            reply = await self.bot.wait_for("message", timeout=120.0, check=check)
            if reply.content.lower() not in ["yes", "y"]:
                await ctx.send("No changes were made then.")
                return
        except asyncio.TimeoutError:
            await ctx.send("I guess you changed your mind...")
            return

        set_server_property(ctx.guild.id, "welcome", message)
        await ctx.send("This server's welcome message has been changed successfully.")

    @commands.command(name="removechar", aliases=["deletechar", "unregisterchar"])
    @checks.is_admin()
    @commands.guild_only()
    async def remove_char(self, ctx, *, name):
        """Removes a registered character."""
        # This could be used to remove deleted chars so we don't need to check anything
        # Except if the char exists in the database...
        c = userDatabase.cursor()
        try:
            c.execute("SELECT name, user_id, world, ABS(level) as level, vocation, guild "
                      "FROM chars WHERE name LIKE ?", (name,))
            result = c.fetchone()
            if result is None or result["user_id"] == 0:
                await ctx.send("There's no character with that name registered.")
                return
            user = self.bot.get_member(result["user_id"])
            if user is not None:
                # User is in another server
                if ctx.guild.get_member(user.id) is None:
                    await ctx.send("The character is assigned to someone on another server.")
                    return
            username = "unknown" if user is None else user.display_name
            c.execute("UPDATE chars SET user_id = 0 WHERE name LIKE ?", (name,))
            await ctx.send("**{0}** was removed successfully from **@{1}**.".format(result["name"], username))
            if user is not None:
                for server in self.bot.get_user_guilds(user.id):
                    world = self.bot.tracked_worlds.get(server.id, None)
                    if world != result["world"]:
                        continue
                    if result["guild"] is None:
                        result["guild"] = "No guild"
                    log_msg = "{0.mention} unregistered:\n\u2023 {1} - Level {2} {3} - **{4}**". \
                        format(user, result["name"], result["level"], get_voc_abb_and_emoji(result["vocation"]),
                               result["guild"])
                    embed = discord.Embed(description=log_msg)
                    embed.set_author(name=f"{user.name}#{user.discriminator}", icon_url=get_user_avatar(user))
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(ctx.author),
                                     icon_url=get_user_avatar(ctx.author))
                    embed.colour = discord.Colour.dark_teal()
                    await self.bot.send_log_message(server, embed=embed)
            return
        finally:
            c.close()
            userDatabase.commit()


def setup(bot):
    bot.add_cog(Admin(bot))
