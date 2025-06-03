"""
Message Router Module

This module determines which bot modules (RAG, Calendar, Fallback) are allowed
to be used in specific Discord channels based on the channel's configuration.

Each channel has a 'type' field in the tenant configuration that controls
which modules can be accessed:
- "rag": Only RAG module allowed
- "calendar": Only Calendar module allowed  
- "rag-calendar": Both RAG and Calendar modules allowed
- "fallback": Only Fallback module allowed (fallback is always allowed by default)

This enables fine-grained control over bot functionality per channel.
"""

from utils.logging_config import logger

def is_module_allowed(module: str, context: dict) -> bool:
    """
    Check if a specific module is allowed in the current channel context.
    
    Args:
        module: The module name to check ("rag", "calendar", or "fallback")
        context: Channel configuration dictionary containing the channel 'type'
        
    Returns:
        bool: True if the module is allowed in this channel, False otherwise
        
    Examples:
        >>> context = {"type": "rag-calendar"}
        >>> is_module_allowed("rag", context)
        True
        >>> is_module_allowed("calendar", context) 
        True
        >>> context = {"type": "rag"}
        >>> is_module_allowed("calendar", context)
        False
    """
    channel_type = context.get("type")
    
    if module == "rag":
        logger.debug("RAG module is allowed for channel type: %s", channel_type)
        return channel_type in ("rag", "rag-calendar")
    
    if module == "calendar":
        logger.debug("Calendar module is allowed for channel type: %s", channel_type)
        return channel_type in ("calendar", "rag-calendar")
    
    if module == "fallback":
        logger.debug("Fallback module is allowed for all channel types")
        # Fallback is always allowed as a safety net for general queries
        return True
    
    # Unknown module - deny by default
    return False
