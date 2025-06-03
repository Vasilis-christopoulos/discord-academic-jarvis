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
        for type_ in ("event", "task"):
            supabase.table("sync_state").update(
                {"first_synced": INITIAL_ISO, "last_synced": INITIAL_ISO}
            ).eq("module", MODULE).eq("type", type_).execute()
        print("✅ watermarks reset")
    except Exception as e:
        print(f"❌ Error resetting watermarks: {e}")

def reset_pinecone():
    try:
        idx  = pc.Index(settings.pinecone_calendar_index)
        stats = idx.describe_index_stats()
        if stats["total_vector_count"]:
            idx.delete(delete_all=True)
            print("✅ cleared Pinecone index")
        else:
            print("⚠️  index already empty")
    except Exception as e:
        print(f"❌ Error resetting Pinecone index: {e}")

if __name__ == "__main__":
    print("Using Pinecone index:", settings.pinecone_calendar_index)
    reset_watermarks()
    reset_pinecone()
