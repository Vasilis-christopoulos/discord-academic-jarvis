# settings.py
"""
Centralized Application and Tenant-Channel Configuration

This module handles all application configuration using Pydantic for validation.
It loads and validates:
1. Environment variables (API keys, database URLs, etc.)
2. Tenant configuration from tenants.json (Discord guilds and channels)

The configuration is validated on startup and will raise errors if any required
settings are missing or invalid, ensuring the application fails fast with clear
error messages rather than failing silently during runtime.

Configuration Sources:
- Environment variables (.env file or system environment)
- tenants.json file for Discord guild/channel configuration

Key Features:
- Type validation using Pydantic models
- Automatic environment variable loading
- Guild and channel configuration validation
- Directory path validation and creation
"""

import os
from dotenv import load_dotenv
load_dotenv(override=True)

import json
from pathlib import Path
from typing import Dict, List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field, field_validator

from utils.logging_config import logger

class ChannelConfig(BaseModel):
    """
    Configuration model for individual Discord channels.
    
    Each channel can have its own data directories and module access controls.
    The 'type' field determines which bot modules are available in this channel.
    """
    name: str                # Human-readable channel name
    description: str         # Channel description for documentation
    data_dir: str           # Directory for channel-specific data storage
    vector_store_path: str  # Directory for channel-specific vector database
    type: str              # Module access control: 'rag', 'calendar', 'rag-calendar', etc.

    model_config = {
        "extra": "forbid"  # Reject unknown fields to catch configuration errors
    }


class TenantConfig(BaseModel):
    """
    Configuration model for Discord guilds (servers) and their channels.
    
    Represents a tenant in the multi-tenant architecture. Each guild can have
    multiple channels with different configurations and access controls.
    """
    guild_id: int                           # Discord guild (server) ID
    name: str                              # Human-readable tenant name
    description: str                       # Tenant description
    calendar_id: Optional[str]             # Google Calendar ID for this tenant
    tasklist_id: Optional[str]             # Google Tasks list ID for this tenant
    data_dir: str                         # Base directory for tenant data
    vector_store_path: str                # Base directory for tenant vector stores
    timezone: str = "America/Toronto"     # Default timezone for date/time operations
    channels: Dict[int, ChannelConfig]    # Channel ID -> Channel configuration mapping

    model_config = {
        "extra": "forbid"  # Reject unknown fields to catch configuration errors
    }


class AppSettings(BaseSettings):
    """
    Main application settings loaded from environment variables.
    
    All sensitive data (API keys, credentials) should be stored in environment
    variables or .env file, never hardcoded. This class validates that all
    required settings are present and non-empty.
    """
    # Discord Bot Configuration
    discord_token: str = Field(..., env="DISCORD_TOKEN")
    
    # OpenAI API Configuration
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    
    # Pinecone Vector Database Configuration
    pinecone_api_key: str = Field(..., env="PINECONE_API_KEY")
    pinecone_calendar_index: str = Field(..., env="PINECONE_CALENDAR_INDEX")
    
    # Supabase Database Configuration
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_api_key: str = Field(..., env="SUPABASE_API_KEY")
    
    # Configuration File Paths
    tenants_file: str = Field("tenants.json", env="TENANTS_FILE")

    model_config = SettingsConfigDict(
        env_file = ".env",           # Load from .env file if present
        env_file_encoding = "utf-8", # Handle unicode in environment files
        case_sensitive = False,      # Allow case-insensitive env var names
        extra = "ignore"            # Ignore unknown environment variables
    )
    
    @field_validator(
        "discord_token",
        "openai_api_key", 
        "pinecone_api_key",
        "pinecone_calendar_index",
        "supabase_url",
        "supabase_api_key",
    )
    def not_empty(cls, v: str) -> str:
        """Validate that critical configuration values are not empty."""
        if not v.strip():
            raise ValueError("Configuration value cannot be empty")
        return v


# Initialize and validate application settings
# This will raise an exception if any required environment variables are missing
settings = AppSettings()

# Load and validate tenant configuration from JSON file
tenants_path = Path(settings.tenants_file)
if not tenants_path.is_file():
    raise FileNotFoundError(f"Tenants file not found: {tenants_path}")

# Parse and validate tenant configuration
raw = json.loads(tenants_path.read_text(encoding="utf-8"))
TENANT_CONFIGS: List[TenantConfig] = []

for guild_str, cfg in raw.items():
    try:
        # Convert guild ID from string to int and validate the entire config
        tenant = TenantConfig(guild_id=int(guild_str), **cfg)
        TENANT_CONFIGS.append(tenant)
    except Exception as e:
        raise RuntimeError(f"Invalid tenant configuration for guild {guild_str}: {e}")

# Log successful configuration loading
logger.info("loaded settings; tenants=%d calendar_index=%s", len(TENANT_CONFIGS), settings.pinecone_calendar_index)
