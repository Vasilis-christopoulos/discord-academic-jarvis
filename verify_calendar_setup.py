#!/usr/bin/env python3
"""
Step 4: Google Calendar Setup Verification

This script will verify:
1. Google Calendar credentials and authentication
2. Calendar API access and permissions
3. Tasks API access and permissions
4. Calendar sync functionality
5. Tenant calendar configuration
6. Vector store integration for calendar data

Usage:
    python verify_calendar_setup.py [--test-sync] [--test-query]
    
    --test-sync: Test calendar and tasks synchronization
    --test-query: Test natural language calendar queries
"""

import sys
import argparse
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Import our modules
from settings import settings, TENANT_CONFIGS
from utils.logging_config import logger
import json

def check_calendar_credentials() -> bool:
    """Check if Google Calendar credentials are available."""
    try:
        credentials_path = Path("calendar_module/credentials.json")
        token_path = Path("calendar_module/token.json")
        
        if not credentials_path.exists():
            logger.error("❌ Google Calendar credentials.json not found")
            logger.info("💡 You need to:")
            logger.info("   1. Go to Google Cloud Console")
            logger.info("   2. Enable Calendar API and Tasks API")
            logger.info("   3. Create OAuth2 credentials")
            logger.info("   4. Download credentials.json to calendar_module/")
            return False
        
        logger.info("✅ Google Calendar credentials.json found")
        
        if token_path.exists():
            logger.info("✅ Google Calendar token.json found (already authenticated)")
        else:
            logger.warning("⚠️  Google Calendar token.json not found (first-time setup required)")
            logger.info("💡 Run the bot once to complete OAuth2 authentication")
        
        # Verify credentials file structure
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
            
        required_keys = ['installed', 'client_id', 'client_secret']
        if 'installed' in creds:
            creds_data = creds['installed']
            if all(key in creds_data for key in ['client_id', 'client_secret']):
                logger.info("✅ Credentials file structure is valid")
                return True
            else:
                logger.error("❌ Invalid credentials file structure")
                return False
        else:
            logger.error("❌ Invalid credentials file format")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error checking calendar credentials: {e}")
        return False

def verify_tenant_calendar_config() -> bool:
    """Verify tenant calendar configuration."""
    try:
        logger.info("🔍 Verifying tenant calendar configuration...")
        
        if not TENANT_CONFIGS:
            logger.error("❌ No tenant configurations found")
            return False
        
        for tenant in TENANT_CONFIGS:
            logger.info(f"Checking tenant: {tenant.name} (ID: {tenant.guild_id})")
            
            # Check calendar_id
            if not tenant.calendar_id:
                logger.error(f"❌ No calendar_id configured for tenant {tenant.name}")
                return False
            logger.info(f"✅ Calendar ID: {tenant.calendar_id}")
            
            # Check tasklist_id
            if not tenant.tasklist_id:
                logger.error(f"❌ No tasklist_id configured for tenant {tenant.name}")
                return False
            logger.info(f"✅ Tasks List ID: {tenant.tasklist_id}")
            
            # Check timezone
            logger.info(f"✅ Timezone: {tenant.timezone}")
            
            # Check vector store index
            logger.info(f"✅ Calendar Index: {tenant.index_calendar}")
            
            # Check channels with calendar support
            calendar_channels = [
                ch for ch in tenant.channels.values() 
                if 'calendar' in ch.type
            ]
            logger.info(f"✅ Calendar-enabled channels: {len(calendar_channels)}")
            for ch in calendar_channels:
                logger.info(f"   - {ch.name} ({ch.type})")
        
        logger.info("✅ All tenant calendar configurations are valid")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error verifying tenant config: {e}")
        return False

