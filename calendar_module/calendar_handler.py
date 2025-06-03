"""
Calendar Module Handler

This module handles calendar and task-related queries by integrating multiple components:
1. Natural language query parsing using LLM
2. Google Calendar and Tasks API synchronization
3. Vector database search for semantic matching
4. Hybrid search combining temporal and semantic filtering
5. LLM-based reranking for relevance

The module supports queries like:
- "When is the project meeting?"
- "What tasks are due this week?"
- "Show me Alice's calendar events"

It uses Pinecone vector database for semantic search and maintains sync with
Google Calendar and Tasks APIs for real-time data.
"""

import pytz
import datetime as dt

from utils.calendar_utils import parse_iso, html_to_discord_md, format_iso_to_local
from utils.reranker_calendar import rerank_llm
from discord import Embed
from .query_parser import parse_query
from .sync import ensure_synced
from .vs_calendar import get_calendar_store
from .delta_sync import delta_sync_calendar, delta_sync_tasks
from utils.logging_config import logger
from utils.hybrid_search_utils import hybrid_search_relative_band
from langchain_core.documents import Document

from langchain_openai import OpenAIEmbeddings

# Initialize components for vector search and embeddings
_embed = OpenAIEmbeddings(model="text-embedding-3-large")  # OpenAI embeddings model
_store = get_calendar_store()                              # Pinecone vector store
_index = _store._index                                     # Direct Pinecone index access
_zero_vec = [0.0] * 3072                                  # Zero vector for window-only queries

async def respond(query: str, context: dict) -> str:
    """
    Process calendar/task queries and return formatted results.
    
    This function orchestrates the complete calendar query pipeline:
    1. Parse natural language query into structured data
    2. Sync calendar/task data from Google APIs
    3. Perform semantic search in vector database
    4. Rerank results using LLM for relevance
    5. Format and return results to user
    
    Args:
        query: User's natural language query about calendar events or tasks
        context: Channel configuration containing tenant info, timezone, etc.
        
    Returns:
        str or List[Embed]: Formatted response for Discord (text or rich embeds)
        
    Example Queries:
        - "When is the project meeting?" -> Specific event lookup
        - "What's happening this week?" -> Time window search
        - "Tasks due for Alice" -> Person-filtered task search
    """

    logger.debug("calendar-in guild=%s channel=%s q=%r", context['guild_id'], context['name'], query)
    
    # 1) Parse the natural language query into structured data
    tz = pytz.timezone(context.get("timezone", "America/Toronto"))
    now = dt.datetime.now(tz)
    parsed = await parse_query(query, now)
    
    # Check if this is actually a calendar/task query
    if not parsed.applicable:
        return "❌ This query is not applicable to calendar or task management."

    # 2) Sync data from Google APIs
    # Incremental sync for recent changes (fast)
    await delta_sync_calendar(context)
    await delta_sync_tasks(context)

    # Bulk sync for the query time window (ensures completeness)
    await ensure_synced(
        type_=parsed.type,
        date_from=parsed.date_from,
        date_to=parsed.date_to,     
        context=context,
    )

    # 3) Build temporal filter for database query
    # Convert RFC 3339 dates to Unix timestamps for Pinecone filtering
    ts_from = int(parse_iso(parsed.date_from).timestamp())
    ts_to = int(parse_iso(parsed.date_to).timestamp()) \
            if parsed.date_to else ts_from  # Safety guard for missing end date

    # Create interval-overlap filter to find events/tasks that intersect the time window
    meta_filter = {
        "$and": [
            {"start_ts": {"$lte": ts_to}},   # Item begins before window ends
            {"end_ts":   {"$gte": ts_from}}, # Item ends after window starts
        ]
    }
    
    # Add type filter if specified (events, tasks, or both)
    if parsed.type and parsed.type != "both":
        meta_filter["$and"].append({"type": {"$eq": parsed.type}})

    # 4) Perform semantic search
    query_text = (parsed.filter or '').strip()
    
    if query_text == "":
        # Time window only query - no semantic search needed
        logger.debug("Window-only query")
        res = _index.query(
            vector=_zero_vec,              # Neutral vector for non-semantic search
            top_k=parsed.limit,
            filter=meta_filter,
            include_metadata=True,
        )
        cand_docs = [
            Document(page_content=m["metadata"]["text"], metadata=m["metadata"])
            for m in res["matches"]
        ]
        docs = cand_docs
    else:
        # Hybrid search: combine semantic similarity with temporal filtering
        cand_docs = hybrid_search_relative_band(
            query=parsed.filter or query,
            k=max(10, parsed.limit * 4),  # Get more candidates for reranking
            meta_filter=meta_filter,
            index=_index,      
            embed=_embed,      
        )
        
        if not cand_docs:
            return "No results found."
        
        # 5) Rerank results using LLM for better relevance
        docs = rerank_llm(query, cand_docs)[:parsed.limit]

    if not docs:
        return "No results found."

    # 6) Format and return results
    tz = pytz.timezone(context.get("timezone","America/Toronto"))
    embeds: list[Embed] = []

    for d in docs:
        md = d.metadata
        title, body_html = d.page_content.split("\n", 1)

        # convert any <a>…</a> → Markdown links
        body_md = html_to_discord_md(body_html).strip() or None


        if md["type"] == "event":
            # parse start/end and format
            start = format_iso_to_local(md["start_dt"])
            end   = format_iso_to_local(md["end_dt"])
            when_field = f"{start} – {end}"

            embed = Embed(
                title=f"{title}",             # event name
                description=body_md,          # clickable links inline
            )
            embed.add_field(name="When", value=when_field, inline=False)

            if md.get("location"):
                embed.add_field(name="Where",
                                value=md["location"], inline=False)

        else:  # task
            # tasks only show the date part
            date_parts = format_iso_to_local(md["start_dt"]).split()
            date_only = " ".join(date_parts[:3])
            embed = Embed(
                title=f"{title}",             # task title
                description=body_md,          # clickable links inline
            )
            embed.add_field(name="Due", value=date_only, inline=False)

        embeds.append(embed)

    return embeds
