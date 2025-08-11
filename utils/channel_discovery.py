"""
Channel Discovery and Permission Management

This module provides runtime channel discovery and feature permission management
based on Discord channel categories. It replaces the static channel configuration
with a dynamic system that automatically discovers channels and applies permissions
based on their category membership.

Key Features:
- Automatic channel discovery based on Discord categories
- Category-based feature permissions (rag, calendar, etc.)
- Channel-specific overrides for special cases
- Fallback permissions for uncategorized channels
- Caching for performance optimization
"""

import discord
from typing import List, Dict, Optional, Set
from pathlib import Path
from settings import TENANT_CONFIGS, TenantConfig
from utils.logging_config import logger

class ChannelInfo:
    """Runtime information about a discovered channel."""
    def __init__(self, channel: discord.TextChannel):
        self.id = channel.id
        self.name = channel.name
        self.guild_id = channel.guild.id
        self.category_id = channel.category_id
        self.category_name = channel.category.name if channel.category else "Uncategorized"
        
    def get_features(self, tenant: TenantConfig) -> List[str]:
        """Get features for this channel based on tenant configuration."""
        # Check for manual override first
        if self.id in tenant.channel_overrides:
            override = tenant.channel_overrides[self.id]
            if override.features is not None:
                return override.features
        
        # Check category permissions
        if self.category_id and self.category_id in tenant.category_permissions:
            return tenant.category_permissions[self.category_id].features
        
        # Use default features
        return tenant.default_features
    
    def get_data_paths(self, tenant: TenantConfig) -> Dict[str, str]:
        """Get data directory and vector store path for this channel."""
        # Check for manual override first
        if self.id in tenant.channel_overrides:
            override = tenant.channel_overrides[self.id]
            if override.data_dir:
                vector_path = override.vector_store_path or f"{override.data_dir}/vector_store"
                return {
                    'data_dir': override.data_dir,
                    'vector_store_path': vector_path
                }
        
        # Check category defaults
        if self.category_id and self.category_id in tenant.category_permissions:
            category = tenant.category_permissions[self.category_id]
            return {
                'data_dir': f"{category.default_data_dir}/{self.id}",
                'vector_store_path': f"{category.default_vector_store_path}/{self.id}"
            }
        
        # Use template defaults
        return {
            'data_dir': tenant.default_data_dir_template.format(
                guild_id=tenant.guild_id,
                channel_id=self.id
            ),
            'vector_store_path': tenant.default_vector_store_template.format(
                guild_id=tenant.guild_id,
                channel_id=self.id
            )
        }

class ChannelDiscoveryService:
    """Service for discovering and managing channel configurations at runtime."""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._channel_cache: Dict[int, ChannelInfo] = {}
        self._last_discovery: Optional[float] = None
        
    async def discover_channels(self, guild_id: int) -> List[ChannelInfo]:
        """Discover all text channels in a guild."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"Guild {guild_id} not found")
            return []
        
        channels = []
        for channel in guild.text_channels:
            # Skip channels the bot can't see or access
            if not channel.permissions_for(guild.me).read_messages:
                continue
                
            channel_info = ChannelInfo(channel)
            channels.append(channel_info)
            self._channel_cache[channel.id] = channel_info
        
        logger.info(f"Discovered {len(channels)} channels in guild {guild.name}")
        return channels
    
    async def get_channel_info(self, channel_id: int) -> Optional[ChannelInfo]:
        """Get channel info, discovering it if not cached."""
        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]
        
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return None
        
        channel_info = ChannelInfo(channel)
        self._channel_cache[channel_id] = channel_info
        return channel_info
    
    async def refresh_guild_channels(self, guild_id: int) -> None:
        """Refresh cached channel information for a guild."""
        # Remove old entries for this guild
        to_remove = [cid for cid, info in self._channel_cache.items() 
                    if info.guild_id == guild_id]
        for cid in to_remove:
            del self._channel_cache[cid]
        
        # Rediscover channels
        await self.discover_channels(guild_id)
    
    async def get_channels_by_category(self, guild_id: int) -> Dict[str, List[ChannelInfo]]:
        """Get channels grouped by category name."""
        channels = await self.discover_channels(guild_id)
        by_category = {}
        
        for channel in channels:
            category = channel.category_name
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(channel)
        
        return by_category

# Global discovery service instance (initialized when bot starts)
discovery_service: Optional[ChannelDiscoveryService] = None

def initialize_discovery_service(bot: discord.Client):
    """Initialize the global discovery service."""
    global discovery_service
    discovery_service = ChannelDiscoveryService(bot)

async def get_channel_features(channel_id: int) -> List[str]:
    """Get features for a channel using auto-discovery."""
    if not discovery_service:
        return []
    
    channel_info = await discovery_service.get_channel_info(channel_id)
    if not channel_info:
        return []
    
    # Find tenant config
    tenant = None
    for t in TENANT_CONFIGS:
        if t.guild_id == channel_info.guild_id:
            tenant = t
            break
    
    if not tenant:
        return []
    
    return channel_info.get_features(tenant)

async def has_feature_access(channel_id: int, feature: str) -> bool:
    """Check if a channel has access to a specific feature."""
    features = await get_channel_features(channel_id)
    return feature in features

async def get_channel_data_paths(channel_id: int) -> Dict[str, str]:
    """Get data paths for a channel using auto-discovery."""
    if not discovery_service:
        return {}
    
    channel_info = await discovery_service.get_channel_info(channel_id)
    if not channel_info:
        return {}
    
    # Find tenant config
    tenant = None
    for t in TENANT_CONFIGS:
        if t.guild_id == channel_info.guild_id:
            tenant = t
            break
    
    if not tenant:
        return {}
    
    return channel_info.get_data_paths(tenant)

def get_tenant_config(guild_id: int) -> Optional[TenantConfig]:
    """Get tenant configuration for a guild."""
    for tenant in TENANT_CONFIGS:
        if tenant.guild_id == guild_id:
            return tenant
    return None
