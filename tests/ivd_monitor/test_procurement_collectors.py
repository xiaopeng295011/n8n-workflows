"""Tests for procurement source collectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from src.ivd_monitor.sources.base import HttpResponse
from src.ivd_monitor.sources.procurement import ConfigurableProcurementCollector


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
def ccgp_response():
    """CCGP JSON response."""
    return (Path(__file__).parent.parent / "data" / "procurement" / "ccgp_page1.json").read_text(encoding="utf-8")


@pytest.fixture
def ccgp_response_page2():
    """CCGP JSON response for page 2."""
    return (Path(__file__).parent.parent / "data" / "procurement" / "ccgp_page2.json").read_text(encoding="utf-8")


def test_procurement_collector_json_mode(ccgp_response):
    """Test procurement collector with JSON mode."""
    mock_client = MockHttpClient(
        {
            "page=1": ccgp_response,
        }
    )

    collector = ConfigurableProcurementCollector(
        source_id="test_ccgp",
        http_client=mock_client,
        region="CN",
        base_url="https://www.ccgp.gov.cn",
        list_url_template="https://search.ccgp.gov.cn/bxsearch?page={page}",
        mode="json",
        pagination={"start": 1, "pages": 1},
        json_list_path=["data", "resultList"],
        fields={
            "title": {"path": "title"},
            "url": {"path": "url"},
            "publish_date": {"path": "timeOpen", "date_format": "%Y-%m-%d %H:%M:%S"},
            "summary": {"path": "brief", "optional": True},
            "status": {"path": "pubType", "optional": True},
            "budget": {"path": "budget", "optional": True},
        },
    )

    records = list(collector.collect())

    assert len(records) == 2

    record1 = records[0]
    assert record1.source == "test_ccgp"
    assert record1.source_type == "procurement"
    assert record1.category == "Procurement"
    assert "国家医疗设备采购项目一" in record1.title
    assert record1.url == "https://www.ccgp.gov.cn/cggg/zygg/notice-1.html"
    assert record1.region == "CN"
    assert record1.metadata["bid_status"] == "招标公告"
    assert record1.metadata["budget"] == "100万元"

    record2 = records[1]
    assert "国家医疗设备采购项目二" in record2.title


def test_procurement_collector_deduplication(ccgp_response, ccgp_response_page2):
    """Test that procurement collector deduplicates by URL across pages."""
    mock_client = MockHttpClient(
        {
            "page=1": ccgp_response,
            "page=2": ccgp_response_page2,
        }
    )

    collector = ConfigurableProcurementCollector(
        source_id="test_ccgp",
        http_client=mock_client,
        region="CN",
        base_url="https://www.ccgp.gov.cn",
        list_url_template="https://search.ccgp.gov.cn/bxsearch?page={page}",
        mode="json",
        pagination={"start": 1, "pages": 2},
        json_list_path=["data", "resultList"],
        fields={
            "title": {"path": "title"},
            "url": {"path": "url"},
            "publish_date": {"path": "timeOpen", "date_format": "%Y-%m-%d %H:%M:%S"},
        },
    )

    records = list(collector.collect())

    assert len(records) == 2

    urls = [r.url for r in records]
    assert len(urls) == len(set(urls))


def test_procurement_collector_html_mode():
    """Test procurement collector with HTML mode."""
    html_content = """
    <html>
        <body>
            <ul class="notice-list">
                <li>
                    <a href="/notice/123" class="notice-link">北京医疗采购公告</a>
                    <span class="date">2024-03-01</span>
                    <span class="status">招标中</span>
                </li>
                <li>
                    <a href="/notice/124" class="notice-link">北京医疗采购公告2</a>
                    <span class="date">2024-03-02</span>
                </li>
            </ul>
        </body>
    </html>
    """

    mock_client = MockHttpClient({"beijing": html_content})

    collector = ConfigurableProcurementCollector(
        source_id="test_beijing",
        http_client=mock_client,
        region="CN-11",
        base_url="https://www.ccgp-beijing.gov.cn",
        list_url_template="https://www.ccgp-beijing.gov.cn/notice",
        mode="html",
        pagination={"start": 1, "pages": 1},
        fields={
            "item_selector": {"selector": "ul.notice-list > li"},
            "title": {"selector": "a.notice-link"},
            "url": {"selector": "a.notice-link", "attr": "href"},
            "publish_date": {"selector": "span.date", "date_format": "%Y-%m-%d"},
            "status": {"selector": "span.status", "optional": True},
        },
    )

    records = list(collector.collect())

    assert len(records) == 2

    record1 = records[0]
    assert record1.source == "test_beijing"
    assert record1.source_type == "procurement"
    assert "北京医疗采购公告" in record1.title
    assert record1.url == "https://www.ccgp-beijing.gov.cn/notice/123"
    assert record1.region == "CN-11"
    assert record1.metadata["bid_status"] == "招标中"


def test_procurement_collector_with_regex_extraction():
    """Test procurement collector with regex field extraction."""
    json_content = """
    {
        "data": {
            "items": [
                {
                    "title": "医疗器械采购项目 - 预算：150万元",
                    "link": "http://example.com/1"
                }
            ]
        }
    }
    """

    mock_client = MockHttpClient({"example": json_content})

    collector = ConfigurableProcurementCollector(
        source_id="test_regex",
        http_client=mock_client,
        region="CN",
        list_url_template="http://example.com/api",
        mode="json",
        pagination={"start": 1, "pages": 1},
        json_list_path=["data", "items"],
        fields={
            "title": {"path": "title"},
            "url": {"path": "link"},
            "budget": {"path": "title", "regex": r"预算[：:]\s*(\d+万元)", "optional": True},
        },
    )

    records = list(collector.collect())

    assert len(records) == 1
    assert records[0].metadata["budget"] == "150万元"


def test_procurement_collector_disabled():
    """Test that disabled collector returns no records."""
    mock_client = MockHttpClient({})

    collector = ConfigurableProcurementCollector(
        source_id="test_disabled",
        http_client=mock_client,
        enabled=False,
        list_url_template="http://example.com",
    )

    records = list(collector.collect())

    assert len(records) == 0
    assert len(mock_client.requests) == 0
