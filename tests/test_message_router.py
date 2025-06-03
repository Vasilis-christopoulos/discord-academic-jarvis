import pytest
from message_router import is_module_allowed

@pytest.mark.parametrize("mod,ctx,exp", [
    ("rag", {"type":"rag"}, True),
    ("calendar", {"type":"rag"}, False),
    ("rag", {"type":"calendar"}, False),
    ("calendar", {"type":"calendar"}, True),
    ("rag", {"type":"rag-calendar"}, True),
    ("calendar", {"type":"rag-calendar"}, True),
    ("fallback", {"type":"rag"}, True),
    ("fallback", {"type":"calendar"}, True),
    ("fallback", {"type":"rag-calendar"}, True),
])
def test_module_allowed(mod, ctx, exp):
    assert is_module_allowed(mod, ctx) is exp
