# tests/test_query_parser_integration.py
import os
import pytest
from datetime import datetime
from calendar_module.query_parser import parse_query, CalQuery

pytestmark = pytest.mark.asyncio

def _skip_if_no_key():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("Skipping integration test: no OPENAI_API_KEY")

async def _assert_common(p: CalQuery):
    assert isinstance(p, CalQuery)
    assert isinstance(p.applicable, bool)
    # limit, if set, must be >0
    if p.limit is not None:
        assert p.limit > 0

@pytest.mark.asyncio
async def test_date_only_query():
    _skip_if_no_key()
    today = datetime.today()
    p = await parse_query("What's on Friday?", today)
    await _assert_common(p)
    assert p.applicable is True
    assert p.type == "both"
    assert p.filter is not None  # The LLM extracts "on Friday" as a filter
    assert p.limit == 10  # Default limit
    assert p.date_from is not None  # Dates are returned as ISO strings
    assert p.date_to is not None

@pytest.mark.asyncio
async def test_next_three_deadlines():
    _skip_if_no_key()
    today = datetime.today()
    p = await parse_query("Next 3 project deadlines?", today)
    await _assert_common(p)
    assert p.applicable is True
    # allow either 'task' or 'both' if the parser hedges
    assert p.type in ("task")
    assert p.limit == 3
    assert p.filter and "project deadline" in p.filter.lower()
    # The LLM may set date ranges for "next" queries
    assert p.date_from is not None or p.date_to is not None

@pytest.mark.asyncio
async def test_bounded_window_query():
    _skip_if_no_key()
    today = datetime.today()
    p = await parse_query("Show me events between May 1 and May 5", today)
    await _assert_common(p)
    assert p.applicable is True
    assert p.type in ["event", "both"]  # Accept either response from OpenAI
    assert p.limit == 10  # Default limit, not extracted from the date range
    assert p.date_from is not None  # Dates are returned as ISO strings
    assert p.date_to is not None
    # Both dates should be present for bounded queries

@pytest.mark.asyncio
async def test_non_calendar_query():
    _skip_if_no_key()
    today = datetime.today()
    p = await parse_query("How hard is this class?", today)
    await _assert_common(p)
    assert p.applicable is False
    # All other fields should then be None
    assert p.type      is None
    assert p.filter    is None
    assert p.limit     is None
    assert p.date_from is None
    assert p.date_to   is None
