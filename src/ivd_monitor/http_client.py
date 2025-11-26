"""HTTP client with retry and timeout support for collectors."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import httpx

from .logging_config import get_logger
from .models import CollectorConfig, CollectorStats

logger = get_logger("http_client")


class HTTPClient:
    """HTTP client wrapper with retry logic, timeout, and exponential backoff."""

    def __init__(self, config: Optional[CollectorConfig] = None) -> None:
        self.config = config or CollectorConfig(name="default")
        self.timeout = httpx.Timeout(
            connect=10.0,
            read=self.config.timeout_seconds,
            write=10.0,
            pool=5.0,
        )
        self.headers = {
            "User-Agent": "IVD-Monitor/1.0 (+https://github.com/yourusername/ivd-monitor)",
            **self.config.headers,
        }

    async def get_async(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        follow_redirects: bool = True,
        stats: Optional[CollectorStats] = None,
    ) -> httpx.Response:
        return await self.request_async(
            "GET",
            url,
            headers=headers,
            params=params,
            follow_redirects=follow_redirects,
            stats=stats,
        )

    def get_sync(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        follow_redirects: bool = True,
        stats: Optional[CollectorStats] = None,
    ) -> httpx.Response:
        return self.request_sync(
            "GET",
            url,
            headers=headers,
            params=params,
            follow_redirects=follow_redirects,
            stats=stats,
        )

    async def request_async(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        follow_redirects: bool = True,
        stats: Optional[CollectorStats] = None,
    ) -> httpx.Response:
        merged_headers = {**self.headers, **(headers or {})}

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=follow_redirects,
        ) as client:
            for attempt in range(self.config.max_retries + 1):
                if stats:
                    stats.http_requests += 1
                try:
                    response = await client.request(
                        method,
                        url,
                        headers=merged_headers,
                        params=params,
                        data=data,
                        json=json,
                    )
                    response.raise_for_status()
                    return response

                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    if self._should_retry_status(status_code) and attempt < self.config.max_retries:
                        delay = self._calculate_retry_delay(attempt + 1)
                        if stats:
                            stats.retry_attempts += 1
                        logger.warning(
                            "Request %s %s failed with status %s. Retrying in %.2fs (attempt %s/%s)",
                            method,
                            url,
                            status_code,
                            delay,
                            attempt + 1,
                            self.config.max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                    logger.error(
                        "Request %s %s failed with status %s: %s",
                        method,
                        url,
                        status_code,
                        exc,
                    )
                    raise

                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt < self.config.max_retries:
                        delay = self._calculate_retry_delay(attempt + 1)
                        if stats:
                            stats.retry_attempts += 1
                        logger.warning(
                            "Request %s %s failed (%s). Retrying in %.2fs (attempt %s/%s)",
                            method,
                            url,
                            exc,
                            delay,
                            attempt + 1,
                            self.config.max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                    logger.error(
                        "Request %s %s failed after %s attempts: %s",
                        method,
                        url,
                        attempt + 1,
                        exc,
                    )
                    raise

        raise RuntimeError(f"Request {method} {url} failed after retries")

    def request_sync(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        follow_redirects: bool = True,
        stats: Optional[CollectorStats] = None,
    ) -> httpx.Response:
        merged_headers = {**self.headers, **(headers or {})}

        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=follow_redirects,
        ) as client:
            for attempt in range(self.config.max_retries + 1):
                if stats:
                    stats.http_requests += 1
                try:
                    response = client.request(
                        method,
                        url,
                        headers=merged_headers,
                        params=params,
                        data=data,
                        json=json,
                    )
                    response.raise_for_status()
                    return response

                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    if self._should_retry_status(status_code) and attempt < self.config.max_retries:
                        delay = self._calculate_retry_delay(attempt + 1)
                        if stats:
                            stats.retry_attempts += 1
                        logger.warning(
                            "Request %s %s failed with status %s. Retrying in %.2fs (attempt %s/%s)",
                            method,
                            url,
                            status_code,
                            delay,
                            attempt + 1,
                            self.config.max_retries,
                        )
                        time.sleep(delay)
                        continue

                    logger.error(
                        "Request %s %s failed with status %s: %s",
                        method,
                        url,
                        status_code,
                        exc,
                    )
                    raise

                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    if attempt < self.config.max_retries:
                        delay = self._calculate_retry_delay(attempt + 1)
                        if stats:
                            stats.retry_attempts += 1
                        logger.warning(
                            "Request %s %s failed (%s). Retrying in %.2fs (attempt %s/%s)",
                            method,
                            url,
                            exc,
                            delay,
                            attempt + 1,
                            self.config.max_retries,
                        )
                        time.sleep(delay)
                        continue

                    logger.error(
                        "Request %s %s failed after %s attempts: %s",
                        method,
                        url,
                        attempt + 1,
                        exc,
                    )
                    raise

        raise RuntimeError(f"Request {method} {url} failed after retries")

    def _should_retry_status(self, status_code: int) -> bool:
        if status_code >= 500:
            return True
        return status_code in {408, 409, 425, 429}

    def _calculate_retry_delay(self, retry_number: int) -> float:
        delay = self.config.retry_base_delay * (
            self.config.retry_exponential_base ** (retry_number - 1)
        )
        return min(delay, self.config.retry_max_delay)
