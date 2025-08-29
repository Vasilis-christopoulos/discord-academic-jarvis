from typing import Optional
from supabase import create_client
from pinecone import Pinecone

from settings import settings, TENANT_CONFIGS

MODULE       = "calendar"
INITIAL_ISO  = None

SUPA_URL = settings.supabase_url
SUPA_KEY = settings.supabase_api_key
supabase = create_client(SUPA_URL, SUPA_KEY)

# Module-level Pinecone client for easier mocking in tests
pc = Pinecone(api_key=settings.pinecone_api_key)

def reset_watermarks():
    """
    Reset calendar sync watermarks and tokens to initial state.
    
    This function clears all synchronization state for both calendar events
    and tasks, forcing a complete re-sync on the next synchronization run.
    It resets:
    - Event and task sync timestamps to INITIAL_ISO date
    - Calendar sync token (for incremental event syncing)
    - Tasks last updated timestamp
    """
    try:
        # Reset sync timestamps
        for type_ in ("event", "task"):
            supabase.table("sync_state").update(
                {"first_synced": INITIAL_ISO, "last_synced": INITIAL_ISO}
            ).eq("module", MODULE).eq("type", type_).execute()
        
        # Clear calendar sync token (for events)
        supabase.table("sync_state").update(
            {"calendar_sync_token": None}
        ).eq("module", MODULE).eq("type", "event").execute()
        
        # Clear tasks last updated timestamp
        supabase.table("sync_state").update(
            {"tasks_last_updated": None}
        ).eq("module", MODULE).eq("type", "task").execute()
        
        print("✅ watermarks reset")
    except Exception as e:
        print(f"❌ Error resetting watermarks: {e}")

def reset_pinecone(index_name: Optional[str] = None):
    """
    Clear all calendar data from the Pinecone vector database.
    
    This function deletes all vectors from the calendar Pinecone index,
    effectively removing all stored calendar events and tasks from the
    vector database. Use with caution as this operation cannot be undone.
    
    Args:
        index_name: Optional index name to use. If not provided, uses first tenant's calendar index.
    """
    try:
        calendar_index = index_name
        if not calendar_index:
            # Check if settings has pinecone_calendar_index attribute (for tests)
            calendar_index = getattr(settings, 'pinecone_calendar_index', None)
            if not calendar_index:
                # Use the first tenant's calendar index, or default if no tenants
                calendar_index = "calendar-hybrid"  # Default
                if TENANT_CONFIGS and len(TENANT_CONFIGS) > 0:
                    calendar_index = TENANT_CONFIGS[0].index_calendar
            
        idx = pc.Index(calendar_index)
        stats = idx.describe_index_stats()
        if stats["total_vector_count"]:
            idx.delete(delete_all=True)
            print("✅ cleared Pinecone index")
        else:
            print("⚠️  index already empty")
    except Exception as e:
        print(f"❌ Error resetting Pinecone index: {e}")

if __name__ == "__main__":
    print("Using Pinecone index: calendar-hybrid")
    reset_watermarks()
    reset_pinecone()
