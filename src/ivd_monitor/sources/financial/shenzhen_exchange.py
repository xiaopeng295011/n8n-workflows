"""Collector for Shenzhen Stock Exchange (SZSE) company announcements."""

from __future__ import annotations

from typing import Dict, List, Optional

from src.ivd_monitor.models import RawRecord
from src.ivd_monitor.sources.base import BaseCollector, CollectorError, PageResult, requests

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:
    BeautifulSoup = None  # type: ignore


class ShenzhenExchangeCollector(BaseCollector):
    """Fetch announcements from Shenzhen Stock Exchange."""

    source_id = "financial.shenzhen_exchange"
    source_name = "Shenzhen Stock Exchange"
    source_type = "financial_reports"
    default_category = "financial_reports"

    api_url = "https://www.szse.cn/api/disc/announcement/annList"
    detail_base = "https://disc.szse.cn/download"

    def __init__(self, session: Optional[requests.Session] = None, *, page_size: int = 30) -> None:
        super().__init__(session=session)
        self.page_size = page_size
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.szse.cn/disclosure/listed/notice/",
            "User-Agent": "Mozilla/5.0",
        }

    def _fetch_page(self, page: int) -> PageResult:
        params = {
            "random": "0.5",
            "channelCode": "listedNotice_disc",
            "seDate": self._date_range_param(),
            "pageSize": str(self.page_size),
            "pageNum": str(page - 1),
        }
        response = self.session.get(self.api_url, params=params, headers=self.headers, timeout=15)
        response.encoding = "utf-8"
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError:
            records = self._parse_html_listing(response.text)
            has_more = len(records) >= self.page_size
            return PageResult(records=records, has_more=has_more)

        records = self._parse_json_response(data)
        data_obj = data.get("data", {}) or {}
        total_pages = (data_obj.get("totalCount", 0) + self.page_size - 1) // self.page_size if isinstance(data_obj, dict) else page
        has_more = page < total_pages if total_pages else len(records) >= self.page_size
        return PageResult(records=records, has_more=has_more)

    def _parse_json_response(self, payload: Dict[str, object]) -> List[RawRecord]:
        container = payload.get("data")
        data_list: List[Dict[str, object]] = []
        if isinstance(container, dict):
            raw_list = container.get("data") or container.get("annList") or container.get("list")
            if isinstance(raw_list, list):
                data_list = [entry for entry in raw_list if isinstance(entry, dict)]
        elif isinstance(container, list):
            data_list = [entry for entry in container if isinstance(entry, dict)]

        if not data_list:
            raise CollectorError("Missing data in SZSE response")

        parsed: List[RawRecord] = []
        for item in data_list:
            if not isinstance(item, dict):
                continue
            title = item.get("announcementTitle") or ""
            company = item.get("secName")
            publish_time = item.get("publishTime")
            publish_date = None
            if publish_time:
                try:
                    publish_date = self._normalize_publish_date(publish_time)
                except CollectorError:
                    pass
            attachment_path = item.get("attachPath") or ""
            url = f"{self.detail_base}/{attachment_path.lstrip('/')}" if attachment_path else ""
            if not url:
                url = f"https://www.szse.cn/disclosure/listed/notice/?announcement_id={item.get('id', '')}"
            companies = self._prepare_companies([company])
            metadata = {
                "announcement_id": item.get("id"),
                "stock_code": item.get("secCode"),
                "announcement_type": item.get("announcementTypeName"),
                "attachment_size": item.get("attachSize"),
            }
            record = RawRecord(
                source=self.source_id,
                source_type=self.source_type,
                category=self.default_category,
                url=url,
                title=title.strip(),
                summary=None,
                publish_date=publish_date,
                companies=companies,
                metadata={k: v for k, v in metadata.items() if v is not None},
                region=self.region,
            )
            parsed.append(record)
        return parsed

    def _parse_html_listing(self, html: str) -> List[RawRecord]:
        if BeautifulSoup is None:
            raise CollectorError("BeautifulSoup is required for HTML parsing")
        soup = BeautifulSoup(html, "html.parser")
        parsed: List[RawRecord] = []
        for item in soup.select(".list li") or soup.select("li"):
            link = item.find("a")
            if not link:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.szse.cn{href if href.startswith('/') else '/' + href}"
            date_node = item.find("span") or item.find("em")
            publish_date = None
            if date_node:
                try:
                    publish_date = self._normalize_publish_date(date_node.get_text(strip=True))
                except CollectorError:
                    pass
            parsed.append(
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
            if len(parsed) >= self.page_size:
                break
        return parsed

    def parse_fixture(self, payload: Dict[str, object], page: int = 1) -> PageResult:
        """Helper for tests to parse fixture payloads without HTTP."""

        records = self._parse_json_response(payload)
        data_obj = payload.get("data", {}) or {}
        total_count = data_obj.get("totalCount", 0)
        total_pages = (total_count + self.page_size - 1) // self.page_size
        return PageResult(records=records, has_more=page < total_pages)
