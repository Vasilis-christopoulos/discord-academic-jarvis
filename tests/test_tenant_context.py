import pytest
from pathlib import Path
import tenant_context

# Point at our sample fixture
tenant_context.TENANTS_FILE = "tests/fixtures/tenants_sample.json"

def test_global_context(tmp_path):
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
def test_channel_context(tmp_path, channel_id, expected_type, expected_ctx):
    ctx = tenant_context.load_tenant_context(111, channel_id)
    assert ctx["type"] == expected_type
    assert ctx["name"] == expected_ctx
    assert Path(ctx["data_dir"]).exists()
