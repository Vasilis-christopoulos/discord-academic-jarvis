#!/usr/bin/env python3
"""
Test Reset Database Script - Bypasses confirmation for testing
"""

import sys
from datetime import date

def test_reset():
    print("🧪 Testing Database Reset Script (Step 3)")
    print("=" * 50)
    
    try:
        from rag_module.database_utils import get_supabase_client
        
        supabase = get_supabase_client()
        print("✅ Connected to Supabase database")
        
        # Reset user rate limits
        print("\n1. Testing user rate limits reset...")
        
        # First get all existing records
        all_limits = supabase.table('rate_limits').select('*').execute()
        user_count = 0
        
        if all_limits.data:
            print(f"   Found {len(all_limits.data)} user rate limit records")
            # Update each record individually with correct field names
            for record in all_limits.data:
                try:
                    result = supabase.table('rate_limits').update({
                        'request_count': 0,
                        'last_updated': 'NOW()'
                    }).eq('id', record['id']).execute()
                    user_count += 1
                except Exception as e:
                    print(f"   ⚠️  Error updating record {record['id']}: {e}")
        else:
            print("   No user rate limit records found")
        
        print(f"   ✅ Reset {user_count} user rate limit records")
        
        # Reset global limits
        print("\n2. Testing global limits reset...")
        
        # Get all global limits
        all_global = supabase.table('global_limits').select('*').execute()
        global_count = 0
        
        if all_global.data:
            print(f"   Found {len(all_global.data)} global limit records")
            # Update each record individually with correct field names
            for record in all_global.data:
                try:
                    result = supabase.table('global_limits').update({
                        'request_count': 0,
                        'last_updated': 'NOW()'
                    }).eq('id', record['id']).execute()
                    global_count += 1
                except Exception as e:
                    print(f"   ⚠️  Error updating record {record['id']}: {e}")
        else:
            print("   No global limit records found")
        
        print(f"   ✅ Reset {global_count} global limit records")
        
        # Clear OpenAI usage
        print("\n3. Testing OpenAI usage tracking reset...")
        
        # Get all OpenAI records
        all_openai = supabase.table('openai_usage_tracking').select('*').execute()
        openai_count = 0
        
        if all_openai.data:
            print(f"   Found {len(all_openai.data)} OpenAI usage records")
            # Delete each record individually
            for record in all_openai.data:
                try:
                    result = supabase.table('openai_usage_tracking').delete().eq('id', record['id']).execute()
                    openai_count += 1
                except Exception as e:
                    print(f"   ⚠️  Error deleting record {record['id']}: {e}")
        else:
            print("   No OpenAI usage records found")
        
        print(f"   ✅ Cleared {openai_count} OpenAI usage records")
        
        print("\n🎉 Database reset script test completed successfully!")
        print("\n📊 Reset summary:")
        print(f"   • User records reset: {user_count}")
        print(f"   • Global records reset: {global_count}")
        print(f"   • OpenAI records cleared: {openai_count}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error testing reset script: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_reset()
    sys.exit(0 if success else 1)
