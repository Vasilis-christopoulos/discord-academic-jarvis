#!/usr/bin/env python3
"""
Configuration Verification Script for Discord Academic Jarvis

This script verifies that all environment variables and configuration files
are properly loaded and validates the system is ready for deployment.

Usage:
    python verify_configuration.py
"""

def verify_environment_variables():
    """Verify all required environment variables are loaded."""
    print("🔍 Verifying Environment Variables...")
    
    try:
        from settings import settings
        
        required_fields = [
            ('discord_token', 'Discord Bot Token'),
            ('openai_api_key', 'OpenAI API Key'),
            ('openai_vision_model', 'OpenAI Vision Model'),
            ('pinecone_api_key', 'Pinecone API Key'),
            ('supabase_url', 'Supabase URL'),
            ('supabase_api_key', 'Supabase API Key'),
            ('aws_access_key_id', 'AWS Access Key ID'),
            ('aws_secret_access_key', 'AWS Secret Access Key'),
            ('aws_region_name', 'AWS Region Name'),
        ]
        
        all_valid = True
        for field, description in required_fields:
            value = getattr(settings, field)
            is_valid = value and value.strip()
            status = '✅' if is_valid else '❌'
            print(f"  {status} {description}: {'SET' if is_valid else 'MISSING'}")
            if not is_valid:
                all_valid = False
        
        return all_valid
        
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        return False

def verify_tenant_configuration():
    """Verify tenant configuration is loaded correctly."""
    print("\n🔍 Verifying Tenant Configuration...")
    
    try:
        from settings import settings, TENANT_CONFIGS
        
        print(f"  ✅ Tenants file: {settings.tenants_file}")
        print(f"  ✅ Number of tenants: {len(TENANT_CONFIGS)}")
        
        if not TENANT_CONFIGS:
            print("  ❌ No tenants configured!")
            return False
        
        for tenant in TENANT_CONFIGS:
            print(f"  ✅ Tenant: {tenant.name} (Guild: {tenant.guild_id})")
            print(f"      Channels: {len(tenant.channels)}")
            print(f"      Admin Role: {tenant.admin_role_id}")
            print(f"      S3 Bucket: {tenant.s3_bucket}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error loading tenant configuration: {e}")
        return False

def verify_main_bot_imports():
    """Verify main bot can import without errors."""
    print("\n🔍 Verifying Main Bot Imports...")
    
    try:
        # Test main bot imports
        from main_bot import settings as bot_settings
        print("  ✅ Main bot imports successful")
        print(f"  ✅ Bot token available: {len(bot_settings.discord_token) > 0}")
        
        # Test RAG module imports
        from rag_module.database_utils import get_supabase_client
        print("  ✅ RAG module imports successful")
        
        # Test calendar module imports (with warning suppression)
        try:
            from calendar_module.calendar_handler import respond
            print("  ✅ Calendar module imports successful")
        except ImportError as e:
            print(f"  ⚠️  Calendar module import warning: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error importing main bot: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_database_connection():
    """Verify database connection is working."""
    print("\n🔍 Verifying Database Connection...")
    
    try:
        from rag_module.database_utils import get_supabase_client
        
        supabase = get_supabase_client()
        
        # Simple test query
        result = supabase.table('rate_limits').select('*').limit(1).execute()
        print(f"  ✅ Supabase connection successful")
        print(f"  ✅ Rate limits table accessible")
        
        return True
        
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def main():
    """Run all configuration verifications."""
    print("🚀 Discord Academic Jarvis - Configuration Verification")
    print("=" * 60)
    
    checks = [
        verify_environment_variables,
        verify_tenant_configuration,
        verify_main_bot_imports,
        verify_database_connection,
    ]
    
    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📊 Verification Summary:")
    
    check_names = [
        "Environment Variables",
        "Tenant Configuration", 
        "Main Bot Imports",
        "Database Connection"
    ]
    
    all_passed = True
    for i, (name, passed) in enumerate(zip(check_names, results)):
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All configuration checks passed! System is ready for deployment.")
    else:
        print("⚠️  Some configuration checks failed. Please fix the issues above.")
    
    return all_passed

if __name__ == "__main__":
    main()
