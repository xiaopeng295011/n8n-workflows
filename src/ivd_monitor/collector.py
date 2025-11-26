"""Base collector implementation for IVD monitor scrapers."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

import httpx

from .http_client import HTTPClient
from .logging_config import get_logger
from .models import (
    CollectionResult,
    CollectorConfig,
    CollectorError,
    CollectorStats,
    RawRecord,
)
from .parser_utils import normalize_publish_date, sanitize_html

logger = get_logger("collector")


class BaseCollector(ABC):
    """Abstract base class for all collectors.
    
    Provides common functionality for HTTP fetching, retry logic,
    timeout controls, and date normalization. Subclasses implement
    the collection logic specific to their data source.
    """

    def __init__(self, config: Optional[CollectorConfig] = None) -> None:
        """Initialize collector with configuration.
        
        Args:
            config: Collector configuration with timeout and retry settings
        """
        self.config = config or CollectorConfig(name=self.__class__.__name__)
        self.http_client = HTTPClient(config=self.config)
        self.logger = get_logger(self.config.name)

    @property
    def name(self) -> str:
        """Return collector name."""
        return self.config.name

    @property
    def enabled(self) -> bool:
        """Return whether collector is enabled."""
        return self.config.enabled

    async def collect(self) -> CollectionResult:
        """Execute collection and return results.
        
        This is the main entry point for running the collector.
        It handles stats tracking and error capture, calling the
        abstract _collect_records method for the actual work.
        
        Returns:
            CollectionResult with records, stats, and any errors
        """
        stats = CollectorStats(collector_name=self.name, started_at=datetime.utcnow())
        
        try:
            self.logger.info(f"Starting collection for {self.name}")
            raw_records = await self._collect_records(stats)
            records = [self._prepare_record(record) for record in raw_records]
            stats.records_collected = len(records)
            stats.completed_at = datetime.utcnow()
            duration = stats.duration_seconds or 0.0
            
            self.logger.info(
                f"Collection completed for {self.name}: "
                f"{stats.records_collected} records, "
                f"{stats.records_failed} failures, "
                f"{stats.retry_attempts} retries, "
                f"{duration:.2f}s"
            )
            
            return CollectionResult(
                collector_name=self.name,
                records=records,
                stats=stats,
                success=True,
            )
            
        except Exception as exc:
            self.logger.exception(f"Collection failed for {self.name}: {exc}")
            stats.completed_at = datetime.utcnow()
            
            error = CollectorError(
                collector_name=self.name,
                error_type=type(exc).__name__,
                message=str(exc),
            )
            stats.add_error(error)
            
            return CollectionResult(
                collector_name=self.name,
                records=[],
                stats=stats,
                success=False,
                error_message=str(exc),
            )

    @abstractmethod
    async def _collect_records(self, stats: CollectorStats) -> List[RawRecord]:
        """Collect records from the source.
        
        This method must be implemented by subclasses to define
        the collection logic specific to their data source.
        
        Args:
            stats: Stats object to update during collection
            
        Returns:
            List of raw records collected
            
        Raises:
            Any exception encountered during collection
        """
        pass

    def _prepare_record(self, record: RawRecord) -> RawRecord:
        """Prepare a record by normalizing dates and sanitizing content.
        
        Args:
            record: Raw record to prepare
            
        Returns:
            Prepared record
        """
        if record.publish_date:
            record.publish_date = self.normalize_date(record.publish_date)
        if record.content_html:
            record.content_html = sanitize_html(record.content_html)
        return record

    def normalize_date(
        self,
        value: Optional[str],
        *,
        default_timezone: str = "UTC",
    ) -> Optional[str]:
        """Normalize a publish date to ISO8601 UTC format.
        
        Args:
            value: Date string to normalize
            default_timezone: Timezone to assume if not specified
            
        Returns:
            ISO8601 UTC date string with Z suffix, or None
        """
        try:
            return normalize_publish_date(value, default_timezone=default_timezone)
        except Exception as exc:
            self.logger.warning(f"Failed to normalize date '{value}': {exc}")
            return None

    async def fetch_url(
        self,
        url: str,
        stats: CollectorStats,
        *,
        retry_on_failure: bool = True,
    ) -> Optional[str]:
        """Fetch URL content with retry logic.
        
        Args:
            url: URL to fetch
            stats: Stats object to update
            retry_on_failure: Whether to retry on failure
            
        Returns:
            Response text, or None if fetch failed
        """
        original_retries = self.http_client.config.max_retries

        if not retry_on_failure:
            self.http_client.config.max_retries = 0

        try:
            response = await self.http_client.get_async(url, stats=stats)
            return response.text

        except Exception as exc:
            error = CollectorError(
                collector_name=self.name,
                error_type=type(exc).__name__,
                message=str(exc),
                url=url,
            )
            stats.add_error(error)
            self.logger.error(f"Failed to fetch {url}: {exc}")
            return None

        finally:
            self.http_client.config.max_retries = original_retries


class SyncCollector(BaseCollector):
    """Base collector that supports synchronous collection methods.
    
    For collectors that need to use synchronous libraries or APIs,
    this class provides a sync-to-async bridge.
    """

    async def _collect_records(self, stats: CollectorStats) -> List[RawRecord]:
        """Run sync collection in a thread pool."""
        return await asyncio.to_thread(self._collect_records_sync, stats)

    @abstractmethod
    def _collect_records_sync(self, stats: CollectorStats) -> List[RawRecord]:
        """Synchronous collection method to implement.
        
        Args:
            stats: Stats object to update during collection
            
        Returns:
            List of raw records collected
        """
        pass
