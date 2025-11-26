"""RSS/Atom feed helpers built on feedparser."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import feedparser

from .http_client import HTTPClient
from .logging_config import get_logger

logger = get_logger("rss")


async def fetch_feed(
    url: str,
    *,
    http_client: Optional[HTTPClient] = None,
    params: Optional[Dict[str, Any]] = None,
) -> feedparser.FeedParserDict:
    """Fetch and parse an RSS feed asynchronously."""
    client = http_client or HTTPClient()
    response = await client.get_async(url, params=params)
    text = response.text
    return await parse_feed_text(text)


async def parse_feed_text(text: str) -> feedparser.FeedParserDict:
    """Parse RSS feed text asynchronously."""
    return await asyncio.to_thread(feedparser.parse, text)
