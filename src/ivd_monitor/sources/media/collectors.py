"""Industry media collectors using RSS or HTML feeds."""

from __future__ import annotations

import json
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


@register_collector("industry_media")
class IndustryMediaCollector(BaseCollector):
    """Collect articles from industry media sources.

    Supports both RSS feeds (default) and HTML scraping when RSS is unavailable.
    """

    def __init__(
        self,
        source_id: str,
        http_client: HttpClient,
        *,
        region: Optional[str] = None,
        enabled: bool = True,
        rate_limit_delay: float = 1.0,
        feed_url: Optional[str] = None,
        list_url: Optional[str] = None,
        mode: str = "rss",
        category: str = "Industry Media",
        timezone: str = "Asia/Shanghai",
        date_format: Optional[str] = None,
        item_selector: str = "article",
        title_selector: str = "h2, h3",
        url_selector: str = "a",
        summary_selector: str = "p",
        date_selector: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(source_id, http_client, region=region, enabled=enabled, rate_limit_delay=rate_limit_delay)

        self.feed_url = feed_url
        self.list_url = list_url or feed_url
        self.mode = mode
        self.category = category
        self.timezone = timezone
        self.date_format = date_format
        self.item_selector = item_selector
        self.title_selector = title_selector
        self.url_selector = url_selector
        self.summary_selector = summary_selector
        self.date_selector = date_selector
        self.base_url = base_url

    def collect(self) -> Iterable[CollectedRecord]:
        if not self.enabled:
            return []

        if self.mode == "rss":
            return self._collect_from_rss()

        return self._collect_from_html()

    def _collect_from_rss(self) -> List[CollectedRecord]:
        if not self.feed_url:
            return []

        response = self._safe_get(self.feed_url)
        if not response:
            return []

        if BeautifulSoup is None:
            raise RuntimeError("BeautifulSoup is required but not installed. Install with: pip install beautifulsoup4")

        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")
        if not items:
            items = soup.find_all("entry")

        records: List[CollectedRecord] = []

        for item in items:
            title_tag = item.find("title")
            link_tag = item.find("link")
            description_tag = item.find("description") or item.find("summary")
            pub_date_tag = item.find("pubDate") or item.find("updated") or item.find("published")

            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            url = link_tag.get("href") if link_tag and link_tag.has_attr("href") else (link_tag.get_text(strip=True) if link_tag else None)

            if not url:
                continue

            url = self._normalize_url(url)

            summary = description_tag.get_text(strip=True) if description_tag else None
            publish_date = self._normalize_publish_date(pub_date_tag.get_text(strip=True) if pub_date_tag else None)

            records.append(
                CollectedRecord(
                    source=self.source_id,
                    source_type="industry_media",
                    category=self.category,
                    title=title,
                    url=url,
                    summary=summary,
                    publish_date=publish_date,
                    region=self.region,
                )
            )

        return self._deduplicate(records)

    def _collect_from_html(self) -> List[CollectedRecord]:
        if not self.list_url:
            return []

        response = self._safe_get(self.list_url)
        if not response:
            return []

        if BeautifulSoup is None:
            raise RuntimeError("BeautifulSoup is required but not installed. Install with: pip install beautifulsoup4")

        soup = self._parse_html(response.text)
        items = soup.select(self.item_selector)

        records: List[CollectedRecord] = []

        for item in items:
            title_tag = item.select_one(self.title_selector)
            link_tag = item.select_one(self.url_selector)
            summary_tag = item.select_one(self.summary_selector)
            date_tag = item.select_one(self.date_selector) if self.date_selector else None

            if not title_tag or not link_tag:
                continue

            title = title_tag.get_text(strip=True)
            url = link_tag.get("href")
            if not url:
                continue

            url = self._normalize_url(url)
            summary = summary_tag.get_text(strip=True) if summary_tag else None
            publish_date = self._normalize_publish_date(date_tag.get_text(strip=True) if date_tag else None)

            records.append(
                CollectedRecord(
                    source=self.source_id,
                    source_type="industry_media",
                    category=self.category,
                    title=title,
                    url=url,
                    summary=summary,
                    publish_date=publish_date,
                    region=self.region,
                )
            )

        return self._deduplicate(records)

    def _normalize_publish_date(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        try:
            if self.date_format:
                dt = datetime.strptime(value, self.date_format)
            else:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))

            try:
                local_tz = ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                local_tz = ZoneInfo("UTC")
            dt = dt.replace(tzinfo=local_tz) if dt.tzinfo is None else dt.astimezone(local_tz)
            return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return value

    def _normalize_url(self, url: str) -> str:
        if url.startswith("http"):
            return url
        if not self.base_url:
            return url
        return urljoin(self.base_url, url)

    def _deduplicate(self, records: List[CollectedRecord]) -> List[CollectedRecord]:
        seen: Dict[str, CollectedRecord] = {}
        for record in records:
            if record.url not in seen:
                seen[record.url] = record
        return list(seen.values())
