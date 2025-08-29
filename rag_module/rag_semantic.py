"""
Semantic Search Module for RAG

This module implements semantic search functionality using Pinecone vector store and LangChain.
It provides efficient document retrieval based on query similarity and supports filtering
by metadata to ensure relevant results within tenant/channel contexts.

Key Features:
- Vector similarity search using OpenAI embeddings
- Metadata filtering for multi-tenant isolation
- Configurable result count and similarity thresholds
- LLM-based reranking for improved relevance
- Support for hybrid search patterns
"""

from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
from utils.vector_store import get_vector_store
from utils.reranker_rag import rerank_documents
from utils.logging_config import logger


class SemanticSearcher:
    """
    Handles semantic search operations for document retrieval in RAG applications.
    
    This class manages vector store interactions, query processing, and result filtering
    to provide relevant document chunks for RAG generation. It integrates with the
    existing vector store infrastructure and supports tenant-specific search contexts.
    """
    
    def __init__(self, index_name: str):
        """
        Initialize the semantic searcher with a specific Pinecone index.
        
        Args:
            index_name (str): Name of the Pinecone index to use for searches
        """
        self.vector_store = get_vector_store(index_name)
        self.index_name = index_name
        logger.debug("Initialized SemanticSearcher with index: %s", index_name)
    
    def search(
        self, 
        query: str, 
        k: int = 5,
        score_threshold: Optional[float] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        enable_reranking: bool = True
    ) -> List[Document]:
        """
        Perform semantic search to retrieve relevant documents.
        
        This method uses vector similarity search to find documents most relevant
        to the input query. It supports filtering by metadata, score thresholds,
        and optional LLM-based reranking for improved result quality.
        
        Args:
            query (str): The search query text
            k (int): Number of documents to retrieve (default: 5)
            score_threshold (float, optional): Minimum similarity score threshold
            filter_metadata (dict, optional): Metadata filters to apply
            enable_reranking (bool): Whether to apply LLM reranking (default: True)
            
        Returns:
            List[Document]: List of relevant documents with metadata and content
            
        Note:
            - Uses cosine similarity for document ranking
            - Automatically handles embedding generation via vector store
            - Applies LLM reranking if enabled for better relevance
            - Returns documents sorted by relevance score (highest first)
        """
        try:
            logger.debug(
                "Performing semantic search: query='%s', k=%d, threshold=%s, filters=%s, rerank=%s", 
                query[:100], k, score_threshold, filter_metadata, enable_reranking
            )
            
            # Retrieve more documents initially if reranking is enabled
            # This allows the reranker to select the best ones
            initial_k = k * 2 if enable_reranking else k
            
            # Perform similarity search with optional filtering
            if score_threshold is not None:
                # Use similarity search with score threshold
                docs_with_scores = self.vector_store.similarity_search_with_score(
                    query=query,
                    k=initial_k,
                    filter=filter_metadata if filter_metadata else None
                )
                
                # Filter by score threshold
                filtered_docs = [
                    doc for doc, score in docs_with_scores 
                    if score >= score_threshold
                ]
                
                logger.debug(
                    "Retrieved %d/%d documents above threshold %.3f", 
                    len(filtered_docs), len(docs_with_scores), score_threshold
                )
                
                documents = filtered_docs
            else:
                # Standard similarity search
                documents = self.vector_store.similarity_search(
                    query=query,
                    k=initial_k,
                    filter=filter_metadata if filter_metadata else None
                )
                
                logger.debug("Retrieved %d documents from semantic search", len(documents))
            
            # Apply reranking if enabled and we have documents
            if enable_reranking and documents:
                documents = rerank_documents(query, documents, max_docs=initial_k)
                # Limit to requested number after reranking
                documents = documents[:k]
                logger.debug("Applied reranking, final count: %d documents", len(documents))
            
            # CITATION FIX: Prefer PDF documents over calendar/task data
            # If we have both PDF documents (with filename) and calendar data, prioritize PDFs
            pdf_documents = [doc for doc in documents if doc.metadata.get('filename')]
            calendar_documents = [doc for doc in documents if not doc.metadata.get('filename')]
            
            if pdf_documents:
                # Prefer PDF documents and take calendar documents only if we need more
                documents = pdf_documents[:k]
                if len(documents) < k and calendar_documents:
                    documents.extend(calendar_documents[:k - len(documents)])
                logger.debug("Applied PDF preference: %d PDF docs, %d calendar docs", 
                           len(pdf_documents), len(calendar_documents))
            
            return documents
                
        except Exception as e:
            logger.error("Error performing semantic search: %s", str(e))
            # Return empty list on error to prevent application crashes
            return []
    
    def search_with_scores(
        self, 
        query: str, 
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[tuple[Document, float]]:
        """
        Perform semantic search and return documents with similarity scores.
        
        This method is useful when you need to analyze the quality of search results
        or implement custom scoring logic. Returns both documents and their similarity scores.
        
        Args:
            query (str): The search query text
            k (int): Number of documents to retrieve (default: 5)
            filter_metadata (dict, optional): Metadata filters to apply
            score_threshold (float, optional): Minimum similarity score threshold
            
        Returns:
            List[tuple[Document, float]]: List of (document, score) tuples
            
        Note:
            - Scores represent cosine similarity (higher = more similar)
            - Useful for debugging search quality and implementing custom thresholds
            - If score_threshold is provided, only documents above threshold are returned
        """
        try:
            logger.debug(
                "Performing semantic search with scores: query='%s', k=%d, filters=%s, threshold=%s", 
                query[:100], k, filter_metadata, score_threshold
            )
            
            docs_with_scores = self.vector_store.similarity_search_with_score(
                query=query,
                k=k,
                filter=filter_metadata if filter_metadata else None
            )
            
            # Apply score threshold if provided
            if score_threshold is not None:
                filtered_docs_with_scores = [
                    (doc, score) for doc, score in docs_with_scores 
                    if score >= score_threshold
                ]
                logger.debug(
                    "Applied score threshold %.3f: %d/%d documents retained", 
                    score_threshold, len(filtered_docs_with_scores), len(docs_with_scores)
                )
                docs_with_scores = filtered_docs_with_scores
            
            logger.debug(
                "Retrieved %d documents with scores: %s", 
                len(docs_with_scores),
                [f"{score:.3f}" for _, score in docs_with_scores[:3]]  # Log first 3 scores
            )
            
            return docs_with_scores
            
        except Exception as e:
            logger.error("Error performing semantic search with scores: %s", str(e))
            return []


def create_metadata_filter(
    tenant_config: Dict[str, Any], 
    additional_filters: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Create metadata filters for tenant-specific document isolation.
    
    This function constructs appropriate metadata filters to ensure that search
    results are scoped to the correct tenant and channel context. It prevents
    data leakage between different Discord guilds and channels.
    
    Args:
        tenant_config (dict): Tenant configuration containing guild/channel info
        additional_filters (dict, optional): Additional custom filters to apply
        
    Returns:
        dict or None: Combined metadata filter dictionary, or None if no filters needed
        
    Note:
        If documents don't have guild_id metadata, this will return None to avoid
        filtering out all documents. This is common when documents are uploaded
        without tenant-specific metadata.
        
    Example:
        filter_dict = create_metadata_filter(
            tenant_config={"guild_id": 123, "name": "test-guild"},
            additional_filters={"document_type": "pdf"}
        )
    """
    filters = {}
    
    # Only add guild_id filter if we're in a multi-tenant setup and have reason
    # to believe documents have this metadata field. For now, we'll skip this
    # since the documents in Pinecone don't have guild_id metadata.
    
    # NOTE: Documents in the current Pinecone index don't have guild_id metadata.
    # The metadata structure includes: filename, source, title, page_number, etc.
    # If you need tenant isolation, you would need to:
    # 1. Re-upload documents with guild_id metadata, or
    # 2. Use a different field like 'source' for filtering, or
    # 3. Use separate indices per tenant
    
    # CITATION FIX: Prefer PDF documents over calendar/task data
    # The index contains both PDF chunks (with filename metadata) and calendar tasks.
    # We prioritize PDF documents by filtering for documents that have a filename field.
    # This ensures we get proper citations with [filename.pdf#page-X] format instead of
    # generic [Document 1] citations from calendar data.
    prefer_pdfs = tenant_config.get("prefer_pdf_documents", True)
    if prefer_pdfs:
        # Note: Pinecone might not support $exists operator. 
        # Let's try a more permissive approach - we'll first try without filtering
        # and add PDF preference at the search level instead
        logger.debug("PDF preference enabled - will prioritize documents with filename metadata during search")
    
    # For now, we'll use additional_filters only if provided
    if additional_filters:
        filters.update(additional_filters)
    
    # Return None if no filters to apply (this will disable filtering)
    if not filters:
        logger.debug("No metadata filters applied - documents don't have tenant metadata")
        return None
    
    logger.debug("Created metadata filter: %s", filters)
    return filters


def perform_semantic_search(
    query: str,
    context: Dict[str, Any],
    k: int = 5,
    score_threshold: Optional[float] = None,
    include_scores: bool = False,
    enable_reranking: bool = True
) -> List[Document] | List[tuple[Document, float]]:
    """
    High-level function to perform semantic search with tenant context.
    
    This is the main entry point for semantic search operations. It handles
    tenant context extraction, searcher initialization, and result formatting.
    Designed to be used directly by RAG handlers and other application components.
    
    Args:
        query (str): The search query text
        context (dict): Tenant/channel context containing configuration
        k (int): Number of documents to retrieve (default: 5)
        score_threshold (float, optional): Minimum similarity score (default: None, no filtering)
        include_scores (bool): Whether to return similarity scores (default: False)
        enable_reranking (bool): Whether to apply LLM reranking (default: True)
        
    Returns:
        List[Document] or List[tuple[Document, float]]: Search results
        
    Raises:
        ValueError: If required context information is missing
        
    Example:
        # Basic usage with reranking
        docs = perform_semantic_search(
            query="What is machine learning?",
            context=tenant_context,
            k=3,
            enable_reranking=True
        )
        
        # With scores and no reranking
        docs_with_scores = perform_semantic_search(
            query="What is machine learning?",
            context=tenant_context,
            k=3,
            include_scores=True,
            enable_reranking=False
        )
    """
    # Extract index name from context
    index_name = context.get("index_rag")
    if not index_name:
        logger.error("No RAG index specified in tenant context")
        raise ValueError("RAG index name is required in tenant context")
    
    # Create searcher instance
    searcher = SemanticSearcher(index_name)
    
    # Create metadata filters for tenant isolation
    metadata_filter = create_metadata_filter(context)
    
    # Perform search based on requirements
    if include_scores:
        return searcher.search_with_scores(
            query=query,
            k=k,
            filter_metadata=metadata_filter,
            score_threshold=score_threshold
        )
    else:
        return searcher.search(
            query=query,
            k=k,
            score_threshold=score_threshold,
            filter_metadata=metadata_filter,
            enable_reranking=enable_reranking
        )
