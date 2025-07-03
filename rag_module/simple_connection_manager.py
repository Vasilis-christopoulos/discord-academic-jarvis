"""
Simple Connection Manager for RAG System

This module provides lightweight connection management and monitoring
that works with the existing LangChain architecture.
"""

import time
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from utils.logging_config import logger


@dataclass
class ConnectionStats:
    """Simple connection statistics tracking."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time / self.total_requests
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100


class SimpleConnectionManager:
    """Simple connection manager for tracking and optimizing API calls."""
    
    def __init__(self):
        """Initialize connection manager."""
        self.stats = ConnectionStats()
        self.request_times = []
        self.max_tracked_times = 100  # Keep last 100 request times
        
        logger.info("Simple connection manager initialized")
    
    async def track_request(self, operation_name: str, func, *args, **kwargs):
        """Track a request and collect statistics."""
        start_time = time.time()
        self.stats.total_requests += 1
        
        try:
            result = await func(*args, **kwargs)
            
            # Track successful request
            elapsed = time.time() - start_time
            self.stats.successful_requests += 1
            self.stats.total_response_time += elapsed
            
            # Keep track of recent response times
            self.request_times.append(elapsed)
            if len(self.request_times) > self.max_tracked_times:
                self.request_times.pop(0)
            
            logger.debug("%s completed successfully in %.3fs", operation_name, elapsed)
            return result
            
        except Exception as e:
            # Track failed request
            elapsed = time.time() - start_time
            self.stats.failed_requests += 1
            self.stats.total_response_time += elapsed
            
            logger.warning("%s failed after %.3fs: %s", operation_name, elapsed, str(e))
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        recent_avg = 0.0
        if self.request_times:
            recent_avg = sum(self.request_times) / len(self.request_times)
        
        return {
            'total_requests': self.stats.total_requests,
            'successful_requests': self.stats.successful_requests,
            'failed_requests': self.stats.failed_requests,
            'success_rate': round(self.stats.success_rate, 2),
            'avg_response_time': round(self.stats.avg_response_time, 3),
            'recent_avg_response_time': round(recent_avg, 3),
            'connection_reuse_rate': 0.0,  # Placeholder for compatibility
            'connection_errors': self.stats.failed_requests
        }
    
    def reset_stats(self):
        """Reset all statistics."""
        self.stats = ConnectionStats()
        self.request_times = []
        logger.info("Connection manager statistics reset")


# Global connection manager instance
_connection_manager: Optional[SimpleConnectionManager] = None


def get_connection_manager() -> SimpleConnectionManager:
    """Get or create the global connection manager."""
    global _connection_manager
    
    if _connection_manager is None:
        _connection_manager = SimpleConnectionManager()
    
    return _connection_manager
