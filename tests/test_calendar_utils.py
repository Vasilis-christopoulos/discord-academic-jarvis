# tests/test_calendar_utils.py
import pytest
import datetime as dt
import pytz
from utils.calendar_utils import (
    parse_iso, format_local, format_iso_to_local, 
    epoch_from_iso, html_to_discord_md
)

class TestParseIso:
    """Test ISO datetime parsing functionality."""
    
    def test_parse_iso_with_z_suffix(self):
        """Test parsing ISO string with Z suffix."""
        iso = "2025-05-28T15:30:00Z"
        result = parse_iso(iso)
        assert result.tzinfo is not None
        assert result.tzinfo == dt.timezone.utc
    
    def test_parse_iso_with_offset(self):
        """Test parsing ISO string with timezone offset."""
        iso = "2025-05-28T15:30:00-04:00"
        result = parse_iso(iso)
        assert result.tzinfo is not None
        assert result.hour == 15
    
    def test_parse_iso_with_milliseconds(self):
        """Test parsing ISO string with milliseconds (note: milliseconds are stripped by parse_iso)."""
        iso = "2025-05-28T15:30:00.123456+05:00"
        result = parse_iso(iso)
        assert result.tzinfo is not None
        # The parse_iso function actually strips microseconds, so it should be 0
        assert result.microsecond == 0
    
    def test_parse_iso_naive_becomes_utc(self):
        """Test that naive datetime gets UTC timezone."""
        iso = "2025-05-28T15:30:00"
        result = parse_iso(iso)
        assert result.tzinfo == dt.timezone.utc

class TestFormatLocal:
    """Test local timezone formatting."""
    
    def test_format_local_default_timezone(self):
        """Test formatting with default Toronto timezone."""
        dt_obj = dt.datetime(2025, 5, 28, 15, 30, tzinfo=dt.timezone.utc)
        result = format_local(dt_obj)
        assert "2025" in result
        assert "May 28" in result
    
    def test_format_local_custom_timezone(self):
        """Test formatting with custom timezone."""
        dt_obj = dt.datetime(2025, 5, 28, 15, 30, tzinfo=dt.timezone.utc)
        result = format_local(dt_obj, tz_name="US/Pacific")
        assert "2025" in result
    
    def test_format_local_custom_format(self):
        """Test formatting with custom format string."""
        dt_obj = dt.datetime(2025, 5, 28, 15, 30, tzinfo=dt.timezone.utc)
        result = format_local(dt_obj, fmt="%Y-%m-%d")
        assert result == "2025-05-28"

class TestFormatIsoToLocal:
    """Test combined ISO parsing and local formatting."""
    
    def test_format_iso_to_local(self):
        """Test converting ISO string to local formatted string."""
        iso = "2025-05-28T15:30:00Z"
        result = format_iso_to_local(iso)
        assert "2025" in result
        assert "May 28" in result

class TestEpochFromIso:
    """Test epoch timestamp conversion."""
    
    def test_epoch_from_iso_valid(self):
        """Test converting valid ISO to epoch."""
        iso = "2025-05-28T15:30:00Z"
        result = epoch_from_iso(iso)
        assert isinstance(result, int)
        assert result > 0
    
    def test_epoch_from_iso_none(self):
        """Test handling None input."""
        result = epoch_from_iso(None)
        assert result is None
    
    def test_epoch_from_iso_empty_string(self):
        """Test handling empty string."""
        result = epoch_from_iso("")
        assert result is None

class TestHtmlToDiscordMd:
    """Test HTML to Markdown conversion."""
    
    def test_simple_link_conversion(self):
        """Test converting simple HTML link to Markdown."""
        html = '<a href="https://example.com">Click here</a>'
        result = html_to_discord_md(html)
        assert result == "[Click here](https://example.com)"
    
    def test_multiple_links(self):
        """Test converting multiple HTML links."""
        html = 'Visit <a href="https://google.com">Google</a> or <a href="https://github.com">GitHub</a>'
        result = html_to_discord_md(html)
        assert "[Google](https://google.com)" in result
        assert "[GitHub](https://github.com)" in result
    
    def test_link_with_attributes(self):
        """Test converting link with additional attributes."""
        html = '<a href="https://example.com" target="_blank" class="link">Example</a>'
        result = html_to_discord_md(html)
        assert result == "[Example](https://example.com)"
    
    def test_no_links(self):
        """Test text without links remains unchanged."""
        text = "This is just plain text"
        result = html_to_discord_md(text)
        assert result == text
    
    def test_malformed_links(self):
        """Test handling of malformed HTML."""
        html = '<a href="https://example.com">Unclosed link'
        result = html_to_discord_md(html)
        # Should not crash, but may not convert properly
        assert isinstance(result, str)
