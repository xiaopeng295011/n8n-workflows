"""Base classes and utilities for data collection."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - fallback for limited environments
    httpx = None  # type: ignore[assignment]

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - fallback for limited environments
    BeautifulSoup = None  # type: ignore[assignment]


class _InlineHttpClient:
    """Inline HTTP client using httpx."""

    def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        if httpx is None:
            raise RuntimeError("httpx is required but not installed. Install with: pip install httpx")
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, params=params, headers=headers)
            return HttpResponse(
                status_code=response.status_code,
                text=response.text,
                url=str(response.url),
                headers=dict(response.headers),
            )


@dataclass
class HttpResponse:
    """Lightweight HTTP response wrapper."""

    status_code: int
    text: str
    url: str
    headers: Dict[str, str]

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        import json

        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code} for {self.url}")


class HttpClient(Protocol):
    """Protocol for HTTP client interface."""

    def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        """Perform a GET request."""
        ...


@dataclass
class CollectedRecord:
    """A single collected record ready for ingestion."""

    source: str
    url: str
    title: Optional[str] = None
    summary: Optional[str] = None
    content_html: Optional[str] = None
    publish_date: Optional[str] = None
    category: Optional[str] = None
    source_type: Optional[str] = None
    region: Optional[str] = None
    companies: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseCollector(ABC):
    """Base class for all source collectors."""

    def __init__(
        self,
        source_id: str,
        http_client: Optional[HttpClient] = None,
        *,
        region: Optional[str] = None,
        enabled: bool = True,
        rate_limit_delay: float = 1.0,
    ) -> None:
        self.source_id = source_id
        self.http_client = http_client or _InlineHttpClient()
        self.region = region
        self.enabled = enabled
        self.rate_limit_delay = rate_limit_delay

    @abstractmethod
    def collect(self) -> Iterable[CollectedRecord]:
        """Collect records from the source."""
        pass

    def _sleep(self, seconds: Optional[float] = None) -> None:
        """Sleep for rate limiting."""
        time.sleep(seconds if seconds is not None else self.rate_limit_delay)

    def _parse_html(self, html: str):
        """Parse HTML with BeautifulSoup."""
        if BeautifulSoup is None:
            raise RuntimeError("BeautifulSoup is required but not installed. Install with: pip install beautifulsoup4")
        return BeautifulSoup(html, "html.parser")

    def _extract_text(self, element: Any, selector: Optional[str] = None) -> Optional[str]:
        """Extract and clean text from a BeautifulSoup element."""
        if selector:
            target = element.select_one(selector)
        else:
            target = element

        if target is None:
            return None

        text = target.get_text(strip=True)
        return text if text else None

    def _absolute_url(self, base_url: str, relative_url: str) -> str:
        """Convert relative URL to absolute."""
        return urljoin(base_url, relative_url)

    def _format_date(self, date_str: Optional[str], format_str: str = "%Y-%m-%d") -> Optional[str]:
        """Parse and format date string to ISO format."""
        if not date_str:
            return None

        try:
            dt = datetime.strptime(date_str.strip(), format_str)
            return dt.isoformat() + "Z"
        except (ValueError, AttributeError):
            return None

    def _safe_get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> Optional[HttpResponse]:
        """Perform HTTP GET with retry logic and error handling."""
        last_error = None
        for attempt in range(max_retries):
            try:
                response = self.http_client.get(url, params=params, headers=headers, timeout=timeout)
                if response.ok:
                    return response
                last_error = RuntimeError(f"HTTP {response.status_code}")
            except Exception as e:
                last_error = e

            if attempt < max_retries - 1:
                self._sleep(self.rate_limit_delay * (attempt + 1))

        return None
