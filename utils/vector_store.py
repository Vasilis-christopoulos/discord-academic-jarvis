from pinecone import Pinecone, ServerlessSpec
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from utils.logging_config import logger
from settings import settings  # holds settings.pinecone_api_key

EMBED_DIM  = 3072  # text-embedding-3-large

# ── new SDK client ────────────────────────────────────────────────────────────
pc = Pinecone(api_key=settings.pinecone_api_key)
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

def get_vector_store(index_name: str) -> PineconeVectorStore:
    """
    Get or create a Pinecone vector store for calendar data.
    
    This function manages Pinecone vector database operations for storing and retrieving
    calendar-related embeddings. It creates a new index if it doesn't exist, or connects
    to an existing one.
    
    Args:
        index_name (str): The name of the Pinecone index to use or create
        
    Returns:
        PineconeVectorStore: A vector store instance configured with the specified
                           Pinecone index and embedding model
                           
    Note:
        - Creates serverless index on AWS us-east-1 if index doesn't exist
        - Uses cosine similarity metric for vector comparisons
        - Index dimension is set to EMBED_DIM constant
        - Requires global 'pc' (Pinecone client) and 'embeddings' objects to be initialized
    """
    if index_name not in pc.list_indexes().names():
        logger.info("Creating index %s …", index_name)
        pc.create_index(
            name=index_name,
            dimension=EMBED_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    index      = pc.Index(index_name)
    logger.info("Using Pinecone index: %s", index_name)
    return PineconeVectorStore(index=index, embedding=embeddings)
