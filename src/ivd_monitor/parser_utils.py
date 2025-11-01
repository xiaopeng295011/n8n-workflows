"""Parsing utilities for the IVD monitor collectors."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Union

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil import tz

DEFAULT_ALLOWED_TAGS: Sequence[str] = (
    "a",
    "p",
    "ul",
    "ol",
    "li",
    "em",
    "strong",
    "blockquote",
    "code",
    "pre",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "span",
    "div",
    "br",
    "img",
)

DEFAULT_ALLOWED_ATTRIBUTES: Dict[str, Iterable[str]] = {
    "a": ("href", "title", "rel"),
    "img": ("src", "alt", "title"),
    "*": ("class", "id", "style"),
}


def sanitize_html(
    html: Optional[str],
    *,
    allowed_tags: Sequence[str] = DEFAULT_ALLOWED_TAGS,
    allowed_attributes: Optional[Dict[str, Iterable[str]]] = None,
) -> str:
    """Sanitize HTML content by removing unsafe tags and attributes."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style"]):
        tag.decompose()

    if allowed_attributes is None:
        allowed_attributes = DEFAULT_ALLOWED_ATTRIBUTES

    allowed_tags_set = set(allowed_tags)

    for tag in soup.find_all(True):
        if tag.name not in allowed_tags_set:
            tag.unwrap()
            continue
        allowed_attrs = set(allowed_attributes.get(tag.name, [])) | set(allowed_attributes.get("*", []))
        for attr in list(tag.attrs):
            if attr not in allowed_attrs:
                del tag.attrs[attr]

    # Extract inner HTML without surrounding <html><body> wrappers
    body = soup.body
    if body:
        sanitized = body.decode_contents()
    else:
        sanitized = str(soup)
    return sanitized.strip()


def normalize_publish_date(
    value: Optional[Union[str, datetime]],
    *,
    default_timezone: Union[str, tz.tzfile, None] = "UTC",
) -> Optional[str]:
    """Normalize publish dates to ISO8601 UTC format with Z suffix."""
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        dt = date_parser.parse(value)

    if dt.tzinfo is None:
        tzinfo = tz.gettz(default_timezone) if isinstance(default_timezone, str) else default_timezone
        if tzinfo is None:
            tzinfo = timezone.utc
        dt = dt.replace(tzinfo=tzinfo)

    dt_utc = dt.astimezone(timezone.utc)
    dt_utc = dt_utc.replace(microsecond=0)
    iso = dt_utc.isoformat()
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso


def ensure_list(value: Optional[Union[str, Sequence[str]]]) -> List[str]:
    """Ensure input is a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
