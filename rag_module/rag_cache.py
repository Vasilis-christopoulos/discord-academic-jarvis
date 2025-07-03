"""
RAG Caching Module

This module implements intelligent caching for the RAG system to improve performance
and reduce API costs. It provides multiple caching layers:

1. Response Cache: Caches complete LLM responses for identical queries
2. Retrieval Cache: Caches vector search results
3. Embedding Cache: Caches query embeddings
4. Context Cache: Caches formatted document contexts

Key Features:
- Memory-efficient LRU cache with TTL (Time To Live)
- Cache invalidation on document updates
- Tenant-specific cache isolation
- Cache hit/miss metrics
- Configurable cache sizes and TTLs
"""

import time
import hashlib
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from threading import RLock
from collections import OrderedDict
from langchain_core.documents import Document

from utils.logging_config import logger


@dataclass
class CacheEntry:
    """Represents a cache entry with TTL support."""
    data: Any
    timestamp: float
    ttl: float
    hit_count: int = 0
    
    @property
    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return time.time() > (self.timestamp + self.ttl)
    
    def touch(self):
        """Update hit count when cache entry is accessed."""
        self.hit_count += 1


class LRUCacheWithTTL:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, max_size: int = 100, default_ttl: float = 3600):
        """
        Initialize LRU cache with TTL.
        
        Args:
            max_size: Maximum number of entries to cache
            default_ttl: Default time-to-live in seconds (1 hour)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expirations': 0
        }
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate a cache key from arguments."""
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        with self.lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            entry = self.cache[key]
            
            # Check if expired
            if entry.is_expired:
                del self.cache[key]
                self.stats['expirations'] += 1
                self.stats['misses'] += 1
                return None
            
            # Move to end (mark as recently used)
            self.cache.move_to_end(key)
            entry.touch()
            self.stats['hits'] += 1
            
            return entry.data
    
    def put(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Put value in cache."""
        with self.lock:
            ttl = ttl or self.default_ttl
            
            # If key exists, update it
            if key in self.cache:
                self.cache[key] = CacheEntry(value, time.time(), ttl)
                self.cache.move_to_end(key)
                return
            
            # If at capacity, remove oldest
            if len(self.cache) >= self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.stats['evictions'] += 1
            
            # Add new entry
            self.cache[key] = CacheEntry(value, time.time(), ttl)
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hit_rate': round(hit_rate, 2),
                'total_hits': self.stats['hits'],
                'total_misses': self.stats['misses'],
                'evictions': self.stats['evictions'],
                'expirations': self.stats['expirations']
            }


class RAGCacheManager:
    """Manages multiple cache layers for the RAG system."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize RAG cache manager.
        
        Args:
            config: Cache configuration dictionary
        """
        config = config or {}
        
        # Initialize different cache layers
        self.response_cache = LRUCacheWithTTL(
            max_size=config.get('response_cache_size', 200),
            default_ttl=config.get('response_ttl', 3600)  # 1 hour
        )
        
        self.retrieval_cache = LRUCacheWithTTL(
            max_size=config.get('retrieval_cache_size', 500),
            default_ttl=config.get('retrieval_ttl', 1800)  # 30 minutes
        )
        
        self.embedding_cache = LRUCacheWithTTL(
            max_size=config.get('embedding_cache_size', 1000),
            default_ttl=config.get('embedding_ttl', 7200)  # 2 hours
        )
        
        self.context_cache = LRUCacheWithTTL(
            max_size=config.get('context_cache_size', 300),
            default_ttl=config.get('context_ttl', 1800)  # 30 minutes
        )
        
        logger.info("RAG cache manager initialized with config: %s", config)
    
    def get_response(self, query: str, tenant_id: str, context_hash: str) -> Optional[str]:
        """Get cached response for a query."""
        cache_key = f"response:{tenant_id}:{self._hash_query(query)}:{context_hash}"
        cached_response = self.response_cache.get(cache_key)
        
        if cached_response:
            logger.debug("Cache hit for response: %s", cache_key[:32])
        
        return cached_response
    
    def cache_response(self, query: str, tenant_id: str, context_hash: str, 
                      response: str, ttl: Optional[float] = None) -> None:
        """Cache a response."""
        cache_key = f"response:{tenant_id}:{self._hash_query(query)}:{context_hash}"
        self.response_cache.put(cache_key, response, ttl)
        logger.debug("Cached response: %s", cache_key[:32])
    
    def get_retrieval_results(self, query: str, tenant_id: str, 
                            top_k: int = 5) -> Optional[List[Document]]:
        """Get cached retrieval results."""
        cache_key = f"retrieval:{tenant_id}:{self._hash_query(query)}:{top_k}"
        cached_results = self.retrieval_cache.get(cache_key)
        
        if cached_results:
            logger.debug("Cache hit for retrieval: %s", cache_key[:32])
        
        return cached_results
    
    def cache_retrieval_results(self, query: str, tenant_id: str, documents: List[Document],
                               top_k: int = 5, ttl: Optional[float] = None) -> None:
        """Cache retrieval results."""
        cache_key = f"retrieval:{tenant_id}:{self._hash_query(query)}:{top_k}"
        self.retrieval_cache.put(cache_key, documents, ttl)
        logger.debug("Cached retrieval results: %s", cache_key[:32])
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached embedding."""
        cache_key = f"embedding:{self._hash_query(text)}"
        cached_embedding = self.embedding_cache.get(cache_key)
        
        if cached_embedding:
            logger.debug("Cache hit for embedding: %s", cache_key[:32])
        
        return cached_embedding
    
    def cache_embedding(self, text: str, embedding: List[float], 
                       ttl: Optional[float] = None) -> None:
        """Cache an embedding."""
        cache_key = f"embedding:{self._hash_query(text)}"
        self.embedding_cache.put(cache_key, embedding, ttl)
        logger.debug("Cached embedding: %s", cache_key[:32])
    
    def get_formatted_context(self, documents: List[Document]) -> Optional[str]:
        """Get cached formatted context."""
        context_hash = self._hash_documents(documents)
        cache_key = f"context:{context_hash}"
        cached_context = self.context_cache.get(cache_key)
        
        if cached_context:
            logger.debug("Cache hit for context: %s", cache_key[:32])
        
        return cached_context
    
    def cache_formatted_context(self, documents: List[Document], context: str,
                               ttl: Optional[float] = None) -> None:
        """Cache formatted context."""
        context_hash = self._hash_documents(documents)
        cache_key = f"context:{context_hash}"
        self.context_cache.put(cache_key, context, ttl)
        logger.debug("Cached formatted context: %s", cache_key[:32])
    
    def invalidate_tenant_cache(self, tenant_id: str) -> None:
        """Invalidate all cache entries for a specific tenant."""
        # This is a simplified version - in production, you'd want more efficient invalidation
        caches = [self.response_cache, self.retrieval_cache, self.context_cache]
        
        for cache in caches:
            with cache.lock:
                keys_to_remove = [
                    key for key in cache.cache.keys() 
                    if key.startswith(f"response:{tenant_id}:") or 
                       key.startswith(f"retrieval:{tenant_id}:")
                ]
                for key in keys_to_remove:
                    del cache.cache[key]
        
        logger.info("Invalidated cache for tenant: %s", tenant_id)
    
    def clear_all_caches(self) -> None:
        """Clear all caches."""
        self.response_cache.clear()
        self.retrieval_cache.clear()
        self.embedding_cache.clear()
        self.context_cache.clear()
        logger.info("All caches cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics for all caches."""
        return {
            'response_cache': self.response_cache.get_stats(),
            'retrieval_cache': self.retrieval_cache.get_stats(),
            'embedding_cache': self.embedding_cache.get_stats(),
            'context_cache': self.context_cache.get_stats()
        }
    
    def _hash_query(self, query: str) -> str:
        """Generate a hash for a query string."""
        return hashlib.sha256(query.encode()).hexdigest()[:16]
    
    def _hash_documents(self, documents: List[Document]) -> str:
        """Generate a hash for a list of documents."""
        doc_contents = [doc.page_content for doc in documents]
        content_str = "".join(doc_contents)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]


# Global cache manager instance
_cache_manager: Optional[RAGCacheManager] = None


def get_cache_manager(config: Optional[Dict[str, Any]] = None) -> RAGCacheManager:
    """Get or create the global cache manager instance."""
    global _cache_manager
    
    if _cache_manager is None:
        _cache_manager = RAGCacheManager(config)
    
    return _cache_manager


def clear_global_cache() -> None:
    """Clear the global cache (useful for testing)."""
    global _cache_manager
    if _cache_manager:
        _cache_manager.clear_all_caches()
