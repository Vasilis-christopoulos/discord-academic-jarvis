"""
Tenant Context Module

This module handles loading and managing tenant-specific configuration for Discord guilds
and channels. It provides a unified interface to access configuration data that includes
both tenant-level settings (like calendar credentials) and channel-specific configurations.

Configuration Hierarchy:
1. Base tenant config (from tenants.json) - applies to entire Discord guild
2. Category-based permissions - features based on Discord channel categories
3. Channel-specific overrides - can override category permissions for specific channels

The module also ensures that required directories (data storage, vector stores) exist
before returning the configuration.
"""

from pathlib import Path
from typing import Optional, Dict
import discord
from settings import TENANT_CONFIGS
from utils.logging_config import logger


def load_tenant_context(guild_id: int, channel_id: int, channel: Optional[discord.TextChannel] = None) -> Optional[Dict]:
    """
    Load and return the merged tenant+channel configuration for a specific Discord guild and channel.

    This function:
    1. Finds the tenant configuration for the given guild_id
    2. Determines channel features based on category permissions or overrides
    3. Applies any channel-specific configuration overrides
    4. Ensures required directories exist (data_dir, vector_store_path)
    5. Returns the merged configuration dictionary

    Args:
        guild_id: Discord guild (server) ID
        channel_id: Discord channel ID within the guild
        channel: Optional Discord channel object for category detection

    Returns:
        Dict containing merged tenant+channel configuration, or None if guild not configured

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
            "features": List[str],  # ["rag", "calendar", etc.]
            "channel_name": str,    # Channel-specific name
            ... # other tenant and channel-specific settings
        }
    """
    # Search through all configured tenants for matching guild
    for tenant in TENANT_CONFIGS:
        if tenant.guild_id == guild_id:
            # Start with the base tenant configuration
            cfg = tenant.model_dump()
            
            # Determine channel features and data paths
            features = []
            data_dir = None
            vector_store_path = None
            channel_name = f"channel-{channel_id}"
            
            # Check for channel-specific override first
            if channel_id in tenant.channel_overrides:
                override = tenant.channel_overrides[channel_id]
                if override.features is not None:
                    features = override.features
                if override.data_dir:
                    data_dir = override.data_dir
                if override.vector_store_path:
                    vector_store_path = override.vector_store_path
                if override.name:
                    channel_name = override.name
                    
                logger.debug("Using channel override for channel %s: features=%s", channel_id, features)
            else:
                # Check category permissions
                category_id = None
                if channel and channel.category:
                    category_id = channel.category_id
                
                if category_id and category_id in tenant.category_permissions:
                    category_config = tenant.category_permissions[category_id]
                    features = category_config.features
                    data_dir = f"{category_config.default_data_dir}/{channel_id}"
                    vector_store_path = f"{category_config.default_vector_store_path}/{channel_id}"
                    
                    logger.debug("Using category permissions for channel %s (category %s): features=%s", 
                               channel_id, category_config.name, features)
                else:
                    # Use default features for uncategorized channels
                    features = tenant.default_features
                    data_dir = tenant.default_data_dir_template.format(
                        guild_id=guild_id,
                        channel_id=channel_id
                    )
                    vector_store_path = tenant.default_vector_store_template.format(
                        guild_id=guild_id,
                        channel_id=channel_id
                    )
                    
                    logger.debug("Using default features for uncategorized channel %s: features=%s", 
                               channel_id, features)
            
            # Add channel-specific configuration to the base config
            cfg.update({
                "channel_id": channel_id,
                "channel_name": channel_name,
                "features": features,
                "data_dir": data_dir or cfg["data_dir"],
                "vector_store_path": vector_store_path,
                "type": "-".join(features) if features else "none"  # Backward compatibility
            })

            # Ensure required directories exist for data storage
            if cfg["data_dir"]:
                Path(cfg["data_dir"]).mkdir(parents=True, exist_ok=True)
            
            # Only create vector_store_path if it exists
            if cfg.get("vector_store_path"):
                Path(cfg["vector_store_path"]).mkdir(parents=True, exist_ok=True)

            logger.debug("ctx-load guild=%s chan=%s features=%s", guild_id, channel_id, features)

            return cfg

    # No configuration found for this guild
    logger.warning("No tenant configuration found for guild_id=%s", guild_id)
    return None


async def load_tenant_context_async(guild_id: int, channel_id: int, bot: Optional[discord.Client] = None) -> Optional[Dict]:
    """
    Async version of load_tenant_context that can fetch channel information from Discord.
    
    This is the preferred method when you have access to the bot instance, as it can
    automatically determine the channel's category for proper feature assignment.
    
    Args:
        guild_id: Discord guild (server) ID
        channel_id: Discord channel ID within the guild
        bot: Discord bot client for fetching channel information
        
    Returns:
        Dict containing merged tenant+channel configuration, or None if guild not configured
    """
    channel = None
    if bot:
        try:
            fetched_channel = bot.get_channel(channel_id)
            if isinstance(fetched_channel, discord.TextChannel):
                channel = fetched_channel
        except Exception as e:
            logger.warning("Failed to fetch channel %s: %s", channel_id, e)
    
    return load_tenant_context(guild_id, channel_id, channel)
