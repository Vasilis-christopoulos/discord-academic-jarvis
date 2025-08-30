# rag_module/ingest_vector_store.py
"""
Vector-store helper for the ingest Lambda.
Uses Pinecone v6 SDK with proper Lambda-compatible configuration.
"""

import os
from typing import List, Dict, Any
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from pinecone import Pinecone, ServerlessSpec
from settings_ingest import settings

# Configure for Lambda environment
os.environ["PINECONE_POOL_THREADS"] = "1"

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072

class LambdaCompatibleVectorStore:
    """
    Lambda-compatible vector store that bypasses LangChain's 
    multiprocessing issues by using Pinecone SDK directly.
    """
    
    def __init__(self, index_name: str):
        self.pc = Pinecone(
            api_key=settings.pinecone_api_key,
            pool_threads=1
        )
        
        # Create index if it doesn't exist
        if index_name not in self.pc.list_indexes().names():
            self.pc.create_index(
                name=index_name,
                dimension=EMBED_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        
        self.index = self.pc.Index(index_name)
        self.embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
    
    def add_documents(self, documents: List[Document]) -> List[str]:
        """
        Add documents using direct Pinecone SDK for better Lambda compatibility.
        Returns list of document IDs.
        """
        if not documents:
            return []
        
        # Extract texts and metadata
        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        
        # Generate embeddings
        embeddings = self.embeddings.embed_documents(texts)
        
        # Prepare vectors for Pinecone
        vectors = []
        doc_ids = []
        
        for i, (text, embedding, metadata) in enumerate(zip(texts, embeddings, metadatas)):
            doc_id = f"doc_{hash(text)}_{i}"
            doc_ids.append(doc_id)
            
            # Add text to metadata (required for retrieval)
            metadata_with_text = {**metadata, "text": text}
            
            vectors.append({
                "id": doc_id,
                "values": embedding,
                "metadata": metadata_with_text
            })
        
        # Batch upsert - much more efficient than individual operations
        batch_size = 100  # Pinecone's recommended batch size
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            self.index.upsert(vectors=batch)
        
        return doc_ids


def get_vector_store(index_name: str) -> LambdaCompatibleVectorStore:
    """
    Return a Lambda-compatible vector store that doesn't use multiprocessing.
    Much faster than the monkey-patched version.
    """
    return LambdaCompatibleVectorStore(index_name)


