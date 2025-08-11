"""
RAG Handler Module

This module implements the main RAG (Retrieval-Augmented Generation) functionality
for the Discord Academic Jarvis bot. It orchestrates document retrieval, context
preparation, and response generation using OpenAI's language models.

Key Features:
- Semantic search-based document retrieval
- Context-aware response generation
- Tenant-specific knowledge isolation
- Efficient prompt engineering for academic content
- Error handling and fallback responses
"""

import asyncio
from typing import Dict, Any, List, Optional
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from .rag_semantic import perform_semantic_search
from .rag_validator import (
    validate_query, 
    validate_tenant_context, 
    validate_context_size,
    QueryValidationError,
    ContextTooLargeError
)
from .rag_resilience import (
    safe_execute,
    RetryConfig,
    RAGTimeoutError,
    RAGRetryExhaustedError,
    RAGCircuitBreakerError
)
from utils.logging_config import logger
from settings import settings


# Initialize OpenAI chat model with timeout settings
llm = ChatOpenAI(
    model="gpt-4o-mini",  # Using efficient model for cost optimization
    temperature=0.1,  # Low temperature for consistent, factual responses
    api_key=settings.openai_api_key,
    request_timeout=30.0,  # 30 second timeout for API calls
    max_retries=0  # We handle retries in our resilience layer
)

# RAG prompt template for academic content with citation support
RAG_PROMPT_TEMPLATE = """You are an intelligent academic assistant helping students with their coursework and research. 

Use the following context information to answer the user's question. The context comes from relevant course materials, documents, and academic resources.

Context Information:
{context}

User Question: {question}

Instructions:
- Provide a clear, accurate, and helpful response based on the context
- If the context doesn't contain enough information to fully answer the question, say so honestly
- Include specific details and examples from the context when relevant
- Use an academic but accessible tone
- IMPORTANT: When referencing information from the context, include the source citation provided in [brackets]
- At the end of your response, provide a "Sources:" section listing all citations used
- Keep your response focused and concise while being thorough

Answer:"""

# Create prompt template
rag_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=RAG_PROMPT_TEMPLATE
)


async def respond(query: str, context: dict, user_id: Optional[str] = None) -> str:
    """
    Generate a response to a user query using RAG (Retrieval-Augmented Generation).
    
    This function orchestrates the complete RAG pipeline with comprehensive validation,
    error handling, and safety measures:
    1. Validates and sanitizes user input
    2. Performs semantic search to retrieve relevant documents
    3. Manages context window and token limits
    4. Generates a response using the language model with retry logic
    5. Handles errors gracefully with appropriate fallback responses
    
    Args:
        query (str): The user's question or query
        context (dict): Tenant/channel context containing configuration and metadata
        user_id (str, optional): User ID for logging and rate limiting
        
    Returns:
        str: Generated response based on retrieved context
        
    Raises:
        QueryValidationError: If query validation fails
        ValueError: If tenant context is invalid
    """
    # Generate correlation ID for request tracking
    import uuid
    correlation_id = str(uuid.uuid4())[:8]
    
    try:
        logger.info("Processing RAG query [%s]: '%s' (user: %s)", 
                   correlation_id, query[:100], user_id or "unknown")
        
        # Step 1: Validate and sanitize input
        try:
            validated_query = validate_query(query, user_id)
            validated_context = validate_tenant_context(context)
        except (QueryValidationError, ValueError) as e:
            logger.warning("Input validation failed [%s]: %s", correlation_id, str(e))
            return _generate_validation_error_response(str(e))
        
        # Step 2: Retrieve relevant documents using semantic search with resilience
        documents = await _retrieve_documents_safely(
            validated_query, 
            validated_context, 
            correlation_id
        )
        
        if not documents:
            logger.warning("No relevant documents found [%s]: '%s'", 
                          correlation_id, validated_query[:50])
            return _generate_no_context_response(validated_query)
        
        # Step 3: Prepare and validate context size
        try:
            formatted_context, was_truncated = _format_and_validate_context(
                documents, 
                validated_query,
                correlation_id
            )
        except ContextTooLargeError as e:
            logger.error("Context too large [%s]: %s", correlation_id, str(e))
            return _generate_context_error_response(validated_query)
        
        # Step 4: Generate response using language model with resilience
        response = await _generate_response_safely(
            validated_query, 
            formatted_context, 
            correlation_id,
            was_truncated
        )
        
        logger.info("Successfully generated RAG response [%s]: %d chars (user: %s)", 
                   correlation_id, len(response), user_id or "unknown")
        return response
        
    except (RAGTimeoutError, RAGRetryExhaustedError, RAGCircuitBreakerError) as e:
        logger.error("RAG service error [%s]: %s", correlation_id, str(e))
        return _generate_service_error_response(query, str(e))
    except Exception as e:
        logger.error("Unexpected error in RAG response generation [%s]: %s", 
                    correlation_id, str(e), exc_info=True)
        return _generate_error_response(query, str(e))


