#!/usr/bin/env python3
"""
Calendar Sync Reset Utility

This script resets the calendar sync state to force a full resync,
which is needed when sync tokens expire or become invalid.
"""

import sys
from pathlib import Path

def reset_calendar_sync():
    """Reset calendar sync state by removing sync tokens."""
    try:
        print("🔄 Resetting calendar sync state...")
        
        # Find and remove sync store files
        sync_files_removed = 0
        
        # Look for sync store files in calendar_module
        calendar_dir = Path("calendar_module")
        if calendar_dir.exists():
            for sync_file in calendar_dir.glob("*sync*"):
                if sync_file.is_file() and sync_file.name not in ["sync.py", "delta_sync.py", "reset_sync.py"]:
                    print(f"   Removing: {sync_file}")
                    sync_file.unlink()
                    sync_files_removed += 1
        
        # Look for sync state in cache directory
        cache_dir = Path("cache")
        if cache_dir.exists():
            for sync_file in cache_dir.rglob("*sync*"):
                if sync_file.is_file():
                    print(f"   Removing: {sync_file}")
                    sync_file.unlink()
                    sync_files_removed += 1
        
        # Look for sync state in data directories
        data_dir = Path("data")
        if data_dir.exists():
            for sync_file in data_dir.rglob("*sync*"):
                if sync_file.is_file():
                    print(f"   Removing: {sync_file}")
                    sync_file.unlink()
                    sync_files_removed += 1
        
        print(f"✅ Reset complete - removed {sync_files_removed} sync state files")
        print("💡 Next calendar sync will perform a full refresh")
        
        return True
        
    except Exception as e:
        print(f"❌ Error resetting calendar sync: {e}")
        return False

if __name__ == "__main__":
    success = reset_calendar_sync()
    sys.exit(0 if success else 1)
