import aiohttp
import asyncio
import discord
from discord.ext import commands
import logging
from config import get_config, set_config, remove_config, create_config_table, set_webhook_url, LOG_EVENTS
from utils import is_event_enabled, log_event, print_request_counts, ramp_up_logging, send_pending_batches, update_request_count, LOG_CHANNELS, LOG_EVENT_SETTINGS, LOG_WEBHOOKS

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True
intents.guild_messages = True
intents.guild_reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f'{bot.user} has connected to Discord!')
    try:
        create_config_table()
        
        for guild in bot.guilds:
            config = get_config(guild.id)
            if config:
                log_channel_name, log_events_str, webhook_url = config
                if log_events_str:
                    log_events = log_events_str.split(',')
                    LOG_EVENT_SETTINGS[guild.id] = set(log_events)
                    log_channel = discord.utils.get(guild.channels, name=log_channel_name)
                    if log_channel:
                        LOG_CHANNELS[guild.id] = log_channel
                        if webhook_url:
                            LOG_WEBHOOKS[guild.id] = webhook_url
                        logging.debug(f"Logging channel for server {guild.name} set to: {log_channel.name}")
                    else:
                        logging.debug(f"Logging channel '{log_channel_name}' not found in server {guild.name}.")
                else:
                    LOG_EVENT_SETTINGS[guild.id] = set(LOG_EVENTS)  # Set default logging events
                    set_config(guild.id, log_channel_name, ','.join(LOG_EVENTS))  # Update the configuration with default events
                    logging.debug(f"No logging events configured for server {guild.name}. Using default settings.")
            else:
                LOG_EVENT_SETTINGS[guild.id] = set(LOG_EVENTS)  # Set default logging events
                set_config(guild.id, None, ','.join(LOG_EVENTS))  # Set default configuration
                logging.debug(f"No configuration found for server {guild.name}. Using default settings.")
    except Exception as e:
        logging.error(f"An error occurred in the on_ready event: {str(e)}")
        await bot.close()  # Terminate the bot if there's an error
        return
    
    bot.loop.create_task(print_request_counts())
    bot.loop.create_task(send_pending_batches())
    bot.loop.create_task(ramp_up_logging())

def has_permission(channel, user, permission):
    user_permissions = channel.permissions_for(user)
    return getattr(user_permissions, permission)

@bot.event
async def on_disconnect():
    from config import close_db_connection
    close_db_connection()
    logging.warning("Bot disconnected.")

