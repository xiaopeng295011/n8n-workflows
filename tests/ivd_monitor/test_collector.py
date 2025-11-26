"""Tests for base collector implementation."""

from datetime import datetime
from typing import List

import pytest

from src.ivd_monitor.collector import BaseCollector
from src.ivd_monitor.models import CollectorConfig, CollectorStats, RawRecord


class MockCollector(BaseCollector):
    """Mock collector for testing."""

    def __init__(self, config=None, records=None, should_fail=False):
        super().__init__(config)
        self.mock_records = records or []
        self.should_fail = should_fail

    async def _collect_records(self, stats: CollectorStats) -> List[RawRecord]:
        if self.should_fail:
            raise ValueError("Mock collector failure")
        return self.mock_records


@pytest.mark.asyncio
async def test_collector_collect_success():
    """Collector should successfully collect records."""
    mock_records = [
        RawRecord(
            source="test",
            url="https://example.com/1",
            title="Test Record 1",
        ),
        RawRecord(
            source="test",
            url="https://example.com/2",
            title="Test Record 2",
        ),
    ]

    collector = MockCollector(records=mock_records)
    result = await collector.collect()

    assert result.success is True
    assert result.record_count == 2
    assert result.stats is not None
    assert result.stats.records_collected == 2
    assert result.stats.records_failed == 0


@pytest.mark.asyncio
async def test_collector_collect_failure():
    """Collector should handle failures gracefully."""
    collector = MockCollector(should_fail=True)
    result = await collector.collect()

    assert result.success is False
    assert result.record_count == 0
    assert result.error_message == "Mock collector failure"
    assert result.stats is not None
    assert result.stats.records_failed == 1


@pytest.mark.asyncio
async def test_collector_normalize_date():
    """Collector should normalize dates to ISO8601 UTC format."""
    collector = MockCollector()

    normalized = collector.normalize_date("2023-11-01T08:00:00+00:00")
    assert normalized == "2023-11-01T08:00:00Z"

    normalized = collector.normalize_date("2023-11-01 08:00:00")
    assert normalized is not None
    assert normalized.endswith("Z")


@pytest.mark.asyncio
async def test_collector_stats_tracking():
    """Collector should track stats correctly."""
    mock_records = [
        RawRecord(source="test", url="https://example.com/1", title="Test 1"),
    ]

    collector = MockCollector(records=mock_records)
    result = await collector.collect()

    assert result.stats.duration_seconds is not None
    assert result.stats.duration_seconds >= 0
    assert result.stats.success_rate == 100.0
