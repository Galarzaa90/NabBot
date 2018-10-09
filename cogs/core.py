import datetime as dt
from typing import List

import discord
from discord.ext import commands

from .utils.checks import CannotEmbed
from .utils import context
from .utils.database import userDatabase, _get_server_property
from .utils.tibia import get_voc_abb_and_emoji
from .utils import log, join_list, get_user_avatar, get_region_string
from .utils import config


class Core:
    """Cog with NabBot's main functions."""

    def __init__(self, bot):
        self.bot = bot

    async def on_command_error(self, ctx: context.NabCtx, error):
        """Handles command errors"""
        if isinstance(error, commands.errors.CommandNotFound):
            return
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(error)
        elif isinstance(error, CannotEmbed):
            await ctx.send(f"{ctx.tick(False)} Sorry, `Embed Links` permission is required for this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{ctx.tick(False)} The correct syntax is: "
                           f"`{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.usage}`.\n"
                           f"Try `{ctx.clean_prefix}help {ctx.command.qualified_name}` for more info.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"{ctx.tick(False)} {error}\n"
                           f"Try `{ctx.clean_prefix}help {ctx.command.qualified_name}` for more info.")
        elif isinstance(error, commands.CommandInvokeError):
            log.error(f"Exception in command: {ctx.message.clean_content}", exc_info=error.original)
            if isinstance(error.original, discord.HTTPException):
                await ctx.send("Sorry, the message was too long to send.")
            else:
                if ctx.bot_permissions.embed_links:
                    embed = discord.Embed(colour=discord.Colour(0xff1414))
                    embed.set_author(name="Support Server", url="https://discord.gg/NmDvhpY",
                                     icon_url=self.bot.user.avatar_url)
                    embed.set_footer(text="Please report this bug in the support server.")
                    embed.add_field(name=f"{ctx.tick(False)}Command Error",
                                    value=f"```py\n{error.original.__class__.__name__}: {error.original}```",
                                    inline=False)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f'{ctx.tick(False)} Command error:\n```py\n{error.original.__class__.__name__}:'
                                   f'{error.original}```')

    async def on_command(self, ctx):
        command = ctx.command.qualified_name
        guild_id = ctx.guild.id if ctx.guild is not None else None
        query = """INSERT INTO command(server_id, channel_id, user_id, date, prefix, command)
                   VALUES ($1, $2, $3, $4, $5, $6)
                """
        await self.bot.pool.execute(query, guild_id, ctx.channel.id, ctx.author.id,
                                    ctx.message.created_at.replace(tzinfo=dt.timezone.utc), ctx.prefix, command)

    async def on_guild_join(self, guild: discord.Guild):
        """Called when the bot joins a guild (server)."""
        log.info("Nab Bot added to server: {0.name} (ID: {0.id})".format(guild))
        message = f"**I've been added to this server.**\n" \
                  f"Some things you should know:\n" \
                  f"‣ My command prefix is: `{config.command_prefix[0]}` (it is customizable)\n" \
                  f"‣ You can see all my commands with: `{config.command_prefix[0]}help` or " \
                  f"`{config.command_prefix[0]}commands`\n" \
                  f"‣ You can configure me using: `{config.command_prefix[0]}settings`\n" \
                  f"‣ You can set a world for me to track by using `{config.command_prefix[0]}settings world`\n" \
                  f"‣ If you want a logging channel, create a channel named `{config.log_channel_name}`\n" \
                  f"‣ If you need help, join my support server: **<https://discord.me/NabBot>**\n" \
                  f"‣ For more information and links in: `{config.command_prefix[0]}about`"
        for member in guild.members:
            if member.id in self.bot.members:
                self.bot.members[member.id].append(guild.id)
            else:
                self.bot.members[member.id] = [guild.id]
        try:
            channel = self.bot.get_top_channel(guild)
            if channel is None:
                log.warning(f"Could not send join message on server: {guild.name}. No allowed channel found.")
                return
            await channel.send(message)
        except discord.HTTPException as e:
            log.error(f"Could not send join message on server: {guild.name}.", exc_info=e)

    async def on_guild_remove(self, guild: discord.Guild):
        """Called when the bot leaves a guild (server)."""
        log.info("Nab Bot left server: {0.name} (ID: {0.id})".format(guild))
        for member in guild.members:
            if member.id in self.bot.members:
                self.bot.members[member.id].remove(guild.id)

    async def on_member_join(self, member: discord.Member):
        """ Called when a member joins a guild (server) the bot is in."""
        log.info("{0.display_name} (ID: {0.id}) joined {0.guild.name}".format(member))
        # Updating member list
        if member.id in self.bot.members:
            self.bot.members[member.id].append(member.guild.id)
        else:
            self.bot.members[member.id] = [member.guild.id]

        embed = discord.Embed(description="{0.mention} joined.".format(member), color=discord.Color.green())
        embed.set_author(name="{0.name}#{0.discriminator} (ID: {0.id})".format(member),
                         icon_url=get_user_avatar(member))

        previously_registered = ""
        # If server is not tracking worlds, we don't check the database
        if member.guild.id in config.lite_servers or self.bot.tracked_worlds.get(member.guild.id) is None:
            await self.bot.send_log_message(member.guild, embed=embed)
        else:
            # Check if user already has characters registered and announce them on log_channel
            # This could be because he rejoined the server or is in another server tracking the same worlds
            world = self.bot.tracked_worlds.get(member.guild.id)
            previously_registered = ""
            if world is not None:
                c = userDatabase.cursor()
                try:
                    c.execute("SELECT name, vocation, ABS(level) as level, guild "
                              "FROM chars WHERE user_id = ? and world = ?", (member.id, world,))
                    results = c.fetchall()
                    if len(results) > 0:
                        previously_registered = "\n\nYou already have these characters in {0} registered to you: *{1}*"\
                            .format(world, join_list([r["name"] for r in results], ", ", " and "))
                        characters = ["\u2023 {name} - Level {level} {voc} - **{guild}**"
                                      .format(**c, voc=get_voc_abb_and_emoji(c["vocation"])) for c in results]
                        embed.add_field(name="Registered characters", value="\n".join(characters))
                finally:
                    c.close()
            self.bot.dispatch("character_change", member.id)
            await self.bot.send_log_message(member.guild, embed=embed)

        welcome_message = _get_server_property(member.guild.id, "welcome")
        welcome_channel_id = _get_server_property(member.guild.id, "welcome_channel", is_int=True)
        if welcome_message is None:
            return
        message = welcome_message.format(user=member, server=member.guild, bot=self.bot, owner=member.guild.owner)
        message += previously_registered
        channel = member.guild.get_channel(welcome_channel_id)
        # If channel is not found, send via pm as fallback
        if channel is None:
            channel = member
        try:
            await channel.send(message)
        except discord.Forbidden:
            try:
                # If bot has no permissions to send the message on that channel, send on private message
                # If the channel was already a private message, don't try it again
                if welcome_channel_id is None:
                    return
                await member.send(message)
            except discord.Forbidden:
                pass

    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves or is kicked from a guild."""
        now = dt.datetime.utcnow()
        self.bot.members[member.id].remove(member.guild.id)
        bot_member: discord.Member = member.guild.me

        embed = discord.Embed(description="Left the server or was kicked", colour=discord.Colour(0xffff00))
        embed.set_author(name="{0.name}#{0.discriminator} (ID: {0.id})".format(member), icon_url=get_user_avatar(member))

        # If bot can see audit log, he can see if it was a kick or member left on it's own
        if bot_member.guild_permissions.view_audit_log:
            async for entry in member.guild.audit_logs(limit=20, reverse=False, action=discord.AuditLogAction.kick,
                                                       after=now-dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at-now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == member.id:
                    embed.description = "Kicked"
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                                     icon_url=get_user_avatar(entry.user))
                    embed.colour = discord.Colour(0xff0000)
                    if entry.reason:
                        embed.description += f"\n**Reason:** {entry.reason}"
                    await self.bot.send_log_message(member.guild, embed=embed)
                    return
            embed.description = "Left the server"
            await self.bot.send_log_message(member.guild, embed=embed)
            return
        # Otherwise, we are not certain
        await self.bot.send_log_message(member.guild, embed=embed)

    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is banned from a guild."""
        now = dt.datetime.utcnow()
        bot_member: discord.Member = guild.me

        embed = discord.Embed(description="Banned", color=discord.Color(0x7a0d0d))
        embed.set_author(name="{0.name}#{0.discriminator}".format(user), icon_url=get_user_avatar(user))

        # If bot can see audit log, we can get more details of the ban
        if bot_member.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=10, reverse=False, action=discord.AuditLogAction.ban,
                                                after=now-dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at-now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == user.id:
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                                     icon_url=get_user_avatar(entry.user))
                    if entry.reason:
                        embed.description += f"\n**Reason:** {entry.reason}"
                    break
        await self.bot.send_log_message(guild, embed=embed)

    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is unbanned from a guild"""
        now = dt.datetime.utcnow()
        bot_member: discord.Member = guild.me

        embed = discord.Embed(description="Unbanned", color=discord.Color(0xff9000))
        embed.set_author(name="{0.name}#{0.discriminator} (ID {0.id})".format(user), icon_url=get_user_avatar(user))

        if bot_member.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=10, reverse=False, action=discord.AuditLogAction.unban,
                                                after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at - now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == user.id:
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                                     icon_url=get_user_avatar(entry.user))
                    break
        await self.bot.send_log_message(guild, embed=embed)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called every time a member is updated"""
        now = dt.datetime.utcnow()
        guild = after.guild
        bot_member = guild.me

        embed = discord.Embed(description=f"{after.mention}: ", color=discord.Colour.blue())
        embed.set_author(name=f"{after.name}#{after.discriminator} (ID: {after.id})", icon_url=get_user_avatar(after))
        changes = True
        if f"{before.name}#{before.discriminator}" != f"{after.name}#{after.discriminator}":
            embed.description += "Name changed from **{0.name}#{0.discriminator}** to **{1.name}#{1.discriminator}**."\
                .format(before, after)
        elif before.nick != after.nick:
            if before.nick is None:
                embed.description += f"Nickname set to **{after.nick}**"
            elif after.nick is None:
                embed.description += f"Nickname **{before.nick}** deleted"
            else:
                embed.description += f"Nickname changed from **{before.nick}** to **{after.nick}**"
            if bot_member.guild_permissions.view_audit_log:
                async for entry in guild.audit_logs(limit=10, reverse=False, action=discord.AuditLogAction.member_update,
                                                    after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                    if abs((entry.created_at - now).total_seconds()) >= 5:
                        # After is broken in the API, so we must check if entry is too old.
                        break
                    if entry.target.id == after.id:
                        # If the user changed their own nickname, no need to specify
                        if entry.user.id == after.id:
                            break
                        icon_url = get_user_avatar(entry.user)
                        embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user), icon_url=icon_url)
                        break
        else:
            changes = False
        if changes:
            await self.bot.send_log_message(after.guild, embed=embed)
        return

    async def on_guild_emojis_update(self, guild: discord.Guild, before: List[discord.Emoji],
                                     after: List[discord.Emoji]):
        """Called every time an emoji is created, deleted or updated."""
        now = dt.datetime.utcnow()
        embed = discord.Embed(color=discord.Color.dark_orange())
        emoji: discord.Emoji = None
        # Emoji deleted
        if len(before) > len(after):
            emoji = discord.utils.find(lambda e: e not in after, before)
            if emoji is None:
                return
            fix = ":" if emoji.require_colons else ""
            embed.set_author(name=f"{fix}{emoji.name}{fix} (ID: {emoji.id})", icon_url=emoji.url)
            embed.description = f"Emoji deleted."
            action = discord.AuditLogAction.emoji_delete
        # Emoji added
        elif len(after) > len(before):
            emoji = discord.utils.find(lambda e: e not in before, after)
            if emoji is None:
                return
            fix = ":" if emoji.require_colons else ""
            embed.set_author(name=f"{fix}{emoji.name}{fix} (ID: {emoji.id})", icon_url=emoji.url)
            embed.description = f"Emoji added."
            action = discord.AuditLogAction.emoji_create
        else:
            old_name = ""
            for new_emoji in after:
                for old_emoji in before:
                    if new_emoji == old_emoji and new_emoji.name != old_emoji.name:
                        old_name = old_emoji.name
                        emoji = new_emoji
                        break
            if emoji is None:
                return
            fix = ":" if emoji.require_colons else ""
            embed.set_author(name=f"{fix}{emoji.name}{fix} (ID: {emoji.id})", icon_url=emoji.url)
            embed.description = f"Emoji renamed from `{fix}{old_name}{fix}` to `{fix}{emoji.name}{fix}`"
            action = discord.AuditLogAction.emoji_update

        # Find author
        if action is not None and guild.me.guild_permissions.view_audit_log:
            async for entry in guild.audit_logs(limit=10, reverse=False, action=action,
                                                after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                if abs((entry.created_at - now).total_seconds()) >= 5:
                    # After is broken in the API, so we must check if entry is too old.
                    break
                if entry.target.id == emoji.id:
                    icon_url = get_user_avatar(entry.user)
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user), icon_url=icon_url)
                    break
        if emoji:
            await self.bot.send_log_message(guild, embed=embed)

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Called every time a guild is updated"""
        now = dt.datetime.utcnow()
        guild = after
        bot_member = guild.me

        embed = discord.Embed(color=discord.Colour(value=0x9b3ee8))
        embed.set_author(name=after.name, icon_url=after.icon_url)

        changes = True
        if before.name != after.name:
            embed.description = "Name changed from **{0.name}** to **{1.name}**".format(before, after)
        elif before.region != after.region:
            embed.description = "Region changed from **{0}** to **{1}**".format(get_region_string(before.region),
                                                                                get_region_string(after.region))
        elif before.icon_url != after.icon_url:
            embed.description = "Icon changed"
            embed.set_thumbnail(url=after.icon_url)
        elif before.owner_id != after.owner_id:
            embed.description = f"Ownership transferred to {after.owner.mention}"
        else:
            changes = False
        if changes:
            if bot_member.guild_permissions.view_audit_log:
                async for entry in guild.audit_logs(limit=1, reverse=False, action=discord.AuditLogAction.guild_update,
                                                    after=now - dt.timedelta(0, 5)):  # type: discord.AuditLogEntry
                    icon_url = get_user_avatar(entry.user)
                    embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user), icon_url=icon_url)
                    break
            await self.bot.send_log_message(after, embed=embed)


def setup(bot):
    bot.add_cog(Core(bot))
