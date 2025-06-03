#!/usr/bin/env python3
"""
Test script to verify HTTP 410 error handling in calendar sync.
"""

import asyncio
import json
import sys
import os
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from calendar_module.delta_sync import delta_sync_calendar
from calendar_module.sync_store import get_calendar_sync_token, set_calendar_sync_token
from utils.logging_config import logger

async def test_sync_with_invalid_token():
    """Test sync behavior with an invalid/expired token."""
    
    # Load context from tenants.json (relative to project root)
    tenants_path = project_root / 'tenants.json'
    with open(tenants_path, 'r') as f:
        tenants = json.load(f)
    
    # Get the first tenant context
    tenant_id = next(iter(tenants))
    context = tenants[tenant_id]
    
    logger.info("Current sync token: %s", get_calendar_sync_token())
    
    # Set an invalid sync token to simulate expiration
    logger.info("Setting invalid sync token to test HTTP 410 handling...")
    set_calendar_sync_token("invalid_expired_token_12345")
    
    try:
        # This should trigger HTTP 410 error and automatically recover
        logger.info("Attempting delta sync with invalid token...")
        await delta_sync_calendar(context)
        logger.info("Delta sync completed successfully!")
        logger.info("New sync token: %s", get_calendar_sync_token())
        
    except Exception as e:
        logger.error("Error during sync: %s", e)
        # Reset token in case of failure
        set_calendar_sync_token("")

if __name__ == "__main__":
    asyncio.run(test_sync_with_invalid_token())
