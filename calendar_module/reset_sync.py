from supabase import create_client
from pinecone import Pinecone

from settings import settings

MODULE       = "calendar"
INITIAL_ISO  = None

SUPA_URL = settings.supabase_url
SUPA_KEY = settings.supabase_api_key
supabase = create_client(SUPA_URL, SUPA_KEY)

# Module-level Pinecone client for easier mocking in tests
pc = Pinecone(api_key=settings.pinecone_api_key)

def reset_watermarks():
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
        
        print("✅ watermarks and sync tokens reset")
    except Exception as e:
        print(f"❌ Error resetting watermarks: {e}")

def reset_pinecone():
    try:
        # Use the default calendar index name from tenant config
        calendar_index = "calendar-hybrid"  # Default calendar index
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
