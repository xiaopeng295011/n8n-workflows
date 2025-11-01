"""Tests for the HTTP client utilities."""

import asyncio
from datetime import datetime

import httpx
import pytest

from src.ivd_monitor.http_client import HTTPClient
from src.ivd_monitor.models import CollectorConfig, CollectorStats


@pytest.mark.asyncio
async def test_http_client_retries_on_server_error(monkeypatch):
    """HTTP client should retry on retryable server errors."""

    attempts = []

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self._attempt = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            self._attempt += 1
            attempts.append(self._attempt)
            request = httpx.Request(method, url)
            if self._attempt < 3:
                response = httpx.Response(500, request=request)
                raise httpx.HTTPStatusError("Server error", request=request, response=response)
            return httpx.Response(200, request=request, text="ok")

    async def noop_sleep(_):
        return None

    monkeypatch.setattr("src.ivd_monitor.http_client.httpx.AsyncClient", DummyAsyncClient)
    monkeypatch.setattr("src.ivd_monitor.http_client.asyncio.sleep", noop_sleep)

    config = CollectorConfig(name="test", max_retries=2, retry_base_delay=0.01)
    client = HTTPClient(config)
    stats = CollectorStats(collector_name="test", started_at=datetime.utcnow())

    response = await client.get_async("https://example.com", stats=stats)

    assert response.status_code == 200
    assert response.text == "ok"
    assert attempts == [1, 2, 3]
    assert stats.http_requests == 3
    assert stats.retry_attempts == 2