async def _retrieve_documents_safely(
    query: str, 
    context: Dict[str, Any], 
    correlation_id: str
) -> List[Document]:
    """
    Retrieve relevant documents using semantic search with comprehensive error handling.
    
    Args:
        query (str): Validated search query
        context (dict): Validated tenant context
        correlation_id (str): Request correlation ID for logging
        
    Returns:
        List[Document]: Retrieved documents (empty list on error)
    """
    async def _retrieve():
        # Run semantic search with reranking in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: perform_semantic_search(
                query=query,
                context=context,
                k=5,  # Retrieve top 5 most relevant documents
                score_threshold=0.3,  # Lowered threshold for better recall
                include_scores=False,
                enable_reranking=True  # Enable LLM reranking for better results
            )
        )
    
    try:
        # Use safe_execute with vector store service resilience
        documents = await safe_execute(
            _retrieve,
            service_name="vector_store",
            timeout_seconds=30.0,
            retry_config=RetryConfig(max_attempts=3, base_delay=2.0)
        )
        
        logger.debug("Retrieved %d documents [%s]: '%s'", 
                    len(documents), correlation_id, query[:50])
        return documents
        
    except (RAGTimeoutError, RAGRetryExhaustedError, RAGCircuitBreakerError) as e:
        logger.error("Document retrieval failed [%s]: %s", correlation_id, str(e))
        raise  # Re-raise to be handled by main respond function
    except Exception as e:
        logger.error("Unexpected error retrieving documents [%s]: %s", 
                    correlation_id, str(e))
        return []  # Return empty list for graceful degradation


async def _retrieve_documents(query: str, context: Dict[str, Any]) -> List[Document]:
    """
    Legacy function for backward compatibility. Use _retrieve_documents_safely instead.
    """
    return await _retrieve_documents_safely(query, context, "legacy")


def _format_and_validate_context(
    documents: List[Document], 
    query: str,
    correlation_id: str
) -> tuple[str, bool]:
    """
    Format retrieved documents into context and validate size constraints.
    
    Args:
        documents (List[Document]): Retrieved documents
        query (str): User query for token estimation
        correlation_id (str): Request correlation ID for logging
        
    Returns:
        tuple[str, bool]: (formatted_context, was_truncated)
        
    Raises:
        ContextTooLargeError: If context cannot fit within token limits
    """
    if not documents:
        return "No relevant context available.", False
    
    # Format documents with citations
    formatted_context = _format_context(documents)
    
    # Validate and potentially truncate context to fit token limits
    validated_context, was_truncated = validate_context_size(formatted_context, query)
    
    if was_truncated:
        logger.info("Context truncated for token limits [%s]: %d -> %d chars", 
                   correlation_id, len(formatted_context), len(validated_context))
    
    logger.debug("Context formatted and validated [%s]: %d docs, %d chars, truncated=%s", 
                correlation_id, len(documents), len(validated_context), was_truncated)
    
    return validated_context, was_truncated


def _format_context(documents: List[Document]) -> str:
    """
    Format retrieved documents into a coherent context string with citations.
    
    Args:
        documents (List[Document]): Retrieved documents
        
    Returns:
        str: Formatted context string with citation anchors
    """
    if not documents:
        return "No relevant context available."
    
    context_parts = []
    citations_used = set()
    
    for i, doc in enumerate(documents, 1):
        # Extract citation anchor from metadata
        citation_anchor = None
        source_info = ""
        
        if doc.metadata:
            # Try to get citation_anchor first
            if "citation_anchor" in doc.metadata:
                citation_anchor = doc.metadata["citation_anchor"]
                citations_used.add(citation_anchor)
            
            # Build source info for context
            if "source" in doc.metadata:
                source_info = f" (Source: {doc.metadata['source']})"
            elif "filename" in doc.metadata:
                source_info = f" (File: {doc.metadata['filename']})"
            
            # If no citation_anchor, create one from available metadata
            if not citation_anchor:
                if "source" in doc.metadata:
                    citation_anchor = f"[{doc.metadata['source']}]"
                elif "filename" in doc.metadata:
                    citation_anchor = f"[{doc.metadata['filename']}]"
                else:
                    citation_anchor = f"[Document {i}]"
                citations_used.add(citation_anchor)
        else:
            citation_anchor = f"[Document {i}]"
            citations_used.add(citation_anchor)
        
        # Format each document chunk with citation
        context_parts.append(f"Document {i}{source_info}:\n{doc.page_content}\n[Citation: {citation_anchor}]")
    
    formatted_context = "\n\n".join(context_parts)
    
    logger.debug("Formatted context with %d documents and %d citations, total length: %d chars", 
                len(documents), len(citations_used), len(formatted_context))
    
    return formatted_context


