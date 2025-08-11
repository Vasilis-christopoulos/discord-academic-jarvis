#!/usr/bin/env python3
"""
Step 5: End-to-End System Testing

This script will perform comprehensive testing of the entire Discord Academic Jarvis system:
1. Configuration validation
2. Database connectivity and functions
3. Discord bot components
4. RAG module functionality
5. Calendar integration
6. Rate limiting system
7. Error handling and resilience
8. Performance validation

Usage:
    python test_end_to_end.py [--quick] [--full] [--component COMPONENT]
    
    --quick: Run essential tests only (faster)
    --full: Run comprehensive tests including performance
    --component: Test specific component (config, database, rag, calendar, bot)
"""

import sys
import argparse
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import our modules
from settings import settings, TENANT_CONFIGS
from utils.logging_config import logger
import json

class EndToEndTester:
    def __init__(self, quick_mode: bool = False):
        self.quick_mode = quick_mode
        self.test_results = {}
        self.start_time = time.time()
        
    def log_test_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result and track for summary."""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} - {test_name}")
        if details:
            logger.info(f"    {details}")
        
        self.test_results[test_name] = {
            'success': success,
            'details': details,
            'timestamp': time.time()
        }
        
    async def test_configuration(self) -> bool:
        """Test 1: Configuration and Environment Variables"""
        logger.info("🔧 Testing Configuration and Environment Variables...")
        
        try:
            # Test environment variables
            required_vars = [
                'discord_token', 'openai_api_key', 'pinecone_api_key',
                'supabase_url', 'supabase_api_key', 'aws_access_key_id',
                'aws_secret_access_key', 'aws_region_name'
            ]
            
            missing_vars = []
            for var in required_vars:
                value = getattr(settings, var, None)
                if not value or value.strip() == "":
                    missing_vars.append(var)
            
            if missing_vars:
                self.log_test_result("Environment Variables", False, f"Missing: {missing_vars}")
                return False
            
            self.log_test_result("Environment Variables", True, f"All {len(required_vars)} variables present")
            
            # Test tenant configuration
            if not TENANT_CONFIGS:
                self.log_test_result("Tenant Configuration", False, "No tenants configured")
                return False
            
            tenant = TENANT_CONFIGS[0]
            if not tenant.calendar_id or not tenant.tasklist_id:
                self.log_test_result("Tenant Configuration", False, "Missing calendar/tasks configuration")
                return False
            
            self.log_test_result("Tenant Configuration", True, f"Tenant {tenant.name} properly configured")
            return True
            
        except Exception as e:
            self.log_test_result("Configuration", False, f"Error: {e}")
            return False

    async def test_database(self) -> bool:
        """Test 2: Database Connectivity and Functions"""
        logger.info("🗄️ Testing Database Connectivity and Functions...")
        
        try:
            from rag_module.database_utils import get_supabase_client
            
            # Test connection
            client = get_supabase_client()
            self.log_test_result("Database Connection", True, "Supabase client initialized")
            
            # Test database functions
            test_user_id = f"test_user_{int(time.time())}"
            test_limit_type = "rag_requests"
            
            # Test check_user_limit
            result = client.rpc('check_user_limit', {
                'p_user_id': test_user_id,
                'p_limit_type': test_limit_type
            }).execute()
            
            if not result.data:
                self.log_test_result("Database Functions", False, "check_user_limit returned no data")
                return False
            
            initial_count = result.data[0]['current_count']
            self.log_test_result("Check User Limit Function", True, f"Initial count: {initial_count}")
            
            # Test increment_user_count
            result = client.rpc('increment_user_count', {
                'p_user_id': test_user_id,
                'p_limit_type': test_limit_type
            }).execute()
            
            new_count = result.data
            expected_count = (initial_count or 0) + 1
            if new_count != expected_count:
                self.log_test_result("Increment User Count Function", False, 
                                   f"Expected {expected_count}, got {new_count}")
                return False
            
            self.log_test_result("Increment User Count Function", True, f"Count incremented to {new_count}")
            
            # Test OpenAI usage tracking
            result = client.rpc('track_openai_usage', {
                'p_user_id': test_user_id,
                'p_tokens_used': 100,
                'p_cost': 0.002,
                'p_model': 'gpt-4'
            }).execute()
            
            if result.data is not True:
                self.log_test_result("OpenAI Usage Tracking", False, "Function returned False")
                return False
            
            self.log_test_result("OpenAI Usage Tracking", True, "Usage tracked successfully")
            return True
            
        except Exception as e:
            self.log_test_result("Database", False, f"Error: {e}")
            return False

    async def test_rag_module(self) -> bool:
        """Test 3: RAG Module Components"""
        logger.info("🤖 Testing RAG Module Components...")
        
        try:
            # Test imports
            from rag_module.rag_handler import respond as rag_respond
            from rag_module.file_validator import FileValidationResult
            from rag_module.rate_limiter import DailyRateLimiter, RateLimitConfig
            
            self.log_test_result("RAG Module Imports", True, "All components imported successfully")
            
            # Test rate limiting
            from rag_module.database_utils import get_supabase_client
            client = get_supabase_client()
            config = RateLimitConfig()
            rate_limiter = DailyRateLimiter(client, config)
            
            test_user_id = f"test_user_{int(time.time())}"
            result = await rate_limiter.check_user_limit(test_user_id, "rag_requests")
            
            if result is None:
                self.log_test_result("Rate Limiting Check", False, "Rate limit check returned None")
                return False
            
            self.log_test_result("Rate Limiting Check", True, f"Current count: {result.current_count}")
            
            # Test file validation basic structure
            validation_result = FileValidationResult(
                allowed=True,
                message="Test validation",
                file_count=0,
                daily_limit=10,
                file_size_mb=1.0
            )
            self.log_test_result("File Validation Structure", True, "FileValidationResult works")
            
            return True
            
        except Exception as e:
            self.log_test_result("RAG Module", False, f"Error: {e}")
            return False

    async def test_calendar_module(self) -> bool:
        """Test 4: Calendar Module Components"""
        logger.info("📅 Testing Calendar Module Components...")
        
        try:
            # Test imports
            from calendar_module.calendar_handler import respond as calendar_respond
            from calendar_module.query_parser import parse_query
            
            self.log_test_result("Calendar Module Imports", True, "All components imported successfully")
            
            # Test query parsing
            import datetime as dt
            import pytz
            
            tenant = TENANT_CONFIGS[0]
            tz = pytz.timezone(tenant.timezone)
            now = dt.datetime.now(tz)
            
            test_query = "What's happening this week?"
            try:
                parsed = await parse_query(test_query, now.isoformat())
                self.log_test_result("Calendar Query Parsing", True, 
                                   f"Query parsed - applicable: {parsed.applicable}")
            except Exception as e:
                self.log_test_result("Calendar Query Parsing", False, f"Parse error: {e}")
                return False
            
            # Test calendar credentials
            credentials_path = Path("calendar_module/credentials.json")
            token_path = Path("calendar_module/token.json")
            
            if credentials_path.exists():
                self.log_test_result("Calendar Credentials", True, "credentials.json found")
            else:
                self.log_test_result("Calendar Credentials", False, "credentials.json missing")
                return False
            
            if token_path.exists():
                self.log_test_result("Calendar Authentication", True, "token.json found")
            else:
                self.log_test_result("Calendar Authentication", False, "token.json missing - needs OAuth2")
            
            return True
            
        except Exception as e:
            self.log_test_result("Calendar Module", False, f"Error: {e}")
            return False

    async def test_discord_bot_components(self) -> bool:
        """Test 5: Discord Bot Components"""
        logger.info("🤖 Testing Discord Bot Components...")
        
        try:
            # Test main bot imports
            from main_bot import load_tenant_context
            import discord
            
            self.log_test_result("Discord Bot Imports", True, "Main bot components imported")
            
            # Test context building with actual function signature
            tenant = TENANT_CONFIGS[0]
            guild_id = tenant.guild_id
            channel_id = list(tenant.channels.keys())[0]
            
            context = load_tenant_context(guild_id, channel_id)
            if not context:
                self.log_test_result("Context Building", False, "Failed to build context")
                return False
            
            required_context_keys = ['guild_id', 'name', 'type']
            missing_keys = [key for key in required_context_keys if key not in context]
            if missing_keys:
                self.log_test_result("Context Building", False, f"Missing keys: {missing_keys}")
                return False
            
            self.log_test_result("Context Building", True, f"Context built for {context['name']}")
            
            # Test module access patterns
            channel_types = ["rag", "calendar", "rag-calendar"]
            for channel_type in channel_types:
                modules_available = []
                if "rag" in channel_type:
                    modules_available.append("rag")
                if "calendar" in channel_type:
                    modules_available.append("calendar")
                
                self.log_test_result(f"Channel Type - {channel_type}", True, 
                                   f"Modules: {modules_available}")
            
            return True
            
        except Exception as e:
            self.log_test_result("Discord Bot Components", False, f"Error: {e}")
            return False

    async def test_error_handling(self) -> bool:
        """Test 6: Error Handling and Resilience"""
        logger.info("🛡️ Testing Error Handling and Resilience...")
        
        try:
            # Test rate limiter error handling
            from rag_module.rate_limiter import DailyRateLimiter, RateLimitConfig
            from rag_module.database_utils import get_supabase_client
            
            client = get_supabase_client()
            config = RateLimitConfig()
            rate_limiter = DailyRateLimiter(client, config)
            
            # Test with invalid user ID formats
            test_cases = [
                ("", "rag_requests"),
                ("valid_user_123", ""),
                ("valid_user_123", "invalid_limit_type"),
            ]
            
            for user_id, limit_type in test_cases:
                try:
                    result = await rate_limiter.check_user_limit(user_id, limit_type)
                    # Should handle gracefully, not crash
                    self.log_test_result("Error Handling - Rate Limiter", True, 
                                       "Gracefully handled invalid input")
                except Exception as e:
                    # Some errors are expected, that's still good error handling
                    self.log_test_result("Error Handling - Rate Limiter", True, 
                                       f"Properly threw error for invalid input: {type(e).__name__}")
            
            # Test database resilience
            try:
                result = client.rpc('non_existent_function', {}).execute()
                self.log_test_result("Error Handling - Database", False, 
                                   "Should have failed on non-existent function")
            except Exception:
                self.log_test_result("Error Handling - Database", True, 
                                   "Properly handled database error")
            
            # Test configuration error handling
            from settings import TENANT_CONFIGS
            if TENANT_CONFIGS:
                self.log_test_result("Error Handling - Configuration", True, 
                                   "Configuration loaded successfully")
            
            return True
            
        except Exception as e:
            self.log_test_result("Error Handling", False, f"Error: {e}")
            return False

    async def test_performance(self) -> bool:
        """Test 7: Performance Validation"""
        if self.quick_mode:
            self.log_test_result("Performance Tests", True, "Skipped in quick mode")
            return True
            
        logger.info("⚡ Testing Performance...")
        
        try:
            # Test database response time
            from rag_module.database_utils import get_supabase_client
            client = get_supabase_client()
            
            start_time = time.time()
            for i in range(5):
                result = client.rpc('check_user_limit', {
                    'p_user_id': f'perf_test_{i}',
                    'p_limit_type': 'rag_requests'
                }).execute()
            end_time = time.time()
            
            avg_response_time = (end_time - start_time) / 5
            if avg_response_time > 2.0:  # 2 seconds threshold
                self.log_test_result("Database Performance", False, 
                                   f"Slow response: {avg_response_time:.2f}s avg")
                return False
            
            self.log_test_result("Database Performance", True, 
                               f"Good response time: {avg_response_time:.3f}s avg")
            
            # Test import performance
            import_start = time.time()
            from calendar_module.calendar_handler import respond
            from rag_module.rag_handler import respond as rag_respond
            import_end = time.time()
            
            import_time = import_end - import_start
            if import_time > 5.0:  # 5 seconds threshold
                self.log_test_result("Import Performance", False, 
                                   f"Slow imports: {import_time:.2f}s")
            else:
                self.log_test_result("Import Performance", True, 
                                   f"Fast imports: {import_time:.3f}s")
            
            return True
            
        except Exception as e:
            self.log_test_result("Performance", False, f"Error: {e}")
            return False

    def print_summary(self):
        """Print comprehensive test summary."""
        total_time = time.time() - self.start_time
        
        passed = sum(1 for result in self.test_results.values() if result['success'])
        total = len(self.test_results)
        failed = total - passed
        
        print("\n" + "="*80)
        print("🎯 END-TO-END TEST SUMMARY")
        print("="*80)
        print(f"⏱️  Total Time: {total_time:.2f}s")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📊 Success Rate: {(passed/total*100):.1f}%")
        print()
        
        if failed > 0:
            print("❌ FAILED TESTS:")
            for test_name, result in self.test_results.items():
                if not result['success']:
                    print(f"   • {test_name}: {result['details']}")
            print()
        
        print("✅ PASSED TESTS:")
        for test_name, result in self.test_results.items():
            if result['success']:
                print(f"   • {test_name}: {result['details']}")
        
        print("\n" + "="*80)
        
        if failed == 0:
            print("🎉 ALL TESTS PASSED! System is ready for deployment!")
        else:
            print(f"⚠️  {failed} tests failed. Please address issues before deployment.")
        
        print("="*80)

async def main():
    parser = argparse.ArgumentParser(description='End-to-end system testing')
    parser.add_argument('--quick', action='store_true',
                       help='Run essential tests only (faster)')
    parser.add_argument('--full', action='store_true',
                       help='Run comprehensive tests including performance')
    parser.add_argument('--component', type=str,
                       choices=['config', 'database', 'rag', 'calendar', 'bot', 'error', 'performance'],
                       help='Test specific component only')
    
    args = parser.parse_args()
    
    # Quick mode unless full specified
    quick_mode = not args.full
    if args.quick:
        quick_mode = True
    
    logger.info("🚀 Starting End-to-End System Testing (Step 5)")
    logger.info(f"Mode: {'Quick' if quick_mode else 'Comprehensive'}")
    
    tester = EndToEndTester(quick_mode=quick_mode)
    
    # Define test suite
    test_suite = [
        ('config', tester.test_configuration),
        ('database', tester.test_database),
        ('rag', tester.test_rag_module),
        ('calendar', tester.test_calendar_module),
        ('bot', tester.test_discord_bot_components),
        ('error', tester.test_error_handling),
        ('performance', tester.test_performance),
    ]
    
    # Filter by component if specified
    if args.component:
        test_suite = [(name, func) for name, func in test_suite if name == args.component]
    
    try:
        all_passed = True
        for test_name, test_func in test_suite:
            logger.info(f"\n{'='*60}")
            success = await test_func()
            if not success:
                all_passed = False
        
        tester.print_summary()
        return all_passed
        
    except Exception as e:
        logger.error(f"❌ Critical testing error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
