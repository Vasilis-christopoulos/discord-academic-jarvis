"""
Calendar Utilities Module

This module provides utility functions for date/time parsing, formatting, and conversion
operations commonly needed when working with calendar and task data from various APIs.

Key Features:
- RFC 3339 date parsing with timezone support
- Local timezone formatting for user-friendly display
- HTML to Discord Markdown conversion
- Epoch timestamp conversion utilities

The utilities handle various date formats from Google Calendar API, user input,
and database storage while maintaining timezone awareness throughout the system.
"""

import re
import datetime as dt
from typing import Optional, List, Dict, Any, Tuple
import pytz

# Date Parsing & Formatting Utilities

def parse_iso(iso: str) -> dt.datetime:
    """
    Safely parse RFC 3339 strings into timezone-aware datetime objects.
    
    Handles various ISO 8601 / RFC 3339 formats commonly returned by APIs:
    - With 'Z' suffix (UTC): "2025-06-02T14:30:00Z"
    - With timezone offset: "2025-06-02T14:30:00-04:00"
    - With milliseconds: "2025-06-02T14:30:00.123-04:00"
    
    Args:
        iso: RFC 3339 formatted date string
        
    Returns:
        datetime: Timezone-aware datetime object
        
    Examples:
        >>> parse_iso("2025-06-02T14:30:00Z")
        datetime.datetime(2025, 6, 2, 14, 30, tzinfo=datetime.timezone.utc)
        >>> parse_iso("2025-06-02T14:30:00-04:00")
        datetime.datetime(2025, 6, 2, 14, 30, tzinfo=datetime.timezone(-4:00))
    """
    # Convert 'Z' suffix to explicit UTC offset
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    
    # Handle milliseconds in timestamps - remove them but keep timezone
    if "." in iso and ("+" in iso[iso.find("T"):] or "-" in iso[iso.find("T"):]):
        base, rest = iso.split('.', 1)
        # Find timezone offset and preserve it
        off_idx = rest.find('+') if '+' in rest else rest.find('-')
        iso = base + rest[off_idx:]
    
    # Parse the ISO string
    dt_obj = dt.datetime.fromisoformat(iso)
    
    # Ensure timezone awareness (default to UTC if no timezone)
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
    
    return dt_obj


def format_local(dt_obj: dt.datetime, tz_name: str = "America/Toronto", fmt: str = "%b %d, %Y %I:%M %p") -> str:
    """
    Convert a timezone-aware datetime to local timezone and format for display.
    
    Args:
        dt_obj: Timezone-aware datetime object to convert
        tz_name: Target timezone name (e.g., "America/Toronto", "UTC")
        fmt: strftime format string for output
        
    Returns:
        str: Formatted local time string
        
    Examples:
        >>> dt_obj = parse_iso("2025-06-02T18:30:00Z")
        >>> format_local(dt_obj, "America/Toronto")
        'Jun 02, 2025 02:30 PM'
    """
    local_tz = pytz.timezone(tz_name)
    return dt_obj.astimezone(local_tz).strftime(fmt)


def format_iso_to_local(iso: str, tz_name: str = "America/Toronto", fmt: str = "%b %d, %Y %I:%M %p") -> str:
    """
    Parse an ISO string and format it as local time in one step.
    
    Convenience function that combines parse_iso() and format_local().
    
    Args:
        iso: RFC 3339 formatted date string
        tz_name: Target timezone for display
        fmt: strftime format string
        
    Returns:
        str: Formatted local time string
        
    Examples:
        >>> format_iso_to_local("2025-06-02T18:30:00Z", "America/Toronto")
        'Jun 02, 2025 02:30 PM'
    """
    return format_local(parse_iso(iso), tz_name, fmt)


def epoch_from_iso(iso: Optional[str]) -> Optional[int]:
    """
    Convert an ISO timestamp to Unix epoch seconds.
    
    Useful for database storage and API calls that expect epoch timestamps.
    
    Args:
        iso: RFC 3339 formatted date string, or None
        
    Returns:
        int: Unix timestamp in seconds, or None if input is None
        
    Examples:
        >>> epoch_from_iso("2025-06-02T18:30:00Z")
        1717346200
        >>> epoch_from_iso(None)
        None
    """
    if not iso:
        return None
    return int(parse_iso(iso).timestamp())

# HTML to Discord Markdown Conversion

def html_to_discord_md(html: str) -> str:
    """
    Convert HTML links to Discord-compatible markdown format.
    
    Transforms HTML anchor tags into Discord markdown links:
    <a href="URL">text</a> → [text](URL)
    
    This is commonly needed when processing event descriptions from Google Calendar
    that may contain HTML formatting.
    
    Args:
        html: String potentially containing HTML anchor tags
        
    Returns:
        str: String with HTML links converted to markdown format
        
    Examples:
        >>> html_to_discord_md('<a href="https://zoom.us/j/123">Join Meeting</a>')
        '[Join Meeting](https://zoom.us/j/123)'
        >>> html_to_discord_md('Regular text with no links')
        'Regular text with no links'
    """
    pattern = re.compile(r'<a\s+href="([^\"]+)"[^>]*>(.*?)</a>')
    return pattern.sub(lambda m: f"[{m.group(2)}]({m.group(1)})", html)