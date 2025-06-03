import pytest
from pathlib import Path
from unittest.mock import patch
import json
import tenant_context
from settings import TenantConfig, ChannelConfig

# Load the sample tenant data
def load_sample_tenant_configs():
    """Load sample tenant configurations for testing."""
    sample_path = Path(__file__).parent / "fixtures" / "tenants_sample.json"
    raw = json.loads(sample_path.read_text(encoding="utf-8"))
    configs = []
    for guild_str, cfg in raw.items():
        tenant = TenantConfig(guild_id=int(guild_str), **cfg)
        configs.append(tenant)
    return configs

@pytest.fixture
def mock_tenant_configs():
    """Fixture to mock TENANT_CONFIGS with sample data."""
    sample_configs = load_sample_tenant_configs()
    with patch('tenant_context.TENANT_CONFIGS', sample_configs):
        yield sample_configs

def test_global_context(tmp_path, mock_tenant_configs):
    ctx = tenant_context.load_tenant_context(111, 999)
    print(ctx) # debug
    assert ctx["name"] == "testguild"
    assert "calendar_id" in ctx
    # data_dir folder was auto‑created
    assert Path(ctx["data_dir"]).exists()

@pytest.mark.parametrize("channel_id,expected_type,expected_ctx", [
    (222, "rag", "test-channel1"),
    (333, "calendar", "test-channel2"),
    (444, "rag-calendar", "test-channel3"),
])
def test_channel_context(tmp_path, channel_id, expected_type, expected_ctx, mock_tenant_configs):
    ctx = tenant_context.load_tenant_context(111, channel_id)
    assert ctx["type"] == expected_type
    assert ctx["name"] == expected_ctx
    assert Path(ctx["data_dir"]).exists()
