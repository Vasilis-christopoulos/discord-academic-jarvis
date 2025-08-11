"""
RAG Error Handling and Resilience Module

This module provides comprehensive error handling, retry logic, timeout management,
and circuit breaker patterns for robust RAG operations in production environments.

Key Features:
- Configurable retry logic with exponential backoff
- Timeout handling for external API calls
- Circuit breaker pattern for failing services
- Detailed error classification and recovery strategies
- Performance monitoring and alerting support
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, TypeVar, Union
from enum import Enum
from dataclasses import dataclass
from functools import wraps
from utils.logging_config import logger

T = TypeVar('T')

class ErrorType(Enum):
    """Classification of different error types for appropriate handling."""
    NETWORK_ERROR = "network_error"
    API_RATE_LIMIT = "api_rate_limit" 
    API_QUOTA_EXCEEDED = "api_quota_exceeded"
    TIMEOUT_ERROR = "timeout_error"
    VALIDATION_ERROR = "validation_error"
    VECTOR_STORE_ERROR = "vector_store_error"
    LLM_ERROR = "llm_error"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True

@dataclass
class CircuitBreakerState:
    """State tracking for circuit breaker pattern."""
    failure_count: int = 0
    last_failure_time: float = 0
    state: str = "closed"  # closed, open, half_open
    failure_threshold: int = 5
    recovery_timeout: float = 60.0

# Global circuit breaker states for different services
_circuit_breakers: Dict[str, CircuitBreakerState] = {}

class RAGTimeoutError(Exception):
    """Raised when operations exceed configured timeouts."""
    pass

class RAGRetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""
    pass

class RAGCircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass

def classify_error(error: Exception) -> ErrorType:
    """
    Classify an error to determine appropriate handling strategy.
    
    Args:
        error (Exception): The error to classify
        
    Returns:
        ErrorType: Classification of the error
    """
    error_str = str(error).lower()
    error_type_name = type(error).__name__.lower()
    
    # Network and connection errors
    if any(keyword in error_str for keyword in ['connection', 'network', 'timeout', 'unreachable']):
        return ErrorType.NETWORK_ERROR
    
    # API rate limiting
    if any(keyword in error_str for keyword in ['rate limit', 'too many requests', '429']):
        return ErrorType.API_RATE_LIMIT
    
    # API quota exceeded
    if any(keyword in error_str for keyword in ['quota', 'billing', 'credits', 'usage limit']):
        return ErrorType.API_QUOTA_EXCEEDED
    
    # Timeout errors
    if 'timeout' in error_type_name or isinstance(error, asyncio.TimeoutError):
        return ErrorType.TIMEOUT_ERROR
    
    # Validation errors
    if any(keyword in error_type_name for keyword in ['validation', 'value']):
        return ErrorType.VALIDATION_ERROR
    
    # Vector store specific errors
    if any(keyword in error_str for keyword in ['pinecone', 'vector', 'index']):
        return ErrorType.VECTOR_STORE_ERROR
    
    # LLM/OpenAI specific errors
    if any(keyword in error_str for keyword in ['openai', 'llm', 'model', 'tokens']):
        return ErrorType.LLM_ERROR
    
    return ErrorType.UNKNOWN_ERROR

def should_retry(error: Exception, attempt: int, max_attempts: int) -> bool:
    """
    Determine if an operation should be retried based on error type and attempt count.
    
    Args:
        error (Exception): The error that occurred
        attempt (int): Current attempt number (1-indexed)
        max_attempts (int): Maximum allowed attempts
        
    Returns:
        bool: True if operation should be retried
    """
    if attempt >= max_attempts:
        return False
    
    error_type = classify_error(error)
    
    # Never retry these error types
    no_retry_errors = {
        ErrorType.VALIDATION_ERROR,
        ErrorType.API_QUOTA_EXCEEDED,
    }
    
    if error_type in no_retry_errors:
        return False
    
    # Always retry these error types (with backoff)
    retry_errors = {
        ErrorType.NETWORK_ERROR,
        ErrorType.TIMEOUT_ERROR,
        ErrorType.API_RATE_LIMIT,
    }
    
    return error_type in retry_errors or error_type == ErrorType.UNKNOWN_ERROR

async def calculate_retry_delay(attempt: int, config: RetryConfig, error: Optional[Exception] = None) -> float:
    """
    Calculate delay before next retry attempt.
    
    Args:
        attempt (int): Current attempt number (1-indexed)
        config (RetryConfig): Retry configuration
        error (Exception, optional): The error that caused the retry
        
    Returns:
        float: Delay in seconds
    """
    if attempt <= 1:
        return 0
    
    # Base exponential backoff
    delay = config.base_delay * (config.exponential_base ** (attempt - 2))
    
    # Apply maximum delay limit
    delay = min(delay, config.max_delay)
    
    # Add jitter to prevent thundering herd
    if config.jitter:
        import random
        delay *= (0.5 + random.random() * 0.5)
    
    # Special handling for rate limit errors
    if error and classify_error(error) == ErrorType.API_RATE_LIMIT:
        delay = max(delay, 10.0)  # Minimum 10 seconds for rate limits
    
    return delay

def with_timeout(timeout_seconds: float):
    """
    Decorator to add timeout handling to async functions.
    
    Args:
        timeout_seconds (float): Timeout in seconds
        
    Returns:
        Decorated function with timeout handling
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.error("Function %s timed out after %s seconds", func.__name__, timeout_seconds)
                raise RAGTimeoutError(f"Operation timed out after {timeout_seconds} seconds")
        return wrapper
    return decorator

