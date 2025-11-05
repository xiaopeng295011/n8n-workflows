"""Collector for Shanghai Stock Exchange (SSE) company announcements."""

from __future__ import annotations

from typing import Dict, List, Optional

from src.ivd_monitor.models import RawRecord
from src.ivd_monitor.sources.base import (
    BaseCollector,
    BeautifulSoup,
    CollectorError,
    PageResult,
    extract_list_entries,
    requests,
)


class ShanghaiExchangeCollector(BaseCollector):
    """Fetch announcements from Shanghai Stock Exchange."""

    source_id = "financial.shanghai_exchange"
    source_name = "Shanghai Stock Exchange"
    source_type = "financial_reports"
    default_category = "financial_reports"

    list_url = "https://www.sse.com.cn/disclosure/listedinfo/announcement/"
    api_url = "https://query.sse.com.cn/infodisplay/queryLatestBulletinNew.do"
    detail_base = "https://www.sse.com.cn"

    def __init__(self, session: Optional[requests.Session] = None, *, page_size: int = 25) -> None:
        super().__init__(session=session)
        self.page_size = page_size
        self.headers = {
            "Referer": self.list_url,
            "User-Agent": "Mozilla/5.0",
        }

    def _fetch_page(self, page: int) -> PageResult:
        params = {
            "productId": "",
            "keyWord": "",
            "pageHelp.pageSize": str(self.page_size),
            "pageHelp.pageNo": str(page),
            "pageHelp.beginPage": str(page),
        }
        response = self.session.get(self.api_url, params=params, headers=self.headers, timeout=15)
        response.encoding = "utf-8"
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError:
            records = self._parse_bulletin_html(response.text)
            has_more = len(records) >= self.page_size
            return PageResult(records=records, has_more=has_more)

        records = self._parse_bulletin_json(data)
        page_total = data.get("pageHelp", {}).get("pageCount", page)
        has_more = page < page_total
        return PageResult(records=records, has_more=has_more)

    def _parse_bulletin_json(self, payload: Dict[str, object]) -> List[RawRecord]:
        result_list = payload.get("result")
        if not isinstance(result_list, list):
            raise CollectorError("Missing result list in SSE response")

        parsed: List[RawRecord] = []
        for item in result_list:
            if not isinstance(item, dict):
                continue
            title = item.get("SSEBulletinTitle") or item.get("title") or ""
            company = item.get("companyName") or item.get("SECURITY_NAME_ABBR")
            publish_date_raw = (
                item.get("SSEDATE")
                or item.get("publishTime")
                or item.get("SSEPublishDate")
                or item.get("SSESecurity")
            )
            publish_date = None
            if publish_date_raw:
                try:
                    publish_date = self._normalize_publish_date(publish_date_raw)
                except CollectorError:
                    publish_date = None
            url_path = item.get("URL") or item.get("PDF_URL") or item.get("sseUrl")
            if url_path and url_path.startswith("http"):
                url = url_path
            elif url_path:
                url = f"{self.detail_base}/{url_path.lstrip('/')}"
            else:
                url = f"{self.list_url}?bulletin_id={item.get('BULLETIN_ID', '')}"
            companies = self._prepare_companies([company])
            metadata = {
                "bulletin_id": item.get("BULLETIN_ID") or item.get("bulletinId"),
                "stock_code": item.get("productId") or item.get("securityCode"),
                "security_code": item.get("SSESecurity") or item.get("SECURITY_CODE"),
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

    def _parse_bulletin_html(self, html: str) -> List[RawRecord]:
        if BeautifulSoup is None:
            raise CollectorError("BeautifulSoup is required for HTML parsing")
        soup = BeautifulSoup(html, "html.parser")
        parsed: List[RawRecord] = []
        candidates = soup.select(".sse_list li") or soup.select(".list li") or soup.select("li")
        for item in candidates:
            link = item.find("a")
            if not link:
                continue
            title = link.get("title") or link.get_text(strip=True)
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = f"{self.detail_base}/{href.lstrip('/')}"
            date_node = item.find("span") or item.find("em")
            publish_date = None
            if date_node:
                try:
                    publish_date = self._normalize_publish_date(date_node.get_text(strip=True))
                except CollectorError:
                    publish_date = None
            parsed.append(
                RawRecord(
                    source=self.source_id,
                    source_type=self.source_type,
                    category=self.default_category,
                    url=href,
                    title=title.strip(),
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

        records = self._parse_bulletin_json(payload)
        page_count = payload.get("pageHelp", {}).get("pageCount", page)
        return PageResult(records=records, has_more=page < page_count)
