from typing import List
from langchain_core.documents import Document
from utils.logging_config import logger

REL_KEEP = 0.5          # keep results whose score ≥ 65 % of best
MIN_SCORE = 0.15
def hybrid_search_relative_band(
    query: str,
    k: int,
    meta_filter: dict,
    index,
    embed,
) -> List[Document]:
    """
    Hybrid (dense + sparse) search that keeps all matches whose hybrid score
    is within REL_KEEP * best_score.  No global threshold required.

    Args:
        query (str):          user search text (may be empty)
        k (int):              desired number of results to return
        meta_filter (dict):   Pinecone metadata filter
        index (pinecone.Index): live index handle
        embed (Embeddings):   embedding model for dense query vector

    Returns:
        List[Document]: ranked documents, size ≤ k
    """
    # 1 — embed query
    dense = embed.embed_query(query)

    # 2 — retrieve a slightly larger pool to allow pruning
    pool_k = max(30, k * 4)
    res = index.query(
        vector=dense,
        text=query,                     # server-side BM25
        top_k=pool_k,
        filter=meta_filter,
        include_metadata=True,
    )

    matches = res["matches"]
    if not matches:
        return []

    # 3 — compute adaptive cut-off
    best   = matches[0]["score"]
    cutoff = best * REL_KEEP

    # 4 — keep everything above cut-off until we reach k docs
    docs: List[Document] = []
    for m in matches:
        if m["score"] < MIN_SCORE:
            continue
        if m["score"] < cutoff or len(docs) >= k:
            break                      # sorted → safe early stop
        text = m["metadata"].get("text") or m["metadata"].get("context", "")
        docs.append(Document(page_content=text, metadata=m["metadata"]))

    return docs
