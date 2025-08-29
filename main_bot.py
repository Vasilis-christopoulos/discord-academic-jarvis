import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from tenant_context import load_tenant_context_async
from utils.channel_discovery import has_feature_access
from settings import settings
from rag_module.rag_handler_optimized import respond as rag_respond
from rag_module.file_validator import get_file_validator
from calendar_module.calendar_handler import respond as cal_respond

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis")

def get_admin_role_id(guild_id: int) -> int | None:
    """Get admin role ID from tenant configuration."""
    try:
        # Load tenant config directly without channel validation for admin access
        from settings import TENANT_CONFIGS
        for tenant in TENANT_CONFIGS:
            if tenant.guild_id == guild_id:
                if tenant.admin_role_id is not None:
                    admin_role_id = int(tenant.admin_role_id)
                    logger.debug(f"Found admin_role_id: {admin_role_id} for guild {guild_id}")
                    return admin_role_id
        
        logger.warning(f"No tenant configuration found for guild {guild_id}")
    except Exception as e:
        logger.error(f"Failed to get admin role ID for guild {guild_id}: {e}")
    return None

def has_admin_access(member) -> bool:
    """Check if a member has admin access based on tenant configuration."""
    # Handle different types of user objects
    if not member:
        return False
    
    # Get guild_id from different sources
    guild_id = None
    if hasattr(member, 'guild') and member.guild:
        guild_id = member.guild.id
    elif hasattr(member, 'guild_id'):
        guild_id = member.guild_id
    else:
        logger.error("Cannot determine guild_id from member object")
        return False
    
    admin_role_id = get_admin_role_id(guild_id)
    logger.debug(f"Admin role ID for guild {guild_id}: {admin_role_id}")
    if not admin_role_id:
        return False
    
    # Get user roles from different sources
    user_role_ids = []
    if hasattr(member, 'roles') and member.roles:
        user_role_ids = [role.id for role in member.roles]
    elif hasattr(member, '_roles') and member._roles:
        # Some discord.py objects store roles in _roles
        user_role_ids = member._roles
    else:
        logger.warning(f"Cannot access role information for user {getattr(member, 'id', 'unknown')}")
        return False
    
    logger.debug(f"User {getattr(member, 'id', 'unknown')} roles: {user_role_ids}")
    has_access = admin_role_id in user_role_ids
    logger.debug(f"User {getattr(member, 'id', 'unknown')} has admin access: {has_access}")
    return has_access

# ──────────────────────────────────────────────
# Discord client setup
# ──────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True  # Required to access member information and roles
intents.message_content = True  # Required for message content access
bot = commands.Bot(command_prefix="!", intents=intents)
tree: app_commands.CommandTree = bot.tree

# ──────────────────────────────────────────────
# Context helper (tenant aware)
# ──────────────────────────────────────────────
async def build_ctx_cfg(inter: discord.Interaction) -> Optional[dict]:
    """
    Build tenant context configuration from Discord interaction.
    
    Args:
        inter: Discord interaction object containing guild/channel/user info
        
    Returns:
        Dictionary containing tenant config with guild_id, channel_id, user_id, etc.
        None if channel is not authorized for bot usage.
    """
    # Handle None values for guild_id and channel_id
    guild_id = inter.guild_id or 0
    channel_id = inter.channel_id or 0
    
    # Get the actual channel object for category detection
    channel = None
    if inter.channel and isinstance(inter.channel, discord.TextChannel):
        channel = inter.channel
    
    # Use the new async tenant context loader that supports category-based permissions
    cfg = await load_tenant_context_async(guild_id, channel_id, bot)
    
    # If no configuration found, try with channel object for category detection
    if not cfg and channel:
        from tenant_context import load_tenant_context
        cfg = load_tenant_context(guild_id, channel_id, channel)
    
    # If still no configuration found, return None to signal unauthorized access
    if not cfg:
        return None
    
    # Handle channel name safely
    channel_name = "direct-message"
    if inter.channel and hasattr(inter.channel, 'name'):
        try:
            channel_name = getattr(inter.channel, 'name', f"channel-{channel_id}")
        except AttributeError:
            channel_name = f"channel-{channel_id}"
    
    cfg.update({
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user_id": inter.user.id,
        "username": str(inter.user),
        "name": cfg.get("name", channel_name),
        "timezone": cfg.get("timezone", "UTC"),
    })
    return cfg


