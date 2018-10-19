import datetime as dt
from typing import List, Any, Dict, Optional

import discord

from .utils import get_user_avatar, log, get_region_string
from .utils.tibia import get_voc_abb_and_emoji, Character
from nabbot import NabBot

COLOUR_CHAR_REGISTERED = discord.Colour.dark_teal()
COLOUR_CHAR_UNREGISTERED = discord.Colour.dark_teal()
COLOUR_CHAR_RENAME = discord.Colour.blurple()
COLOUR_CHAR_TRANSFERRED = discord.Colour.greyple()
COLOUR_MEMBER_JOINED = discord.Colour.green()
COLOUR_MEMBER_JOINED_BOT = discord.Colour.dark_green()
COLOUR_MEMBER_UPDATE = discord.Colour.blue()
COLOUR_MEMBER_KICK = discord.Colour.red()
COLOUR_MEMBER_REMOVE = discord.Colour(0xffff00)  # yellow
COLOUR_MEMBER_BAN = discord.Colour.dark_red()
COLOUR_MEMBER_UNBAN = discord.Colour.orange()
COLOUR_EMOJI_UPDATE = discord.Colour.dark_orange()
COLOUR_GUILD_UPDATE = discord.Colour.purple()


class ServerLog:
    def __init__(self, bot: NabBot):
        self.bot = bot

    async def on_characters_registered(self, user: discord.User, added: List[Character], updated: List[Dict[str, Any]],
                                       author: discord.User=None):
        """Called when a user registers new characters

        Announces the new characters on the server log."""
        user_guilds = self.bot.get_user_guilds(user.id)
        embed = discord.Embed(colour=COLOUR_CHAR_REGISTERED)
        embed.set_author(name=f"{user.name}#{user.discriminator}", icon_url=get_user_avatar(user))

        for char in added:
            await self.add_character_history(char.id, "owner", "0", str(char.owner))
        for char in updated:
            await self.add_character_history(char["id"], "owner", str(char["prevowner"]), str(user.id))

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
                tibia_guild = char.guild or "No guild"
                voc = get_voc_abb_and_emoji(char.vocation)
                description += f"\n‣ {char.name} - Level {char.level} {voc} - **{tibia_guild}**"
            for char in _updated:
                voc = get_voc_abb_and_emoji(char["vocation"])
                tibia_guild = char["guild"] or "No guild"
                description += f"\n‣ {char['name']} - Level {char['level']} {voc} - **{tibia_guild}** (Reassigned)"
            embed.description = description
            await self.bot.send_log_message(guild, embed=embed)

    async def on_character_unregistered(self, user: discord.user, char: Dict[str, Any], author: discord.User=None):
        user_guilds = self.bot.get_user_guilds(user.id)
        embed = discord.Embed(colour=COLOUR_CHAR_UNREGISTERED)
        embed.set_author(name=f"{user.name}#{user.discriminator}", icon_url=get_user_avatar(user))
        voc = get_voc_abb_and_emoji(char["vocation"])
        tibia_guild = char["guild"] if char["guild"] else "No guild"
        await self.add_character_history(char["id"], "owner", str(user.id), None)
        if author is not None:
            embed.set_footer(text=f"{author.name}#{author.discriminator}", icon_url=get_user_avatar(author))
        for guild in user_guilds:
            world = self.bot.tracked_worlds.get(guild.id)
            if char["world"] != world:
                continue
            embed.description = f"{user.mention} unregistered:" \
                                f"\n‣ {char['name']} - Level {char['level']} {voc} - **{tibia_guild}**"
            await self.bot.send_log_message(guild, embed=embed)

    async def on_character_rename(self, char: Character, old_name: str):
        """Called when a character is renamed."""
        user_id = char.owner
        new_name = char.name
        user_guilds = self.bot.get_user_guilds(user_id)
        await self.add_character_history(char.id, "name", old_name, char.name)
        for guild in user_guilds:
            if self.bot.tracked_worlds.get(guild.id) != char.world:
                continue
            member = guild.get_member(user_id)
            if member is None:
                continue

            embed = discord.Embed(colour=COLOUR_CHAR_RENAME,
                                  description=f"A character of {member.mention} changed name.\n"
                                              f"‣ **{old_name}** -> **{new_name}**")
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=get_user_avatar(member))
            await self.bot.send_log_message(guild, embed=embed)

    async def on_character_transferred(self, char: Character, old_world: str):
        user_id = char.owner
        user_guilds = self.bot.get_user_guilds(user_id)
        voc = get_voc_abb_and_emoji(char.vocation)
        await self.add_character_history(char.id, "name", old_world, char.world)
        for guild in user_guilds:
            tracked_world = self.bot.tracked_worlds.get(guild.id)
            if not(char.world == tracked_world or old_world == tracked_world):
                continue
            member = guild.get_member(user_id)
            if member is None:
                continue
            embed = discord.Embed(colour=COLOUR_CHAR_TRANSFERRED,
                                  description=f"A character of {member.mention} transferred:\n"
                                              f"‣ **{char.name}**  - Level {char.level} {voc} - "
                                              f"{old_world} -> {char.world}")
            embed.set_author(name=f"{member.name}#{member.discriminator}", icon_url=get_user_avatar(member))
            await self.bot.send_log_message(guild, embed=embed)

    async def on_character_guild_change(self, char: Character, old_guild: str):
        await self.add_character_history(char.id, "guild", old_guild, char.guild_name)

    async def on_guild_emojis_update(self, guild: discord.Guild, before: List[discord.Emoji],
                                     after: List[discord.Emoji]):
        """Called every time an emoji is created, deleted or updated."""
        embed = discord.Embed(colour=COLOUR_EMOJI_UPDATE)
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
        if action is not None:
            entry = await self.get_audit_entry(guild, action, emoji)
            if entry:
                embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                                 icon_url=get_user_avatar(entry.user))
        if emoji:
            await self.bot.send_log_message(guild, embed=embed)

    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Called every time a guild is updated"""
        embed = discord.Embed(colour=COLOUR_GUILD_UPDATE)
        embed.set_author(name=after.name, icon_url=after.icon_url)

        changes = True
        if before.name != after.name:
            embed.description = f"Name changed from **{before.name}** to **{after.name}**"
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
            entry = await self.get_audit_entry(after, discord.AuditLogAction.guild_update)
            if entry:
                icon_url = get_user_avatar(entry.user)
                embed.set_footer(text=f"{entry.user.name}#{entry.user.discriminator}", icon_url=icon_url)
            await self.bot.send_log_message(after, embed=embed)

    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is banned from a guild."""
        embed = discord.Embed(description="Banned", colour=COLOUR_MEMBER_BAN)
        embed.set_author(name="{0.name}#{0.discriminator}".format(user), icon_url=get_user_avatar(user))

        # If bot can see audit log, we can get more details of the ban
        entry = await self.get_audit_entry(guild, discord.AuditLogAction.ban, user)
        if entry:
            embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                             icon_url=get_user_avatar(entry.user))
            if entry.reason:
                embed.description += f"\n**Reason:** {entry.reason}"
        await self.bot.send_log_message(guild, embed=embed)

    async def on_member_join(self, member: discord.Member):
        """ Called when a member joins a guild (server) the bot is in."""
        log.info(f"{member.display_name} (ID: {member.id}) joined {member.guild.name}")

        embed = discord.Embed(description=f"{member.mention} joined.", colour=COLOUR_MEMBER_JOINED)
        embed.set_author(name=f"{member.name}#{member.discriminator} (ID: {member.id})",
                         icon_url=get_user_avatar(member))
        if member.bot:
            embed.colour = COLOUR_MEMBER_JOINED_BOT
            embed.description = f"Bot {member.mention} added."
            return await self.bot.send_log_message(member.guild, embed=embed)

        world = self.bot.tracked_worlds.get(member.guild.id)
        # If server is not tracking worlds, we don't check the database
        if world is None:
            return await self.bot.send_log_message(member.guild, embed=embed)

        # Check if user already has characters registered and announce them on log_channel
        # This could be because he rejoined the server or is in another server tracking the same worlds
        rows = await self.bot.pool.fetch("""SELECT name, vocation, abs(level) as level, guild FROM "character" 
                                            WHERE user_id = $1 AND world = $2 ORDER BY level DESC""", member.id, world)
        if rows:
            self.bot.dispatch("character_change", member.id)
            characters = ""
            for c in rows:
                voc = get_voc_abb_and_emoji(c["vocation"])
                guild = c["guild"] or "No guild"
                characters += f"\n\u2023 {c['name']} - Level {c['level']} {voc} - **{guild}**"
            embed.add_field(name="Registered characters", value=characters)
        await self.bot.send_log_message(member.guild, embed=embed)

    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves or is kicked from a guild."""
        bot_member: discord.Member = member.guild.me
        embed = discord.Embed(description="Left the server or was kicked", colour=COLOUR_MEMBER_REMOVE)
        embed.set_author(name=f"{member.name}#{member.discriminator} (ID: {member.id})",
                         icon_url=get_user_avatar(member))

        tracked_world = self.bot.tracked_worlds.get(member.guild.id)
        rows = await self.bot.pool.fetch("""SELECT name, vocation, abs(level) as level, guild FROM "character"
                                            WHERE user_id = $1 AND world = $2""", member.id, tracked_world)
        registered_chars = "\nRegistered characters:" if rows else ""
        for char in rows:
            voc = get_voc_abb_and_emoji(char["vocation"])
            tibia_guild = dict(char).get("guild", "No guild")
            registered_chars += f"\n‣ {char['name']} - Level {char['level']} {voc} - **{tibia_guild}** (Reassigned)"

        # If bot can see audit log, he can see if it was a kick or member left on it's own
        if bot_member.guild_permissions.view_audit_log:
            entry = await self.get_audit_entry(member.guild, discord.AuditLogAction.kick, member)
            if entry:
                embed.description = "Kicked"
                embed.set_footer(text=f"{entry.user.name}#{entry.user.discriminator}",
                                 icon_url=get_user_avatar(entry.user))
                embed.colour = COLOUR_MEMBER_KICK
                if entry.reason:
                    embed.description += f"\n**Reason:** {entry.reason}"
                embed.description += registered_chars
                await self.bot.send_log_message(member.guild, embed=embed)
                return
            embed.description = "Left the server"
            await self.bot.send_log_message(member.guild, embed=embed)
            return
        # Otherwise, we are not certain
        await self.bot.send_log_message(member.guild, embed=embed)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called every time a member is updated"""
        embed = discord.Embed(description=f"{after.mention}: ", colour=COLOUR_MEMBER_UPDATE)
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
            entry = await self.get_audit_entry(after.guild, discord.AuditLogAction.member_update, after)
            if entry:
                if entry.user.id != after.id:
                    icon_url = get_user_avatar(entry.user)
                    embed.set_footer(text=f"{entry.user.name}#{entry.user.discriminator}", icon_url=icon_url)
        else:
            changes = False
        if changes:
            await self.bot.send_log_message(after.guild, embed=embed)

    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Called when a member is unbanned from a guild"""
        embed = discord.Embed(description="Unbanned", colour=COLOUR_MEMBER_UNBAN)
        embed.set_author(name="{0.name}#{0.discriminator} (ID {0.id})".format(user), icon_url=get_user_avatar(user))

        entry = await self.get_audit_entry(guild, discord.AuditLogAction.unban, user)
        if entry:
            embed.set_footer(text="{0.name}#{0.discriminator}".format(entry.user),
                             icon_url=get_user_avatar(entry.user))
        await self.bot.send_log_message(guild, embed=embed)

    @staticmethod
    async def get_audit_entry(guild: discord.Guild, action: discord.AuditLogAction,
                              target: Any=None) -> Optional[discord.AuditLogEntry]:
        """Gets an audit log entry of the specified action type."""
        if not guild.me.guild_permissions.view_audit_log:
            return
        now = dt.datetime.utcnow()
        after = now - dt.timedelta(0, 5)
        async for entry in guild.audit_logs(limit=10, reverse=False, action=action, after=after):
            if abs((entry.created_at - now)) >= dt.timedelta(seconds=5):
                break
            if target is not None and entry.target.id == target.id:
                return entry

    async def add_character_history(self, char_id: int, change_type: str, before, after):
        await self.bot.pool.execute("""INSERT INTO character_history(character_id, change_type, before, after)
                                       values($1, $2, $3, $4)""", char_id, change_type, before, after)


def setup(bot):
    bot.add_cog(ServerLog(bot))