def with_retry(config: Optional[RetryConfig] = None):
    """
    Decorator to add retry logic to async functions.
    
    Args:
        config (RetryConfig, optional): Retry configuration
        
    Returns:
        Decorated function with retry logic
    """
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    
                    if not should_retry(e, attempt, config.max_attempts):
                        logger.error("Non-retryable error in %s (attempt %d): %s", 
                                   func.__name__, attempt, str(e))
                        raise e
                    
                    if attempt < config.max_attempts:
                        delay = await calculate_retry_delay(attempt, config, e)
                        logger.warning("Retrying %s after error (attempt %d/%d, delay=%.1fs): %s", 
                                     func.__name__, attempt, config.max_attempts, delay, str(e))
                        
                        if delay > 0:
                            await asyncio.sleep(delay)
                    else:
                        logger.error("All retry attempts exhausted for %s: %s", func.__name__, str(e))
            
            raise RAGRetryExhaustedError(f"All {config.max_attempts} retry attempts failed. Last error: {last_error}")
        
        return wrapper
    return decorator

def get_circuit_breaker(service_name: str) -> CircuitBreakerState:
    """
    Get or create circuit breaker state for a service.
    
    Args:
        service_name (str): Name of the service
        
    Returns:
        CircuitBreakerState: Circuit breaker state
    """
    if service_name not in _circuit_breakers:
        _circuit_breakers[service_name] = CircuitBreakerState()
    
    return _circuit_breakers[service_name]

def update_circuit_breaker(service_name: str, success: bool):
    """
    Update circuit breaker state based on operation result.
    
    Args:
        service_name (str): Name of the service
        success (bool): Whether the operation succeeded
    """
    breaker = get_circuit_breaker(service_name)
    current_time = time.time()
    
    if success:
        # Reset on successful operation
        if breaker.state == "half_open":
            breaker.state = "closed"
            logger.info("Circuit breaker for %s reset to closed state", service_name)
        breaker.failure_count = 0
    else:
        # Increment failure count
        breaker.failure_count += 1
        breaker.last_failure_time = current_time
        
        # Open circuit if threshold exceeded
        if breaker.failure_count >= breaker.failure_threshold and breaker.state == "closed":
            breaker.state = "open"
            logger.warning("Circuit breaker for %s opened after %d failures", 
                         service_name, breaker.failure_count)

def check_circuit_breaker(service_name: str) -> bool:
    """
    Check if circuit breaker allows operation to proceed.
    
    Args:
        service_name (str): Name of the service
        
    Returns:
        bool: True if operation should proceed
        
    Raises:
        RAGCircuitBreakerError: If circuit breaker is open
    """
    breaker = get_circuit_breaker(service_name)
    current_time = time.time()
    
    if breaker.state == "closed":
        return True
    
    if breaker.state == "open":
        # Check if recovery timeout has passed
        if current_time - breaker.last_failure_time >= breaker.recovery_timeout:
            breaker.state = "half_open"
            logger.info("Circuit breaker for %s moved to half-open state", service_name)
            return True
        else:
            raise RAGCircuitBreakerError(f"Circuit breaker for {service_name} is open")
    
    # half_open state - allow one attempt
    return True

def with_circuit_breaker(service_name: str):
    """
    Decorator to add circuit breaker pattern to functions.
    
    Args:
        service_name (str): Name of the service for circuit breaker tracking
        
    Returns:
        Decorated function with circuit breaker protection
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Check if circuit breaker allows operation
            check_circuit_breaker(service_name)
            
            try:
                result = await func(*args, **kwargs)
                update_circuit_breaker(service_name, success=True)
                return result
            except Exception as e:
                update_circuit_breaker(service_name, success=False)
                raise e
        
        return wrapper
    return decorator

async def safe_execute(
    func: Callable[[], T], 
    service_name: str,
    timeout_seconds: float = 30.0,
    retry_config: Optional[RetryConfig] = None
) -> T:
    """
    Execute a function with comprehensive error handling, timeout, retry, and circuit breaker.
    
    Args:
        func: Async function to execute
        service_name: Service name for circuit breaker
        timeout_seconds: Timeout in seconds
        retry_config: Retry configuration
        
    Returns:
        Result of the function execution
        
    Raises:
        Various RAG-specific errors based on failure mode
    """
    if retry_config is None:
        retry_config = RetryConfig()
    
    @with_circuit_breaker(service_name)
    @with_retry(retry_config)
    @with_timeout(timeout_seconds)
    async def _execute():
        return await func()
    
    return await _execute()
