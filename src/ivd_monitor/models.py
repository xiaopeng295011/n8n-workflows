"""Shared data models for the IVD monitor scraper core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RawRecord:
    """Represents a raw record collected from a source before database insertion.
    
    This model captures all the information scraped from external sources
    and serves as the input for database insertion operations.
    """
    
    source: str
    url: str
    title: str
    summary: Optional[str] = None
    content_html: Optional[str] = None
    publish_date: Optional[str] = None  # ISO8601 format expected
    category: Optional[str] = None
    companies: List[str] = field(default_factory=list)
    source_type: Optional[str] = None
    region: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate required fields."""
        if not self.source:
            raise ValueError("source is required")
        if not self.url:
            raise ValueError("url is required")
        if not self.title:
            raise ValueError("title is required")


@dataclass
class CollectorError:
    """Represents an error encountered during collection.
    
    Used to track failures without crashing the entire collection run,
    enabling partial success scenarios and error reporting.
    """
    
    collector_name: str
    error_type: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    url: Optional[str] = None
    retry_count: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging or serialization."""
        return {
            "collector_name": self.collector_name,
            "error_type": self.error_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "url": self.url,
            "retry_count": self.retry_count,
            "context": self.context,
        }


@dataclass
class CollectorStats:
    """Statistics for a collection run.
    
    Tracks success/failure counts, timing, and other metrics
    to enable monitoring and performance analysis.
    """
    
    collector_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    records_collected: int = 0
    records_failed: int = 0
    http_requests: int = 0
    retry_attempts: int = 0
    errors: List[CollectorError] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate duration in seconds if completed."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        total = self.records_collected + self.records_failed
        if total == 0:
            return 0.0
        return (self.records_collected / total) * 100
    
    def add_error(self, error: CollectorError) -> None:
        """Add an error to the stats."""
        self.errors.append(error)
        self.records_failed += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging or serialization."""
        return {
            "collector_name": self.collector_name,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "records_collected": self.records_collected,
            "records_failed": self.records_failed,
            "http_requests": self.http_requests,
            "retry_attempts": self.retry_attempts,
            "success_rate": self.success_rate,
            "error_count": len(self.errors),
            "metadata": self.metadata,
        }


@dataclass
class CollectorConfig:
    """Configuration for a collector instance.
    
    Encapsulates timeout, retry, and other operational settings
    that can be customized per collector.
    """
    
    name: str
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_base_delay: float = 1.0  # Base delay for exponential backoff
    retry_max_delay: float = 60.0
    retry_exponential_base: float = 2.0
    headers: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_base_delay <= 0:
            raise ValueError("retry_base_delay must be positive")


@dataclass
class CollectionResult:
    """Result of a collection operation.
    
    Contains both successful records and any errors encountered,
    along with statistics about the collection run.
    """
    
    collector_name: str
    records: List[RawRecord] = field(default_factory=list)
    stats: Optional[CollectorStats] = None
    success: bool = True
    error_message: Optional[str] = None
    
    @property
    def record_count(self) -> int:
        """Count of successfully collected records."""
        return len(self.records)
    
    @property
    def error_count(self) -> int:
        """Count of errors encountered."""
        return len(self.stats.errors) if self.stats else 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging or serialization."""
        return {
            "collector_name": self.collector_name,
            "success": self.success,
            "record_count": self.record_count,
            "error_count": self.error_count,
            "error_message": self.error_message,
            "stats": self.stats.to_dict() if self.stats else None,
        }


@dataclass
class CollectorManagerResult:
    """Aggregate result from running multiple collectors."""

    records: List[RawRecord] = field(default_factory=list)
    errors: List[CollectorError] = field(default_factory=list)
    stats: Dict[str, CollectorStats] = field(default_factory=dict)
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "record_count": len(self.records),
            "error_count": len(self.errors),
            "stats": {name: stat.to_dict() for name, stat in self.stats.items()},
        }
