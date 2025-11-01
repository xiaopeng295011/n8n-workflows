"""Collector for National Healthcare Security Administration policy updates."""

from __future__ import annotations

from typing import List, Optional

from src.ivd_monitor.models import RawRecord
from src.ivd_monitor.sources.base import (
    BaseCollector,
    BeautifulSoup,
    CollectorError,
    PageResult,
    extract_list_entries,
    requests,
)


class NHSACollector(BaseCollector):
    """Fetch policy announcements from the National Healthcare Security Administration."""

    source_id = "regulatory.nhsa_policy"
    source_name = "National Healthcare Security Administration"
    source_type = "reimbursement_policy"
    default_category = "reimbursement_policy"

    list_url = "https://www.nhsa.gov.cn/col/col5881/index.html"
    base_url = "https://www.nhsa.gov.cn"

    def __init__(self, session: Optional[requests.Session] = None, *, page_size: int = 20) -> None:
        super().__init__(session=session)
        self.page_size = page_size
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": self.base_url,
        }

    def _fetch_page(self, page: int) -> PageResult:
        if page == 1:
            url = self.list_url
        else:
            url = f"https://www.nhsa.gov.cn/col/col5881/index_{page}.html"
        response = self.session.get(url, headers=self.headers, timeout=15)
        response.encoding = "utf-8"
        response.raise_for_status()
        records = self._parse_html_listing(response.text)
        has_more = len(records) >= self.page_size
        return PageResult(records=records, has_more=has_more)

    def _parse_html_listing(self, html: str) -> List[RawRecord]:
        records: List[RawRecord] = []
        if BeautifulSoup is not None:
            soup = BeautifulSoup(html, "html.parser")
            nodes = soup.select("ul.list-box li") or soup.select("li.list-item") or soup.select("li")
            for item in nodes:
                link_node = item.find("a")
                if not link_node:
                    continue
                title = link_node.get_text(strip=True)
                href = link_node.get("href", "")
                if href and not href.startswith("http"):
                    if href.startswith("./"):
                        href = href[2:]
                    href = f"{self.base_url}/{href.lstrip('/')}"
                date_node = item.select_one(".date") or item.select_one("span.time") or item.find("span")
                publish_date = None
                if date_node:
                    date_text = date_node.get_text(strip=True)
                    try:
                        publish_date = self._normalize_publish_date(date_text)
                    except CollectorError:
                        publish_date = None
                records.append(
                    RawRecord(
                        source=self.source_id,
                        source_type=self.source_type,
                        category=self.default_category,
                        url=href,
                        title=title,
                        summary=None,
                        publish_date=publish_date,
                        companies=[],
                        metadata={},
                        region=self.region,
                    )
                )
                if len(records) >= self.page_size:
                    break
        if not records:
            entries = extract_list_entries(html)
            for entry in entries:
                href = entry.get("href") or ""
                if href and not href.startswith("http"):
                    if href.startswith("./"):
                        href = href[2:]
                    href = f"{self.base_url}/{href.lstrip('/')}"
                date_text = entry.get("date")
                publish_date = None
                if date_text:
                    try:
                        publish_date = self._normalize_publish_date(date_text)
                    except CollectorError:
                        publish_date = None
                records.append(
                    RawRecord(
                        source=self.source_id,
                        source_type=self.source_type,
                        category=self.default_category,
                        url=href,
                        title=entry.get("title", ""),
                        summary=None,
                        publish_date=publish_date,
                        companies=[],
                        metadata={},
                        region=self.region,
                    )
                )
                if len(records) >= self.page_size:
                    break
        return records

    def parse_fixture(self, html: str, page: int = 1) -> PageResult:
        """Parse HTML fixture for testing."""

        records = self._parse_html_listing(html)
        has_more = len(records) >= self.page_size
        return PageResult(records=records, has_more=has_more)
