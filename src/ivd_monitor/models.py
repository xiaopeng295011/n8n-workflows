"""Data models for IVD Monitor collectors."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RawRecord:
    """Raw record returned by collectors before database insertion.
    
    This dataclass represents a single news item, regulatory announcement,
    or financial report scraped from a source, ready to be inserted into
    the IVD database.
    """
    
    source: str
    url: str
    title: Optional[str] = None
    summary: Optional[str] = None
    content_html: Optional[str] = None
    publish_date: Optional[datetime] = None
    source_type: Optional[str] = None
    category: Optional[str] = None
    companies: List[str] = field(default_factory=list)
    region: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    scraped_at: Optional[datetime] = None
    
    def to_db_params(self) -> Dict[str, Any]:
        """Convert to parameters for IVDDatabase.insert_record()."""
        return {
            "source": self.source,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "content_html": self.content_html,
            "publish_date": self.publish_date,
            "source_type": self.source_type,
            "category": self.category,
            "companies": self.companies,
            "region": self.region,
            "metadata": self.metadata,
            "scraped_at": self.scraped_at,
        }
