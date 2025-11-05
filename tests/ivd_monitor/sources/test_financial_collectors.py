import json
from datetime import timezone
from pathlib import Path

import pytest

from src.ivd_monitor.sources.financial import JuchaoCollector, ShanghaiExchangeCollector, ShenzhenExchangeCollector

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def test_juchao_multi_page_parsing():
    collector = JuchaoCollector(page_size=30)

    page_one = collector.parse_fixture(load_json("juchao_page1.json"), page=1)
    assert page_one.has_more is True
    page_two = collector.parse_fixture(load_json("juchao_page2.json"), page=2)
    assert page_two.has_more is False

    records = page_one.records + page_two.records
    assert len(records) == 3

    first = records[0]
    assert "贵州茅台" in first.title
    assert first.publish_date is not None
    assert first.publish_date.tzinfo == timezone.utc
    assert first.source_type == "financial_reports"
    assert first.category == "financial_reports"
    assert first.metadata["cninfo_id"] == "1201900001"

    companies = {record.companies[0] for record in records if record.companies}
    assert "宁波先锋" in companies


def test_shanghai_exchange_json_parsing():
    collector = ShanghaiExchangeCollector(page_size=25)
    page = collector.parse_fixture(load_json("shanghai_exchange_page1.json"), page=1)

    assert page.has_more is True
    assert len(page.records) == 2

    primary = page.records[0]
    assert primary.publish_date is not None
    assert primary.publish_date.tzinfo == timezone.utc
    assert primary.title.startswith("上海复星医药")
    assert primary.source_type == "financial_reports"
    assert primary.metadata["bulletin_id"] == "1234567890"
    assert primary.companies == ["复星医药"]


def test_shenzhen_exchange_json_parsing():
    collector = ShenzhenExchangeCollector(page_size=30)
    page = collector.parse_fixture(load_json("shenzhen_exchange_page1.json"), page=1)

    assert page.has_more is True
    assert len(page.records) == 2

    record = page.records[0]
    assert record.publish_date is not None
    assert record.publish_date.tzinfo == timezone.utc
    assert "新产品获批" in record.title or "公告" in record.title
    assert record.metadata["announcement_id"] == "11223344"
    assert record.source_type == "financial_reports"

    params = record.to_db_params()
    assert params["source"] == collector.source_id
    assert params["publish_date"].tzinfo == timezone.utc