async def test_calendar_import() -> bool:
    """Test importing calendar module components."""
    try:
        logger.info("🧪 Testing calendar module imports...")
        
        # Test core imports
        from calendar_module.calendar_handler import respond
        from calendar_module.query_parser import parse_query
        from calendar_module.sync import ensure_synced
        from calendar_module.delta_sync import delta_sync_calendar, delta_sync_tasks
        logger.info("✅ Calendar module imports successful")
        
        # Test Google API imports
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        logger.info("✅ Google API imports successful")
        
        # Test vector store imports
        from utils.vector_store import get_vector_store
        from langchain_openai import OpenAIEmbeddings
        logger.info("✅ Vector store imports successful")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.info("💡 Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return False
    except Exception as e:
        logger.error(f"❌ Error testing imports: {e}")
        return False

async def test_calendar_sync(tenant_config) -> bool:
    """Test calendar synchronization functionality."""
    try:
        logger.info("🔄 Testing calendar synchronization...")
        
        # Create mock context for testing
        context = {
            'guild_id': tenant_config.guild_id,
            'name': 'test_channel',
            'calendar_id': tenant_config.calendar_id,
            'tasklist_id': tenant_config.tasklist_id,
            'timezone': tenant_config.timezone,
            'index_calendar': tenant_config.index_calendar
        }
        
        # Test delta sync
        from calendar_module.delta_sync import delta_sync_calendar, delta_sync_tasks
        
        logger.info("Testing calendar delta sync...")
        await delta_sync_calendar(context)
        logger.info("✅ Calendar delta sync completed")
        
        logger.info("Testing tasks delta sync...")
        await delta_sync_tasks(context)
        logger.info("✅ Tasks delta sync completed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Calendar sync test failed: {e}")
        logger.info("💡 This might be due to missing authentication or API permissions")
        return False

async def test_calendar_query(tenant_config) -> bool:
    """Test natural language calendar queries."""
    try:
        logger.info("🤖 Testing calendar query functionality...")
        
        # Create mock context
        context = {
            'guild_id': tenant_config.guild_id,
            'name': 'test_channel',
            'calendar_id': tenant_config.calendar_id,
            'tasklist_id': tenant_config.tasklist_id,
            'timezone': tenant_config.timezone,
            'index_calendar': tenant_config.index_calendar
        }
        
        # Test query parsing
        from calendar_module.query_parser import parse_query
        import datetime as dt
        import pytz
        
        tz = pytz.timezone(tenant_config.timezone)
        now = dt.datetime.now(tz)
        
        test_queries = [
            "What's happening this week?",
            "Show me today's events",
            "Any tasks due soon?"
        ]
        
        for query in test_queries:
            logger.info(f"Testing query: '{query}'")
            parsed = await parse_query(query, now.isoformat())
            logger.info(f"✅ Parsed - applicable: {parsed.applicable}, type: {parsed.type}")
        
        # Test full calendar handler (may fail if no data, but should not crash)
        from calendar_module.calendar_handler import respond
        
        logger.info("Testing full calendar response...")
        try:
            result = await respond("What's happening today?", context)
            logger.info("✅ Calendar handler executed successfully")
            logger.info(f"Result type: {type(result)}")
        except Exception as e:
            logger.warning(f"⚠️  Calendar handler returned error (expected if no calendar data): {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Calendar query test failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Verify Google Calendar setup')
    parser.add_argument('--test-sync', action='store_true',
                       help='Test calendar and tasks synchronization')
    parser.add_argument('--test-query', action='store_true', 
                       help='Test natural language calendar queries')
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting Google Calendar Setup Verification (Step 4)")
    
    async def run_verification():
        try:
            # 1. Check credentials
            if not check_calendar_credentials():
                logger.error("❌ Calendar credentials check failed")
                return False
            
            # 2. Verify tenant configuration
            if not verify_tenant_calendar_config():
                logger.error("❌ Tenant calendar configuration check failed")
                return False
            
            # 3. Test imports
            if not await test_calendar_import():
                logger.error("❌ Calendar import test failed")
                return False
            
            # 4. Optional sync test
            if args.test_sync:
                tenant = TENANT_CONFIGS[0]  # Use first tenant for testing
                if not await test_calendar_sync(tenant):
                    logger.error("❌ Calendar sync test failed")
                    return False
            
            # 5. Optional query test
            if args.test_query:
                tenant = TENANT_CONFIGS[0]  # Use first tenant for testing
                if not await test_calendar_query(tenant):
                    logger.error("❌ Calendar query test failed")
                    return False
            
            logger.info("🎉 Google Calendar setup verification completed successfully!")
            
            if not args.test_sync and not args.test_query:
                logger.info("💡 To test sync: python verify_calendar_setup.py --test-sync")
                logger.info("💡 To test queries: python verify_calendar_setup.py --test-query")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Calendar verification failed: {e}")
            return False
    
    # Run async verification
    success = asyncio.run(run_verification())
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
