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
from pydantic import BaseModel, Field, field_validator, AliasChoices

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
    admin_role_id: Optional[int] = None     # Discord role ID for admin access to file uploads
    calendar_id: Optional[str]             # Google Calendar ID for this tenant
    tasklist_id: Optional[str]             # Google Tasks list ID for this tenant
    data_dir: str                         # Base directory for tenant data
    index_rag: str                # Index name for RAG vector store
    index_calendar: str         # Index name for calendar vector store
    timezone: str = "America/Toronto"    # Default timezone for date/time operations
    s3_image_prefix: str                 # S3 prefixes for storing images
    s3_raw_docs_prefix: str          # S3 prefixes for storing raw documents
    s3_bucket: str             # S3 bucket name for storing tenant data
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
    discord_token: str = Field(default="", description="Discord bot token")
    
    # OpenAI API Configuration  
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_vision_model: str = Field(default="gpt-4o", description="OpenAI vision model to use")
    
    # Pinecone Vector Database Configuration
    pinecone_api_key: str = Field(default="", description="Pinecone API key")
    
    # Supabase Database Configuration
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_api_key: str = Field(default="", description="Supabase API key")
    
    # AWS S3 Configuration
    aws_access_key_id: str = Field(default="", description="AWS access key ID")
    aws_secret_access_key: str = Field(default="", description="AWS secret access key")
    aws_region_name: str = Field(
        default="ca-central-1", 
        description="AWS region name",
        validation_alias=AliasChoices('aws_region_name', 'AWS_REGION_NAME', 'AWS_REGION')
    )
    
    # Configuration File Paths
    tenants_file: str = Field(default="tenants.json", description="Path to tenants configuration file")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    @field_validator(
        "discord_token",
        "openai_api_key",
        "openai_vision_model", 
        "pinecone_api_key",
        "supabase_url",
        "supabase_api_key",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_region_name",
        "tenants_file"
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
logger.info("loaded settings; tenants=%d index=%s", len(TENANT_CONFIGS), TENANT_CONFIGS[0].index_calendar)
