import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from tenant_context import load_tenant_context
from message_router import is_module_allowed
from rag_module.rag_handler import respond as rag_respond
from calendar_module.calendar_handler import respond as cal_respond
from fallback_module.fallback_handler import respond as fb_respond

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")


@bot.command(name="jarvis")
async def jarvis(ctx, module: str, *, rest: str = None):
    """
    Usage:
      !jarvis rag <query>
      !jarvis calendar <query>
      !jarvis <free‑form query>        # fallback/general
    """
    # Determine requested module & query text
    mod = module.lower()
    if mod in ("rag", "calendar"):
        query = rest or ""
    else:
        # no explicit module → treat entire input as fallback query
        query = " ".join([module, rest]) if rest else module
        mod = "fallback"

    # Load tenant+channel context
    ctx_cfg = load_tenant_context(ctx.guild.id, ctx.channel.id)
    if not ctx_cfg:
        return await ctx.send("⚠️ This server/channel isn’t configured.")

    # Check if this module is allowed here
    if not is_module_allowed(mod, ctx_cfg):
        return await ctx.send(f"❌ `{mod}` is not enabled in this channel.")

    # Delegate to the right handler
    if mod == "rag":
        answer = await rag_respond(query, ctx_cfg)
    elif mod == "calendar":
        answer = await cal_respond(query, ctx_cfg)
    else:
        answer = await fb_respond(query, ctx_cfg)


    await ctx.send(answer)


if __name__ == "__main__":
    bot.run(TOKEN)
