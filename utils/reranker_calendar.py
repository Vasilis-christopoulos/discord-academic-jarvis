# utils/reranker.py
import json, re
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from utils.calendar_utils import html_to_discord_md
from utils.logging_config import logger

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

_HTML_TAG_RX = re.compile(r"<[^>]+>")   # crude tag stripper

def _clean(text: str, max_tokens: int = 60) -> str:
    """
    • Convert <a href> to Markdown so link text is kept.
    • Remove any other HTML tags.
    • Collapse newlines, trim to ~max_tokens worth of chars.
    """
    text = html_to_discord_md(text)           # keeps [text](url)
    text = _HTML_TAG_RX.sub("", text)         # drop remaining tags
    text = text.replace("\n", " ").strip()
    # rough char budget (≈4 chars/token)
    limit = max_tokens * 4
    return text[:limit] + ("…" if len(text) > limit else "")

def rerank_llm(query: str, docs: List[Document]) -> List[Document]:
    """
    Rerank calendar documents using LLM-based relevance scoring.
    
    This function takes a list of calendar events and tasks retrieved from
    semantic search and reranks them based on semantic relevance to the user's
    query using an LLM. It formats the documents for the LLM, gets relevance
    scores, and returns the documents sorted by relevance.
    
    Args:
        query: User's natural language query about calendar events/tasks
        docs: List of Document objects from initial semantic search
        
    Returns:
        List[Document]: Reranked documents sorted by relevance (most relevant first)
        
    Note:
        - Handles both calendar events and tasks with appropriate formatting
        - Includes location and timing information for better context
        - Limits to top 20 items to manage token usage
    """
    # Early exit for empty input
    if not docs:
        return []

    lines = []
    for i, d in enumerate(docs):
        title, desc = (d.page_content.split("\n", 1) + [""])[:2]
        title = _clean(title, 25)               # ≈15 tokens
        desc  = _clean(desc, 60)                # ≈25 tokens

        typ = d.metadata.get("type", "?")
        if typ == "event":
            start = d.metadata.get("start_dt", "")[:16].replace("T", " ")
            # Include location for better context
            location = d.metadata.get("location", "")
            if location:
                location_clean = _clean(location, 20)
                lines.append(
                    f"[{i}] 🗓 EVENT | {title} | {desc} | Location: {location_clean} (Starts: {start})")
            else:
                lines.append(
                    f"[{i}] 🗓 EVENT | {title} | {desc} (Starts: {start})")
        else:
            due = d.metadata.get("start_dt", "")[:10]
            lines.append(
                f"[{i}] ✅ TASK  | {title} | {desc} (Due: {due})")

    block = "\n".join(lines[:20])  # cap to 20 items

    prompt = f"""
    System:
    You are an assistant that ranks calendar items based on relevance to user questions.

    User:
    QUESTION: "{query}"

    CANDIDATES (each line starts with an index):
    {block}

    # INSTRUCTIONS
    1. For each candidate, assign a RELEVANCE score from 0 to 1:
        - 1.0 = Perfectly matches the question
        - 0.7-0.9 = Highly relevant 
        - 0.4-0.6 = Moderately relevant
        - 0.1-0.3 = Weakly relevant
        - 0.0 = Not relevant at all

    2. ONLY include candidates with score ≥ 0.4 in your output.
    3. If NO candidate scores ≥ 0.4, return an empty list [].
    4. Be strict - only return truly relevant items for the specific question.

    ## RELEVANCE GUIDELINES FOR SPORTS QUERIES
    - If question asks about "sport" or "sports": ONLY return events that are clearly sports-related
    - Sports keywords: soccer, football, basketball, tennis, hockey, game, match, tournament
    - Sports locations: stadium, field, court, arena, gym (NOT offices, conference rooms)
    - Business events at sports venues are NOT sports activities

    ## RANKING RULES
    - If the question contains "event", "summit", "conference", "seminar", etc. events outrank tasks.
    - If the question contains "task", "to-do", "deadline", etc. tasks outrank events.

    ## OUTPUT FORMAT
    Return ONLY a JSON array of indices, ordered by relevance.
    Examples: [0, 2, 1] or [1] or []

    Do NOT include explanations or other text.
    """.strip()

    try:
        reply = _llm.invoke(prompt).content
        if not isinstance(reply, str):
            return docs
        ids = json.loads(reply)
        assert isinstance(ids, list)
    except Exception:
        return docs
    logger.debug(ids)
    ranked = [docs[i] for i in ids if 0 <= i < len(docs)]
    logger.debug("rerank: %d", len(docs))

    return ranked