"""Tests for the collector manager."""

from datetime import datetime
from typing import List

import pytest

from src.ivd_monitor.collector import BaseCollector
from src.ivd_monitor.collector_manager import CollectorManager
from src.ivd_monitor.models import CollectorStats, RawRecord


class SuccessfulCollector(BaseCollector):
    """Collector that returns a fixed set of records."""

    def __init__(self, name="success_collector"):
        super().__init__()
        self.config.name = name

    async def _collect_records(self, stats: CollectorStats) -> List[RawRecord]:
        return [
            RawRecord(
                source=self.name,
                url="https://example.com/success",
                title="Success",
                publish_date="2023-11-01 08:00:00",
            )
        ]


class FailingCollector(BaseCollector):
    """Collector that raises an exception."""

    def __init__(self, name="fail_collector"):
        super().__init__()
        self.config.name = name

    async def _collect_records(self, stats: CollectorStats) -> List[RawRecord]:
        raise RuntimeError("Collector failure")


@pytest.mark.asyncio
async def test_collector_manager_handles_partial_failures():
    """Collector manager should aggregate records and errors."""
    manager = CollectorManager(
        collectors=[SuccessfulCollector(), FailingCollector()]
    )

    result = await manager.collect_all()

    assert result.success is False
    assert len(result.records) == 1
    assert result.records[0].publish_date == "2023-11-01T08:00:00Z"
    assert any(error.collector_name == "fail_collector" for error in result.errors)
    assert result.stats["success_collector"].records_collected == 1
    assert result.stats["fail_collector"].records_failed == 1
