"""
Phase 2 Configuration

Configuration settings for RAG system performance optimizations.
These settings can be tuned based on your specific deployment environment
and performance requirements.
"""

# Cache Configuration
CACHE_CONFIG = {
    # Response Cache Settings
    'response_cache_size': 300,      # Maximum number of cached responses
    'response_ttl': 3600,            # Response cache TTL in seconds (1 hour)
    
    # Retrieval Cache Settings  
    'retrieval_cache_size': 500,     # Maximum number of cached retrieval results
    'retrieval_ttl': 1800,           # Retrieval cache TTL in seconds (30 minutes)
    
    # Embedding Cache Settings
    'embedding_cache_size': 1000,    # Maximum number of cached embeddings
    'embedding_ttl': 7200,           # Embedding cache TTL in seconds (2 hours)
    
    # Context Cache Settings
    'context_cache_size': 300,       # Maximum number of cached formatted contexts
    'context_ttl': 1800,             # Context cache TTL in seconds (30 minutes)
}

# Performance Optimization Settings
PERFORMANCE_CONFIG = {
    # Timeout Settings
    'document_retrieval_timeout': 15.0,  # Document retrieval timeout
    'llm_generation_timeout': 25.0,      # LLM response generation timeout
    'total_request_timeout': 45.0,       # Total request timeout
    
    # Retry Configuration
    'max_retry_attempts': 3,             # Maximum retry attempts
    'base_retry_delay': 1.0,             # Base delay between retries
    'max_retry_delay': 10.0,             # Maximum delay between retries
    
    # Concurrency Settings
    'max_concurrent_requests': 10,       # Maximum concurrent requests per handler
    'request_queue_size': 50,            # Maximum request queue size
    
    # Resource Limits
    'max_context_tokens': 12000,         # Maximum context tokens for LLM
    'max_response_tokens': 2000,         # Maximum response tokens from LLM
    'max_documents_per_query': 8,        # Maximum documents to retrieve per query
}

# Monitoring and Logging Configuration
MONITORING_CONFIG = {
    # Performance Metrics
    'enable_performance_tracking': True,  # Enable performance metrics collection
    'metrics_retention_hours': 24,        # How long to retain metrics
    'slow_query_threshold': 10.0,         # Log queries slower than this (seconds)
    
    # Cache Monitoring
    'log_cache_stats_interval': 300,      # Log cache stats every N seconds
    'cache_hit_rate_alert_threshold': 10, # Alert if cache hit rate drops below %
    
    # Health Checks
    'health_check_interval': 60,          # Health check interval in seconds
    'health_check_timeout': 5.0,          # Health check timeout
}

# Environment-Specific Configurations
ENVIRONMENT_CONFIGS = {
    'development': {
        'cache_config': {
            **CACHE_CONFIG,
            'response_cache_size': 50,
            'retrieval_cache_size': 100,
            'embedding_cache_size': 200,
        },
        'performance_config': {
            **PERFORMANCE_CONFIG,
            'max_concurrent_requests': 3,
        }
    },
    
    'staging': {
        'cache_config': {
            **CACHE_CONFIG,
            'response_cache_size': 150,
            'retrieval_cache_size': 250,
            'embedding_cache_size': 500,
        },
        'performance_config': {
            **PERFORMANCE_CONFIG,
            'max_concurrent_requests': 5,
        }
    },
    
    'production': {
        'cache_config': CACHE_CONFIG,
        'performance_config': PERFORMANCE_CONFIG,
    }
}

# Auto-scaling Configuration (for production)
AUTO_SCALING_CONFIG = {
    'enable_auto_scaling': True,
    
    # Cache auto-scaling
    'cache_usage_scale_threshold': 80,    # Scale up cache when usage > 80%
    'cache_hit_rate_scale_threshold': 30, # Scale up cache when hit rate < 30%
    'cache_scale_factor': 1.5,            # Multiply cache size by this factor
    'max_cache_scale_factor': 3.0,        # Maximum scaling factor
}

def get_config(environment: str = 'production') -> dict:
    """
    Get configuration for specified environment.
    
    Args:
        environment: Environment name ('development', 'staging', 'production')
        
    Returns:
        Complete configuration dictionary
    """
    if environment not in ENVIRONMENT_CONFIGS:
        environment = 'production'
    
    config = ENVIRONMENT_CONFIGS[environment]
    
    return {
        'cache_config': config['cache_config'],
        'performance_config': config['performance_config'],
        'monitoring_config': MONITORING_CONFIG,
        'auto_scaling_config': AUTO_SCALING_CONFIG,
        'environment': environment
    }

def get_cache_config(environment: str = 'production') -> dict:
    """Get cache configuration for specified environment."""
    return get_config(environment)['cache_config']

def get_performance_config(environment: str = 'production') -> dict:
    """Get performance configuration for specified environment."""
    return get_config(environment)['performance_config']

# Default configuration (production)
DEFAULT_CONFIG = get_config('production')
