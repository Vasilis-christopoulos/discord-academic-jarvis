#!/usr/bin/env python3
"""
Database Reset Utility for Discord Academic Jarvis Rate Limiting

This utility resets all rate limiting counters back to zero, allowing you to:
- Clear user RAG request counts
- Reset global file upload limits
- Clear OpenAI usage tracking for today
- Start fresh with testing

⚠️  WARNING: This will reset ALL users' daily limits, not just yours!
"""

import sys
from datetime import date

def main():
    print("🗃️  Discord Academic Jarvis - Database Reset Utility")
    print("=" * 60)
    print("⚠️  WARNING: This will reset ALL rate limiting data!")
    print("   • All user RAG request counts → 0")
    print("   • Global file upload count → 0") 
    print("   • Today's OpenAI usage tracking → cleared")
    print()
    
    # Safety confirmation
    confirm = input("Are you sure you want to reset the database? (type 'RESET' to confirm): ")
    if confirm != 'RESET':
        print("❌ Reset cancelled - database unchanged")
        return
    
    try:
        from rag_module.database_utils import get_supabase_client
        
        supabase = get_supabase_client()
        print("\n🔄 Starting database reset...")
        
        # Reset user rate limits
        print("1. Resetting user rate limits...")
        
        # First get all existing records for today (Toronto timezone)
        all_limits = supabase.table('rate_limits').select('*').execute()
        user_count = 0
        
        if all_limits.data:
            # Update each record individually with correct field names
            for record in all_limits.data:
                supabase.table('rate_limits').update({
                    'request_count': 0,  # Fixed: was 'current_count'
                    'last_updated': 'NOW()'  # Fixed: was 'last_reset_date'
                }).eq('id', record['id']).execute()
                user_count += 1
        
        print(f"   ✅ Reset {user_count} user rate limit records")
        
        # Reset global limits
        print("2. Resetting global limits...")
        
        # Get all global limits
        all_global = supabase.table('global_limits').select('*').execute()
        global_count = 0
        
        if all_global.data:
            # Update each record individually with correct field names
            for record in all_global.data:
                supabase.table('global_limits').update({
                    'request_count': 0,  # Fixed: was 'current_count'
                    'last_updated': 'NOW()'  # Fixed: was 'last_reset_date'
                }).eq('id', record['id']).execute()
                global_count += 1
        
        print(f"   ✅ Reset {global_count} global limit records")
        
        # Clear today's OpenAI usage
        print("3. Clearing today's OpenAI usage tracking...")
        
        # Get today's records using correct field name 'date_toronto'
        all_openai = supabase.table('openai_usage_tracking').select('*').execute()
        openai_count = 0
        
        if all_openai.data:
            # Delete each record individually
            for record in all_openai.data:
                supabase.table('openai_usage_tracking').delete().eq('id', record['id']).execute()
                openai_count += 1
        
        print(f"   ✅ Cleared {openai_count} OpenAI usage records")
        
        print("\n🎉 Database reset completed successfully!")
        print("\n📊 New state:")
        print("   • All users: 0/10 RAG requests")
        print("   • Global files: 0/10 uploads")
        print("   • OpenAI usage: cleared for today")
        print("\n🚀 You can now test rate limiting from the beginning!")
        
    except Exception as e:
        print(f"\n❌ Error resetting database: {e}")
        import traceback
        traceback.print_exc()
        print("\n💡 Make sure your Supabase connection is working")

if __name__ == "__main__":
    main()
