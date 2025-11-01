"""RSS feed collector."""

from __future__ import annotations

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


@register_collector("rss_feed")
class RSSFeedCollector(BaseCollector):
    """Collect articles from RSS or Atom feeds."""

    def __init__(
        self,
        source_id: str,
        http_client: HttpClient,
        *,
        region: Optional[str] = None,
        enabled: bool = True,
        rate_limit_delay: float = 1.0,
        feed_url: str,
        category: str = "Industry Media",
        timezone: str = "Asia/Shanghai",
        base_url: Optional[str] = None,
    ) -> None:
        super().__init__(source_id, http_client, region=region, enabled=enabled, rate_limit_delay=rate_limit_delay)

        self.feed_url = feed_url
        self.category = category
        self.timezone = timezone
        self.base_url = base_url

    def collect(self) -> Iterable[CollectedRecord]:
        if not self.enabled:
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
            record = self._build_record_from_item(item)
            if record:
                records.append(record)

        return self._deduplicate(records)

    def _build_record_from_item(self, item: Any) -> Optional[CollectedRecord]:
        title_tag = item.find("title")
        link_tag = item.find("link")
        description_tag = item.find("description") or item.find("summary") or item.find("content")
        pub_date_tag = item.find("pubDate") or item.find("updated") or item.find("published")

        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

        url = None
        if link_tag:
            if link_tag.has_attr("href"):
                url = link_tag.get("href")
            else:
                url = link_tag.get_text(strip=True)

        if not url:
            return None

        url = self._normalize_url(url)

        summary = None
        content_html = None
        if description_tag:
            text = description_tag.get_text(strip=True)
            if len(text) > 500:
                summary = text[:500] + "..."
            else:
                summary = text

            if description_tag.find():
                content_html = str(description_tag)

        publish_date = None
        if pub_date_tag:
            date_text = pub_date_tag.get_text(strip=True)
            publish_date = self._normalize_publish_date(date_text)

        return CollectedRecord(
            source=self.source_id,
            source_type="industry_media",
            category=self.category,
            title=title,
            url=url,
            summary=summary,
            content_html=content_html,
            publish_date=publish_date,
            region=self.region,
        )

    def _normalize_publish_date(self, value: str) -> Optional[str]:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(value)
            try:
                return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
            except ZoneInfoNotFoundError:
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
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
