"""Collector base classes and helper utilities for the IVD monitor."""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from types import SimpleNamespace
from typing import List, Optional, Sequence

try:  # pragma: no cover - optional dependency for runtime fetch
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    class _UnavailableSession:  # type: ignore
        def __init__(self, *args, **kwargs) -> None:
            self._reason = "requests library is required for network operations"

        def get(self, *args, **kwargs):  # pragma: no cover
            raise RuntimeError(self._reason)

        def post(self, *args, **kwargs):  # pragma: no cover
            raise RuntimeError(self._reason)

    requests = SimpleNamespace(Session=_UnavailableSession)  # type: ignore

try:  # pragma: no cover - optional dependency for HTML parsing
    from bs4 import BeautifulSoup  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

from zoneinfo import ZoneInfo

from src.ivd_monitor.models import RawRecord


CN_TZ = ZoneInfo("Asia/Shanghai")

_TAG_RE = re.compile(r"<[^>]+>")
_LIST_ITEM_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.I | re.S)
_LINK_RE = re.compile(r'<a[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>', re.I | re.S)
_DATE_RE = re.compile(r"<(?:span|em)[^>]*>(?P<date>.*?)</(?:span|em)>", re.I | re.S)


def _strip_html(text: str) -> str:
    cleaned = _TAG_RE.sub("", text)
    return " ".join(cleaned.split())


def extract_list_entries(html: str) -> List[dict[str, Optional[str]]]:
    """Extract link/title/date triples from simple HTML list markup."""

    entries: List[dict[str, Optional[str]]] = []
    for match in _LIST_ITEM_RE.finditer(html):
        block = match.group(1)
        link = _LINK_RE.search(block)
        if not link:
            continue
        href = unescape(link.group("href").strip())
        title = _strip_html(link.group("title"))
        date_match = _DATE_RE.search(block)
        date_text = _strip_html(date_match.group("date")) if date_match else None
        entries.append({"title": title, "href": href, "date": date_text})
    return entries


class CollectorError(RuntimeError):
    """Raised when a collector encounters a recoverable error."""


@dataclass
class PageResult:
    """Represents the records parsed from a single page fetch."""

    records: List[RawRecord]
    has_more: bool


class BaseCollector(abc.ABC):
    """Base class for all IVD monitor collectors."""

    source_id: str
    source_name: str
    source_type: str
    default_category: str
    region: str = "CN"
    encoding: str = "utf-8"
    page_size: int = 30
    max_pages: int = 5
    date_window: int = 30  # days

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()

    def fetch_latest(self, pages: Optional[int] = None) -> List[RawRecord]:
        """Fetch records for the most recent period across `pages` pages.

        Args:
            pages: Number of pages to fetch. Defaults to ``self.max_pages``.

        Returns:
            List of :class:`RawRecord` instances ordered newest first.
        """

        total_pages = pages or self.max_pages
        aggregated: List[RawRecord] = []
        for page in range(1, total_pages + 1):
            result = self._fetch_page(page)
            aggregated.extend(result.records)
            if not result.has_more:
                break
            if len(result.records) < self.page_size:
                break
        return aggregated

    @abc.abstractmethod
    def _fetch_page(self, page: int) -> PageResult:
        """Fetch and parse a single page of data."""

    def _normalize_publish_date(self, value: object, *, tz: ZoneInfo = CN_TZ) -> Optional[datetime]:
        """Normalise publish dates to UTC, supporting multiple input types."""

        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=tz)
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)):
            # treat as unix timestamp in seconds
            dt = datetime.fromtimestamp(float(value), tz=tz)
            return dt.astimezone(timezone.utc)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            parsed = self._parse_datetime_string(text)
            if parsed is None:
                raise CollectorError(f"Unsupported datetime format: {value}")
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=tz)
            return parsed.astimezone(timezone.utc)
        raise CollectorError(f"Unsupported datetime type: {type(value)!r}")

    def _parse_datetime_string(self, text: str) -> Optional[datetime]:
        """Parse a datetime string used by upstream sources."""

        candidates = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
        ]
        for fmt in candidates:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        # Chinese date formats like 2023年10月31日
        if "年" in text and "月" in text and "日" in text:
            try:
                cleaned = (
                    text.replace("年", "-")
                    .replace("月", "-")
                    .replace("日", "")
                    .replace("号", "")
                )
                return self._parse_datetime_string(cleaned)
            except CollectorError:
                pass
        if text.endswith("Z"):
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                pass
        # ISO 8601 with timezone offset
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _date_range_param(self, *, days: Optional[int] = None) -> str:
        """Return a date range string compatible with Chinese disclosure APIs."""

        days = days or self.date_window
        end = datetime.now(tz=CN_TZ).date()
        start = end - timedelta(days=days)
        return f"{start.isoformat()}~{end.isoformat()}"

    def _prepare_companies(self, values: Sequence[str | None]) -> List[str]:
        """Clean company names while preserving order."""

        seen: set[str] = set()
        result: List[str] = []
        for item in values:
            if not item:
                continue
            name = item.strip()
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
        return result
