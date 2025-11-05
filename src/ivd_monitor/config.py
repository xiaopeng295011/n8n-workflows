"""Configuration loader for IVD monitor collectors."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


class SourceConfig:
    """Configuration for a single collector source."""

    def __init__(self, source_id: str, data: Dict[str, Any]) -> None:
        self.source_id = source_id
        self.enabled = data.get("enabled", True)
        self.source_name = data.get("source_name", "")
        self.source_type = data.get("source_type", "")
        self.default_category = data.get("default_category", "")
        self.language_encoding = data.get("language_encoding", "utf-8")
        self.region = data.get("region", "CN")
        self.pagination_strategy = data.get("pagination_strategy", "api_page")
        self.page_size = data.get("page_size", 20)
        self.max_pages = data.get("max_pages", 5)
        self.date_window_days = data.get("date_window_days", 30)
        self.rate_limit_delay_ms = data.get("rate_limit_delay_ms", 200)
        self.description = data.get("description", "")
        self.fallback_strategy = data.get("fallback_strategy", "")
        self.required_params = data.get("required_params", [])


class IVDConfig:
    """Central configuration container for IVD monitor collectors."""

    DEFAULT_CONFIG_PATH = Path("config/ivd_sources.yaml")

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        if not path.is_absolute():
            path = Path.cwd() / path
        self.config_path = path
        self._data = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {"sources": {}, "settings": {}, "categories": {}}
        with open(self.config_path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def get_source(self, source_id: str) -> Optional[SourceConfig]:
        sources_dict = self._data.get("sources", {})
        if source_id not in sources_dict:
            return None
        return SourceConfig(source_id, sources_dict[source_id])

    def get_enabled_sources(self) -> List[SourceConfig]:
        sources_dict = self._data.get("sources", {})
        enabled = [
            SourceConfig(sid, source_data)
            for sid, source_data in sources_dict.items()
            if source_data.get("enabled", True)
        ]
        return enabled

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._data.get("settings", {}).get(key, default)

    def get_category_info(self, category: str) -> Dict[str, str]:
        return self._data.get("categories", {}).get(category, {})
