"""Integration tests for the scraper core."""

import asyncio
from datetime import datetime

import pytest

from src.ivd_monitor.collector_manager import CollectorManager
from src.ivd_monitor.example_collector import ExampleRSSCollector
from src.ivd_monitor.logging_config import setup_logging
from src.ivd_monitor.models import CollectorConfig


SAMPLE_RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <link>https://example.com</link>
    <description>Sample RSS feed for testing</description>
    <item>
      <title>Test Article 1</title>
      <link>https://example.com/article1</link>
      <description>This is the first test article</description>
      <pubDate>Wed, 01 Nov 2023 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Test Article 2</title>
      <link>https://example.com/article2</link>
      <description>This is the second test article</description>
      <pubDate>Wed, 01 Nov 2023 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class MockHTTPClient:
    """Mock HTTP client that returns sample RSS feed."""

    def __init__(self, config=None):
        self.config = config

    async def get_async(self, url, **kwargs):
        class MockResponse:
            text = SAMPLE_RSS_FEED
            status_code = 200

        return MockResponse()


@pytest.mark.asyncio
async def test_end_to_end_collection_flow(monkeypatch):
    """Test end-to-end collection flow with example collector."""
    setup_logging(console=False)

    config = CollectorConfig(
        name="test_rss_collector",
        timeout_seconds=10.0,
        max_retries=2,
    )

    collector = ExampleRSSCollector(
        feed_url="https://example.com/feed.xml",
        config=config,
    )

    monkeypatch.setattr(collector, "http_client", MockHTTPClient())

    result = await collector.collect()

    assert result.success is True
    assert result.record_count == 2
    assert result.stats.records_collected == 2
    assert result.stats.duration_seconds is not None

    assert result.records[0].title == "Test Article 1"
    assert result.records[0].url == "https://example.com/article1"
    assert result.records[0].publish_date is not None

    assert result.records[1].title == "Test Article 2"
    assert result.records[1].url == "https://example.com/article2"


@pytest.mark.asyncio
async def test_collector_manager_integration(monkeypatch):
    """Test collector manager with multiple collectors."""
    setup_logging(console=False)

    config1 = CollectorConfig(name="collector1", max_retries=2)
    config2 = CollectorConfig(name="collector2", max_retries=2)

    collector1 = ExampleRSSCollector("https://example.com/feed1.xml", config1)
    collector2 = ExampleRSSCollector("https://example.com/feed2.xml", config2)

    monkeypatch.setattr(collector1, "http_client", MockHTTPClient())
    monkeypatch.setattr(collector2, "http_client", MockHTTPClient())

    manager = CollectorManager([collector1, collector2])
    result = await manager.collect_all()

    assert result.success is True
    assert len(result.records) == 4
    assert len(result.stats) == 2
    assert result.stats["collector1"].records_collected == 2
    assert result.stats["collector2"].records_collected == 2
