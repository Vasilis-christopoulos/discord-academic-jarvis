# calendar_module/vs_calendar.py
from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from utils.logging_config import logger
from settings import settings  # holds settings.pinecone_api_key

INDEX_NAME = "calendar-hybrid"
EMBED_DIM  = 3072  # text-embedding-3-large

# ── new SDK client ────────────────────────────────────────────────────────────
pc = Pinecone(api_key=settings.pinecone_api_key)

if INDEX_NAME not in pc.list_indexes().names():
    logger.info("Creating index %s …", INDEX_NAME)
    pc.create_index(
        name=INDEX_NAME,
        dimension=EMBED_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )

index      = pc.Index(INDEX_NAME)
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

def get_calendar_store() -> PineconeVectorStore:
    logger.info("Using Pinecone index: %s", INDEX_NAME)
    return PineconeVectorStore(index=index, embedding=embeddings)
