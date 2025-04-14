import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

# Load .env variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Setup bot with basic permissions
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

bot.run(TOKEN)
