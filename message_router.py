"""
Message Router Module

This module handles routing of Discord messages to appropriate modules
based on channel configuration and permissions.
"""

from typing import Dict, Any, Optional

def is_module_allowed(module_name: str, channel_context: Optional[Dict[str, Any]] = None) -> bool:
    """
    Check if a module is allowed in the given channel context.
    
    Args:
        module_name (str): Name of the module ('rag', 'calendar', etc.)
        channel_context (dict): Channel context with features list
        
    Returns:
        bool: True if module is allowed, False otherwise
    """
    if not channel_context:
        return False
        
    features = channel_context.get('features', [])
    return module_name in features