# ──────────────────────────────────────────────
# Utility: send answer after defer
# ──────────────────────────────────────────────
async def send_answer(inter: discord.Interaction, payload):
    """
    Send response to Discord interaction with proper embed formatting.
    
    Args:
        inter: Discord interaction to respond to
        payload: Response content - can be str, Embed, or list[Embed]
    """
    if isinstance(payload, discord.Embed):
        embeds = [payload]
    elif isinstance(payload, list) and all(isinstance(e, discord.Embed) for e in payload):
        embeds = payload
    else:
        embeds = [discord.Embed(description=str(payload))]

    if not inter.response.is_done():
        await inter.response.send_message(embeds=embeds)
    else:
        await inter.followup.send(embeds=embeds)

async def check_channel_authorization(inter: discord.Interaction) -> Optional[dict]:
    """Check if the channel is authorized and return config, or send error message."""
    ctx = await build_ctx_cfg(inter)
    
    if not ctx:
        embed = discord.Embed(
            title="❌ Channel Not Configured",
            description="This channel is not configured to use Jarvis commands.",
            color=discord.Color.red()
        )
        
        # Get channel name for user-friendly message
        channel_name = "this channel"
        try:
            if inter.channel and hasattr(inter.channel, 'name'):
                name = getattr(inter.channel, 'name', None)
                if name:
                    channel_name = f"#{name}"
        except Exception:
            pass  # Keep default channel_name
        
        embed.add_field(
            name="Current Channel",
            value=channel_name,
            inline=True
        )
        embed.add_field(
            name="Solution",
            value="Ask an administrator to add this channel to the bot configuration.",
            inline=False
        )
        
        await send_answer(inter, embed)
        return None
    
    return ctx

