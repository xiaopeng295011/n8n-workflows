"""Example RSS collector demonstrating the scraper core."""

from typing import List

from .collector import BaseCollector
from .models import CollectorConfig, CollectorStats, RawRecord
from .parser_utils import sanitize_html
from .rss import fetch_feed


class ExampleRSSCollector(BaseCollector):
    """Example collector for RSS feeds.
    
    Demonstrates how to implement a collector using the scraper core.
    This can be used as a template for creating new collectors.
    """

    def __init__(self, feed_url: str, config: CollectorConfig = None) -> None:
        """Initialize RSS collector.
        
        Args:
            feed_url: URL of the RSS feed to collect
            config: Optional collector configuration
        """
        if config is None:
            config = CollectorConfig(
                name="example_rss_collector",
                timeout_seconds=30.0,
                max_retries=3,
            )
        super().__init__(config)
        self.feed_url = feed_url

    async def _collect_records(self, stats: CollectorStats) -> List[RawRecord]:
        """Collect records from RSS feed.
        
        Args:
            stats: Stats object to update during collection
            
        Returns:
            List of raw records
        """
        self.logger.info(f"Fetching RSS feed: {self.feed_url}")
        
        feed = await fetch_feed(self.feed_url, http_client=self.http_client)
        
        if feed.bozo:
            self.logger.warning(f"Feed parsing had issues: {getattr(feed, 'bozo_exception', None)}")
        
        records = []
        for entry in feed.entries:
            try:
                record = self._parse_entry(entry)
                if record:
                    records.append(record)
            except Exception as exc:
                self.logger.warning(f"Failed to parse entry: {exc}")
        
        self.logger.info(f"Collected {len(records)} records from feed")
        return records

    def _parse_entry(self, entry) -> RawRecord:
        """Parse a feed entry into a RawRecord.
        
        Args:
            entry: feedparser entry object
            
        Returns:
            RawRecord instance
        """
        url = getattr(entry, "link", None)
        title = getattr(entry, "title", "Untitled")
        
        if not url:
            return None
        
        summary = getattr(entry, "summary", None)
        content = getattr(entry, "content", None)
        
        content_html = None
        if content and len(content) > 0:
            content_html = sanitize_html(content[0].get("value", ""))
        elif summary:
            content_html = sanitize_html(summary)
        
        publish_date = None
        if hasattr(entry, "published"):
            publish_date = self.normalize_date(entry.published)
        elif hasattr(entry, "updated"):
            publish_date = self.normalize_date(entry.updated)
        
        return RawRecord(
            source=self.name,
            url=url,
            title=title,
            summary=summary,
            content_html=content_html,
            publish_date=publish_date,
        )
