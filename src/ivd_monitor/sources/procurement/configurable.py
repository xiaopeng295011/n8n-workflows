"""Configurable procurement collectors for Chinese government procurement portals."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - fallback for limited environments
    BeautifulSoup = None  # type: ignore[assignment]

from ..base import BaseCollector, CollectedRecord, HttpClient
from ..config import register_collector


@dataclass
class FieldSpec:
    """Represents a field extraction specification."""

    selector: Optional[str] = None
    attr: Optional[str] = None
    path: Optional[str] = None
    regex: Optional[str] = None
    regex_group: Optional[int] = None
    date_format: Optional[str] = None
    optional: bool = False
    default: Optional[str] = None


@register_collector("procurement")
class ConfigurableProcurementCollector(BaseCollector):
    """Configurable collector for procurement portals."""

    def __init__(
        self,
        source_id: str,
        http_client: HttpClient,
        *,
        region: Optional[str] = None,
        enabled: bool = True,
        rate_limit_delay: float = 1.0,
        base_url: Optional[str] = None,
        list_url_template: str,
        mode: str = "html",
        pagination: Optional[Dict[str, Any]] = None,
        fields: Optional[Dict[str, Dict[str, Any]]] = None,
        json_list_path: Optional[List[str]] = None,
        default_date_format: Optional[str] = None,
        timezone: str = "Asia/Shanghai",
        constant_metadata: Optional[Dict[str, Any]] = None,
        category: str = "Procurement",
    ) -> None:
        super().__init__(source_id, http_client, region=region, enabled=enabled, rate_limit_delay=rate_limit_delay)

        self.base_url = base_url
        self.list_url_template = list_url_template
        self.mode = mode
        self.pagination = pagination or {}
        self.field_specs = self._build_field_specs(fields or {})
        self.json_list_path = json_list_path
        self.default_date_format = default_date_format
        self.timezone = timezone
        self.constant_metadata = constant_metadata or {}
        self.category = category

    def collect(self) -> Iterable[CollectedRecord]:
        """Collect procurement records from the configured portal."""
        if not self.enabled:
            return []

        records: List[CollectedRecord] = []

        page_start = int(self.pagination.get("start", 1))
        page_count = int(self.pagination.get("pages", 1))

        for page in range(page_start, page_start + page_count):
            page_url = self._resolve_page_url(page)
            response = self._safe_get(page_url)
            if not response:
                break

            try:
                if self.mode == "json":
                    items = self._extract_json_items(response)
                elif self.mode == "html":
                    items = self._extract_html_items(response)
                else:
                    raise ValueError(f"Unsupported mode: {self.mode}")
            except Exception:
                break

            if not items:
                break

            for item in items:
                record = self._build_record(item)
                if record:
                    records.append(record)

            self._sleep()

        return self._deduplicate(records)

    def _resolve_page_url(self, page: int) -> str:
        """Construct page URL based on pagination settings."""
        if "{page}" in self.list_url_template:
            return self.list_url_template.format(page=page)

        if self.pagination.get("type") == "query":
            separator = "&" if "?" in self.list_url_template else "?"
            param = self.pagination.get("param", "page")
            return f"{self.list_url_template}{separator}{param}={page}"

        return self.list_url_template

    def _extract_json_items(self, response) -> List[Dict[str, Any]]:
        """Extract items from JSON response."""
        data = json.loads(response.text)

        if not self.json_list_path:
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
            return []

        for key in self.json_list_path:
            if isinstance(data, dict):
                data = data.get(key)
            else:
                data = None

            if data is None:
                return []

        if isinstance(data, list):
            return data

        return []

    def _extract_html_items(self, response) -> List[Any]:
        """Extract items from HTML response."""
        if BeautifulSoup is None or not callable(BeautifulSoup):
            raise RuntimeError("BeautifulSoup is required but not installed. Install with: pip install beautifulsoup4")
        soup = BeautifulSoup(response.text, "html.parser")
        item_selector = self.field_specs.get("item_selector")
        selector = item_selector.selector if item_selector else "li"
        return soup.select(selector)

    def _build_record(self, item: Any) -> Optional[CollectedRecord]:
        """Build a collected record from raw item data."""
        title = self._extract_field(item, "title")
        url = self._extract_field(item, "url")

        if not title or not url:
            return None

        url = self._normalize_url(url)
        publish_date = self._extract_field(item, "publish_date")
        publish_date_iso = self._normalize_publish_date("publish_date", publish_date)

        summary = self._extract_field(item, "summary")
        status = self._extract_field(item, "status")
        budget = self._extract_field(item, "budget")
        region = self._extract_field(item, "region") or self.region

        metadata = {**self.constant_metadata}
        if status:
            metadata["bid_status"] = status
        if budget:
            metadata["budget"] = budget

        return CollectedRecord(
            source=self.source_id,
            source_type="procurement",
            category=self.category,
            title=title,
            url=url,
            summary=summary,
            publish_date=publish_date_iso,
            region=region,
            metadata=metadata if metadata else None,
        )

    def _normalize_url(self, url: str) -> str:
        """Convert relative URLs to absolute URLs using base_url."""
        if url.startswith("http"):
            return url
        if not self.base_url:
            return url
        return urljoin(self.base_url, url)

    def _normalize_publish_date(self, field_name: str, value: Optional[str]) -> Optional[str]:
        """Normalize publish date to ISO format."""
        if not value:
            return None

        spec = self.field_specs.get(field_name)
        date_format = (spec.date_format if spec else None) or self.default_date_format

        if not date_format:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                return value

        try:
            dt = datetime.strptime(value, date_format)
            try:
                local_tz = ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                local_tz = ZoneInfo("UTC")
            dt = dt.replace(tzinfo=local_tz)
            return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return value

    def _extract_field(self, item: Any, field_name: str) -> Optional[str]:
        """Extract field value using configured specifications."""
        spec = self.field_specs.get(field_name)
        if not spec:
            return None

        value = None

        if isinstance(item, dict):
            value = self._extract_from_json(item, spec)
        else:
            value = self._extract_from_html(item, spec)

        if value is None:
            return spec.default if spec.optional else None

        if spec.regex:
            match = re.search(spec.regex, value)
            if not match:
                return spec.default if spec.optional else None
            if spec.regex_group is not None:
                try:
                    value = match.group(spec.regex_group)
                except IndexError:
                    return spec.default if spec.optional else None
            else:
                value = match.group(1) if match.groups() else match.group(0)

        return value.strip() if isinstance(value, str) else value

    def _extract_from_json(self, data: Dict[str, Any], spec: FieldSpec) -> Optional[str]:
        """Extract value from JSON data using dot-separated path."""
        if not spec.path:
            return None

        value: Any = data
        for key in spec.path.split('.'):
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None

            if value is None:
                return None

        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)

        return str(value)

    def _extract_from_html(self, element: Any, spec: FieldSpec) -> Optional[str]:
        """Extract value from HTML element using CSS selector."""
        target = element
        if spec.selector:
            target = element.select_one(spec.selector)

        if target is None:
            return None

        if spec.attr:
            value = target.get(spec.attr)
        else:
            value = target.get_text(strip=True)

        if value is None:
            return None

        return str(value)

    def _build_field_specs(self, raw_specs: Dict[str, Dict[str, Any]]) -> Dict[str, FieldSpec]:
        """Convert raw field specification dictionary into FieldSpec objects."""
        specs: Dict[str, FieldSpec] = {}
        for name, options in raw_specs.items():
            specs[name] = FieldSpec(
                selector=options.get("selector"),
                attr=options.get("attr"),
                path=options.get("path"),
                regex=options.get("regex"),
                regex_group=options.get("regex_group"),
                date_format=options.get("date_format"),
                optional=options.get("optional", False),
                default=options.get("default"),
            )

        if "item_selector" not in specs and "item_selector" in raw_specs:
            specs["item_selector"] = FieldSpec(selector=raw_specs["item_selector"].get("selector", "li"))

        return specs

    def _deduplicate(self, records: List[CollectedRecord]) -> List[CollectedRecord]:
        """Deduplicate records by URL."""
        seen = {}
        for record in records:
            if record.url not in seen:
                seen[record.url] = record
        return list(seen.values())
