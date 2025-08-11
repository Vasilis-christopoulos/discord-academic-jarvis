"""
Tenant Context Module

This module handles loading and managing tenant-specific configuration for Discord guilds
and channels. It provides a unified interface to access configuration data that includes
both tenant-level settings (like calendar credentials) and channel-specific overrides.

Configuration Hierarchy:
1. Base tenant config (from tenants.json) - applies to entire Discord guild
2. Channel-specific overrides - can override certain tenant settings per channel

The module also ensures that required directories (data storage, vector stores) exist
before returning the configuration.
"""

from pathlib import Path
from typing import Optional, Dict
from settings import TENANT_CONFIGS
from utils.logging_config import logger


def load_tenant_context(guild_id: int, channel_id: int) -> Optional[Dict]:
    """
    Load and return the merged tenant+channel configuration for a specific Discord guild and channel.

    This function:
    1. Finds the tenant configuration for the given guild_id
    2. Checks if the channel is specifically configured (security requirement)
    3. Applies any channel-specific configuration overrides
    4. Ensures required directories exist (data_dir, vector_store_path)
    5. Returns the merged configuration dictionary

    Args:
        guild_id: Discord guild (server) ID
        channel_id: Discord channel ID within the guild

    Returns:
        Dict containing merged tenant+channel configuration, or None if guild/channel not configured

    Configuration Structure:
        {
            "guild_id": int,
            "name": str,
            "description": str,
            "calendar_id": str,
            "tasklist_id": str,
            "data_dir": str,
            "vector_store_path": str,
            "timezone": str,
            "type": str,  # Channel-specific: "rag", "calendar", "rag-calendar", etc.
            ... # other channel-specific overrides
        }
    """
    # Search through all configured tenants for matching guild
    for tenant in TENANT_CONFIGS:
        if tenant.guild_id == guild_id:
            # Check if this specific channel is configured
            chan_cfg = tenant.channels.get(channel_id)
            if not chan_cfg:
                logger.warning("Channel %s not configured in guild %s. Available channels: %s", 
                             channel_id, guild_id, list(tenant.channels.keys()))
                return None

            # Start with the base tenant configuration
            cfg = tenant.model_dump()

            # Merge channel config into tenant config (channel config takes precedence)
            cfg.update(chan_cfg.model_dump())

            # Ensure required directories exist for data storage
            Path(cfg["data_dir"]).mkdir(parents=True, exist_ok=True)
            
            # Only create vector_store_path if it exists (from channel config)
            if "vector_store_path" in cfg:
                Path(cfg["vector_store_path"]).mkdir(parents=True, exist_ok=True)

            logger.debug("ctx-load guild=%s chan=%s cfg=%s", guild_id, channel_id, cfg["name"])

            return cfg

    # No configuration found for this guild
    logger.warning("No tenant configuration found for guild_id=%s", guild_id)
    return None
