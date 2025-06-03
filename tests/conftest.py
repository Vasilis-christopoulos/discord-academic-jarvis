# tests/conftest.py
import sys, os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Insert the project root (one level up) onto sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# Set up test environment variables BEFORE any imports
test_env = {
    "DISCORD_TOKEN": "test_discord_token_12345",
    "OPENAI_API_KEY": "test_openai_key_12345", 
    "PINECONE_API_KEY": "test_pinecone_key_12345",
    "PINECONE_CALENDAR_INDEX": "test-calendar-index",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_API_KEY": "test_supabase_key_12345",
    "TENANTS_FILE": "tests/fixtures/tenants_sample.json"
}

for key, value in test_env.items():
    if key not in os.environ:
        os.environ[key] = value

# Early mocking to prevent real API client initialization
# This needs to happen before any modules are imported that use these clients
_supabase_patcher = patch('supabase.create_client')
_pinecone_patcher = patch('pinecone.Pinecone')
_openai_patcher = patch('openai.OpenAI')

# Start patches immediately
mock_supabase = _supabase_patcher.start()
mock_pinecone = _pinecone_patcher.start()
mock_openai = _openai_patcher.start()

# Configure the mocks
mock_supabase_instance = MagicMock()
mock_supabase.return_value = mock_supabase_instance

mock_pinecone_instance = MagicMock()
mock_pinecone.return_value = mock_pinecone_instance

mock_openai_instance = MagicMock()
mock_openai.return_value = mock_openai_instance

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment with mocked external dependencies."""
    # Patches are already started above, just yield to maintain the session
    yield
    
    # Clean up patches when session ends
    _supabase_patcher.stop()
    _pinecone_patcher.stop() 
    _openai_patcher.stop()

@pytest.fixture
def sample_tenant_config():
    """Provide a sample tenant configuration for testing."""
    """Provide a sample tenant configuration for testing."""
    return {
        "guild_id": 111,
        "name": "testguild",
        "description": "Test guild",
        "calendar_id": "cal@ex.com",
        "tasklist_id": "test_tasklist_id", 
        "data_dir": "data/111",
        "vector_store_path": "vector_store/111",
        "timezone": "America/Toronto",
        "channels": {
            222: {
                "name": "test-channel1",
                "description": "Test channel",
                "type": "rag",
                "data_dir": "data/111/course_A",
                "vector_store_path": "vector_store/111/course_A"
            }
        }
    }
