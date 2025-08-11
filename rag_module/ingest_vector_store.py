# rag_module/ingest_vector_store.py
"""
Vector-store helper for the ingest Lambda.

Uses the new langchain-pinecone integration (≥0.1.0) plus the
Pinecone v6 SDK.
"""

from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore           # NEW
from pinecone import Pinecone, ServerlessSpec                # SDK v6+

from settings_ingest import settings  # your slim Lambda settings


EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM   = 3072


# ──────────────────────────────────────────────────────────────
# build (or connect to) Pinecone index and return an LC store
# ──────────────────────────────────────────────────────────────
def get_vector_store(index_name: str) -> PineconeVectorStore:
    """
    Return a langchain-pinecone VectorStore bound to *index_name*.
    Creates the serverless index (cosine, AWS us-east-1) if needed.
    """
    pc = Pinecone(api_key=settings.pinecone_api_key)         # new client

    if index_name not in pc.list_indexes().names():
        pc.create_index(
            name=index_name,
            dimension=EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    index = pc.Index(index_name)                             # real SDK Index
    embed = OpenAIEmbeddings(model=EMBED_MODEL)

    # text_key is mandatory with langchain-pinecone ≥0.1.0
    return PineconeVectorStore(index=index, embedding=embed, text_key="text")


