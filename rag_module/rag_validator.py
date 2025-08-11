"""
RAG Input Validation and Safety Module

This module provides comprehensive input validation, sanitization, and safety checks
for RAG queries to prevent abuse, injection attacks, and system overload.

Key Features:
- Query length and content validation
- Input sanitization and cleaning
- Rate limiting support utilities
- Safety checks for malicious content
- Token counting and context management
"""

import re
import html
from typing import Dict, Any, Optional, Tuple
from utils.logging_config import logger

# Configuration constants
MAX_QUERY_LENGTH = 2000  # Maximum characters in a query
MIN_QUERY_LENGTH = 3     # Minimum meaningful query length
MAX_TOKENS_PER_REQUEST = 12000  # Conservative limit for gpt-4o-mini context window
ESTIMATED_CHARS_PER_TOKEN = 4  # Rough estimate for token counting

# Patterns for potentially harmful content
SUSPICIOUS_PATTERNS = [
    r'<script[^>]*>.*?</script>',  # Script tags (updated)
    r'<script[^>]*>',             # Opening script tags
    r'javascript:',               # JavaScript URLs
    r'data:text/html',            # Data URLs
    r'eval\s*\(',                # eval() calls
    r'exec\s*\(',                # exec() calls
    r'\bSELECT\b.*\bFROM\b',      # SQL injection patterns
    r'\bUNION\b.*\bSELECT\b',     # SQL UNION attacks
    r'\bDROP\b.*\bTABLE\b',       # SQL DROP commands
    r'<[^>]*on\w+\s*=',           # Event handlers (onclick, onload, etc.)
    r'alert\s*\(',                # JavaScript alerts
]

class QueryValidationError(Exception):
    """Raised when query validation fails."""
    pass

class ContextTooLargeError(Exception):
    """Raised when context exceeds token limits."""
    pass

def validate_query(query: str, user_id: Optional[str] = None) -> str:
    """
    Validate and sanitize user query input.
    
    Args:
        query (str): Raw user query
        user_id (str, optional): User ID for logging purposes
        
    Returns:
        str: Cleaned and validated query
        
    Raises:
        QueryValidationError: If query fails validation
    """
    if not isinstance(query, str):
        raise QueryValidationError("Query must be a string")
    
    # Remove excessive whitespace and normalize
    cleaned_query = ' '.join(query.strip().split())
    
    # Check length constraints
    if len(cleaned_query) < MIN_QUERY_LENGTH:
        raise QueryValidationError(f"Query too short (minimum {MIN_QUERY_LENGTH} characters)")
    
    if len(cleaned_query) > MAX_QUERY_LENGTH:
        raise QueryValidationError(f"Query too long (maximum {MAX_QUERY_LENGTH} characters)")
    
    # Check for empty or whitespace-only queries
    if not cleaned_query or cleaned_query.isspace():
        raise QueryValidationError("Query cannot be empty or contain only whitespace")
    
    # Sanitize HTML entities and potential injection attempts
    sanitized_query = html.escape(cleaned_query, quote=False)
    
    # Check for suspicious patterns
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, sanitized_query, re.IGNORECASE):
            logger.warning("Suspicious pattern detected in query from user %s: %s", 
                         user_id or "unknown", pattern)
            raise QueryValidationError("Query contains potentially harmful content")
    
    # Additional safety: Remove any remaining HTML-like tags
    sanitized_query = re.sub(r'<[^>]+>', '', sanitized_query)
    
    logger.debug("Query validated successfully for user %s: length=%d", 
                user_id or "unknown", len(sanitized_query))
    
    return sanitized_query