@bot.event
async def on_guild_channel_create(channel):
    if not is_event_enabled(channel.guild.id, 'guild_channel_create'):
        return

    log_channel = LOG_CHANNELS.get(channel.guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
            update_request_count()
            if entry.target.id == channel.id:
                if isinstance(channel, discord.CategoryChannel):
                    embed = discord.Embed(title=f"Category created: {channel.name}", color=discord.Color.green())
                else:
                    embed = discord.Embed(title=f"Channel created: {channel.mention}", color=discord.Color.green())
                    embed.add_field(name="Category", value=channel.category.name if channel.category else "None")
                embed.add_field(name="Created by", value=f"{entry.user.mention} ({entry.user.id})")
                embed.add_field(name="ID", value=channel.id)
                
                # Include role and permission information
                roles_with_perms = []
                for role in channel.guild.roles:
                    role_perms = channel.overwrites_for(role).pair()
                    if role_perms[0] or role_perms[1]:
                        roles_with_perms.append(f"{role.mention}: {', '.join(perm for perm, value in role_perms if value)}")
                
                if roles_with_perms:
                    embed.add_field(name="Role Permissions", value="\n".join(roles_with_perms), inline=False)
                
                asyncio.create_task(log_event(channel.guild.id, 'guild_channel_create', embed))
                break

@bot.event
async def on_guild_channel_delete(channel):
    if not is_event_enabled(channel.guild.id, 'guild_channel_delete'):
        return

    log_channel = LOG_CHANNELS.get(channel.guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            update_request_count()
            if entry.target.id == channel.id:
                if isinstance(channel, discord.CategoryChannel):
                    embed = discord.Embed(title=f"Category deleted: {channel.name}", color=discord.Color.red())
                else:
                    embed = discord.Embed(title=f"Channel deleted: {channel.name}", color=discord.Color.red())
                    embed.add_field(name="Category", value=channel.category.name if channel.category else "None")
                embed.add_field(name="Deleted by", value=f"{entry.user.mention} ({entry.user.id})")
                embed.add_field(name="ID", value=channel.id)
                asyncio.create_task(log_event(channel.guild.id, 'guild_channel_delete', embed))
                break

@bot.event
async def on_guild_channel_update(before, after):
    if not is_event_enabled(before.guild.id, 'guild_channel_update'):
        return

    log_channel = LOG_CHANNELS.get(before.guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in before.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
            update_request_count()
            if entry.target.id == before.id:
                if before.name != after.name:
                    if isinstance(after, discord.CategoryChannel):
                        embed = discord.Embed(title="Category name updated", color=discord.Color.blue())
                    else:
                        embed = discord.Embed(title="Channel name updated", color=discord.Color.blue())
                    embed.add_field(name="Channel", value=after.mention)
                    embed.add_field(name="Before", value=before.name, inline=False)
                    embed.add_field(name="After", value=after.name, inline=False)
                    asyncio.create_task(log_event(before.guild.id, 'guild_channel_update', embed))

                if before.category != after.category:
                    embed = discord.Embed(title="Channel category updated", color=discord.Color.blue())
                    embed.add_field(name="Channel", value=after.mention)
                    embed.add_field(name="Before", value=before.category.name if before.category else "None", inline=False)
                    embed.add_field(name="After", value=after.category.name if after.category else "None", inline=False)
                    asyncio.create_task(log_event(before.guild.id, 'guild_channel_update', embed))
                
                # Check for permission changes
                before_roles_with_perms = []
                for role in before.guild.roles:
                    role_perms = before.overwrites_for(role).pair()
                    if role_perms[0] or role_perms[1]:
                        before_roles_with_perms.append(f"{role.mention}: {', '.join(perm for perm, value in role_perms if value)}")
                
                after_roles_with_perms = []
                for role in after.guild.roles:
                    role_perms = after.overwrites_for(role).pair()
                    if role_perms[0] or role_perms[1]:
                        after_roles_with_perms.append(f"{role.mention}: {', '.join(perm for perm, value in role_perms if value)}")
                
                if before_roles_with_perms != after_roles_with_perms:
                    embed = discord.Embed(title="Channel permissions updated", color=discord.Color.blue())
                    embed.add_field(name="Channel", value=after.mention)
                    embed.add_field(name="Before", value="\n".join(before_roles_with_perms) or "None", inline=False)
                    embed.add_field(name="After", value="\n".join(after_roles_with_perms) or "None", inline=False)
                    asyncio.create_task(log_event(before.guild.id, 'guild_channel_update', embed))
                
                break

@bot.event
async def on_guild_emojis_update(guild, before, after):
    if not is_event_enabled(guild.id, 'guild_emojis_update'):
        return

    log_channel = LOG_CHANNELS.get(guild.id)
    if log_channel:
        if len(before) < len(after):
            new_emoji = next(emoji for emoji in after if emoji not in before)
            embed = discord.Embed(title="Emoji created", color=discord.Color.green())
            embed.add_field(name="Name", value=new_emoji.name)
            embed.add_field(name="ID", value=new_emoji.id)
            embed.set_thumbnail(url=new_emoji.url)
            asyncio.create_task(log_event(guild.id, 'guild_emojis_update', embed))
        elif len(before) > len(after):
            removed_emoji = next(emoji for emoji in before if emoji not in after)
            embed = discord.Embed(title="Emoji deleted", color=discord.Color.red())
            embed.add_field(name="Name", value=removed_emoji.name)
            embed.add_field(name="ID", value=removed_emoji.id)
            asyncio.create_task(log_event(guild.id, 'guild_emojis_update', embed))

@bot.event
async def on_guild_join(guild):
    default_log_events = ','.join(LOG_EVENTS)
    LOG_EVENT_SETTINGS[guild.id] = set(LOG_EVENTS)
    set_config(guild.id, 'log', default_log_events)
    logging.debug(f"Joined server {guild.name}. Set default configuration.")

@bot.event
async def on_guild_remove(guild):
    if guild.id in LOG_CHANNELS:
        del LOG_CHANNELS[guild.id]
        del LOG_EVENT_SETTINGS[guild.id]
        remove_config(guild.id)
        logging.debug(f"Removed logging channel entry and configuration for server {guild.name}.")

@bot.event
async def on_guild_role_create(role):
    if not is_event_enabled(role.guild.id, 'guild_role_create'):
        return

    log_channel = LOG_CHANNELS.get(role.guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
            update_request_count()
            if entry.target.id == role.id:
                embed = discord.Embed(title=f"Role created: {role.name}", color=discord.Color.green())
                embed.add_field(name="Created by", value=f"{entry.user.mention} ({entry.user.id})")
                embed.add_field(name="Role ID", value=role.id)
                asyncio.create_task(log_event(role.guild.id, 'guild_role_create', embed))
                break

@bot.event
async def on_guild_role_delete(role):
    if not is_event_enabled(role.guild.id, 'guild_role_delete'):
        return

    log_channel = LOG_CHANNELS.get(role.guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            update_request_count()
            if entry.target.id == role.id:
                embed = discord.Embed(title=f"Role deleted: {role.name}", color=discord.Color.red())
                embed.add_field(name="Deleted by", value=f"{entry.user.mention} ({entry.user.id})")
                embed.add_field(name="Role ID", value=role.id)
                asyncio.create_task(log_event(role.guild.id, 'guild_role_delete', embed))
                break

@bot.event
async def on_guild_role_update(before, after):
    if not is_event_enabled(before.guild.id, 'guild_role_update'):
        return

    log_channel = LOG_CHANNELS.get(before.guild.id)
    if log_channel:
        if before.name != after.name:
            embed = discord.Embed(title="Role name updated", color=discord.Color.blue())
            embed.add_field(name="Role", value=after.mention)
            embed.add_field(name="Before", value=before.name, inline=False)
            embed.add_field(name="After", value=after.name, inline=False)
            asyncio.create_task(log_event(before.guild.id, 'guild_role_update', embed))

        if before.permissions != after.permissions:
            embed = discord.Embed(title="Role permissions updated.", color=discord.Color.blue())
            embed.add_field(name="Role", value=after.mention)
            
            before_permissions = list(before.permissions)
            after_permissions = list(after.permissions)
            
            removed_permissions = [perm for perm, value in before_permissions if perm not in after_permissions]
            added_permissions = [perm for perm, value in after_permissions if perm not in before_permissions]
            
            if removed_permissions:
                embed.add_field(name="Removed Permissions", value=", ".join(removed_permissions), inline=False)
            if added_permissions:
                embed.add_field(name="Added Permissions", value=", ".join(added_permissions), inline=False)
            
            asyncio.create_task(log_event(before.guild.id, 'guild_role_update', embed))

        if before.color != after.color:
            embed = discord.Embed(title="Role colour updated", color=discord.Color.blue())
            embed.add_field(name="Role", value=after.mention)
            embed.add_field(name="Before", value=str(before.color), inline=False)
            embed.add_field(name="After", value=str(after.color), inline=False)
            asyncio.create_task(log_event(before.guild.id, 'guild_role_update', embed))

@bot.event
async def on_guild_update(before, after):
    if not is_event_enabled(after.id, 'guild_update'):
        return

    log_channel = LOG_CHANNELS.get(after.id)
    if log_channel:
        if before.name != after.name:
            embed = discord.Embed(title="Server name updated", color=discord.Color.blue())
            embed.add_field(name="Before", value=before.name, inline=False)
            embed.add_field(name="After", value=after.name, inline=False)
            asyncio.create_task(log_event(after.id, 'guild_update', embed))

        if before.icon != after.icon:
            embed = discord.Embed(title="Server icon updated", color=discord.Color.blue())
            embed.set_thumbnail(url=after.icon.url)
            asyncio.create_task(log_event(after.id, 'guild_update', embed))

        if before.region != after.region:
            embed = discord.Embed(title="Server region updated", color=discord.Color.blue())
            embed.add_field(name="Before", value=str(before.region), inline=False)
            embed.add_field(name="After", value=str(after.region), inline=False)
            asyncio.create_task(log_event(after.id, 'guild_update', embed))

        if before.premium_tier != after.premium_tier:
            embed = discord.Embed(title="Server boost level updated.", color=discord.Color.purple())
            embed.add_field(name="Before", value=f"Level {before.premium_tier}")
            embed.add_field(name="After", value=f"Level {after.premium_tier}")
            asyncio.create_task(log_event(after.id, 'guild_update', embed))

@bot.event
async def on_invite_create(invite):
    if not is_event_enabled(invite.guild.id, 'invite_create'):
        return

    log_channel = LOG_CHANNELS.get(invite.guild.id)
    if log_channel:
        embed = discord.Embed(title="Invite created", color=discord.Color.green())
        embed.add_field(name="Code", value=invite.code)
        embed.add_field(name="Inviter", value=f"{invite.inviter.mention} ({invite.inviter.id})")
        embed.add_field(name="Channel", value=invite.channel.mention)
        embed.add_field(name="Max Uses", value=invite.max_uses)
        embed.add_field(name="Temporary", value=invite.temporary)
        asyncio.create_task(log_event(invite.guild.id, 'invite_create', embed))

@bot.event
async def on_invite_delete(invite):
    if not is_event_enabled(invite.guild.id, 'invite_delete'):
        return

    log_channel = LOG_CHANNELS.get(invite.guild.id)
    if log_channel:
        embed = discord.Embed(title="Invite deleted", color=discord.Color.red())
        embed.add_field(name="Code", value=invite.code)
        embed.add_field(name="Channel", value=invite.channel.mention)
        asyncio.create_task(log_event(invite.guild.id, 'invite_delete', embed))

@bot.event
async def on_member_join(member):
    if not is_event_enabled(member.guild.id, 'member_join'):
        return

    log_channel = LOG_CHANNELS.get(member.guild.id)
    if log_channel:
        embed = discord.Embed(title=f"{member} joined the server", color=discord.Color.green())
        embed.set_thumbnail(url=member.avatar.url)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})")
        asyncio.create_task(log_event(member.guild.id, 'member_join', embed))

@bot.event
async def on_member_remove(member):
    if not is_event_enabled(member.guild.id, 'member_remove'):
        return

    log_channel = LOG_CHANNELS.get(member.guild.id)
    if log_channel:
        embed = discord.Embed(title=f"{member} left the server", color=discord.Color.red())
        embed.set_thumbnail(url=member.avatar.url)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})")
        asyncio.create_task(log_event(member.guild.id, 'member_remove', embed))

@bot.event
async def on_message_delete(message):
    if not is_event_enabled(message.guild.id, 'message_delete'):
        return

    log_channel = LOG_CHANNELS.get(message.guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in message.guild.audit_logs(limit=1, action=discord.AuditLogAction.message_delete):
            update_request_count()
            if entry.target.id == message.author.id and entry.extra.channel.id == message.channel.id:
                if hasattr(entry, 'bulk') and entry.bulk:
                    embed = discord.Embed(title=f"Multiple messages deleted by a moderator in {message.channel.mention}", color=discord.Color.red())
                    embed.add_field(name="Deleted by", value=f"{entry.user.mention} ({entry.user.id})")
                    asyncio.create_task(log_event(message.guild.id, 'message_delete', embed))
                else:
                    embed = discord.Embed(title=f"Message deleted by a moderator in {message.channel.mention}", color=discord.Color.red())
                    embed.set_thumbnail(url=message.author.avatar.url)
                    embed.add_field(name="Author", value=f"{message.author.mention} ({message.author.id})")
                    if hasattr(entry.extra, 'content') and entry.extra.content:
                        embed.add_field(name="Content", value=entry.extra.content, inline=False)
                    else:
                        embed.add_field(name="Content", value=message.content, inline=False)
                    embed.add_field(name="Deleted by", value=f"{entry.user.mention} ({entry.user.id})")
                    asyncio.create_task(log_event(message.guild.id, 'message_delete', embed))
                return

        embed = discord.Embed(title=f"Message deleted in {message.channel.mention}", color=discord.Color.red())
        embed.set_thumbnail(url=message.author.avatar.url)
        embed.add_field(name="Author", value=f"{message.author.mention} ({message.author.id})")
        embed.add_field(name="Content", value=message.content, inline=False)
        asyncio.create_task(log_event(message.guild.id, 'message_delete', embed))

@bot.event
async def on_message_edit(before, after):
    if not is_event_enabled(before.guild.id, 'message_edit'):
        return

    log_channel = LOG_CHANNELS.get(before.guild.id)
    if log_channel:
        embed = discord.Embed(title=f"Message edited in {before.channel.mention}", color=discord.Color.blue())
        embed.set_thumbnail(url=before.author.avatar.url)
        embed.add_field(name="Author", value=f"{before.author.mention} ({before.author.id})")
        embed.add_field(name="Before", value=before.content, inline=False)
        embed.add_field(name="After", value=after.content, inline=False)
        asyncio.create_task(log_event(before.guild.id, 'message_edit', embed))

@bot.event
async def on_member_ban(guild, user):
    if not is_event_enabled(guild.id, 'member_ban'):
        return

    log_channel = LOG_CHANNELS.get(guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            update_request_count()
            if entry.target == user:
                embed = discord.Embed(title=f"{user} was banned from the server", color=discord.Color.red())
                embed.set_thumbnail(url=user.avatar.url)
                embed.add_field(name="User", value=f"{user.mention} ({user.id})")
                embed.add_field(name="Banned by", value=f"{entry.user.mention} ({entry.user.id})")
                embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
                asyncio.create_task(log_event(guild.id, 'member_ban', embed))
                return

@bot.event
async def on_member_kick(guild, user):
    if not is_event_enabled(guild.id, 'member_kick'):
        return

    log_channel = LOG_CHANNELS.get(guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            update_request_count()
            if entry.target == user:
                embed = discord.Embed(title=f"{user} was kicked from the server", color=discord.Color.red())
                embed.set_thumbnail(url=user.avatar.url)
                embed.add_field(name="User", value=f"{user.mention} ({user.id})")
                embed.add_field(name="Kicked by", value=f"{entry.user.mention} ({entry.user.id})")
                embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
                asyncio.create_task(log_event(guild.id, 'member_kick', embed))
                return

@bot.event
async def on_member_remove_timeout(member):
    if not is_event_enabled(member.guild.id, 'member_remove_timeout'):
        return

    log_channel = LOG_CHANNELS.get(member.guild.id)
    if log_channel:
        embed = discord.Embed(title=f"{member}'s timeout was removed", color=discord.Color.green())
        embed.set_thumbnail(url=member.avatar.url)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})")
        asyncio.create_task(log_event(member.guild.id, 'member_remove_timeout', embed))

@bot.event
async def on_member_timeout(member, until):
    if not is_event_enabled(member.guild.id, 'member_timeout'):
        return

    log_channel = LOG_CHANNELS.get(member.guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
            update_request_count()
            if entry.target == member and entry.before.communication_disabled_until is None and entry.after.communication_disabled_until is not None:
                embed = discord.Embed(title=f"{member} was timed out until {until}", color=discord.Color.red())
                embed.set_thumbnail(url=member.avatar.url)
                embed.add_field(name="User", value=f"{member.mention} ({member.id})")
                embed.add_field(name="Timed out by", value=f"{entry.user.mention} ({entry.user.id})")
                embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
                asyncio.create_task(log_event(member.guild.id, 'member_remove_timeout', embed))
                return

@bot.event
async def on_member_unban(guild, user):
    if not is_event_enabled(guild.id, 'member_unban'):
        return

    log_channel = LOG_CHANNELS.get(guild.id)
    if log_channel and has_permission(log_channel, log_channel.guild.me, 'view_audit_log'):
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
            update_request_count()
            if entry.target == user:
                embed = discord.Embed(title=f"{user} was unbanned from the server", color=discord.Color.green())
                embed.set_thumbnail(url=user.avatar.url)
                embed.add_field(name="User", value=f"{user.mention} ({user.id})")
                embed.add_field(name="Unbanned by", value=f"{entry.user.mention} ({entry.user.id})")
                asyncio.create_task(log_event(guild.id, 'member_unban', embed))
                return

@bot.event
async def on_member_update(before, after):
    if not is_event_enabled(after.id, 'member_update'):
        return

    log_channel = LOG_CHANNELS.get(before.guild.id)
    if log_channel:
        if before.roles != after.roles:
            embed = discord.Embed(title=f"{after}'s roles were updated", color=discord.Color.blue())
            embed.set_thumbnail(url=after.avatar.url)
            embed.add_field(name="User", value=f"{after.mention} ({after.id})")
            embed.add_field(name="Before", value=", ".join([role.name for role in before.roles]), inline=False)
            embed.add_field(name="After", value=", ".join([role.name for role in after.roles]), inline=False)
            asyncio.create_task(log_event(before.guild.id, 'member_update', embed))

        if before.nick != after.nick:
            embed = discord.Embed(title=f"{before}'s nickname was updated", color=discord.Color.blue())
            embed.set_thumbnail(url=before.avatar.url)
            embed.add_field(name="User", value=f"{before.mention} ({before.id})")
            embed.add_field(name="Before", value=before.nick, inline=False)
            embed.add_field(name="After", value=after.nick, inline=False)
            asyncio.create_task(log_event(before.guild.id, 'member_update', embed))

        if before.premium_since != after.premium_since:
            if after.premium_since is not None:
                embed = discord.Embed(title=f"{before} boosted the server", color=discord.Color.purple())
                embed.set_thumbnail(url=before.avatar.url)
                embed.add_field(name="User", value=f"{before.mention} ({before.id})")
                asyncio.create_task(log_event(before.guild.id, 'member_update', embed))
            else:
                embed = discord.Embed(title=f"{before} unboosted the server", color=discord.Color.purple())
                embed.set_thumbnail(url=before.avatar.url)
                embed.add_field(name="User", value=f"{before.mention} ({before.id})")
                asyncio.create_task(log_event(before.guild.id, 'member_update', embed))

@bot.event
async def on_reaction_add(reaction, user):
    if not is_event_enabled(reaction.message.guild.id, 'reaction_add'):
      return

    log_channel = LOG_CHANNELS.get(reaction.message.guild.id)
    if log_channel:
        embed = discord.Embed(title=f"{user} reacted with {reaction.emoji} to a message", color=discord.Color.blue())
        embed.set_thumbnail(url=user.avatar.url)
        embed.add_field(name="User", value=f"{user.mention} ({user.id})")
        embed.add_field(name="Message", value=f"[Jump to Message]({reaction.message.jump_url})", inline=False)
        asyncio.create_task(log_event(reaction.message.guild.id, 'reaction_add', embed))

@bot.event
async def on_reaction_remove(reaction, user):
    if not is_event_enabled(reaction.message.guild.id, 'reaction_remove'):
        return

    log_channel = LOG_CHANNELS.get(reaction.message.guild.id)
    if log_channel:
        embed = discord.Embed(title=f"{user} removed their {reaction.emoji} reaction from a message", color=discord.Color.blue())
        embed.set_thumbnail(url=user.avatar.url)
        embed.add_field(name="User", value=f"{user.mention} ({user.id})")
        embed.add_field(name="Message", value=f"[Jump to Message]({reaction.message.jump_url})", inline=False)
        asyncio.create_task(log_event(reaction.message.guild.id, 'reaction_remove', embed))

@bot.event
async def on_voice_state_update(member, before, after):
    if not is_event_enabled(member.guild.id, 'voice_state_update'):
        return

    log_channel = LOG_CHANNELS.get(member.guild.id)
    if log_channel:
        # Check if the member joined or left a voice channel
        if before.channel is None and after.channel is not None:
            embed = discord.Embed(title=f"{member} joined voice channel {after.channel.mention}", color=discord.Color.green())
            embed.set_thumbnail(url=member.avatar.url)
            embed.add_field(name="User", value=f"{member.mention} ({member.id})")
            embed.add_field(name="Channel", value=f"{after.channel.mention} ({after.channel.id})")
            asyncio.create_task(log_event(member.guild.id, 'voice_state_update', embed))
        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(title=f"{member} left voice channel {before.channel.mention}", color=discord.Color.red())
            embed.set_thumbnail(url=member.avatar.url)
            embed.add_field(name="User", value=f"{member.mention} ({member.id})")
            embed.add_field(name="Channel", value=f"{before.channel.mention} ({before.channel.id})")
            asyncio.create_task(log_event(member.guild.id, 'voice_state_update', embed))
        # Check if the member moved between voice channels
        elif before.channel != after.channel:
            embed = discord.Embed(title=f"{member} moved from {before.channel.mention} to {after.channel.mention}", color=discord.Color.blue())
            embed.set_thumbnail(url=member.avatar.url)
            embed.add_field(name="User", value=f"{member.mention} ({member.id})")
            embed.add_field(name="Before", value=f"{before.channel.mention} ({before.channel.id})")
            embed.add_field(name="After", value=f"{after.channel.mention} ({after.channel.id})")
            asyncio.create_task(log_event(member.guild.id, 'voice_state_update', embed))

@bot.event
async def on_webhooks_update(channel):
    if not is_event_enabled(channel.guild.id, 'webhooks_update'):
        return

    log_channel = LOG_CHANNELS.get(channel.guild.id)
    if log_channel:
        webhook_url = LOG_WEBHOOKS.get(channel.guild.id)
        if webhook_url:
            try:
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(webhook_url, session=session)
                    await webhook.fetch()
            except discord.NotFound:
                # If the webhook is invalid, delete it from the dictionary
                del LOG_WEBHOOKS[channel.guild.id]
                webhook = None

            if webhook is not None:
                # If a valid webhook exists, log the event
                embed = discord.Embed(title="Webhooks updated", color=discord.Color.blue())
                embed.add_field(name="Channel", value=channel.mention)
                asyncio.create_task(log_event(channel.guild.id, 'webhooks_update', embed))

@bot.command()
async def loghelp(ctx):
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())
    embed.add_field(name="!setlogconfig <log_channel_name> <log_events>", value="Set the logging channel and events to log (comma-separated).", inline=False)
    embed.add_field(name="!getlogconfig", value="Get the current logging configuration.", inline=False)
    embed.add_field(name="Possible Log Events", value=", ".join(LOG_EVENTS), inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_guild=True)
async def getlogconfig(ctx):
    config = get_config(ctx.guild.id)
    if config:
        log_channel_name, log_events, webhook_url = config
        log_channel = discord.utils.get(ctx.guild.text_channels, name=log_channel_name)
        if log_channel:
            log_channel_mention = log_channel.mention
        else:
            log_channel_mention = log_channel_name
        log_events_formatted = ', '.join(log_events.split(','))
        await ctx.send(f"Current configuration:\nLogging Channel: {log_channel_mention}\nLogging Events: {log_events_formatted}")
    else:
        await ctx.send("No configuration found for this server.")

@getlogconfig.error
async def getlogconfig_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have the required permissions to use this command.")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def setlogconfig(ctx, log_channel: discord.TextChannel = None, *, log_events: str = None):
    # Check permission
    if log_channel and not has_permission(log_channel, log_channel.guild.me, 'manage_webhooks'):
        await ctx.send(f"Unable to manage webhooks in {log_channel.mention}, please check that I have sufficient permission.")
        return

    # If only the channel is provided, update the channel
    if log_channel and not log_events:
        # Check if a Logging Webhook exists in the old channel
        old_log_channel = LOG_CHANNELS.get(ctx.guild.id)
        if old_log_channel:
            webhook = None
            for hook in await old_log_channel.webhooks():
                if hook.name == "LoggerHead":
                    webhook = hook
                    break
            if webhook:
                await webhook.delete()

        # Create a new Logging Webhook in the new channel
        webhook = None
        for hook in await log_channel.webhooks():
            if hook.name == "LoggerHead":
                webhook = hook
                break
        if webhook is None:
            async with aiohttp.ClientSession() as session:
                async with session.get(bot.user.avatar.url) as response:
                    avatar_bytes = await response.read()
            webhook = await log_channel.create_webhook(name="LoggerHead", avatar=avatar_bytes)

        set_config(ctx.guild.id, log_channel.name, None)  # Update only the channel name
        LOG_CHANNELS[ctx.guild.id] = log_channel
        LOG_WEBHOOKS[ctx.guild.id] = webhook.url
        set_webhook_url(ctx.guild.id, webhook.url)  # Update the webhook URL in the database
        await ctx.send(f"Logging channel updated to: {log_channel.mention}")
        return

    # If only the log events are provided, update the log events
    if log_events and not log_channel:
        # Check if the user wants to disable all logging events
        if log_events.lower() in ["none", ""]:
            log_events = ""  # Set log_events to an empty string to indicate no events should be logged
        else:
            # Split the log_events string by comma and any surrounding whitespace
            log_events_list = [event.strip() for event in log_events.split(',')]
            invalid_events = [event for event in log_events_list if event not in LOG_EVENTS]
            if invalid_events:
                await ctx.send(f"Invalid log events: {', '.join(invalid_events)}. Please provide valid events.")
                return
            log_events = ','.join(log_events_list)  # Rejoin the valid events

        # Update only the log events
        LOG_EVENT_SETTINGS[ctx.guild.id] = set(log_events_list)
        set_config(ctx.guild.id, None, log_events)
        await ctx.send(f"Logging events updated.")
        return

    # If both channel and log events are provided, update both
    if log_channel and log_events:
        # Check if the user wants to disable all logging events
        if log_events.lower() in ["none", ""]:
            log_events = ""  # Set log_events to an empty string to indicate no events should be logged
        else:
            # Split the log_events string by comma and any surrounding whitespace
            log_events_list = [event.strip() for event in log_events.split(',')]
            invalid_events = [event for event in log_events_list if event not in LOG_EVENTS]
            if invalid_events:
                await ctx.send(f"Invalid log events: {', '.join(invalid_events)}. Please provide valid events.")
                return
            log_events = ','.join(log_events_list)  # Rejoin the valid events
    
        # Check if a Logging Webhook exists in the old channel
        old_log_channel = LOG_CHANNELS.get(ctx.guild.id)
        if old_log_channel:
            webhook = None
            for hook in await old_log_channel.webhooks():
                if hook.name == "LoggerHead":
                    webhook = hook
                    break
            if webhook:
                await webhook.delete()
    
        # Create a new Logging Webhook in the new channel
        webhook = None
        for hook in await log_channel.webhooks():
            if hook.name == "LoggerHead":
                webhook = hook
                break
        if webhook is None:
            avatar_url = bot.user.avatar.url
            async with aiohttp.ClientSession() as session:
                async with session.get(bot.user.avatar.url) as response:
                    avatar_bytes = await response.read()
            webhook = await log_channel.create_webhook(name="LoggerHead", avatar=avatar_bytes)
    
        LOG_EVENT_SETTINGS[ctx.guild.id] = set(log_events_list)
        set_config(ctx.guild.id, log_channel.name, log_events)
        LOG_CHANNELS[ctx.guild.id] = log_channel
        LOG_WEBHOOKS[ctx.guild.id] = webhook.url
        set_webhook_url(ctx.guild.id, webhook.url)  # Update the webhook URL in the database
        await ctx.send(f"Configuration updated.")

@setlogconfig.error
async def setlogconfig_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have the required permissions to use this command.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error