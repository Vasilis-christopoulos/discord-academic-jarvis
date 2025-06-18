import logging
import discord
from discord import app_commands
from discord.ext import commands
from tenant_context import load_tenant_context
from settings import settings
from rag_module.rag_handler import respond as rag_respond
from calendar_module.calendar_handler import respond as cal_respond

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis")

# ──────────────────────────────────────────────
# Discord client setup
# ──────────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix=None, intents=intents)
tree: app_commands.CommandTree = bot.tree

# ──────────────────────────────────────────────
# Context helper (tenant aware)
# ──────────────────────────────────────────────
async def build_ctx_cfg(inter: discord.Interaction) -> dict:
    cfg = load_tenant_context(inter.guild_id, inter.channel_id) or {}
    cfg.update({
        "guild_id": inter.guild_id,
        "channel_id": inter.channel_id,
        "user_id": inter.user.id,
        "username": str(inter.user),
        "name": cfg.get("name", inter.channel.name),
        "timezone": cfg.get("timezone", "UTC"),
    })
    return cfg


# ──────────────────────────────────────────────
# Utility: send answer after defer
# ──────────────────────────────────────────────
async def send_answer(inter: discord.Interaction, payload):
    """Payload may be str, Embed, or list[Embed]."""
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

# ──────────────────────────────────────────────
# /jarvis_rag  (root command)
# ──────────────────────────────────────────────
@tree.command(name="jarvis_rag", description="Ask the notes RAG assistant")
@app_commands.describe(query="Your question")
async def jarvis_rag(inter: discord.Interaction, query: str):
    await inter.response.defer()
    ctx = await build_ctx_cfg(inter)
    result = await rag_respond(query, ctx)
    await send_answer(inter, result)

# ──────────────────────────────────────────────
# /jarvis_calendar  (root command)
# ──────────────────────────────────────────────
@tree.command(name="jarvis_calendar", description="Ask calendar questions")
@app_commands.describe(query="Your calendar query")
async def jarvis_calendar(inter: discord.Interaction, query: str):
    await inter.response.defer()
    ctx = await build_ctx_cfg(inter)
    result = await cal_respond(query, ctx)
    await send_answer(inter, result)

# ──────────────────────────────────────────────
# on_ready – sync commands
# ──────────────────────────────────────────────
@bot.event
async def on_ready():
    # ---- REMOVE OLD /jarvis group commands ----
    cmds_to_delete = [cmd for cmd in await bot.tree.fetch_commands()
                      if cmd.name in ("jarvis", "jarvis calendar", "jarvis rag")]
    for cmd in cmds_to_delete:
        await bot.tree.delete_command(cmd.id)
        logger.info("Deleted legacy command %s", cmd.name)

    # ---- Sync new root commands ----
    
    await tree.sync()   # force push to all guilds

    logger.info("Jarvis online as %s", bot.user)


# ──────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────
if __name__ == "__main__":
    token = settings.discord_token
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN env var missing!")
    bot.run(token)