def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a text string.
    
    This is a rough estimation. For production, consider using tiktoken library
    for more accurate token counting.
    
    Args:
        text (str): Text to estimate tokens for
        
    Returns:
        int: Estimated number of tokens
    """
    if not text:
        return 0
    
    # Basic estimation: chars/4 + adjustment for punctuation and structure
    base_tokens = len(text) // ESTIMATED_CHARS_PER_TOKEN
    
    # Add tokens for structural elements (newlines, punctuation, etc.)
    structural_tokens = text.count('\n') + text.count('.') + text.count(',')
    
    return base_tokens + structural_tokens

def validate_context_size(context: str, query: str) -> Tuple[str, bool]:
    """
    Validate that context + query fit within token limits.
    
    Args:
        context (str): Formatted context from documents
        query (str): User query
        
    Returns:
        Tuple[str, bool]: (potentially_truncated_context, was_truncated)
        
    Raises:
        ContextTooLargeError: If even truncated context is too large
    """
    # Estimate tokens for query and template overhead
    query_tokens = estimate_tokens(query)
    template_overhead = 200  # Estimated tokens for prompt template
    
    available_tokens = MAX_TOKENS_PER_REQUEST - query_tokens - template_overhead
    
    if available_tokens <= 0:
        raise ContextTooLargeError("Query too long to process")
    
    context_tokens = estimate_tokens(context)
    
    if context_tokens <= available_tokens:
        # Context fits within limits
        return context, False
    
    # Need to truncate context
    logger.warning("Context too large (%d tokens), truncating to fit %d tokens", 
                  context_tokens, available_tokens)
    
    # Calculate target character count for truncation
    target_chars = available_tokens * ESTIMATED_CHARS_PER_TOKEN
    
    if target_chars <= 0:
        raise ContextTooLargeError("Cannot fit any context within token limits")
    
    # Truncate context intelligently (try to break at document boundaries)
    truncated_context = _smart_truncate_context(context, target_chars)
    
    return truncated_context, True

def _smart_truncate_context(context: str, target_chars: int) -> str:
    """
    Intelligently truncate context to fit within character/token limits.
    
    Tries to break at document boundaries to maintain coherence.
    
    Args:
        context (str): Full context string
        target_chars (int): Target character count
        
    Returns:
        str: Truncated context
    """
    if len(context) <= target_chars:
        return context
    
    # Try to find good breaking points (document boundaries)
    doc_boundaries = []
    for i, line in enumerate(context.split('\n')):
        if line.startswith('Document '):
            doc_boundaries.append((i, context.find(line)))
    
    if doc_boundaries:
        # Find the last complete document that fits
        current_pos = 0
        for doc_idx, char_pos in doc_boundaries:
            if char_pos >= target_chars:
                break
            current_pos = char_pos
        
        # Find the end of the last complete document
        next_doc_start = target_chars
        for doc_idx, char_pos in doc_boundaries:
            if char_pos > current_pos:
                next_doc_start = char_pos
                break
        
        # Truncate at the end of the last complete document or at target
        truncate_at = min(next_doc_start - 1, target_chars)
        truncated = context[:truncate_at].rstrip()
        
        # Add truncation notice
        truncated += "\n\n[... Context truncated due to length limits ...]"
        
        return truncated
    
    # Fallback: simple truncation with notice
    truncated = context[:target_chars - 50].rstrip()
    truncated += "\n\n[... Context truncated due to length limits ...]"
    
    return truncated

def validate_tenant_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate tenant context contains required fields for RAG operations.
    
    Args:
        context (dict): Tenant context dictionary
        
    Returns:
        dict: Validated context
        
    Raises:
        ValueError: If required fields are missing or invalid
    """
    required_fields = ['index_rag']
    
    for field in required_fields:
        if field not in context:
            raise ValueError(f"Missing required field in tenant context: {field}")
        
        if not context[field] or not isinstance(context[field], str):
            raise ValueError(f"Invalid value for {field} in tenant context")
    
    # Validate index name format (basic check)
    index_name = context['index_rag']
    if not re.match(r'^[a-zA-Z0-9\-_]+$', index_name):
        raise ValueError(f"Invalid index name format: {index_name}")
    
    logger.debug("Tenant context validated successfully for index: %s", index_name)
    
    return context

def is_query_safe_for_processing(query: str) -> bool:
    """
    Quick safety check for query content.
    
    Args:
        query (str): Query to check
        
    Returns:
        bool: True if query appears safe to process
    """
    try:
        validate_query(query)
        return True
    except QueryValidationError:
        return False
