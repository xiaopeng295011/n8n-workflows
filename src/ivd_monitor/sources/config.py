"""Configuration for source collectors."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .base import BaseCollector, HttpClient

COLLECTOR_REGISTRY: Dict[str, Type[BaseCollector]] = {}


def register_collector(collector_type: str) -> Any:
    """Decorator to register a collector class."""

    def decorator(cls: Type[BaseCollector]) -> Type[BaseCollector]:
        COLLECTOR_REGISTRY[collector_type] = cls
        return cls

    return decorator


@dataclass
class SourceConfig:
    """Configuration for a single source."""

    source_id: str
    collector_type: str
    enabled: bool = True
    region: Optional[str] = None
    source_type: Optional[str] = None
    category: Optional[str] = None
    rate_limit_delay: float = 1.0
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SourcesConfiguration:
    """Configuration for all sources."""

    sources: List[SourceConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SourcesConfiguration:
        """Load configuration from dictionary."""
        sources = []
        for source_data in data.get("sources", []):
            sources.append(
                SourceConfig(
                    source_id=source_data["source_id"],
                    collector_type=source_data["collector_type"],
                    enabled=source_data.get("enabled", True),
                    region=source_data.get("region"),
                    source_type=source_data.get("source_type"),
                    category=source_data.get("category"),
                    rate_limit_delay=source_data.get("rate_limit_delay", 1.0),
                    extra_params=source_data.get("extra_params", {}),
                )
            )
        return cls(sources=sources)

    @classmethod
    def from_json_file(cls, path: Path) -> SourcesConfiguration:
        """Load configuration from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "sources": [
                {
                    "source_id": source.source_id,
                    "collector_type": source.collector_type,
                    "enabled": source.enabled,
                    "region": source.region,
                    "source_type": source.source_type,
                    "category": source.category,
                    "rate_limit_delay": source.rate_limit_delay,
                    "extra_params": source.extra_params,
                }
                for source in self.sources
            ]
        }

    def get_enabled_sources(self) -> List[SourceConfig]:
        """Get list of enabled sources."""
        return [source for source in self.sources if source.enabled]


def load_sources_configuration(path: Optional[Path] = None) -> SourcesConfiguration:
    """Load sources configuration from file or return default."""
    if path is None:
        path = Path("config/ivd_sources.json")

    if not path.exists():
        return SourcesConfiguration()

    return SourcesConfiguration.from_json_file(path)


def build_collectors_from_config(
    config: SourcesConfiguration,
    http_client: HttpClient,
) -> List[BaseCollector]:
    """Build collector instances from configuration."""
    collectors = []

    for source_config in config.get_enabled_sources():
        collector_cls = COLLECTOR_REGISTRY.get(source_config.collector_type)
        if collector_cls is None:
            continue

        collector = collector_cls(
            source_id=source_config.source_id,
            http_client=http_client,
            region=source_config.region,
            enabled=source_config.enabled,
            rate_limit_delay=source_config.rate_limit_delay,
            **source_config.extra_params,
        )
        collectors.append(collector)

    return collectors