async def _generate_response_safely(
    query: str, 
    context: str, 
    correlation_id: str,
    was_truncated: bool = False
) -> str:
    """
    Generate a response using the language model with comprehensive error handling.
    
    Args:
        query (str): User query
        context (str): Formatted and validated context
        correlation_id (str): Request correlation ID for logging
        was_truncated (bool): Whether context was truncated
        
    Returns:
        str: Generated response
        
    Raises:
        RAGTimeoutError, RAGRetryExhaustedError, RAGCircuitBreakerError: On service failures
    """
    async def _generate():
        # Format the prompt with query and context
        formatted_prompt = rag_prompt.format(
            question=query,
            context=context
        )
        
        # Generate response asynchronously
        response = await llm.ainvoke(formatted_prompt)
        
        # Extract text content from response
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Add truncation notice if context was truncated
        if was_truncated:
            response_text += "\n\n*Note: Some context was truncated due to length limits. " \
                           "For more complete information, try a more specific query.*"
        
        return response_text
    
    try:
        # Use safe_execute with LLM service resilience
        response_text = await safe_execute(
            _generate,
            service_name="openai_llm",
            timeout_seconds=45.0,  # Longer timeout for LLM generation
            retry_config=RetryConfig(
                max_attempts=3, 
                base_delay=5.0,  # Longer delays for LLM retries
                max_delay=60.0
            )
        )
        
        logger.debug("Generated response [%s]: %d chars", correlation_id, len(response_text))
        return response_text
        
    except (RAGTimeoutError, RAGRetryExhaustedError, RAGCircuitBreakerError) as e:
        logger.error("LLM response generation failed [%s]: %s", correlation_id, str(e))
        raise  # Re-raise to be handled by main respond function


async def _generate_response(query: str, context: str) -> str:
    """
    Legacy function for backward compatibility. Use _generate_response_safely instead.
    """
    return await _generate_response_safely(query, context, "legacy")


def _generate_validation_error_response(error_message: str) -> str:
    """
    Generate a response for input validation errors.
    
    Args:
        error_message (str): Validation error message
        
    Returns:
        str: User-friendly validation error response
    """
    return (
        "I couldn't process your question due to an input issue. Please check that:\n\n"
        "• Your question is between 3 and 2000 characters\n"
        "• It doesn't contain special characters or formatting\n"
        "• It's a genuine academic question\n\n"
        "Please try rephrasing your question and ask again."
    )


def _generate_context_error_response(query: str) -> str:
    """
    Generate a response when context is too large to process.
    
    Args:
        query (str): User query
        
    Returns:
        str: Context error response
    """
    return (
        "I found relevant information for your question, but it's too extensive to process "
        "in a single response. To get a more focused answer, please:\n\n"
        "• Make your question more specific\n"
        "• Ask about a particular aspect of the topic\n"
        "• Break down complex questions into smaller parts\n\n"
        "This will help me provide you with a more targeted and useful response."
    )


def _generate_service_error_response(query: str, error_message: str) -> str:
    """
    Generate a response for service-level errors (timeouts, circuit breakers, etc.).
    
    Args:
        query (str): User query
        error_message (str): Service error message
        
    Returns:
        str: Service error response
    """
    return (
        "I'm currently experiencing high demand or technical difficulties. "
        "Please try your question again in a few moments.\n\n"
        "If this problem continues, you can:\n"
        "• Wait a minute and try again\n"
        "• Simplify your question\n"
        "• Contact your instructor for immediate help\n\n"
        "I apologize for the inconvenience!"
    )


def _generate_no_context_response(query: str) -> str:
    """
    Generate a response when no relevant context is found.
    
    Args:
        query (str): User query
        
    Returns:
        str: Fallback response
    """
    return (
        "I couldn't find relevant information in the available course materials "
        "to answer your question. This might be because:\n\n"
        "• The topic isn't covered in the uploaded documents\n"
        "• The question is too specific or uses different terminology\n"
        "• The relevant materials haven't been uploaded yet\n\n"
        "Try rephrasing your question or ask your instructor about additional resources.\n\n"
        "**Sources:** No relevant sources found in the knowledge base."
    )


def _generate_error_response(query: str, error: str) -> str:
    """
    Generate an error response when something goes wrong.
    
    Args:
        query (str): User query
        error (str): Error message
        
    Returns:
        str: Error response
    """
    logger.error("RAG error for query '%s': %s", query[:50], error)
    
    return (
        "I'm sorry, but I encountered an error while processing your question. "
        "Please try again in a moment. If the problem persists, please contact "
        "the administrator."
    )
    