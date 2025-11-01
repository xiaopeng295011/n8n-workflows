"""HTTP client implementation using httpx."""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from .base import HttpResponse


class HttpxClient:
    """HTTP client implementation using httpx."""

    def __init__(self, timeout: float = 30.0, follow_redirects: bool = True) -> None:
        self.timeout = timeout
        self.follow_redirects = follow_redirects

    def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> HttpResponse:
        """Perform a GET request."""
        if httpx is None:
            raise RuntimeError("httpx is required but not installed. Install with: pip install httpx")

        with httpx.Client(timeout=timeout or self.timeout, follow_redirects=self.follow_redirects) as client:
            response = client.get(url, params=params, headers=headers)

            return HttpResponse(
                status_code=response.status_code,
                text=response.text,
                url=str(response.url),
                headers=dict(response.headers),
            )
