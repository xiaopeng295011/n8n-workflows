import json
from datetime import timezone
from pathlib import Path

import pytest

from src.ivd_monitor.sources.regulatory import NMPACollector, NHSACollector, NHCCollector

FIXTURES = Path(__file__).parent / "fixtures"


def load_json(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_html(name: str) -> str:
    with open(FIXTURES / name, "r", encoding="utf-8") as handle:
        return handle.read()


def test_nmpa_collector_json_parsing():
    collector = NMPACollector(page_size=20)
    page = collector.parse_fixture(load_json("nmpa_page1.json"))

    assert page.has_more is True
    assert len(page.records) == 2

    first = page.records[0]
    assert "全自动化学发光免疫分析仪" in first.title
    assert first.publish_date is not None
    assert first.publish_date.tzinfo == timezone.utc
    assert first.source_type == "product_launches"
    assert first.category == "product_launches"
    assert first.companies == ["北京华科泰生物技术有限公司"]
    assert first.metadata["certificate_no"] == "国械注准2023312345"
    assert first.summary
    assert "HKT-AI 3000" in first.summary

    second = page.records[1]
    assert "新型冠状病毒" in second.title
    assert second.companies == ["深圳市优迅医学检验实验室有限公司"]
    assert second.url.startswith("https://")


def test_nhsa_collector_html_parsing():
    collector = NHSACollector(page_size=20)
    page = collector.parse_fixture(load_html("nhsa_page1.html"), page=1)

    assert len(page.records) == 3

    first = page.records[0]
    assert "医疗保障支持疫情防控" in first.title
    assert first.publish_date is not None
    assert first.publish_date.tzinfo == timezone.utc
    assert first.source_type == "reimbursement_policy"
    assert first.category == "reimbursement_policy"
    assert first.url.endswith("art_1234_98765.html")

    last = page.records[2]
    assert "体外诊断试剂" in last.title
    assert last.publish_date.year == 2023
    assert last.publish_date.month == 10


def test_nhc_collector_html_parsing():
    collector = NHCCollector(page_size=20)
    page = collector.parse_fixture(load_html("nhc_page1.html"), page=1)

    assert len(page.records) == 2

    first = page.records[0]
    assert "三级医院检验能力提升" in first.title
    assert first.publish_date is not None
    assert first.publish_date.tzinfo == timezone.utc
    assert first.source_type == "health_commission_policy"
    assert first.category == "health_commission_policy"
    assert first.metadata["document_id"] == "2f7cb88d91c24b9bb1ff0c585a355c1f"

    second = page.records[1]
    assert "医疗质量安全指标" in second.title
    assert second.url.startswith("https://www.nhc.gov.cn/")


def test_all_collectors_return_raw_records():
    nmpa_page = NMPACollector().parse_fixture(load_json("nmpa_page1.json"))
    nhsa_page = NHSACollector().parse_fixture(load_html("nhsa_page1.html"))
    nhc_page = NHCCollector().parse_fixture(load_html("nhc_page1.html"))

    aggregated = nmpa_page.records + nhsa_page.records + nhc_page.records
    assert len(aggregated) == 7

    for record in aggregated:
        assert record.source
        assert record.url
        assert record.source_type
        assert record.category
        assert record.region == "CN"

        params = record.to_db_params()
        assert "source" in params
        assert "url" in params
        assert "category" in params
