from typing import List, Any, Dict

import discord
import datetime as dt

from cogs.utils import get_user_avatar, join_list, log, get_region_string
from cogs.utils.database import get_server_property
from cogs.utils.tibia import get_voc_abb_and_emoji, Character
from nabbot import NabBot


class ServerLog:
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def on_characters_registered(self, user: discord.User, added: List[Character], updated: List[Dict[str, Any]],
                                       author: discord.User=None):
        user_guilds = self.bot.get_user_guilds(user.id)
        embed = discord.Embed()
        embed.set_author(name=f"{user.name}#{user.discriminator}", icon_url=get_user_avatar(user))
        embed.colour = discord.Colour.dark_teal()
        if author is not None:
            embed.set_footer(text=f"{author.name}#{author.discriminator}", icon_url=get_user_avatar(author))
        for guild in user_guilds:
            world = self.bot.tracked_worlds.get(guild.id)
            _added = [c for c in added if c.world == world]
            _updated = [c for c in updated if c["world"] == world]
            if not _added and not _updated:
                continue
            description = f"{user.mention} registered the following characters:"
            for char in _added:
                tibia_guild = char.guild if char.guild else "No guild"
                voc = get_voc_abb_and_emoji(char.vocation)
                description += f"\n‣ {char.name} - Level {char.level} {voc} - **{tibia_guild}**"
            for char in _updated:
                voc = get_voc_abb_and_emoji(char["vocation"])
                tibia_guild = char["guild"] if char["guild"] else "No guild"
                description += f"\n‣ {char['name']} - Level {char['level']} {voc} - **{tibia_guild}** (Reassigned)"
            embed.description = description
            await self.bot.send_log_message(guild, embed=embed)

    async def on_character_unregistered(self, user: discord.user, char: Dict[str, Any], author: discord.User=None):
        user_guilds = self.bot.get_user_guilds(user.id)
        embed = discord.Embed()
        embed.set_author(name=f"{user.name}#{user.discriminator}", icon_url=get_user_avatar(user))
        embed.colour = discord.Colour.dark_teal()
        if author is not None:
            embed.set_footer(text=f"{author.name}#{author.discriminator}", icon_url=get_user_avatar(author))
        for guild in user_guilds:
            world = self.bot.tracked_worlds.get(guild.id)
            if char["world"] != world:
                continue
            voc = get_voc_abb_and_emoji(char["vocation"])
            tibia_guild = char["guild"] if char["guild"] else "No guild"
            embed.description = f"{user.mention} unregistered:" \
                                f"\n‣ {char['name']} - Level {char['level']} {voc} - **{tibia_guild}**"
            await self.bot.send_log_message(guild, embed=embed)

    async def on_character_rename(self, old_name, char: Character):
        """Called when a character is renamed."""
        user_id = char.owner
        new_name = char.name
        user_guilds = self.bot.get_user_guilds(user_id)

        for guild in user_guilds:
            member = guild.get_member(user_id)
            if member is None:
                continue
            if self.bot.tracked_worlds.get(guild.id) != char.world:
                continue
            embed = discord.Embed(color=discord.Color.blurple(),
                                  description=f"A character of {member.mention} changed name.\n"
                                              f"‣ **{old_name}** -> **{new_name}**")
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=get_user_avatar(member))
            await self.bot.send_log_message(guild, embed=embed)

    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves or is kicked from a guild."""
        self.bot.members[member.id].remove(member.guild.id)
        now = dt.datetime.utcnow()
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

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called every time a member is updated"""
        now = dt.datetime.utcnow()
        guild = after.guild
        bot_member = guild.me

        embed = discord.Embed(description=f"{after.mention}: ", color=discord.Colour.blue())
        embed.set_author(name=f"{after.name}#{after.discriminator} (ID: {after.id})", icon_url=get_user_avatar(after))
        changes = True
        if f"{before.name}#{before.discriminator}" != f"{after.name}#{after.discriminator}":
            embed.description += "Name changed from **{0.name}#{0.discriminator}** to **{1.name}#{1.discriminator}**." \
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

    async def on_member_join(self, member: discord.Member):
        """ Called when a member joins a guild (server) the bot is in."""
        log.info("{0.display_name} (ID: {0.id}) joined {0.guild.name}".format(member))

        embed = discord.Embed(description="{0.mention} joined.".format(member), color=discord.Color.green())
        embed.set_author(name="{0.name}#{0.discriminator} (ID: {0.id})".format(member),
                         icon_url=get_user_avatar(member))

        previously_registered = ""
        # If server is not tracking worlds, we don't check the database
        if member.guild.id in self.bot.config.lite_servers or self.bot.tracked_worlds.get(member.guild.id) is None:
            await self.bot.send_log_message(member.guild, embed=embed)
        else:
            # Check if user already has characters registered and announce them on log_channel
            # This could be because he rejoined the server or is in another server tracking the same worlds
            world = self.bot.tracked_worlds.get(member.guild.id)
            previously_registered = ""
            if world is not None:
                results = await self.bot.pool.fetch("""SELECT name, vocation, abs(level) as level, guild
                                                       FROM "character" WHERE user_id = $1 AND world = $2""",
                                                    member.id, world)
                if len(results) > 0:
                    previously_registered = "\n\nYou already have these characters in {0} registered to you: *{1}*" \
                        .format(world, join_list([r["name"] for r in results], ", ", " and "))
                    characters = ["\u2023 {name} - Level {level} {voc} - **{guild}**"
                                      .format(**c, voc=get_voc_abb_and_emoji(c["vocation"])) for c in results]
                    embed.add_field(name="Registered characters", value="\n".join(characters))
            self.bot.dispatch("character_change", member.id)
            await self.bot.send_log_message(member.guild, embed=embed)

        welcome_message = await get_server_property(self.bot.pool, member.guild.id, "welcome")
        welcome_channel_id = await get_server_property(self.bot.pool, member.guild.id, "welcome_channel")
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



def setup(bot):
    bot.add_cog(ServerLog(bot))
