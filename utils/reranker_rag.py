"""
Document Reranker for RAG

This module provides reranking capabilities to improve the relevance of retrieved documents
in RAG applications. It uses LLM-based scoring to reorder documents based on query relevance.
"""

import json
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from utils.logging_config import logger
from settings import settings

# Initialize LLM for reranking
_rerank_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=settings.openai_api_key
)

def rerank_documents(query: str, documents: List[Document], max_docs: int = 10) -> List[Document]:
    """
    Rerank documents based on their relevance to the query using LLM scoring.
    
    This function uses an LLM to evaluate the relevance of each document to the query
    and reorders them accordingly. Documents with low relevance scores are filtered out.
    
    Args:
        query (str): The user's query
        documents (List[Document]): Documents to rerank
        max_docs (int): Maximum number of documents to consider (default: 10)
        
    Returns:
        List[Document]: Reranked documents, ordered by relevance
        
    Note:
        - Only returns documents with relevance score >= 0.4
        - Uses efficient prompt engineering to minimize LLM costs
        - Falls back to original order if reranking fails
    """
    if not documents:
        return []
    
    # Limit number of documents to avoid token limits
    docs_to_rank = documents[:max_docs]
    
    try:
        # Prepare document summaries for reranking
        doc_summaries = []
        for i, doc in enumerate(docs_to_rank):
            # Create a concise summary of the document
            content_preview = _clean_content(doc.page_content, max_chars=300)
            
            # Include source information if available
            source_info = ""
            if doc.metadata and "source" in doc.metadata:
                source_info = f" (Source: {doc.metadata['source']})"
            elif doc.metadata and "filename" in doc.metadata:
                source_info = f" (File: {doc.metadata['filename']})"
            
            doc_summaries.append(f"[{i}] {content_preview}{source_info}")
        
        # Create reranking prompt
        candidates_text = "\n".join(doc_summaries)
        
        prompt = f"""You are an expert at evaluating document relevance for academic and educational queries.

QUERY: "{query}"

CANDIDATE DOCUMENTS (each line starts with an index):
{candidates_text}

INSTRUCTIONS:
1. Evaluate each document's relevance to the query on a scale from 0 to 1:
   - 1.0: Highly relevant, directly answers the query
   - 0.7-0.9: Very relevant, contains key information
   - 0.4-0.6: Moderately relevant, contains some useful information
   - 0.0-0.3: Not relevant or only tangentially related

2. ONLY include documents with score >= 0.4 in your response.

3. Consider:
   - Direct relevance to the query topic
   - Quality and depth of information
   - Complementary information value (different perspectives on same topic)
   - Academic/educational value
   - Specificity to the user's question

4. For queries about specific people, topics, or entities, include ALL documents that mention the subject, even if they provide different types of information (visual descriptions, personality traits, biographical details, etc.)

5. IMPORTANT: When multiple documents discuss the same person/entity, they should ALL be included as they provide complementary information. A visual description and personality description are BOTH valuable for understanding "who" someone is.

6. Respond with a JSON array of document indices, ordered by relevance (highest first).
   Example: [2, 0, 5]

7. If no documents score >= 0.4, respond with an empty array: []

Response (JSON array only):"""

        # Get reranking from LLM
        logger.debug("Reranking prompt: %s", prompt)
        response = _rerank_llm.invoke(prompt)
        logger.debug("Reranking response: %s", response.content.strip())
        
        ranked_indices = json.loads(response.content.strip())
        
        # Validate response
        if not isinstance(ranked_indices, list):
            logger.warning("Invalid reranking response format, using original order")
            return docs_to_rank
        
        # Reorder documents based on ranking
        reranked_docs = []
        for idx in ranked_indices:
            if isinstance(idx, int) and 0 <= idx < len(docs_to_rank):
                reranked_docs.append(docs_to_rank[idx])
        
        # Fallback: If we're missing documents that mention the same entity as the query,
        # check for potential false negatives and include them
        if len(reranked_docs) < len(docs_to_rank):
            reranked_docs = _apply_entity_fallback(query, docs_to_rank, reranked_docs)
        
        logger.debug(
            "Reranked %d documents: %d -> %d relevant documents",
            len(docs_to_rank), len(docs_to_rank), len(reranked_docs)
        )
        
        return reranked_docs
        
    except Exception as e:
        logger.warning("Error in document reranking: %s, using original order", str(e))
        return docs_to_rank


def _clean_content(content: str, max_chars: int = 300) -> str:
    """
    Clean and truncate document content for reranking.
    
    Args:
        content (str): Original document content
        max_chars (int): Maximum characters to keep
        
    Returns:
        str: Cleaned and truncated content
    """
    # Remove excessive whitespace and normalize
    cleaned = " ".join(content.split())
    
    # Truncate if too long
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "…"
    
    return cleaned


def rerank_with_scores(query: str, docs_with_scores: List[tuple[Document, float]]) -> List[Document]:
    """
    Rerank documents that come with similarity scores.
    
    This function combines semantic similarity scores with LLM-based relevance scoring
    for improved document ranking.
    
    Args:
        query (str): The user's query
        docs_with_scores (List[tuple[Document, float]]): Documents with similarity scores
        
    Returns:
        List[Document]: Reranked documents
    """
    if not docs_with_scores:
        return []
    
    # Extract documents for reranking
    documents = [doc for doc, _ in docs_with_scores]
    
    # Apply LLM reranking
    reranked_docs = rerank_documents(query, documents)
    
    logger.debug("Reranked %d documents with scores", len(reranked_docs))
    
    return reranked_docs


def _apply_entity_fallback(query: str, all_docs: List[Document], ranked_docs: List[Document]) -> List[Document]:
    """
    Apply fallback logic to include documents about the same entity that might have been filtered out.
    
    This function looks for proper nouns/names in the query and ensures all documents
    mentioning those entities are included, even if the reranker scored them low.
    """
    import re
    
    # Extract potential entity names from query (capitalized words)
    entity_pattern = r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b'
    entities = re.findall(entity_pattern, query)
    
    if not entities:
        return ranked_docs
    
    # Get indices of already ranked documents
    ranked_indices = set()
    for ranked_doc in ranked_docs:
        for i, doc in enumerate(all_docs):
            if doc.page_content == ranked_doc.page_content:
                ranked_indices.add(i)
                break
    
    # Check unranked documents for entity mentions
    additional_docs = []
    for i, doc in enumerate(all_docs):
        if i not in ranked_indices:
            # Check if any entity from the query appears in this document
            for entity in entities:
                if entity.lower() in doc.page_content.lower():
                    logger.debug("Fallback: Including document %d that mentions entity '%s'", i, entity)
                    additional_docs.append(doc)
                    break
    
    # Combine ranked docs with additional entity-related docs
    result = ranked_docs + additional_docs
    logger.debug("Entity fallback: %d ranked + %d additional = %d total docs", 
                len(ranked_docs), len(additional_docs), len(result))
    
    return result
