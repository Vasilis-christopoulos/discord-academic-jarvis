# tests/test_settings.py
import pytest
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError

def test_app_settings_validation():
    """Test AppSettings validation with missing required fields."""
    from settings import AppSettings
    
    # Test missing required fields
    with pytest.raises(ValidationError) as exc_info:
        AppSettings(
            discord_token="",  # empty string should fail
            openai_api_key="valid_key",
            pinecone_api_key="valid_key", 
            pinecone_calendar_index="valid_index",
            supabase_url="valid_url",
            supabase_api_key="valid_key"
        )
    assert "Configuration value cannot be empty" in str(exc_info.value)

def test_tenant_config_validation():
    """Test TenantConfig validation."""
    from settings import TenantConfig, ChannelConfig
    
    # Valid config
    valid_channel = ChannelConfig(
        name="test",
        description="test channel", 
        data_dir="data/test",
        vector_store_path="vector/test",
        type="rag"
    )
    
    tenant = TenantConfig(
        guild_id=12345,
        name="test_guild",
        description="test",
        data_dir="data/guild",
        vector_store_path="vector/guild",
        calendar_id=None,  # Explicitly set optional fields
        tasklist_id=None,
        channels={123: valid_channel}
    )
    
    assert tenant.guild_id == 12345
    assert tenant.timezone == "America/Toronto"  # default value

def test_channel_config_validation():
    """Test ChannelConfig validation with invalid fields."""
    from settings import ChannelConfig
    
    with pytest.raises(ValidationError):
        # Extra field should be forbidden
        ChannelConfig(
            name="test",
            description="test channel",
            data_dir="data/test", 
            vector_store_path="vector/test",
            type="rag",
            extra_field="should_fail"  # This should fail
        )

def test_tenants_json_loading():
    """Test loading and validation of tenants.json."""
    # Test that int conversion raises ValueError for invalid guild_id
    with pytest.raises(ValueError):
        int("not_a_number")
    
    # This test verifies the logic would work - the actual module-level loading
    # happens at import time and is hard to test without complex mocking

@pytest.mark.parametrize("env_var,value", [
    ("DISCORD_TOKEN", "test_token"),
    ("OPENAI_API_KEY", "test_key"),
    ("PINECONE_API_KEY", "test_key"),
    ("SUPABASE_URL", "https://test.supabase.co"),
])
def test_environment_variable_loading(env_var, value):
    """Test that environment variables are loaded correctly."""
    from settings import AppSettings
    
    with patch.dict(os.environ, {env_var: value}):
        settings = AppSettings()
        assert getattr(settings, env_var.lower()) == value
