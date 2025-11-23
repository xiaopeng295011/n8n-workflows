"""Tests for industry media source collectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from src.ivd_monitor.sources.base import HttpResponse
from src.ivd_monitor.sources.media import IndustryMediaCollector, RSSFeedCollector


class MockHttpClient:
    """Mock HTTP client for testing."""

    def __init__(self, responses: Dict[str, str]) -> None:
        self.responses = responses
        self.requests: list[tuple[str, Optional[Dict[str, Any]]]] = []

    def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        self.requests.append((url, params))

        for pattern, content in self.responses.items():
            if pattern in url:
                return HttpResponse(
                    status_code=200,
                    text=content,
                    url=url,
                    headers={},
                )

        return HttpResponse(
            status_code=404,
            text="Not Found",
            url=url,
            headers={},
        )


@pytest.fixture
def rss_feed():
    """Sample RSS feed."""
    return (Path(__file__).parent.parent / "data" / "media" / "sample_rss.xml").read_text(encoding="utf-8")


@pytest.fixture
def html_list():
    """Sample HTML article list."""
    return (Path(__file__).parent.parent / "data" / "media" / "industry_list.html").read_text(encoding="utf-8")


def test_rss_feed_collector(rss_feed):
    """Test RSS feed collector."""
    mock_client = MockHttpClient({"ivdnews": rss_feed})

    collector = RSSFeedCollector(
        source_id="test_rss",
        http_client=mock_client,
        feed_url="https://www.ivdnews.cn/feed",
        category="Industry Media",
        region="CN",
    )

    records = list(collector.collect())

    assert len(records) == 2

    record1 = records[0]
    assert record1.source == "test_rss"
    assert record1.source_type == "industry_media"
    assert record1.category == "Industry Media"
    assert "New IVD Device Approved" in record1.title
    assert record1.url == "https://www.ivdnews.cn/article/2024/device-approval"
    assert record1.region == "CN"
    assert record1.summary is not None

    record2 = records[1]
    assert "IVD Market Growth" in record2.title


def test_rss_feed_collector_deduplication(rss_feed):
    """Test RSS feed collector deduplicates by URL."""
    mock_client = MockHttpClient({"ivdnews": rss_feed})

    collector = RSSFeedCollector(
        source_id="test_rss",
        http_client=mock_client,
        feed_url="https://www.ivdnews.cn/feed",
        category="Industry Media",
    )

    records = list(collector.collect())

    urls = [r.url for r in records]
    assert len(urls) == len(set(urls))


def test_industry_media_collector_html_mode(html_list):
    """Test industry media collector with HTML mode."""
    mock_client = MockHttpClient({"medinnovation": html_list})

    collector = IndustryMediaCollector(
        source_id="test_html",
        http_client=mock_client,
        mode="html",
        list_url="https://www.medinnovation.cn/articles",
        category="Industry Media",
        region="CN",
        item_selector="div.article",
        title_selector="h2 a",
        url_selector="h2 a",
        summary_selector="p.summary",
        date_selector="time",
        date_format="%Y-%m-%d",
        base_url="https://www.medinnovation.cn",
    )

    records = list(collector.collect())

    assert len(records) == 2

    record1 = records[0]
    assert record1.source == "test_html"
    assert record1.source_type == "industry_media"
    assert record1.category == "Industry Media"
    assert "新型体外诊断技术" in record1.title
    assert record1.url == "https://www.medinnovation.cn/articles/innovation-1"
    assert record1.region == "CN"
    assert "检测效率" in record1.summary

    urls = [r.url for r in records]
    assert len(urls) == len(set(urls))


def test_industry_media_collector_rss_mode(rss_feed):
    """Test industry media collector with RSS mode."""
    mock_client = MockHttpClient({"ivdnews": rss_feed})

    collector = IndustryMediaCollector(
        source_id="test_rss_mode",
        http_client=mock_client,
        mode="rss",
        feed_url="https://www.ivdnews.cn/feed",
        category="Industry Media",
    )

    records = list(collector.collect())

    assert len(records) == 2
    assert all(r.source_type == "industry_media" for r in records)


def test_media_collector_disabled():
    """Test that disabled collector returns no records."""
    mock_client = MockHttpClient({})

    collector = RSSFeedCollector(
        source_id="test_disabled",
        http_client=mock_client,
        enabled=False,
        feed_url="https://www.example.com/feed",
    )

    records = list(collector.collect())

    assert len(records) == 0
    assert len(mock_client.requests) == 0


def test_media_collector_handles_missing_summary(html_list):
    """Test that collector handles missing summary gracefully."""
    html_no_summary = """
    <html>
        <body>
            <div class="article">
                <h2><a href="/article/1">Title Only Article</a></h2>
                <time datetime="2024-03-10">2024-03-10</time>
            </div>
        </body>
    </html>
    """

    mock_client = MockHttpClient({"example": html_no_summary})

    collector = IndustryMediaCollector(
        source_id="test_missing",
        http_client=mock_client,
        mode="html",
        list_url="https://www.example.com/articles",
        item_selector="div.article",
        title_selector="h2 a",
        url_selector="h2 a",
        summary_selector="p.summary",
        date_selector="time",
        base_url="https://www.example.com",
    )

    records = list(collector.collect())

    assert len(records) == 1
    assert records[0].summary is None
