"""
Sync Store Module - Calendar Synchronization State Management

This module handles persistent storage of synchronization state for Google Calendar
and Tasks APIs. It maintains sync tokens and timestamps to enable efficient
incremental synchronization using a Supabase database backend.
"""

import datetime as dt
from typing import Optional, Tuple
from rag_module.database_utils import get_supabase_client
from utils.logging_config import logger

# Module identifier for the sync_state table
MODULE_NAME = "calendar"

def get_first_last(sync_type: str) -> Tuple[Optional[dt.datetime], Optional[dt.datetime]]:
    """
    Get the first and last sync dates for a given sync type.
    
    Args:
        sync_type: The type of sync ("event" or "task")
        
    Returns:
        Tuple of (first_synced, last_synced) as datetime objects or (None, None)
    """
    try:
        supabase = get_supabase_client()
        
        response = (
            supabase.table("sync_state")
            .select("first_synced,last_synced")
            .eq("module", MODULE_NAME)
            .eq("type", sync_type)
            .single()
            .execute()
        )
        
        data = response.data
        first_str = data.get("first_synced")
        last_str = data.get("last_synced")
        
        first = dt.datetime.fromisoformat(first_str.replace("Z", "+00:00")) if first_str else None
        last = dt.datetime.fromisoformat(last_str.replace("Z", "+00:00")) if last_str else None
        
        return first, last
        
    except Exception as e:
        logger.error(f"Error getting first/last sync dates for {sync_type}: {e}")
        return None, None

def set_first_last(sync_type: str, first: dt.datetime, last: dt.datetime) -> None:
    """
    Set the first and last sync dates for a given sync type.
    
    Args:
        sync_type: The type of sync ("event" or "task")
        first: First sync datetime
        last: Last sync datetime
    """
    try:
        supabase = get_supabase_client()
        
        # Convert to ISO string format
        first_iso = first.isoformat()
        last_iso = last.isoformat()
        
        # Upsert the record
        (
            supabase.table("sync_state")
            .update({
                "first_synced": first_iso,
                "last_synced": last_iso
            })
            .eq("module", MODULE_NAME)
            .eq("type", sync_type)
            .execute()
        )
        
        logger.debug(f"Updated first/last sync dates for {sync_type}")
        
    except Exception as e:
        logger.error(f"Error setting first/last sync dates for {sync_type}: {e}")

def get_calendar_sync_token() -> Optional[str]:
    """
    Get the stored calendar sync token for incremental synchronization.
    
    Returns:
        The sync token or None if not found
    """
    try:
        supabase = get_supabase_client()
        
        response = (
            supabase.table("sync_state")
            .select("calendar_sync_token")
            .eq("module", MODULE_NAME)
            .eq("type", "event")
            .single()
            .execute()
        )
        
        return response.data.get("calendar_sync_token")
        
    except Exception as e:
        logger.error(f"Error getting calendar sync token: {e}")
        return None

def set_calendar_sync_token(token: Optional[str]) -> None:
    """
    Set the calendar sync token for incremental synchronization.
    
    Args:
        token: The sync token to store, or None to clear the token
    """
    try:
        supabase = get_supabase_client()
        
        # Use update since records already exist
        response = (
            supabase.table("sync_state")
            .update({"calendar_sync_token": token})
            .eq("module", MODULE_NAME)
            .eq("type", "event")
            .execute()
        )
        
        if token:
            logger.debug("Updated calendar sync token")
        else:
            logger.debug("Cleared calendar sync token")
        
    except Exception as e:
        logger.error(f"Error setting calendar sync token: {e}")

def get_tasks_last_updated() -> Optional[str]:
    """
    Get the last updated timestamp for tasks synchronization.
    
    Returns:
        The last updated timestamp or None if not found
    """
    try:
        supabase = get_supabase_client()
        
        response = (
            supabase.table("sync_state")
            .select("tasks_last_updated")
            .eq("module", MODULE_NAME)
            .eq("type", "task")
            .single()
            .execute()
        )
        
        return response.data.get("tasks_last_updated")
        
    except Exception as e:
        logger.error(f"Error getting tasks last updated: {e}")
        return None

def set_tasks_last_updated(timestamp: str) -> None:
    """
    Set the last updated timestamp for tasks synchronization.
    
    Args:
        timestamp: The timestamp to store
    """
    try:
        supabase = get_supabase_client()
        
        # Use update since records already exist
        response = (
            supabase.table("sync_state")
            .update({"tasks_last_updated": timestamp})
            .eq("module", MODULE_NAME)
            .eq("type", "task")
            .execute()
        )
        
        logger.debug("Updated tasks last updated timestamp")
        
    except Exception as e:
        logger.error(f"Error setting tasks last updated: {e}")

# Legacy file-based sync store for compatibility
import json
import os
from pathlib import Path
from typing import Dict, Any

class SyncStore:
    """Simple file-based storage for calendar sync state."""
    
    def __init__(self, store_path: str = "calendar_module/sync_state.json"):
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        
    def get_sync_token(self, calendar_id: str, sync_type: str) -> Optional[str]:
        """Get stored sync token for incremental sync."""
        try:
            if not self.store_path.exists():
                return None
                
            with open(self.store_path, 'r') as f:
                data = json.load(f)
                
            key = f"{calendar_id}_{sync_type}"
            return data.get(key, {}).get('sync_token')
            
        except Exception as e:
            logger.warning(f"Failed to read sync token: {e}")
            return None
    
    def set_sync_token(self, calendar_id: str, sync_type: str, token: str) -> None:
        """Store sync token for future incremental sync."""
        try:
            # Load existing data
            data = {}
            if self.store_path.exists():
                with open(self.store_path, 'r') as f:
                    data = json.load(f)
            
            # Update sync token
            key = f"{calendar_id}_{sync_type}"
            if key not in data:
                data[key] = {}
            
            data[key]['sync_token'] = token
            data[key]['last_updated'] = str(Path(__file__).stat().st_mtime)
            
            # Save updated data
            with open(self.store_path, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save sync token: {e}")
    
    def clear_sync_token(self, calendar_id: str, sync_type: str) -> None:
        """Clear stored sync token to force full resync."""
        try:
            if not self.store_path.exists():
                return
                
            with open(self.store_path, 'r') as f:
                data = json.load(f)
            
            key = f"{calendar_id}_{sync_type}"
            if key in data:
                del data[key]
                
                with open(self.store_path, 'w') as f:
                    json.dump(data, f, indent=2)
                    
                logger.info(f"Cleared sync token for {key}")
                
        except Exception as e:
            logger.error(f"Failed to clear sync token: {e}")

# Global sync store instance
_sync_store = None

def get_sync_store() -> SyncStore:
    """Get or create global sync store instance."""
    global _sync_store
    if _sync_store is None:
        _sync_store = SyncStore()
    return _sync_store