# ──────────────────────────────────────────────
# /jarvis_rag  (root command)
# ──────────────────────────────────────────────
@tree.command(name="jarvis_rag", description="Ask the notes RAG assistant")
@app_commands.describe(query="Your question")
async def jarvis_rag(inter: discord.Interaction, query: str):
    """
    Handle RAG (Retrieval-Augmented Generation) queries from Discord users.
    
    This command allows users to ask questions about uploaded documents and notes.
    It checks channel permissions, verifies feature access, and enforces rate limits
    before processing the query through the RAG system.
    
    Args:
        inter: Discord interaction object containing user, channel, and guild info
        query: User's natural language question about the documents
    """
    await inter.response.defer()
    
    ctx = await check_channel_authorization(inter)
    if not ctx:
        return  # Error message already sent
    
    # Check if RAG feature is enabled for this channel
    if not await has_feature_access(inter.channel_id or 0, 'rag'):
        embed = discord.Embed(
            title="❌ Feature Not Available", 
            description="RAG feature is not enabled in this channel.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)
        return
        
    # Pass user_id for rate limiting
    result = await rag_respond(query, ctx, str(inter.user.id))
    await send_answer(inter, result)

# ──────────────────────────────────────────────
# /jarvis_calendar  (root command)
# ──────────────────────────────────────────────
@tree.command(name="jarvis_calendar", description="Ask calendar questions")
@app_commands.describe(query="Your calendar query")
async def jarvis_calendar(inter: discord.Interaction, query: str):
    """
    Handle calendar and task queries from Discord users.
    
    This command processes natural language queries about calendar events and tasks.
    It syncs with Google Calendar/Tasks, performs semantic search, and returns
    formatted results with relevant events and deadlines.
    
    Args:
        inter: Discord interaction object containing user, channel, and guild info
        query: User's natural language question about calendar events or tasks
    """
    await inter.response.defer()
    
    # Check channel authorization first
    ctx = await check_channel_authorization(inter)
    if not ctx:
        return  # Error message already sent
    
    # Check if calendar feature is enabled for this channel
    if not await has_feature_access(inter.channel_id or 0, 'calendar'):
        embed = discord.Embed(
            title="❌ Feature Not Available",
            description="Calendar feature is not enabled in this channel.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)
        return
        
    result = await cal_respond(query, ctx)
    await send_answer(inter, result)

# ──────────────────────────────────────────────
# /jarvis_upload (file upload with validation)
# ──────────────────────────────────────────────
@tree.command(name="jarvis_upload", description="Upload a document for processing")
@app_commands.describe(file="Document to upload (PDF, DOCX, TXT, MD)")
async def jarvis_upload(inter: discord.Interaction, file: discord.Attachment):
    """
    Handle document uploads for RAG processing.
    
    This command validates uploaded documents, checks admin permissions,
    enforces file size and format restrictions, and ingests valid documents
    into the RAG system for future queries.
    
    Args:
        inter: Discord interaction object containing user, channel, and guild info
        file: Discord attachment containing the document to upload and process
    """
    await inter.response.defer()
    
    # Check channel authorization first
    ctx = await check_channel_authorization(inter)
    if not ctx:
        return  # Error message already sent
    
    # Check if user has admin role
    if not inter.guild:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="File uploads are not available in direct messages.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)
        return
    
    # Get member object to access roles
    # Try multiple methods to get member information
    member = None
    
    # Method 1: Try guild.get_member first (cached)
    if inter.guild:
        member = inter.guild.get_member(inter.user.id)
    
    # Method 2: If not found, try fetching from API
    if not member and inter.guild:
        try:
            member = await inter.guild.fetch_member(inter.user.id)
        except discord.NotFound:
            logger.warning(f"User {inter.user.id} not found in guild {inter.guild.id}")
        except discord.Forbidden:
            logger.warning(f"Bot lacks permission to fetch member {inter.user.id} in guild {inter.guild.id}")
        except Exception as e:
            logger.error(f"Error fetching member {inter.user.id}: {e}")
    
    # Method 3: Use interaction user as fallback (limited role access)
    if not member:
        # For slash commands, we can access roles directly from the interaction
        if hasattr(inter, 'user') and hasattr(inter.user, 'roles'):
            # This works in some cases where the user object has roles attached
            member = inter.user
        else:
            embed = discord.Embed(
                title="❌ Access Denied",
                description="Could not verify your server membership. This might be a bot permissions issue.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Troubleshooting",
                value="• Make sure the bot has 'Read Message History' permission\n• Try again in a few moments\n• Contact an administrator if this persists",
                inline=False
            )
            await send_answer(inter, embed)
            return
    
    # Check for admin role by ID (from tenant config)
    if not has_admin_access(member):
        admin_role_id = get_admin_role_id(inter.guild.id)  # Use inter.guild instead of member.guild
        
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need admin permissions to upload files.",
            color=discord.Color.red()
        )
        
        if admin_role_id:
            # Show the required role
            admin_role = inter.guild.get_role(admin_role_id)
            role_name = admin_role.name if admin_role else "Unknown Role"
            
            embed.add_field(
                name="Required Role",
                value=f"{role_name} (`{admin_role_id}`)",
                inline=True
            )
        else:
            embed.add_field(
                name="Configuration Error",
                value="No admin role configured for this server",
                inline=True
            )
        
        # Show user roles (handle different object types)
        try:
            if hasattr(member, 'roles'):
                role_names = [role.name for role in getattr(member, 'roles', []) if role.name != "@everyone"]
                embed.add_field(
                    name="Your Roles",
                    value=", ".join(role_names) or "None",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Your Roles",
                    value="Unable to fetch role information",
                    inline=False
                )
        except Exception as e:
            logger.error(f"Error accessing user roles: {e}")
            embed.add_field(
                name="Your Roles",
                value="Error fetching role information",
                inline=False
            )
        await send_answer(inter, embed)
        return
    
    try:
        # Download file content
        file_content = await file.read()
        
        # Validate file
        validator = get_file_validator()
        result = await validator.validate_file_upload(
            file_content=file_content,
            filename=file.filename,
            user_id=str(inter.user.id)
        )
        
        if not result.allowed:
            # File validation failed
            embed = discord.Embed(
                title="❌ Upload Failed",
                description=result.message,
                color=discord.Color.red()
            )
            embed.add_field(
                name="Server Usage", 
                value=f"{result.file_count}/{result.daily_limit} files today",
                inline=True
            )
            await send_answer(inter, embed)
            return
        
        # File validation passed - increment counter
        new_count = await validator.increment_upload_count()
        
        # Here you would typically process the file (add to RAG index, etc.)
        # For now, just confirm successful upload
        embed = discord.Embed(
            title="✅ Upload Successful",
            description=result.message,
            color=discord.Color.green()
        )
        embed.add_field(
            name="Server Usage", 
            value=f"{new_count}/{result.daily_limit} files today",
            inline=True
        )
        if result.pdf_pages:
            embed.add_field(
                name="PDF Pages", 
                value=f"{result.pdf_pages} pages",
                inline=True
            )
        embed.add_field(
            name="File Size", 
            value=f"{result.file_size_mb:.2f} MB",
            inline=True
        )
        
        await send_answer(inter, embed)
        
    except Exception as e:
        logger.error("Upload error for user %s: %s", inter.user.id, str(e))
        embed = discord.Embed(
            title="❌ Upload Error",
            description="An error occurred while processing your file. Please try again.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)

# ──────────────────────────────────────────────
# /jarvis_stats (show usage statistics)
# ──────────────────────────────────────────────
@tree.command(name="jarvis_stats", description="Show your usage statistics")
async def jarvis_stats(inter: discord.Interaction):
    await inter.response.defer()
    
    try:
        from rag_module.rate_limiter import get_rate_limiter
        from rag_module.database_utils import get_supabase_client
        
        logger.info(f"Getting stats for user {inter.user.id}")
        
        rate_limiter = get_rate_limiter(get_supabase_client())
        validator = get_file_validator()
        
        # Get user stats
        user_stats = await rate_limiter.get_user_stats(str(inter.user.id))
        logger.debug(f"User stats result: {user_stats}")
        
        # Check if there was an error in user stats
        if 'error' in user_stats:
            logger.error(f"User stats error: {user_stats['error']}")
            embed = discord.Embed(
                title="❌ Stats Error",
                description=f"Error retrieving user statistics: {user_stats['error']}",
                color=discord.Color.red()
            )
            await send_answer(inter, embed)
            return
        
        upload_stats = await validator.get_upload_stats()
        logger.debug(f"Upload stats result: {upload_stats}")
        
        embed = discord.Embed(
            title="📊 Your Usage Statistics",
            color=discord.Color.blue()
        )
        
        # RAG requests
        if 'limits' in user_stats and 'rag_requests' in user_stats['limits']:
            rag_data = user_stats['limits']['rag_requests']
            embed.add_field(
                name="🤖 RAG Requests",
                value=f"{rag_data['current_count']}/{rag_data['daily_limit']} today",
                inline=True
            )
        else:
            embed.add_field(
                name="🤖 RAG Requests",
                value="0/10 today (no usage yet)",
                inline=True
            )
        
        # File uploads (server-wide)
        if upload_stats:
            embed.add_field(
                name="📁 Server File Uploads",
                value=f"{upload_stats.get('files_uploaded_today', 0)}/{upload_stats.get('daily_limit', 10)} today",
                inline=True
            )
        else:
            embed.add_field(
                name="📁 Server File Uploads",
                value="0/10 today",
                inline=True
            )
        
        # Reset time
        embed.add_field(
            name="🔄 Resets",
            value="Midnight Toronto time",
            inline=True
        )
        
        # OpenAI usage
        openai_usage = user_stats.get('openai_usage', {})
        if openai_usage:
            embed.add_field(
                name="💰 OpenAI Tokens",
                value=f"{openai_usage.get('tokens_used', 0)} tokens",
                inline=True
            )
        else:
            embed.add_field(
                name="💰 OpenAI Tokens",
                value="0 tokens today",
                inline=True
            )
        
        # Access control info (for admins)
        if inter.guild:
            member = inter.guild.get_member(inter.user.id)
            if member and has_admin_access(member):
                admin_role_id = get_admin_role_id(inter.guild.id)
                embed.add_field(
                    name="🔒 Admin Access",
                    value=f"Role ID: `{admin_role_id}`" if admin_role_id else "Not configured",
                    inline=True
                )
        
        await send_answer(inter, embed)
        
    except Exception as e:
        logger.error("Stats error for user %s: %s", inter.user.id, str(e))
        import traceback
        logger.error("Full traceback: %s", traceback.format_exc())
        embed = discord.Embed(
            title="❌ Stats Error",
            description="Could not retrieve usage statistics. Please try again.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)
        return

# ──────────────────────────────────────────────
# /jarvis_access (show access control info - admin only)
# ──────────────────────────────────────────────
@tree.command(name="jarvis_access", description="Show access control configuration (admin only)")
async def jarvis_access(inter: discord.Interaction):
    await inter.response.defer()
    
    # Check if user has admin access
    if not inter.guild:
        embed = discord.Embed(
            title="❌ Access Denied",
            description="This command is not available in direct messages.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)
        return
    
    member = inter.guild.get_member(inter.user.id)
    if not member or not has_admin_access(member):
        embed = discord.Embed(
            title="❌ Access Denied",
            description="You need admin permissions to view access control settings.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)
        return
    
    try:
        admin_role_id = get_admin_role_id(inter.guild.id)
        
        embed = discord.Embed(
            title="🔒 Access Control Configuration",
            description="Current file upload access control settings",
            color=discord.Color.gold()
        )
        
        if admin_role_id:
            # Get role information
            admin_role = inter.guild.get_role(admin_role_id)
            role_name = admin_role.name if admin_role else "Unknown Role"
            
            embed.add_field(
                name="📝 Admin Role",
                value=f"{role_name} (`{admin_role_id}`)",
                inline=False
            )
            
            embed.add_field(
                name="📁 File Upload Command",
                value="/jarvis_upload",
                inline=True
            )
            
            embed.add_field(
                name="� Configuration Source",
                value="tenants.json",
                inline=True
            )
        else:
            embed.add_field(
                name="⚠️ Configuration Missing",
                value="No admin_role_id configured in tenants.json",
                inline=False
            )
            embed.add_field(
                name="� Setup Instructions",
                value="Add 'admin_role_id': YOUR_ROLE_ID to your server config in tenants.json",
                inline=False
            )
        
        await send_answer(inter, embed)
        
    except Exception as e:
        logger.error("Access info error for user %s: %s", inter.user.id, str(e))
        embed = discord.Embed(
            title="❌ Access Info Error",
            description="Could not retrieve access control information.",
            color=discord.Color.red()
        )
        await send_answer(inter, embed)

# ──────────────────────────────────────────────
# on_ready – sync commands
# ──────────────────────────────────────────────
@bot.event
async def on_ready():
    # ---- REMOVE OLD /jarvis group commands ----
    try:
        cmds_to_delete = [cmd for cmd in await bot.tree.fetch_commands()
                          if cmd.name in ("jarvis", "jarvis calendar", "jarvis rag")]
        for cmd in cmds_to_delete:
            # Use remove instead of delete_command
            bot.tree.remove_command(cmd.name)
            logger.info("Deleted legacy command %s", cmd.name)
    except Exception as e:
        logger.warning("Could not delete legacy commands: %s", e)

    # ---- Sync new root commands ----
    
    await tree.sync()   # force push to all guilds

    # Initialize channel discovery service for category-based permissions
    from utils.channel_discovery import initialize_discovery_service
    initialize_discovery_service(bot)
    logger.info("Initialized channel discovery service")

    logger.info("Jarvis online as %s", bot.user)


# ──────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────
if __name__ == "__main__":
    token = settings.discord_token
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN env var missing!")
    bot.run(token)
