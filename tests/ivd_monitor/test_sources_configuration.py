"""Tests for source configuration and collector building."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from src.ivd_monitor.sources.base import HttpResponse
from src.ivd_monitor.sources.config import SourcesConfiguration, build_collectors_from_config, load_sources_configuration


class MockHttpClient:
    """Mock HTTP client for configuration tests."""

    def __init__(self) -> None:
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
        return HttpResponse(status_code=200, text="{}", url=url, headers={})


def test_sources_configuration_from_dict():
    """Test creating configuration from dictionary data."""
    data = {
        "sources": [
            {
                "source_id": "example",
                "collector_type": "procurement",
                "enabled": True,
                "extra_params": {
                    "list_url_template": "https://example.com/api?page={page}",
                },
            },
            {
                "source_id": "disabled",
                "collector_type": "procurement",
                "enabled": False,
            },
        ]
    }

    config = SourcesConfiguration.from_dict(data)
    enabled_sources = config.get_enabled_sources()

    assert len(enabled_sources) == 1
    assert enabled_sources[0].source_id == "example"


def test_load_sources_configuration(tmp_path: Path):
    """Test loading sources configuration from JSON file."""
    config_path = tmp_path / "sources.json"
    data = {
        "sources": [
            {
                "source_id": "example",
                "collector_type": "procurement",
                "enabled": True,
                "extra_params": {
                    "list_url_template": "https://example.com/api",
                },
            }
        ]
    }
    config_path.write_text(json.dumps(data), encoding="utf-8")

    config = load_sources_configuration(config_path)

    assert len(config.sources) == 1
    assert config.sources[0].source_id == "example"


def test_build_collectors_from_config(tmp_path: Path):
    """Test building collectors from configuration."""
    config_path = tmp_path / "sources.json"
    data = {
        "sources": [
            {
                "source_id": "procurement_test",
                "collector_type": "procurement",
                "enabled": True,
                "extra_params": {
                    "mode": "json",
                    "list_url_template": "https://example.com/api?page={page}",
                    "pagination": {"start": 1, "pages": 1},
                },
            },
            {
                "source_id": "media_test",
                "collector_type": "rss_feed",
                "enabled": False,
                "extra_params": {
                    "feed_url": "https://example.com/feed",
                },
            }
        ]
    }
    config_path.write_text(json.dumps(data), encoding="utf-8")

    config = load_sources_configuration(config_path)
    http_client = MockHttpClient()

    collectors = build_collectors_from_config(config, http_client)

    assert len(collectors) == 1
    assert collectors[0].source_id == "procurement_test"
    assert collectors[0].enabled is True
