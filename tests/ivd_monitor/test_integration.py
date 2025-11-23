"""Integration tests for procurement and media collectors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from src.ivd_monitor.database import IVDDatabase
from src.ivd_monitor.sources import build_collectors_from_config, load_sources_configuration
from src.ivd_monitor.sources.base import HttpResponse


class MockHttpClient:
    """Mock HTTP client for integration testing."""

    def __init__(self, responses: Dict[str, str]) -> None:
        self.responses = responses

    def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
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
def test_config(tmp_path: Path) -> Path:
    """Create a test configuration file."""
    config = {
        "sources": [
            {
                "source_id": "test_procurement",
                "collector_type": "procurement",
                "enabled": True,
                "region": "CN",
                "category": "Procurement",
                "extra_params": {
                    "mode": "json",
                    "list_url_template": "https://test.example.com/api?page={page}",
                    "pagination": {"start": 1, "pages": 1},
                    "json_list_path": ["data", "items"],
                    "fields": {
                        "title": {"path": "title"},
                        "url": {"path": "url"},
                        "publish_date": {"path": "date", "date_format": "%Y-%m-%d"},
                    },
                    "base_url": "https://test.example.com",
                },
            },
            {
                "source_id": "test_media",
                "collector_type": "rss_feed",
                "enabled": True,
                "region": "CN",
                "extra_params": {
                    "feed_url": "https://test.example.com/feed",
                    "category": "Industry Media",
                },
            },
            {
                "source_id": "disabled_source",
                "collector_type": "procurement",
                "enabled": False,
                "extra_params": {
                    "list_url_template": "https://disabled.example.com/api",
                },
            },
        ]
    }

    config_path = tmp_path / "test_sources.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


@pytest.fixture
def mock_responses() -> Dict[str, str]:
    """Create mock responses for testing."""
    return {
        "test.example.com/api": json.dumps(
            {
                "data": {
                    "items": [
                        {
                            "title": "测试采购公告",
                            "url": "/notice/1",
                            "date": "2024-03-01",
                        }
                    ]
                }
            }
        ),
        "test.example.com/feed": """<?xml version="1.0"?>
            <rss version="2.0">
                <channel>
                    <item>
                        <title>Test Article</title>
                        <link>https://test.example.com/article/1</link>
                        <pubDate>Mon, 01 Mar 2024 10:00:00 +0000</pubDate>
                    </item>
                </channel>
            </rss>
        """,
    }


def test_end_to_end_ingestion(test_config: Path, mock_responses: Dict[str, str], tmp_path: Path):
    """Test end-to-end ingestion from configuration to database."""
    db_path = tmp_path / "test.db"
    db = IVDDatabase(db_path=str(db_path))

    config = load_sources_configuration(test_config)
    assert len(config.sources) == 3

    enabled_sources = config.get_enabled_sources()
    assert len(enabled_sources) == 2

    http_client = MockHttpClient(mock_responses)
    collectors = build_collectors_from_config(config, http_client)

    assert len(collectors) == 2

    total_records = 0
    for collector in collectors:
        run_id = db.start_ingestion_run(source=collector.source_id)

        for record in collector.collect():
            result = db.insert_record(
                source=record.source,
                source_type=record.source_type,
                category=record.category,
                title=record.title,
                url=record.url,
                summary=record.summary,
                publish_date=record.publish_date,
                region=record.region,
                metadata=record.metadata,
                ingestion_run_id=run_id,
            )
            total_records += 1
            assert result.status in ["inserted", "duplicate"]

        db.complete_ingestion_run(run_id, status="completed")

    assert total_records == 2

    metrics = db.get_ingestion_metrics()
    assert metrics["total_runs"] == 2
    assert metrics["records_processed"] == 2
    assert metrics["new_records"] == 2

    procurement_records = db.get_records_by_category("Procurement")
    assert len(procurement_records) == 1
    assert procurement_records[0]["source"] == "test_procurement"
    assert procurement_records[0]["region"] == "CN"

    with db._connect() as conn:
        media_records = conn.execute(
            "SELECT * FROM records WHERE source_type = ?",
            ("industry_media",),
        ).fetchall()
    assert len(media_records) == 1


def test_deduplication_across_runs(test_config: Path, mock_responses: Dict[str, str], tmp_path: Path):
    """Test that duplicate records are detected across multiple runs."""
    db_path = tmp_path / "test_dup.db"
    db = IVDDatabase(db_path=str(db_path))

    config = load_sources_configuration(test_config)
    http_client = MockHttpClient(mock_responses)
    collectors = build_collectors_from_config(config, http_client)

    for _ in range(2):
        for collector in collectors:
            run_id = db.start_ingestion_run(source=collector.source_id)
            for record in collector.collect():
                db.insert_record(
                    source=record.source,
                    source_type=record.source_type,
                    category=record.category,
                    title=record.title,
                    url=record.url,
                    summary=record.summary,
                    publish_date=record.publish_date,
                    region=record.region,
                    ingestion_run_id=run_id,
                )
            db.complete_ingestion_run(run_id)

    with db._connect() as conn:
        total_records = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    assert total_records == 2

    metrics = db.get_ingestion_metrics()
    assert metrics["total_runs"] == 4
    assert metrics["new_records"] == 2
    assert metrics["duplicate_records"] == 2
