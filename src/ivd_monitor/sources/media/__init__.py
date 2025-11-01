"""Industry media source collectors."""

from .collectors import IndustryMediaCollector
from .rss import RSSFeedCollector

__all__ = [
    "IndustryMediaCollector",
    "RSSFeedCollector",
]
