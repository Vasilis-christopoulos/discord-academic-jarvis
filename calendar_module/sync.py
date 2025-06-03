# jarvis_calendar/sync.py

import pytz
import datetime as dt
from pathlib import Path
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

from langchain_core.documents import Document

from .sync_store import get_first_last, set_first_last
from .vs_calendar import get_calendar_store
from utils.calendar_utils import epoch_from_iso, parse_iso
from utils.logging_config import logger

# Constants & Paths
SCOPES     = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]
BASE       = Path(__file__).parent
CRED_PATH  = BASE / "credentials.json"
TOKEN_PATH = BASE / "token.json"
FUTURE_HORIZON = 30    # days ahead if date_to is None

# Google Auth Helper
async def get_creds() -> Credentials:
    """
    Obtain or refresh Google OAuth credentials, saving token.json locally.
    """
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # If no creds or creds invalid → run full flow
    if not creds or not creds.valid:
        if creds and creds.expired:
            try:
                creds.refresh(Request())
            except RefreshError:
                # Refresh token is bad: delete and re-authorize
                TOKEN_PATH.unlink(missing_ok=True)
                creds = None

        if not creds:
            # Full OAuth dance
            flow = InstalledAppFlow.from_client_secrets_file(str(CRED_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
            TOKEN_PATH.write_text(creds.to_json())

    return creds


# only what we need from each API
CAL_FIELDS = ",".join([
    "items("
      "id,"
      "summary,"
      "description,"
      "location,"
      "start(dateTime,date),"
      "end(dateTime,date)"
    "),"
    "nextPageToken"
])

TASK_FIELDS = ",".join([
    "items("
      "id,"
      "title,"
      "notes,"
      "due"
    "),"
    "nextPageToken"
])

# Fetch Google Calendar/Tasks
async def fetch_google(
    type_: str,
    date_from: str,
    date_to: Optional[str],
    context: dict,
) -> List[Document]:
    """
    Fetch *all* Calendar events and/or Tasks in [date_from, date_to].
    Uses paging + fields masks for speed.
    """
    creds     = await get_creds()
    if not creds:
        logger.error("Failed to get Google credentials.")
        return []
    try:
        svc_cal   = build("calendar", "v3", credentials=creds)
        svc_tasks = build("tasks",   "v1", credentials=creds).tasks()
    except Exception as err:
        logger.error("Error building Google API services: %s", err)
        return []

    docs: List[Document] = []
    tz_local = pytz.timezone(context.get("timezone", "America/Toronto"))

    # EVENTS  
    if type_ in ("event", "both"):
        page_token = None
        while True:
            try:
                resp = svc_cal.events().list(
                    calendarId   = context["calendar_id"],
                    timeMin      = date_from,
                    timeMax      = date_to or date_from,
                    timeZone     = context.get("timezone","America/Toronto"),
                    singleEvents = True,
                    orderBy      = "startTime",
                    showDeleted  = False,
                    pageToken    = page_token,
                    fields       = CAL_FIELDS,         
                ).execute()
            except Exception as err:
                logger.error("Error fetching events: %s", err)
                break

            for ev in resp.get("items", []):
                print(ev) # debug
                start_iso = ev["start"].get("dateTime") or ev["start"].get("date")
                end_iso = ev["end"].get("dateTime")   or ev["end"].get("date")
                loc = ev.get("location")
                metadata={
                        "id":       ev["id"],
                        "type":     "event",
                        "start_dt": start_iso,
                        "end_dt":   end_iso,
                        "start_ts": epoch_from_iso(start_iso),
                        "end_ts":   epoch_from_iso(end_iso),
                    }
                if loc is not None:
                    metadata["location"] = loc

                docs.append(Document(
                    page_content=f"{ev.get('summary','')}\n{ev.get('description','')}",
                    metadata=metadata
                ))

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    # TASKS
    if type_ in ("task", "both"):
        page_token = None
        while True:
            try:
                resp = svc_tasks.list(
                    tasklist    = context["tasklist_id"],
                    dueMin      = date_from,
                    dueMax      = date_to or date_from,
                    showDeleted = False,
                    pageToken   = page_token,
                    fields      = TASK_FIELDS,        
                ).execute()
            except Exception as err:
                logger.error("Error fetching tasks: %s", err)
                break

            for tk in resp.get("items", []):
                tid     = tk["id"]
                title   = tk.get("title","")
                notes   = tk.get("notes","")
                due_iso = tk.get("due")         

                if not due_iso:
                    start_dt = end_dt = due_ts = None
                else:
                    dt_parsed = parse_iso(due_iso)
                    # all‑day vs. timed task
                    if due_iso.endswith("Z") and "T00:00:00" in due_iso:
                        # full‑day window
                        date_str   = due_iso.split("T",1)[0]
                        start_dt   = tz_local.localize(
                            dt.datetime.fromisoformat(date_str + "T00:00:00")
                        )
                        end_dt     = start_dt + dt.timedelta(
                                             hours=23, minutes=59, seconds=59)
                    else:
                        # point in time
                        start_dt = end_dt = dt_parsed.astimezone(tz_local)

                    due_ts = int(start_dt.timestamp())

                docs.append(Document(
                    page_content=f"{title}\n{notes}",
                    metadata={
                        "id":       tid,
                        "type":     "task",
                        "start_dt": start_dt.isoformat() if due_iso else None,
                        "end_dt":   end_dt.isoformat()   if due_iso else None,
                        "start_ts": due_ts,
                        "end_ts":   due_ts,
                    }
                ))

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    return docs

# Sync Orchestrator
async def ensure_synced(
    type_: str,
    date_from: str,
    date_to: Optional[str],
    context: dict
) -> None:
    """
    Ensures each requested type ('event','task') is synced over the needed slices.
    Uses per-type watermarks (first/last) from sync_store.
    """
    wanted = ["event", "task"] if type_ == "both" else [type_]
    for t in wanted:
        first, last = get_first_last(t)          # tz‑aware datetimes
        start = parse_iso(date_from)
        end   = parse_iso(date_to) if date_to \
                else (start + dt.timedelta(days=FUTURE_HORIZON))

        # build the missing slices
        slices: list[tuple[dt.datetime, dt.datetime]] = []
        if first is None and last is None:
            # first sync ever
            slices.append((start, end))
        elif start < first:
            slices.append((start, first))
        elif end > last:
            slices.append((last, end))

        if not slices:
            continue                            # nothing to fetch

        store = get_calendar_store()

        for s, e in slices:
            docs = await fetch_google(
                type_=t,
                date_from=s.isoformat(),
                date_to=e.isoformat(),
                context=context,
            )
            logger.debug("sync %s %s→%s fetched=%d", t, s, e, len(docs))

            # Upsert if we actually got docs
            if docs:
                try:
                    store.add_documents(docs, ids=[d.metadata["id"] for d in docs])
                except Exception as err:
                    logger.error("⚠️ Failed to upsert %s: %s", t, err)
                    continue
                logger.debug("sync %s %s→%s upserted=%d", t, s, e, len(docs))
            else:
                logger.debug("sync %s %s→%s no docs", t, s, e)
                continue
            
            # Update the water‑marks
            if first is None:
                first = s
            elif s < first:
                first = s
            if last is None:
                last = e
            elif e > last:
                last = e


        # write back the updated water‑marks
        logger.debug("sync %s first=%s last=%s", t, first, last)
        if first is not None and last is not None:
            set_first_last(t, first, last)