"""
Discord Academic Jarvis Bot - Main Entry Point

This is the core Discord bot file that handles incoming commands and routes them
to appropriate modules based on channel configuration and user input.

The bot supports three main modules:
1. RAG (Retrieval-Augmented Generation) - For document-based Q&A
2. Calendar - For calendar and task management queries  
3. Fallback - For general conversational queries

Usage Examples:
- !jarvis rag What's in the syllabus?
- !jarvis calendar When is the next deadline?
- !jarvis How are you today?
"""

import discord
from discord.ext import commands
from discord import Embed
from dotenv import load_dotenv
from tenant_context import load_tenant_context
from message_router import is_module_allowed
from rag_module.rag_handler import respond as rag_respond
from calendar_module.calendar_handler import respond as cal_respond
from fallback_module.fallback_handler import respond as fb_respond
from settings import settings
from utils.logging_config import logger


# Load environment variables from .env file
load_dotenv()
TOKEN = settings.discord_token

# Configure Discord bot intents (permissions for what the bot can access)
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.guilds = True          # Required to access guild information

# Initialize the Discord bot with command prefix "!"
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """
    Event handler called when the bot successfully connects to Discord.
    Logs the bot's name and the guild it's connected to.
    """
    logger.info("Bot is ready and logged in as %s for guild name: %s guild id: %s", bot.user.name, [g.name for g in bot.guilds][0], [g.id for g in bot.guilds][0])


@bot.command(name="jarvis", description="Jarvis commands")
async def jarvis(ctx, module: str, *, rest: str = None):
    """
    Main command handler for the Jarvis bot.
    
    Routes user queries to appropriate modules based on the first parameter:
    - !jarvis rag <query>      -> RAG module for document-based Q&A
    - !jarvis calendar <query> -> Calendar module for schedule/task queries
    - !jarvis <free-form>      -> Fallback module for general conversation
    
    Args:
        ctx: Discord command context containing guild, channel, user info
        module: First parameter - either 'rag', 'calendar', or any other text
        rest: Remaining text after the module parameter
    """

    # 1) Parse command and determine target module + query text
    mod = module.lower()
    if mod in ("rag", "calendar"):
        # Explicit module call: !jarvis rag <query> or !jarvis calendar <query>
        query = rest or ""
        if not query.strip():
            await ctx.send("❌ Missing query text.")
            logger.warning(
                "empty-query guild=%s chan=%s user=%s mod=%s",
                ctx.guild.id, ctx.channel.id, ctx.author.id, mod
            )
            return
    else:
        # Free-form query: !jarvis <anything> -> route to fallback module
        query = f"{module} {rest}".strip() if rest else module
        mod   = "fallback"

    # 2) Load tenant configuration and validate channel permissions
    ctx_cfg = load_tenant_context(ctx.guild.id, ctx.channel.id)
    if not ctx_cfg:
        await ctx.send("⚠️ This server/channel isn't configured.")
        logger.warning(
            "unconfigured guild=%s chan=%s user=%s", 
            ctx.guild.id, ctx.channel.id, ctx.author.id
        )
        return

    # Check if the requested module is allowed in this channel
    if not is_module_allowed(mod, ctx_cfg):
        await ctx.send(f"❌ `{mod}` is not enabled in this channel.")
        logger.info(
            "blocked guild=%s chan=%s user=%s mod=%s", 
            ctx.guild.id, ctx.channel.id, ctx.author.id, mod
        )
        return

    # 3) Route to appropriate module handler
    try:
        if mod == "rag":
            answer = await rag_respond(query, ctx_cfg)
        elif mod == "calendar":
            answer = await cal_respond(query, ctx_cfg)
        else:
            answer = await fb_respond(query, ctx_cfg)
    except Exception as e:
        # Log the error with context, then re-raise for global error handler
        logger.error(
            "handler-fail guild=%s chan=%s user=%s mod=%s err=%s",
            ctx.guild.id, ctx.channel.id, ctx.author.id, mod, e
        )
        raise  # Let the global error handler (on_command_error) process this

    # 4) Send the response back to Discord
    if isinstance(answer, list) and all(isinstance(e, Embed) for e in answer):
        # Handle list of Discord embeds (rich formatted responses)
        await ctx.send(embeds=answer)
    else:
        # Handle plain text responses
        await ctx.send(answer)

@bot.event
async def on_command_error(ctx, error):
    """
    Global error handler for Discord bot commands.
    
    Logs the full traceback for debugging and provides user-friendly error messages.
    This catches any unhandled exceptions from command handlers.
    
    Args:
        ctx: Discord command context where the error occurred
        error: The exception that was raised
    """
    # Log full traceback for debugging
    logger.exception("Unhandled command error: %s", error)
    # Send user-friendly error message
    await ctx.send("⚠️  Sorry, I ran into an unexpected error.")


if __name__ == "__main__":
    # Start the Discord bot using the token from environment variables
    bot.run(TOKEN)
