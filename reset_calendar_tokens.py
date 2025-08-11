#!/usr/bin/env python3
"""
Simple script to reset calendar sync tokens without complex imports.
This helps resolve infinite loop issues in calendar synchronization.
"""

import os
import sys

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supabase import create_client

# Import settings safely
try:
    from settings import settings
    SUPA_URL = settings.supabase_url
    SUPA_KEY = settings.supabase_api_key
except ImportError:
    # Fallback to environment variables
    SUPA_URL = os.getenv('SUPABASE_URL')
    SUPA_KEY = os.getenv('SUPABASE_API_KEY')

if not SUPA_URL or not SUPA_KEY:
    print("❌ Error: Could not load Supabase credentials")
    print("💡 Make sure your .env file is properly configured")
    exit(1)

supabase = create_client(SUPA_URL, SUPA_KEY)

MODULE = "calendar"

def reset_sync_tokens():
    """Reset sync tokens to clear infinite loop issues."""
    try:
        print("🔄 Resetting calendar sync tokens...")
        
        # Clear calendar sync token (for events)
        supabase.table("sync_state").update(
            {"calendar_sync_token": None}
        ).eq("module", MODULE).eq("type", "event").execute()
        
        # Clear tasks last updated timestamp
        supabase.table("sync_state").update(
            {"tasks_last_updated": None}
        ).eq("module", MODULE).eq("type", "task").execute()
        
        # Reset sync timestamps
        for type_ in ("event", "task"):
            supabase.table("sync_state").update(
                {"first_synced": None, "last_synced": None}
            ).eq("module", MODULE).eq("type", type_).execute()
        
        print("✅ Calendar sync tokens and timestamps reset successfully!")
        print("📝 The next calendar query will perform a fresh full sync.")
        
    except Exception as e:
        print(f"❌ Error resetting sync tokens: {e}")
        return False
        
    return True

if __name__ == "__main__":
    print("🛠️  Calendar Sync Token Reset Utility")
    print("=" * 40)
    success = reset_sync_tokens()
    if success:
        print("\n🎉 Reset completed! You can now test calendar queries again.")
    else:
        print("\n❌ Reset failed. Check your database connection.")
