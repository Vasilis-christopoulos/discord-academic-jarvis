"""
Utility functions for creating and managing shared database connections.
"""

from supabase import create_client, Client
from settings import settings
from utils.logging_config import logger

# Global supabase client instance
_supabase_client: Client = None  # type: ignore

def get_supabase_client() -> Client:
    """
    Get or create a shared Supabase client instance.
    
    Returns:
        Client: Supabase client instance
    """
    global _supabase_client
    
    if _supabase_client is None:
        try:
            _supabase_client = create_client(
                settings.supabase_url,
                settings.supabase_api_key
            )
            logger.info("Supabase client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    return _supabase_client
