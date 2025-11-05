"""Collector implementation for CNInfo (巨潮资讯) announcements."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from src.ivd_monitor.models import RawRecord
from src.ivd_monitor.sources.base import BaseCollector, CollectorError, PageResult, requests


class JuchaoCollector(BaseCollector):
    """Fetch announcements from the CNInfo disclosure platform."""

    source_id = "financial.cninfo_juchao"
    source_name = "CNInfo Juchao"
    source_type = "financial_reports"
    default_category = "financial_reports"

    api_url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    detail_base = "https://static.cninfo.com.cn/"

    def __init__(self, session: Optional[requests.Session] = None, *, page_size: int = 30) -> None:
        super().__init__(session=session)
        self.page_size = page_size
        self.headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "Origin": "https://www.cninfo.com.cn",
            "Referer": "https://www.cninfo.com.cn/",
            "User-Agent": "Mozilla/5.0",
        }

    def _fetch_page(self, page: int) -> PageResult:
        payload = {
            "pageNum": page,
            "pageSize": self.page_size,
            "column": "sse",
            "tabName": "fulltext",
            "plate": "sh;sz;szse",
            "seDate": self._date_range_param(),
            "sortName": "time",
            "sortType": "desc",
            "token": "query",
        }
        response = self.session.post(self.api_url, json=payload, headers=self.headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        records = self._parse_announcements(data)
        total_pages = int(data.get("totalpages") or page)
        has_more = page < total_pages
        return PageResult(records=records, has_more=has_more)

    def _parse_announcements(self, payload: Dict[str, object]) -> List[RawRecord]:
        announcements = payload.get("announcements")
        if not isinstance(announcements, list):
            raise CollectorError("Missing announcements array in CNInfo response")

        parsed: List[RawRecord] = []
        for item in announcements:
            if not isinstance(item, dict):
                continue
            publish_ts = item.get("announcementTime")
            # CNInfo uses milliseconds
            publish_date = None
            if publish_ts is not None:
                publish_date = self._normalize_publish_date(int(publish_ts) / 1000)
            title = item.get("announcementTitle") or ""
            summary = item.get("announcementTitle")
            url_path = item.get("adjunctUrl") or ""
            if url_path.startswith("http"):
                url = url_path
            else:
                url = f"{self.detail_base}{url_path.lstrip('/')}"
            companies = self._prepare_companies([item.get("secName")])
            metadata = {
                "cninfo_id": item.get("announcementId"),
                "stock_code": item.get("secCode"),
                "column": item.get("columnId"),
                "adjunct_type": item.get("adjunctType"),
                "adjunct_size": item.get("adjunctSize"),
            }
            record = RawRecord(
                source=self.source_id,
                source_type=self.source_type,
                category=self.default_category,
                url=url,
                title=title.strip(),
                summary=summary.strip() if summary else None,
                publish_date=publish_date,
                companies=companies,
                metadata={k: v for k, v in metadata.items() if v is not None},
                region=self.region,
            )
            parsed.append(record)
        return parsed

    def parse_fixture(self, payload: Dict[str, object], page: int = 1) -> PageResult:
        """Helper for tests to parse fixture payloads without HTTP."""

        records = self._parse_announcements(payload)
        total_pages = int(payload.get("totalpages") or page)
        return PageResult(records=records, has_more=page < total_pages)
