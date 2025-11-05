"""Collector for National Medical Products Administration approvals."""

from __future__ import annotations

from typing import Dict, List, Optional

from src.ivd_monitor.models import RawRecord
from src.ivd_monitor.sources.base import BaseCollector, CollectorError, PageResult, requests

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    BeautifulSoup = None  # type: ignore


class NMPACollector(BaseCollector):
    """Fetch medical device approval entries from the NMPA."""

    source_id = "regulatory.nmpa_approvals"
    source_name = "National Medical Products Administration"
    source_type = "product_launches"
    default_category = "product_launches"

    api_url = "https://www.nmpa.gov.cn/data/i/v1/medicalDevice/registration"
    list_url = "https://www.nmpa.gov.cn/xxgk/ggtg/ylqx/index.html"

    def __init__(self, session: Optional[requests.Session] = None, *, page_size: int = 20) -> None:
        super().__init__(session=session)
        self.page_size = page_size
        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": self.list_url,
        }

    def _fetch_page(self, page: int) -> PageResult:
        params = {
            "page": page,
            "size": self.page_size,
            "searchText": "",
            "sort": "-issueDate",
        }
        response = self.session.get(self.api_url, params=params, headers=self.headers, timeout=20)
        response.encoding = "utf-8"
        response.raise_for_status()
        try:
            data = response.json()
            records = self._parse_json_payload(data)
            total = int(data.get("total", 0))
            has_more = page * self.page_size < total
            return PageResult(records=records, has_more=has_more)
        except ValueError:
            records = self._parse_html_listing(response.text)
            has_more = len(records) == self.page_size
            return PageResult(records=records, has_more=has_more)

    def _parse_json_payload(self, payload: Dict[str, object]) -> List[RawRecord]:
        data_list = payload.get("list") or payload.get("data")
        if isinstance(data_list, dict):
            data_list = data_list.get("list")
        if not isinstance(data_list, list):
            raise CollectorError("Missing approvals list in NMPA response")

        parsed: List[RawRecord] = []
        for item in data_list:
            if not isinstance(item, dict):
                continue
            title = item.get("productName") or item.get("title") or ""
            company = item.get("companyName") or item.get("enterprise")
            approve_date = item.get("issueDate") or item.get("publishDate")
            publish_date = None
            if approve_date:
                try:
                    publish_date = self._normalize_publish_date(approve_date)
                except CollectorError:
                    publish_date = None
            link = item.get("docUrl") or item.get("url") or ""
            if link and not link.startswith("http"):
                link = f"https://www.nmpa.gov.cn{link if link.startswith('/') else '/' + link}"
            metadata = {
                "certificate_no": item.get("approvalNumber") or item.get("issueNumber"),
                "product_category": item.get("productType"),
                "nmpa_id": item.get("id"),
            }
            summary_parts = [item.get("productModel"), item.get("productCategory")]
            summary = "；".join(part for part in summary_parts if part)
            record = RawRecord(
                source=self.source_id,
                source_type=self.source_type,
                category=self.default_category,
                url=link,
                title=title.strip(),
                summary=summary or None,
                publish_date=publish_date,
                companies=self._prepare_companies([company]),
                metadata={k: v for k, v in metadata.items() if v},
                region=self.region,
            )
            parsed.append(record)
        return parsed

    def _parse_html_listing(self, html: str) -> List[RawRecord]:
        if BeautifulSoup is None:
            raise CollectorError("BeautifulSoup is required for HTML parsing")
        soup = BeautifulSoup(html, "html.parser")
        records: List[RawRecord] = []
        for item in soup.select(".list ul li") or soup.select("li"):
            link = item.find("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.nmpa.gov.cn{href if href.startswith('/') else '/' + href}"
            date_node = item.find("span") or item.find("em")
            publish_date = None
            if date_node:
                try:
                    publish_date = self._normalize_publish_date(date_node.get_text(strip=True))
                except CollectorError:
                    publish_date = None
            record = RawRecord(
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
            records.append(record)
        return records

    def parse_fixture(self, payload: Dict[str, object]) -> PageResult:
        records = self._parse_json_payload(payload)
        total = int(payload.get("total", len(records)))
        has_more = len(records) < total
        return PageResult(records=records, has_more=has_more)
