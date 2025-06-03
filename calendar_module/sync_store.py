from supabase import create_client, Client
import datetime as dt
from utils.calendar_utils import parse_iso
from settings import settings
from utils.logging_config import logger

# SUPABASE configuration
url = settings.supabase_url
key = settings.supabase_api_key
supabase: Client = create_client(url, key)

MODULE_NAME = "calendar"

def get_first_last(type_: str) -> tuple[dt.datetime, dt.datetime]:
    """
    Get the first and last synced dates for a given type.
    """
    try:
        row = (
            supabase.table("sync_state")
            .select("first_synced,last_synced")
            .eq("module", MODULE_NAME)
            .eq("type", type_)
            .single()
            .execute()
        ).data
        first = parse_iso(row["first_synced"]) if row["first_synced"] else None
        last  = parse_iso(row["last_synced"])  if row["last_synced"]  else None
    except Exception as e:
        logger.error("Error fetching first/last synced dates: %s", e)
        first, last = None, None
    return first, last

def set_first_last(type_: str, first: dt.datetime, last: dt.datetime):
    """
    Set the first and last synced dates for a given type.
    """
    try:
        supabase.table("sync_state").update({
            "first_synced": first.isoformat(),
            "last_synced":  last.isoformat()
        }).eq("module", MODULE_NAME).eq("type", type_).execute()
    except Exception as e:
        logger.error("Error setting first/last synced dates: %s", e)
    
def get_calendar_sync_token() -> str | None:
    """
    Get the calendar sync token.
    """
    try:
        r = supabase.table("sync_state").select("calendar_sync_token").eq("module", MODULE_NAME).eq("type", "event").single().execute()
    except Exception as e:
        logger.error("Error fetching calendar sync token: %s", e)
        return None
    return r.data.get("calendar_sync_token")

def set_calendar_sync_token(token: str) -> None:
    """
    Set the calendar sync token.
    """
    try:
        supabase.table("sync_state").update({"calendar_sync_token": token}).eq("module", MODULE_NAME).eq("type", "event").execute()
    except Exception as e:
        logger.error("Error setting calendar sync token: %s", e)

def get_tasks_last_updated() -> str | None:
    """
    Get the last updated timestamp for tasks.
    """
    try:
        r = supabase.table("sync_state").select("tasks_last_updated").eq("module", MODULE_NAME).eq("type", "task").single().execute()
    except Exception as e:
        logger.error("Error fetching tasks last updated timestamp: %s", e)
        return None
    return r.data.get("tasks_last_updated")

def set_tasks_last_updated(ts_iso: str) -> None:
    """
    Set the last updated timestamp for tasks.
    """
    try:
        supabase.table("sync_state").update({"tasks_last_updated": ts_iso}).eq("module", MODULE_NAME).eq("type", "task").execute()
    except Exception as e:
        logger.error("Error setting tasks last updated timestamp: %s", e)