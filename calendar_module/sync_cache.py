"""
Optimized calendar sync module with performance improvements.

Key optimizations:
1. Local sync token fallback when Supabase fails
2. Smarter sync frequency (avoid re-sync on every query)
3. Better error handling and recovery
4. Reduced API calls
"""

import os
import json
import datetime as dt
from pathlib import Path
from typing import Optional
from utils.logging_config import logger

# Local fallback for sync tokens when Supabase fails
LOCAL_SYNC_DIR = Path("data/sync_cache")
LOCAL_SYNC_DIR.mkdir(exist_ok=True)

CALENDAR_TOKEN_FILE = LOCAL_SYNC_DIR / "calendar_token.json"
TASKS_UPDATED_FILE = LOCAL_SYNC_DIR / "tasks_updated.json"
SYNC_STATUS_FILE = LOCAL_SYNC_DIR / "sync_status.json"

class SyncCache:
    """Local caching for sync tokens and status."""
    
    @staticmethod
    def get_calendar_sync_token() -> Optional[str]:
        """Get calendar sync token with local fallback."""
        try:
            # Try database first
            from calendar_module.sync_store import get_calendar_sync_token as db_get_token
            token = db_get_token()
            if token:
                return token
        except Exception as e:
            logger.debug(f"Database token fetch failed: {e}")
        
        # Fallback to local file
        try:
            if CALENDAR_TOKEN_FILE.exists():
                data = json.loads(CALENDAR_TOKEN_FILE.read_text())
                return data.get("token")
        except Exception as e:
            logger.debug(f"Local token fetch failed: {e}")
        
        return None
    
    @staticmethod
    def set_calendar_sync_token(token: str):
        """Set calendar sync token with local backup."""
        try:
            # Try database first
            from calendar_module.sync_store import set_calendar_sync_token as db_set_token
            db_set_token(token)
        except Exception as e:
            logger.debug(f"Database token save failed: {e}")
        
        # Always save locally as backup
        try:
            data = {
                "token": token,
                "updated": dt.datetime.now().isoformat(),
                "source": "fallback"
            }
            CALENDAR_TOKEN_FILE.write_text(json.dumps(data, indent=2))
            logger.debug("Saved calendar token to local cache")
        except Exception as e:
            logger.warning(f"Failed to save token locally: {e}")
    
    @staticmethod
    def get_tasks_last_updated() -> Optional[str]:
        """Get tasks last updated with local fallback."""
        try:
            # Try database first
            from calendar_module.sync_store import get_tasks_last_updated as db_get_updated
            updated = db_get_updated()
            if updated:
                return updated
        except Exception as e:
            logger.debug(f"Database tasks fetch failed: {e}")
        
        # Fallback to local file
        try:
            if TASKS_UPDATED_FILE.exists():
                data = json.loads(TASKS_UPDATED_FILE.read_text())
                return data.get("last_updated")
        except Exception as e:
            logger.debug(f"Local tasks fetch failed: {e}")
        
        return None
    
    @staticmethod
    def set_tasks_last_updated(timestamp: str):
        """Set tasks last updated with local backup."""
        try:
            # Try database first
            from calendar_module.sync_store import set_tasks_last_updated as db_set_updated
            db_set_updated(timestamp)
        except Exception as e:
            logger.debug(f"Database tasks save failed: {e}")
        
        # Always save locally as backup
        try:
            data = {
                "last_updated": timestamp,
                "updated": dt.datetime.now().isoformat(),
                "source": "fallback"
            }
            TASKS_UPDATED_FILE.write_text(json.dumps(data, indent=2))
            logger.debug("Saved tasks timestamp to local cache")
        except Exception as e:
            logger.warning(f"Failed to save tasks timestamp locally: {e}")
    
    @staticmethod
    def get_last_sync_time() -> Optional[dt.datetime]:
        """Get the last successful sync time to avoid redundant syncs."""
        try:
            if SYNC_STATUS_FILE.exists():
                data = json.loads(SYNC_STATUS_FILE.read_text())
                last_sync = data.get("last_sync")
                if last_sync:
                    return dt.datetime.fromisoformat(last_sync)
        except Exception:
            pass
        return None
    
    @staticmethod
    def set_last_sync_time():
        """Record successful sync time."""
        try:
            data = {
                "last_sync": dt.datetime.now().isoformat(),
                "calendar_events": 0,  # Could track counts
                "tasks": 0
            }
            SYNC_STATUS_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.debug(f"Failed to record sync time: {e}")
    
    @staticmethod
    def should_skip_sync(max_age_minutes: float = 5.0) -> bool:
        """Check if we can skip sync based on recent successful sync."""
        last_sync = SyncCache.get_last_sync_time()
        if not last_sync:
            return False
        
        age = dt.datetime.now() - last_sync
        if age.total_seconds() < (max_age_minutes * 60):
            logger.debug(f"Skipping sync, last sync was {age.total_seconds():.1f}s ago")
            return True
        
        return False

# Usage example
def example_optimized_sync():
    """Example of how to use the optimized sync cache."""
    cache = SyncCache()
    
    # Check if we can skip sync
    if cache.should_skip_sync(max_age_minutes=2):
        print("⚡ Skipping sync - recent data available")
        return
    
    # Get tokens with fallback
    calendar_token = cache.get_calendar_sync_token()
    tasks_updated = cache.get_tasks_last_updated()
    
    print(f"Calendar token: {'✅' if calendar_token else '❌'}")
    print(f"Tasks updated: {'✅' if tasks_updated else '❌'}")
    
    # After successful sync
    cache.set_last_sync_time()
    print("✅ Sync completed and cached")

if __name__ == "__main__":
    example_optimized_sync()
