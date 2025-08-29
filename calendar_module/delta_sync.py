# calendar_module/delta_sync.py
from pathlib import Path
import datetime as dt
import pytz
import dateparser
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_core.documents import Document
from pinecone.openapi_support.exceptions import NotFoundException
from typing import Iterable

from .sync_store import (
    get_calendar_sync_token, set_calendar_sync_token,
    get_tasks_last_updated,   set_tasks_last_updated
)
from utils.vector_store import get_vector_store
from .sync        import get_creds
from utils.calendar_utils import epoch_from_iso
from utils.logging_config import logger
import asyncio

BASE = Path(__file__).parent

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly"]


TOKEN_PATH = BASE / "token.json"


# utils/pinecone_barrier.py
import asyncio
from typing import Iterable

# deal with pinecone's delay 
def _extract_vectors(resp):
    """
    Extract vectors from a Pinecone response.
    """
    if isinstance(resp, dict):
        return resp.get("vectors", {})
    if hasattr(resp, "vectors"):  
        return resp.vectors or {}
    # fall-back
    try:
        return resp.to_dict().get("vectors", {})
    except Exception:
        return {}

async def barrier(vstore, ids: Iterable[str], *, gone=False, pause=0.05):
    """
    Wait until every id is present (gone=False) or absent (gone=True).

    vstore : PineconeVectorStore
    ids    : iterable of vector IDs
    """
    index = getattr(vstore, "_index", None) \
            or getattr(vstore, "_pinecone_index", None)
    if index is None:
        raise TypeError("barrier() expected a PineconeVectorStore")

    ids = list(ids)
    while True:
        vectors = _extract_vectors(index.fetch(ids=ids))
        if (gone and not vectors) or (not gone and len(vectors) == len(ids)):
            return
        await asyncio.sleep(pause)



def safe_delete(store, ids):
    try:
        if ids:
            store.delete(ids=ids, async_req= False)
            logger.debug("🗑  Deleted %d stale vectors", len(ids))
    except NotFoundException:
        logger.debug("Vector(s) already gone; ignoring 404 during delete.")
    except Exception:
        logger.exception("Error deleting vectors from Pinecone")

async def delta_sync_calendar(context: dict):
    """Pull only the changed events since our last syncToken."""
    token = get_calendar_sync_token()
    creds = await get_creds()
    svc   = build("calendar", "v3", credentials=creds)

    to_upsert, to_delete = [], []
    page_token = None
    next_sync_token = None
    
    # Track if we're doing a full sync (no token) to prevent infinite loops
    is_full_sync = not token
    
    while True:
        try:
            # Prepare request parameters
            request_params = {
                "calendarId": context["calendar_id"],
                "showDeleted": True,
                "pageToken": page_token,
            }
            
            # Only add syncToken if we have one (for incremental sync)
            if token:
                request_params["syncToken"] = token
            
            resp = svc.events().list(**request_params).execute()
            
        except HttpError as err:
            # handle sync token expiration (HTTP 410)
            if err.resp.status == 410:
                if is_full_sync:
                    # If we're already doing a full sync and getting 410, something is wrong
                    logger.error("Full sync failed with 410 error. Calendar API issue.")
                    raise
                    
                logger.warning("Sync token expired, switching to full sync.")
                # Clear the token and switch to full sync mode
                set_calendar_sync_token(None)
                token = None
                is_full_sync = True
                page_token = None  # Reset pagination for full sync
                continue  # Retry the request without syncToken
                
            raise  # re-raise other errors

        for ev in resp.get("items", []):
            if ev.get("status") == "cancelled":
                to_delete.append(ev["id"])
            else:
                start = ev["start"].get("dateTime") or ev["start"].get("date")
                end   = ev["end"].get("dateTime")   or ev["end"].get("date")
                loc = ev.get("location")
                metadata={
                        "id":       ev["id"],
                        "type":     "event",
                        "start_dt": start,
                        "end_dt":   end,
                        "start_ts": epoch_from_iso(start),
                        "end_ts":   epoch_from_iso(end),
                    }
                if loc is not None:
                    metadata["location"] = loc
                to_upsert.append(Document(
                    page_content=f"{ev.get('summary','')}\n{ev.get('description','')}",
                    metadata=metadata
                ))
        page_token = resp.get("nextPageToken")
        next_sync_token = resp.get("nextSyncToken", next_sync_token)
        if not page_token:
            break

    store = get_vector_store(context.get("index_calendar", "calendar-hybrid"))
    if to_upsert:
        logger.debug("delta_sync_calendar: upsert %d", len(to_upsert))
        try:
            store.add_documents(to_upsert, ids=[d.metadata["id"] for d in to_upsert], async_req=False)
            await barrier(store, [d.metadata["id"] for d in to_upsert])
        except Exception as err:
            logger.error("⚠️ Failed to upsert events: %s", err)
    if to_delete:
            logger.debug("delta_sync_calendar: delete %d", len(to_delete))
            safe_delete(store, to_delete)
            await barrier(store, to_delete, gone=True)
    
    logger.info("delta calendar add=%d del=%d", len(to_upsert), len(to_delete))

    # bump syncToken to the next
    if next_sync_token:
        set_calendar_sync_token(next_sync_token)

