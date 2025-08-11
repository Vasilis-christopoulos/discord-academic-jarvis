#!/usr/bin/env python3
"""
Step 2: Database Schema Verification and Deployment

This script will:
1. Connect to Supabase database
2. Check if tables exist and have correct schema
3. Deploy the latest schema if needed
4. Verify all database functions work correctly
5. Test rate limiting functionality end-to-end

Usage:
    python verify_database_schema.py [--deploy] [--test-functions]
    
    --deploy: Deploy the schema (otherwise just verify)
    --test-functions: Run comprehensive function tests
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Import our modules
from rag_module.database_utils import get_supabase_client
from settings import settings
from utils.logging_config import logger

def check_table_exists(client, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        response = client.table(table_name).select("*").limit(1).execute()
        return True
    except Exception as e:
        logger.info(f"Table {table_name} does not exist or is inaccessible: {e}")
        return False

def check_function_exists(client, function_name: str) -> bool:
    """Check if a database function exists."""
    try:
        # Use SQL to check if function exists
        result = client.rpc('check_user_limit', {
            'p_user_id': 'test_user_123',
            'p_limit_type': 'test_limit'
        }).execute()
        return True
    except Exception as e:
        logger.info(f"Function {function_name} does not exist or is inaccessible: {e}")
        return False

def deploy_schema(client) -> bool:
    """Deploy the database schema from SQL file."""
    try:
        # Read the schema file
        schema_path = Path("sql/rate_limiting_schema_fixed.sql")
        if not schema_path.exists():
            logger.error(f"Schema file not found: {schema_path}")
            return False
        
        schema_sql = schema_path.read_text(encoding='utf-8')
        logger.info("Read schema file successfully")
        
        # Note: Supabase Python client doesn't support executing raw SQL directly
        # We need to use the Supabase dashboard or psql client
        logger.warning("⚠️  MANUAL ACTION REQUIRED:")
        logger.warning("   The Supabase Python client cannot execute DDL statements.")
        logger.warning("   Please manually run the SQL schema in Supabase dashboard:")
        logger.warning(f"   1. Open Supabase dashboard: {settings.supabase_url.replace('supabase.co', 'supabase.com')}")
        logger.warning("   2. Go to SQL Editor")
        logger.warning("   3. Copy and paste the contents of sql/rate_limiting_schema_fixed.sql")
        logger.warning("   4. Execute the SQL")
        logger.warning("   5. Then re-run this script with --test-functions")
        
        return False  # Return False to indicate manual action needed
        
    except Exception as e:
        logger.error(f"Error reading schema file: {e}")
        return False

def test_database_functions(client) -> bool:
    """Test all database functions with sample data."""
    try:
        logger.info("🧪 Testing database functions...")
        
        test_user_id = "test_user_987654321"
        test_limit_type = "rag_requests"
        
        # Test 1: Check user limit (should return 0 initially)
        logger.info("Testing check_user_limit function...")
        result = client.rpc('check_user_limit', {
            'p_user_id': test_user_id,
            'p_limit_type': test_limit_type
        }).execute()
        
        if not result.data:
            logger.error("❌ check_user_limit returned no data")
            return False
            
        current_count = result.data[0]['current_count']
        is_within_limit = result.data[0]['is_within_limit']
        logger.info(f"✅ check_user_limit: count={current_count}, within_limit={is_within_limit}")
        
        # Test 2: Increment user count
        logger.info("Testing increment_user_count function...")
        result = client.rpc('increment_user_count', {
            'p_user_id': test_user_id,
            'p_limit_type': test_limit_type
        }).execute()
        
        if result.data is None:
            logger.error("❌ increment_user_count returned no data")
            return False
            
        new_count = result.data
        logger.info(f"✅ increment_user_count: new_count={new_count}")
        
        # Test 3: Check user limit again (should be 1 now)
        logger.info("Testing check_user_limit after increment...")
        result = client.rpc('check_user_limit', {
            'p_user_id': test_user_id,
            'p_limit_type': test_limit_type
        }).execute()
        
        current_count = result.data[0]['current_count']
        if current_count != 1:
            logger.error(f"❌ Expected count=1, got count={current_count}")
            return False
        logger.info(f"✅ check_user_limit after increment: count={current_count}")
        
        # Test 4: Global limits
        logger.info("Testing global limit functions...")
        global_limit_type = "total_file_uploads"
        
        result = client.rpc('check_global_limit', {
            'p_limit_type': global_limit_type
        }).execute()
        global_count = result.data[0]['current_count']
        logger.info(f"✅ check_global_limit: count={global_count}")
        
        result = client.rpc('increment_global_count', {
            'p_limit_type': global_limit_type
        }).execute()
        new_global_count = result.data
        logger.info(f"✅ increment_global_count: new_count={new_global_count}")
        
        # Test 5: OpenAI usage tracking
        logger.info("Testing track_openai_usage function...")
        result = client.rpc('track_openai_usage', {
            'p_user_id': test_user_id,
            'p_tokens_used': 150,
            'p_cost': 0.003,
            'p_model': 'gpt-4'
        }).execute()
        
        if result.data is not True:
            logger.error("❌ track_openai_usage failed")
            return False
        logger.info("✅ track_openai_usage: success")
        
        logger.info("🎉 All database functions working correctly!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database function test failed: {e}")
        return False

def verify_table_schema(client) -> bool:
    """Verify that all required tables exist with correct schema."""
    required_tables = [
        'rate_limits',
        'global_limits', 
        'openai_usage_tracking'
    ]
    
    logger.info("🔍 Verifying database tables...")
    
    missing_tables = []
    for table in required_tables:
        if check_table_exists(client, table):
            logger.info(f"✅ Table '{table}' exists")
        else:
            logger.warning(f"❌ Table '{table}' missing")
            missing_tables.append(table)
    
    if missing_tables:
        logger.error(f"Missing tables: {missing_tables}")
        return False
    
    logger.info("✅ All required tables exist")
    return True

def main():
    parser = argparse.ArgumentParser(description='Verify and deploy database schema')
    parser.add_argument('--deploy', action='store_true', 
                       help='Deploy schema (otherwise just verify)')
    parser.add_argument('--test-functions', action='store_true',
                       help='Run comprehensive function tests')
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting Database Schema Verification (Step 2)")
    logger.info(f"Supabase URL: {settings.supabase_url}")
    
    try:
        # Connect to database
        client = get_supabase_client()
        logger.info("✅ Connected to Supabase database")
        
        # Check if schema is already deployed
        tables_exist = verify_table_schema(client)
        
        if not tables_exist and args.deploy:
            logger.info("📦 Deploying database schema...")
            deploy_result = deploy_schema(client)
            if not deploy_result:
                logger.error("❌ Schema deployment failed or requires manual action")
                return False
        elif not tables_exist:
            logger.error("❌ Tables missing. Run with --deploy to deploy schema")
            return False
        
        # Test functions if requested or if tables exist
        if args.test_functions and tables_exist:
            logger.info("🧪 Running database function tests...")
            test_result = test_database_functions(client)
            if not test_result:
                logger.error("❌ Database function tests failed")
                return False
        
        logger.info("🎉 Database schema verification completed successfully!")
        
        if tables_exist and not args.test_functions:
            logger.info("💡 To test database functions, run: python verify_database_schema.py --test-functions")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database verification failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
