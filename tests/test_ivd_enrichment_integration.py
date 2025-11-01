"""Integration tests for IVD enrichment pipeline with database persistence."""

import sqlite3
from datetime import datetime

import pytest

from src.ivd_monitor.categorization import CategoryClassifier, enrich_records
from src.ivd_monitor.company_matching import CompanyMatcher
from src.ivd_monitor.database import IVDDatabase


@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary database path."""
    return tmp_path / "test_ivd.db"


@pytest.fixture
def ivd_db(db_path):
    """Create a test IVDDatabase instance."""
    db = IVDDatabase(db_path=str(db_path))
    db.initialize()
    return db


@pytest.fixture
def company_matcher():
    """Create a CompanyMatcher instance."""
    return CompanyMatcher()


@pytest.fixture
def category_classifier():
    """Create a CategoryClassifier instance."""
    return CategoryClassifier()


def test_enrichment_before_database_insert(ivd_db, company_matcher, category_classifier):
    """Test that enrichment works before database insertion."""
    # Raw record without enrichment
    raw_record = {
        "source": "cninfo",
        "url": "https://example.com/report-1",
        "title": "迈瑞医疗2023年第三季度财报",
        "summary": "公司Q3营收增长25%，净利润增长30%",
        "content_html": "<p>迈瑞医疗发布财报，业绩增长显著</p>",
        "publish_date": "2023-11-01T08:00:00Z",
    }

    # Enrich the record
    enriched = enrich_records([raw_record], company_matcher=company_matcher, category_classifier=category_classifier)[0]

    # Verify enrichment
    assert "companies" in enriched
    assert "迈瑞医疗" in enriched["companies"]
    assert enriched["category"] == CategoryClassifier.CATEGORY_FINANCIAL

    # Insert enriched record
    result = ivd_db.insert_record(
        source=enriched["source"],
        url=enriched["url"],
        category=enriched["category"],
        companies=enriched["companies"],
        title=enriched["title"],
        summary=enriched["summary"],
        content_html=enriched["content_html"],
        publish_date=enriched["publish_date"],
    )

    assert result.status == "inserted"

    # Query and verify stored data
    records = ivd_db.get_records_by_category(CategoryClassifier.CATEGORY_FINANCIAL)
    assert len(records) == 1
    assert "迈瑞医疗" in records[0]["companies"]
    assert records[0]["category"] == CategoryClassifier.CATEGORY_FINANCIAL


def test_multi_company_detection_and_persistence(ivd_db, company_matcher, category_classifier):
    """Test detection and storage of multiple companies in one record."""
    raw_record = {
        "source": "industry_news",
        "url": "https://example.com/industry-report",
        "title": "IVD行业展会报告",
        "summary": "迈瑞医疗、安图生物、华大基因参展",
        "content_html": "<p>迈瑞医疗展示新品，安图生物发布化学发光系统，华大基因展示基因测序技术</p>",
        "publish_date": "2023-11-02T09:00:00Z",
    }

    enriched = enrich_records([raw_record], company_matcher=company_matcher, category_classifier=category_classifier)[0]

    # Should detect multiple companies
    assert len(enriched["companies"]) >= 3
    assert "迈瑞医疗" in enriched["companies"]
    assert "安图生物" in enriched["companies"]
    assert "华大基因" in enriched["companies"]

    # Insert and verify
    ivd_db.insert_record(
        source=enriched["source"],
        url=enriched["url"],
        category=enriched["category"],
        companies=enriched["companies"],
        title=enriched["title"],
        summary=enriched["summary"],
        content_html=enriched["content_html"],
        publish_date=enriched["publish_date"],
    )

    # Query by each company
    mindray_records = ivd_db.get_records_by_company("迈瑞医疗")
    assert len(mindray_records) == 1

    autobio_records = ivd_db.get_records_by_company("安图生物")
    assert len(autobio_records) == 1

    bgi_records = ivd_db.get_records_by_company("华大基因")
    assert len(bgi_records) == 1


def test_category_based_querying(ivd_db, company_matcher, category_classifier):
    """Test querying enriched records by category."""
    records = [
        {
            "source": "cninfo",
            "url": "https://example.com/financial-1",
            "title": "迈瑞医疗财报",
            "summary": "业绩增长",
            "content_html": "<p>营收利润双增</p>",
            "publish_date": "2023-11-01T08:00:00Z",
        },
        {
            "source": "medtech",
            "url": "https://example.com/product-1",
            "title": "新产品获批上市",
            "summary": "安图生物新品获NMPA批准",
            "content_html": "<p>安图生物新型化学发光系统获批</p>",
            "publish_date": "2023-11-01T10:00:00Z",
        },
        {
            "source": "bidding_platform",
            "url": "https://example.com/bidding-1",
            "title": "医疗设备招标公告",
            "summary": "某医院IVD设备集中采购",
            "content_html": "<p>招标项目包含多个品类</p>",
            "publish_date": "2023-11-01T12:00:00Z",
        },
    ]

    enriched_records = enrich_records(records, company_matcher=company_matcher, category_classifier=category_classifier)

    # Insert all
    for enriched in enriched_records:
        ivd_db.insert_record(
            source=enriched["source"],
            url=enriched["url"],
            category=enriched["category"],
            companies=enriched.get("companies", []),
            title=enriched["title"],
            summary=enriched["summary"],
            content_html=enriched["content_html"],
            publish_date=enriched["publish_date"],
        )

    # Query by category
    financial = ivd_db.get_records_by_category(CategoryClassifier.CATEGORY_FINANCIAL)
    assert len(financial) == 1
    assert "迈瑞医疗" in financial[0]["companies"]

    product_launches = ivd_db.get_records_by_category(CategoryClassifier.CATEGORY_PRODUCT_LAUNCH)
    assert len(product_launches) == 1
    assert "安图生物" in product_launches[0]["companies"]

    bidding = ivd_db.get_records_by_category(CategoryClassifier.CATEGORY_BIDDING)
    assert len(bidding) == 1


def test_ingestion_run_with_enrichment(ivd_db, company_matcher, category_classifier):
    """Test full ingestion run with enrichment tracking."""
    run_id = ivd_db.start_ingestion_run(source="test_feed")

    records = [
        {
            "source": "cninfo",
            "url": f"https://example.com/record-{i}",
            "title": f"迈瑞医疗报告{i}",
            "summary": "业绩报告",
            "content_html": "<p>财务数据</p>",
            "publish_date": f"2023-11-0{i+1}T08:00:00Z",
        }
        for i in range(3)
    ]

    enriched_records = enrich_records(records, company_matcher=company_matcher, category_classifier=category_classifier)

    for enriched in enriched_records:
        ivd_db.insert_record(
            source=enriched["source"],
            url=enriched["url"],
            category=enriched["category"],
            companies=enriched["companies"],
            title=enriched["title"],
            summary=enriched["summary"],
            content_html=enriched["content_html"],
            publish_date=enriched["publish_date"],
            ingestion_run_id=run_id,
        )

    ivd_db.complete_ingestion_run(run_id)

    # Verify metrics
    metrics = ivd_db.get_ingestion_metrics()
    assert metrics["total_runs"] == 1
    assert metrics["new_records"] == 3

    # Verify all records have enrichment
    all_records = ivd_db.get_records_by_company("迈瑞医疗")
    assert len(all_records) == 3
    for record in all_records:
        assert record["category"] == CategoryClassifier.CATEGORY_FINANCIAL
        assert "迈瑞医疗" in record["companies"]


def test_chinese_language_matching_and_categorization(ivd_db, company_matcher, category_classifier):
    """Test Chinese language support throughout pipeline."""
    record = {
        "source": "医保局",
        "url": "https://example.com/policy-1",
        "title": "关于完善医保支付政策的通知",
        "summary": "医疗保障局发布新的医保目录调整方案",
        "content_html": "<p>本次调整涉及多项诊断项目，将提高医保支付比例</p>",
        "publish_date": "2023-11-01T08:00:00Z",
    }

    enriched = enrich_records([record], company_matcher=company_matcher, category_classifier=category_classifier)[0]

    assert enriched["category"] == CategoryClassifier.CATEGORY_NHSA_POLICY

    ivd_db.insert_record(
        source=enriched["source"],
        url=enriched["url"],
        category=enriched["category"],
        companies=enriched.get("companies", []),
        title=enriched["title"],
        summary=enriched["summary"],
        content_html=enriched["content_html"],
        publish_date=enriched["publish_date"],
    )

    policy_records = ivd_db.get_records_by_category(CategoryClassifier.CATEGORY_NHSA_POLICY)
    assert len(policy_records) == 1


def test_alias_handling_in_database_queries(ivd_db, company_matcher, category_classifier):
    """Test that company aliases are properly normalized in database."""
    # Use alias in content
    record = {
        "source": "news",
        "url": "https://example.com/news-1",
        "title": "Mindray announces new product",
        "summary": "深圳迈瑞推出创新诊断设备",
        "content_html": "<p>Mindray公司发布新品</p>",
        "publish_date": "2023-11-01T08:00:00Z",
    }

    enriched = enrich_records([record], company_matcher=company_matcher, category_classifier=category_classifier)[0]

    # Should normalize to canonical name
    assert "迈瑞医疗" in enriched["companies"]

    ivd_db.insert_record(
        source=enriched["source"],
        url=enriched["url"],
        category=enriched["category"],
        companies=enriched["companies"],
        title=enriched["title"],
        summary=enriched["summary"],
        content_html=enriched["content_html"],
        publish_date=enriched["publish_date"],
    )

    # Query using canonical name
    records = ivd_db.get_records_by_company("迈瑞医疗")
    assert len(records) == 1


def test_edge_case_no_companies_detected(ivd_db, company_matcher, category_classifier):
    """Test handling of records with no detected companies."""
    record = {
        "source": "generic_news",
        "url": "https://example.com/generic-1",
        "title": "行业一般性新闻",
        "summary": "关于IVD行业的一般性报道",
        "content_html": "<p>行业概况和趋势分析</p>",
        "publish_date": "2023-11-01T08:00:00Z",
    }

    enriched = enrich_records([record], company_matcher=company_matcher, category_classifier=category_classifier)[0]

    # Should have empty companies list
    assert enriched["companies"] == []
    # Should still have a category
    assert enriched["category"] == CategoryClassifier.CATEGORY_INDUSTRY_MEDIA

    result = ivd_db.insert_record(
        source=enriched["source"],
        url=enriched["url"],
        category=enriched["category"],
        companies=enriched["companies"],
        title=enriched["title"],
        summary=enriched["summary"],
        content_html=enriched["content_html"],
        publish_date=enriched["publish_date"],
    )

    assert result.status == "inserted"

    # Verify in database
    conn = sqlite3.connect(str(ivd_db.db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT companies, category FROM records WHERE id = ?", (result.record_id,)).fetchone()
        assert row is not None
        assert row["companies"] == "[]"
        assert row["category"] == CategoryClassifier.CATEGORY_INDUSTRY_MEDIA
    finally:
        conn.close()
