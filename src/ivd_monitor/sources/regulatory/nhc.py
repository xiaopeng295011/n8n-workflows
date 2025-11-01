"""Collector for National Health Commission notices."""

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


class NHCCollector(BaseCollector):
    """Fetch policy notices from the National Health Commission."""

    source_id = "regulatory.nhc_notices"
    source_name = "National Health Commission"
    source_type = "health_commission_policy"
    default_category = "health_commission_policy"

    list_url = "https://www.nhc.gov.cn/guihuaxxs/s10742/s14680/index.shtml"
    base_url = "https://www.nhc.gov.cn"

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
            suffix = "index.shtml" if page == 1 else f"index_{page-1}.shtml"
            url = f"https://www.nhc.gov.cn/guihuaxxs/s10742/s14680/{suffix}"
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
            nodes = soup.select(".list li") or soup.select("li")
            for item in nodes:
                link_node = item.find("a")
                if not link_node:
                    continue
                title = link_node.get_text(strip=True)
                href = link_node.get("href", "")
                if href and not href.startswith("http"):
                    href = f"{self.base_url}/{href.lstrip('/')}"
                date_node = item.find("span") or item.select_one(".date")
                publish_date = None
                if date_node:
                    date_text = date_node.get_text(strip=True)
                    try:
                        publish_date = self._normalize_publish_date(date_text)
                    except CollectorError:
                        publish_date = None
                doc_id = href.split("/")[-1].split(".")[0] if href else None
                metadata = {"document_id": doc_id} if doc_id else {}
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
                        metadata=metadata,
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
                    href = f"{self.base_url}/{href.lstrip('/')}"
                date_text = entry.get("date")
                publish_date = None
                if date_text:
                    try:
                        publish_date = self._normalize_publish_date(date_text)
                    except CollectorError:
                        publish_date = None
                doc_id = href.split("/")[-1].split(".")[0] if href else None
                metadata = {"document_id": doc_id} if doc_id else {}
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
                        metadata=metadata,
                        region=self.region,
                    )
                )
                if len(records) >= self.page_size:
                    break
        return records

    def parse_fixture(self, html: str, page: int = 1) -> PageResult:
        records = self._parse_html_listing(html)
        has_more = len(records) >= self.page_size
        return PageResult(records=records, has_more=has_more)
