"""
Daily rate limiter using Supabase with Toronto timezone support.
Handles user-level and global rate limits with warning thresholds.

Features:
- User RAG requests: 10 per day per user
- Global file uploads: 10 per day total across all users  
- PDF page validation: 20 pages max per file
- OpenAI usage monitoring
- Toronto timezone handling with automatic EST/EDT transitions
- Warning thresholds at 80% of limit
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, date, timedelta
import pytz
from supabase import Client
from utils.logging_config import logger

@dataclass
class RateLimitResult:
    """Result of rate limit check with all necessary information."""
    allowed: bool
    current_count: int
    daily_limit: int
    warning_threshold: bool  # True if at 80% of limit
    wisdom_warning: bool     # True if at 70% of limit (new wisdom warning)
    message: str
    reset_time: datetime
    limit_type: str

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting system."""
    user_rag_requests: int = 10
    user_file_uploads: int = 5
    global_file_uploads: int = 10
    pdf_page_limit: int = 20
    timezone: str = "America/Toronto"
    warning_threshold: float = 0.8  # 80%
    wisdom_threshold: float = 0.7   # 70% - new wisdom warning
    enable_rate_limiting: bool = True

class DailyRateLimiter:
    """
    Production-ready daily rate limiter with timezone support.
    
    Integrates with Supabase database functions to provide:
    - User-level rate limiting for RAG requests
    - Global rate limiting for file uploads
    - OpenAI usage tracking
    - Automatic daily resets at midnight Toronto time
    """
    
    def __init__(self, supabase_client: Client, config: RateLimitConfig):
        self.supabase = supabase_client
        self.config = config
        self.timezone = pytz.timezone(config.timezone)
        logger.info("Rate limiter initialized with config: user_rag=%d, global_files=%d, timezone=%s",
                   config.user_rag_requests, config.global_file_uploads, config.timezone)
        
    async def check_user_limit(self, user_id: str, limit_type: str) -> RateLimitResult:
        """
        Check if user can make a request based on their daily limit.
        
        Args:
            user_id (str): Discord user ID
            limit_type (str): Type of limit to check ('rag_requests', 'file_uploads')
            
        Returns:
            RateLimitResult: Complete information about limit status
        """
        if not self.config.enable_rate_limiting:
            # Rate limiting disabled - allow all requests
            return RateLimitResult(
                allowed=True,
                current_count=0,
                daily_limit=999999,
                warning_threshold=False,
                wisdom_warning=False,
                message="Rate limiting disabled",
                reset_time=self.get_next_reset_time(),
                limit_type=limit_type
            )
        
        try:
            # Call Supabase function to check user limit
            result = self.supabase.rpc(
                'check_user_limit',
                {'p_user_id': user_id, 'p_limit_type': limit_type}  # Use string user_id
            ).execute()
            
            if not result.data:
                raise Exception("No data returned from check_user_limit")
            
            data = result.data[0]
            current_count = data.get('current_count', 0) or 0  # Handle None values
            
            # Get the appropriate limit based on limit type
            if limit_type == "rag_requests":
                daily_limit = self.config.user_rag_requests
            elif limit_type == "file_uploads":
                daily_limit = self.config.user_file_uploads
            else:
                daily_limit = 10  # Default fallback
                
            # Check if limit is exceeded
            can_proceed = current_count < daily_limit
            # Wisdom warning should trigger on the 7th request (when about to reach 70%)
            # So we check if current_count + 1 (the next request) would reach 70%
            wisdom_warning = (current_count + 1) >= int(daily_limit * self.config.wisdom_threshold)  # 70% wisdom warning
            
            # Create user-friendly message
            message = self._format_limit_message(
                can_proceed,
                current_count, 
                daily_limit,
                wisdom_warning,
                self.get_next_reset_time().isoformat(),
                limit_type
            )
            
            return RateLimitResult(
                allowed=can_proceed,
                current_count=current_count,
                daily_limit=daily_limit,
                warning_threshold=False,  # Always False since we removed 80% warnings
                wisdom_warning=wisdom_warning,
                message=message,
                reset_time=self.get_next_reset_time(),
                limit_type=limit_type
            )
            
        except Exception as e:
            logger.error(f"Error checking user limit for {user_id}: {e}")
            # Fail open - allow request but log error
            return RateLimitResult(
                allowed=True,
                current_count=0,
                daily_limit=self.config.user_rag_requests,
                warning_threshold=False,
                wisdom_warning=False,
                message="Rate limit check failed - allowing request",
                reset_time=self.get_next_reset_time(),
                limit_type=limit_type
            )
    
    async def check_global_limit(self, limit_type: str) -> RateLimitResult:
        """
        Check global limits (like total file uploads per day).
        
        Args:
            limit_type (str): Type of global limit ('total_file_uploads')
            
        Returns:
            RateLimitResult: Complete information about global limit status
        """
        if not self.config.enable_rate_limiting:
            return RateLimitResult(
                allowed=True,
                current_count=0,
                daily_limit=999999,
                warning_threshold=False,
                wisdom_warning=False,
                message="Rate limiting disabled",
                reset_time=self.get_next_reset_time(),
                limit_type=limit_type
            )
        
        try:
            # Call Supabase function to check global limit
            result = self.supabase.rpc(
                'check_global_limit',
                {'p_limit_type': limit_type}
            ).execute()

            if not result.data:
                raise Exception("No data returned from check_global_limit")

            data = result.data[0]
            current_count = data.get('current_count', 0) or 0  # Handle None values
            
            # Get the appropriate limit based on limit type
            if limit_type == "total_file_uploads":
                daily_limit = self.config.global_file_uploads
            else:
                daily_limit = 100  # Default fallback
                
            # Check if limit is exceeded
            can_proceed = current_count < daily_limit

            # Create system-wide message
            message = self._format_global_limit_message(
                can_proceed,
                current_count, 
                daily_limit,
                self.get_next_reset_time().isoformat(),
                limit_type
            )

            return RateLimitResult(
                allowed=can_proceed,
                current_count=current_count,
                daily_limit=daily_limit,
                warning_threshold=False,  # No 80% warnings
                wisdom_warning=False,  # Global limits don't use wisdom warnings
                message=message,
                reset_time=self.get_next_reset_time(),
                limit_type=limit_type
            )
            
        except Exception as e:
            logger.error(f"Error checking global limit for {limit_type}: {e}")
            # Fail open - allow request but log error
            return RateLimitResult(
                allowed=True,
                current_count=0,
                daily_limit=self.config.global_file_uploads,
                warning_threshold=False,
                wisdom_warning=False,
                message="Global limit check failed - allowing request",
                reset_time=self.get_next_reset_time(),
                limit_type=limit_type
            )
    
    async def increment_user_count(self, user_id: str, limit_type: str) -> int:
        """
        Increment user's daily counter after successful action.
        
        Args:
            user_id (str): Discord user ID
            limit_type (str): Type of limit to increment
            
        Returns:
            int: New count after increment
        """
        if not self.config.enable_rate_limiting:
            return 0
        
        try:
            result = self.supabase.rpc(
                'increment_user_count',
                {'p_user_id': user_id, 'p_limit_type': limit_type}
            ).execute()
            
            new_count = result.data if result.data else 0
            logger.debug(f"Incremented {limit_type} for user {user_id}: {new_count}")
            return new_count
            
        except Exception as e:
            logger.error(f"Error incrementing user count for {user_id}: {e}")
            return 0
    
    async def increment_global_count(self, limit_type: str) -> int:
        """
        Increment global counter after successful action.
        
        Args:
            limit_type (str): Type of global limit to increment
            
        Returns:
            int: New count after increment
        """
        if not self.config.enable_rate_limiting:
            return 0
        
        try:
            result = self.supabase.rpc(
                'increment_global_count',
                {'p_limit_type': limit_type}
            ).execute()
            
            new_count = result.data if result.data else 0
            logger.debug(f"Incremented global {limit_type}: {new_count}")
            return new_count
            
        except Exception as e:
            logger.error(f"Error incrementing global count for {limit_type}: {e}")
            return 0
    
    async def track_openai_usage(self, user_id: str, tokens: int, cost: float, model: str = "gpt-4") -> None:
        """
        Track OpenAI usage for monitoring and analytics.
        
        Args:
            user_id (str): Discord user ID
            tokens (int): Number of tokens used
            cost (float): Estimated cost in USD
            model (str): OpenAI model used
        """
        try:
            self.supabase.rpc(
                'track_openai_usage',
                {
                    'p_user_id': user_id,
                    'p_tokens_used': tokens,
                    'p_cost': cost,
                    'p_model': model
                }
            ).execute()
            
            logger.debug(f"Tracked OpenAI usage for user {user_id}: {tokens} tokens, ${cost:.4f}")
            
        except Exception as e:
            logger.error(f"Error tracking OpenAI usage for {user_id}: {e}")
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get user's current usage statistics across all limit types.
        
        Args:
            user_id (str): Discord user ID
            
        Returns:
            Dict[str, Any]: User's current usage stats
        """
        try:
            # Use user_id as string directly
            user_id_str = str(user_id)
            
            # Get user limits
            user_result = self.supabase.table('rate_limits').select('*').eq(
                'user_id', user_id_str
            ).execute()
            
            logger.debug(f"User limits query result for {user_id}: {len(user_result.data)} records")
            
            # Get OpenAI usage for today (and yesterday to handle timezone issues)
            now_toronto = datetime.now(self.timezone)
            today_str = now_toronto.date().isoformat()
            yesterday_str = (now_toronto.date() - timedelta(days=1)).isoformat()
            
            # Try both today and yesterday due to potential timezone issues in the database
            openai_result = self.supabase.table('openai_usage_tracking').select('*').eq(
                'user_id', user_id_str
            ).in_('date_toronto', [today_str, yesterday_str]).execute()
            
            logger.debug(f"OpenAI usage query result for {user_id}: {len(openai_result.data)} records")
            
            # Structure the response
            stats = {
                'user_id': user_id,
                'limits': {},
                'openai_usage': openai_result.data[0] if openai_result.data else {},
                'next_reset': self.get_next_reset_time().isoformat()
            }
            
            # Convert user limits to expected format
            for row in user_result.data:
                stats['limits'][row['limit_type']] = {
                    'current_count': row['request_count'],  # Note: column name is request_count in schema
                    'daily_limit': self.config.user_rag_requests if row['limit_type'] == 'rag_requests' else self.config.user_file_uploads,
                    'last_reset': row['date_toronto']
                }
            
            logger.debug(f"User stats compiled successfully for {user_id}")
            return stats
            
        except ValueError as e:
            logger.error(f"Invalid user_id format {user_id}: {e}")
            return {'user_id': user_id, 'error': f'Invalid user ID format: {e}'}
        except Exception as e:
            logger.error(f"Error getting user stats for {user_id}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {'user_id': user_id, 'error': str(e)}
    
    def get_next_reset_time(self) -> datetime:
        """
        Get the next reset time (midnight Toronto time).
        
        Returns:
            datetime: Next reset time in Toronto timezone
        """
        now_toronto = datetime.now(self.timezone)
        tomorrow = now_toronto.date() + timedelta(days=1)
        midnight_toronto = self.timezone.localize(
            datetime.combine(tomorrow, datetime.min.time())
        )
        return midnight_toronto
    
    def _format_limit_message(self, can_proceed: bool, current: int, limit: int, 
                            wisdom_warning: bool, reset_time: str, limit_type: str) -> str:
        """Format user-friendly rate limit message."""
        
        reset_dt = datetime.fromisoformat(reset_time.replace('Z', '+00:00'))
        time_until_reset = reset_dt - datetime.now(pytz.UTC)
        hours = int(time_until_reset.total_seconds() // 3600)
        minutes = int((time_until_reset.total_seconds() % 3600) // 60)
        
        if not can_proceed:
            if limit_type == 'rag_requests':
                return (f"⏰ **Daily limit reached!** You've used {current}/{limit} RAG queries today.\n"
                       f"🔄 **Resets in**: {hours}h {minutes}m\n"
                       f"💡 **Tip**: Try refining your questions to get better results with fewer queries.")
            else:
                return (f"⏰ **Daily {limit_type} limit reached!** ({current}/{limit})\n"
                       f"🔄 **Resets in**: {hours}h {minutes}m")
        
        elif wisdom_warning and limit_type == 'rag_requests':
            # This request will be the 7th request (70% threshold)
            upcoming_count = current + 1
            remaining = limit - upcoming_count
            return (f"🧠 **Wisdom Warning**: This will be request {upcoming_count}/{limit}. You'll have {remaining} remaining - spend them wisely.\n"
                   f"🔄 **Resets in**: {hours}h {minutes}m")
        
        else:
            return f"✅ Usage: {current}/{limit} {limit_type} today"
    
    def _format_global_limit_message(self, can_proceed: bool, current: int, limit: int, 
                                   reset_time: str, limit_type: str) -> str:
        """Format global limit message."""
        
        reset_dt = datetime.fromisoformat(reset_time.replace('Z', '+00:00'))
        time_until_reset = reset_dt - datetime.now(pytz.UTC)
        hours = int(time_until_reset.total_seconds() // 3600)
        minutes = int((time_until_reset.total_seconds() % 3600) // 60)
        
        if not can_proceed:
            return (f"📁 **Daily file upload limit reached!** The server has processed {current}/{limit} files today.\n"
                   f"🔄 **Resets in**: {hours}h {minutes}m\n"
                   f"⏳ **Please try again**: After the reset time.")
        
        else:
            return f"📊 Server file usage: {current}/{limit} today"

# Helper function to get rate limiter instance
def get_rate_limiter(supabase_client: Client, config: Optional[RateLimitConfig] = None) -> DailyRateLimiter:
    """
    Factory function to create rate limiter instance.
    
    Args:
        supabase_client: Supabase client instance
        config: Rate limiting configuration (uses defaults if None)
        
    Returns:
        DailyRateLimiter: Configured rate limiter instance
    """
    if config is None:
        config = RateLimitConfig()
    
    return DailyRateLimiter(supabase_client, config)