# Regex to grab times like "5pm", "5:00 pm", "17:00", etc.
_TIME_RX = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.IGNORECASE)

async def delta_sync_tasks(context: dict):
    """Pull only changed tasks, parse times from title/notes if present."""
    last = get_tasks_last_updated()
    creds = await get_creds()
    svc   = build("tasks", "v1", credentials=creds).tasks()

    to_upsert, to_delete = [], []
    tz = pytz.timezone(context.get("timezone", "America/Toronto"))
    page_token = None
    while True:
        try:
            resp = svc.list(
                tasklist    = context["tasklist_id"],
                showDeleted = True,
                updatedMin  = last,
                pageToken   = page_token,
            ).execute()
        except HttpError as err:
            logger.error("Tasks API error: %s", err)
            # For tasks API, we don't have sync tokens, just continue with what we have
            break
        except Exception as err:
            logger.error("Unexpected error in tasks sync: %s", err)
            break

        for tk in resp.get("items", []):
            tid = tk["id"]
            if tk.get("deleted")  or tk.get("status") == "completed":
                to_delete.append(tid)
                continue

            due_iso = tk.get("due")  # always midnight Z if date-only
            if not due_iso:
                # floating task: no due date at all
                metadata = {"id": tid, "type": "task"}
                to_upsert.append(Document(page_content=f"{tk.get('title','')}\n{tk.get('notes','')}",
                                          metadata=metadata))
                continue

            # 1) extract the date
            date_str = due_iso.split("T", 1)[0]  # "2025-05-03"
            # 2) look for a time hint in title or notes
            text_blob = f"{tk.get('title','')} {tk.get('notes','')}"
            m = _TIME_RX.search(text_blob)

            if m:
                # we have something like "5pm" or "5:00 pm"
                time_str = m.group(1)
                # parse into a time-aware datetime
                # dateparser will pick up your locale/tz automatically
                dt_obj = dateparser.parse(
                    f"{date_str} {time_str}",
                    settings={
                      "TIMEZONE": context.get("timezone", "America/Toronto"),
                      "RETURN_AS_TIMEZONE_AWARE": True,
                    }
                )
                # fallback if dateparser fails
                if not dt_obj:
                    # default to local midnight
                    naive = dt.datetime.fromisoformat(date_str + "T00:00:00")
                    if naive.tzinfo is None:
                        dt_obj = tz.localize(naive)
                    else:
                        dt_obj = naive
            else:
                # no time found → full-day window
                naive_start = dt.datetime.fromisoformat(date_str + "T00:00:00")
                start_dt    = tz.localize(naive_start)
                dt_obj      = start_dt  # we'll use this for start, and compute end below

            # 3) compute start_ts and end_ts
            start_dt = dt_obj
            # if time was parsed, start_dt==end_dt; else full-day → end at 23:59:59
            if m:
                end_dt = start_dt
            else:
                end_dt = start_dt + dt.timedelta(hours=23, minutes=59, seconds=59)

            start_ts = int(start_dt.timestamp())
            end_ts   = int(end_dt.timestamp())

            metadata = {
                "id":       tid,
                "type":     "task",
                "start_dt": start_dt.isoformat(),
                "end_dt":   end_dt.isoformat(),
                "start_ts": start_ts,
                "end_ts":   end_ts,
            }

            to_upsert.append(Document(
                page_content=f"{tk.get('title','')}\n{tk.get('notes','')}",
                metadata=metadata
            ))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    store = get_vector_store(context.get("index_calendar", "calendar-hybrid"))
    if to_upsert:
        logger.debug("delta_sync_tasks: upsert %d", len(to_upsert))
        try:
            store.add_documents(to_upsert, ids=[d.metadata["id"] for d in to_upsert], async_req=False)
            await barrier(store, [d.metadata["id"] for d in to_upsert])
        except Exception as err:
            logger.error("⚠️ Failed to upsert tasks: %s", err)
    if to_delete:
        logger.debug("delta_sync_tasks: delete %d", len(to_delete))
        safe_delete(store, to_delete)
        await barrier(store, to_delete, gone=True)
    
    logger.info("delta calendar add=%d del=%d", len(to_upsert), len(to_delete))


    # bump updatedMin to now
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    set_tasks_last_updated(now_iso)


