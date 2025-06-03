# utils/reranker.py
import json, re
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from utils.calendar_utils import html_to_discord_md
from utils.logging_config import logger

_llm = ChatOpenAI(model="gpt-4.1-nano", temperature=0)

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
            lines.append(
                f"[{i}] 🗓 EVENT | {title} | {desc} (Starts: {start})")
        else:
            due = d.metadata.get("start_dt", "")[:10]
            lines.append(
                f"[{i}] ✅ TASK  | {title} | {desc} (Due: {due})")

    block = "\n".join(lines[:20])  # cap to 20 items

    prompt = f"""
    System:
    You are an assistant that ranks calendar items.

    User:
    QUESTION: "{query}"

    CANDIDATES (each line starts with an index):
    {block}

    # INSTRUCTIONS
    1. For each candidate, assign a RELEVANCE score **from 0 to 1** 
        based on how well it answers the question, not just containing keywords.
        - 1 means highly relevant, 0 means not relevant at all.

    2. DISCARD every candidate with score < **0.5**. 
    3. If no candidate scores ≥ 0.5, reply with an empty list [].

    ## RANKING RULES
    - If the question contains “event”, "summit", "conference", "seminar", etc. events outrank tasks.
    - If the question contains “task”, “to-do”, "deadline", etc. tasks outrank events.

    ## OUTPUT FORMAT
    Reply with a JSON array of indices of the candidates in order of relevance.
    Example valid reply:  [1, 0]

    Do NOT output anything else.
    """.strip()

    try:
        reply = _llm.invoke(prompt).content
        ids = json.loads(reply)
        assert isinstance(ids, list)
    except Exception:
        return docs
    logger.debug(ids)
    ranked = [docs[i] for i in ids if 0 <= i < len(docs)]
    logger.debug("rerank: %d", len(docs))

    return ranked