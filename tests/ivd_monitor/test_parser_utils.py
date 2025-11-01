"""Tests for parser utilities."""

from datetime import datetime, timezone

import pytest

from src.ivd_monitor.parser_utils import (
    ensure_list,
    normalize_publish_date,
    sanitize_html,
)


def test_sanitize_html_removes_scripts():
    """Sanitize HTML should remove script tags."""
    html = '<p>Hello</p><script>alert("xss")</script>'
    clean = sanitize_html(html)
    assert "<script>" not in clean
    assert "alert" not in clean
    assert "Hello" in clean


def test_sanitize_html_removes_dangerous_attributes():
    """Sanitize HTML should remove dangerous attributes."""
    html = '<a href="/page" onclick="alert(1)">Link</a>'
    clean = sanitize_html(html)
    assert "onclick" not in clean
    assert 'href="/page"' in clean


def test_normalize_publish_date_iso8601():
    """Normalize date should convert to ISO8601 UTC format with Z suffix."""
    result = normalize_publish_date("2023-11-01T08:00:00+00:00")
    assert result == "2023-11-01T08:00:00Z"


def test_normalize_publish_date_naive_datetime():
    """Normalize date should treat naive dates as UTC by default."""
    result = normalize_publish_date("2023-11-01 08:00:00")
    assert result is not None
    assert result.startswith("2023-11-01T08:00:00")
    assert result.endswith("Z")


def test_normalize_publish_date_datetime_object():
    """Normalize date should handle datetime objects."""
    dt = datetime(2023, 11, 1, 8, 0, 0, tzinfo=timezone.utc)
    result = normalize_publish_date(dt)
    assert result == "2023-11-01T08:00:00Z"


def test_ensure_list_string():
    """Ensure list should convert a single string to a list."""
    result = ensure_list("item")
    assert result == ["item"]


def test_ensure_list_list():
    """Ensure list should keep a list as is."""
    result = ensure_list(["item1", "item2"])
    assert result == ["item1", "item2"]


def test_ensure_list_none():
    """Ensure list should return an empty list for None."""
    result = ensure_list(None)
    assert result == []
