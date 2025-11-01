"""Tests for IVD email digest builder."""

from datetime import date, datetime
from pathlib import Path

import pytest

from src.ivd_monitor.database import IVDDatabase
from src.ivd_monitor.email_builder import DigestConfig, EmailDigestBuilder


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "ivd_monitor.db"


@pytest.fixture
def ivd_db(db_path):
    db = IVDDatabase(db_path=str(db_path))
    db.initialize()
    return db


@pytest.fixture
def sample_records(ivd_db):
    """Create sample records for testing digest generation."""
    test_date = "2024-01-15"

    records = [
        {
            "source": "NMPA Website",
            "url": "https://example.com/nhsa-policy-1",
            "category": "nhsa_policy",
            "companies": ["华大基因", "Huada Gene"],
            "title": "医保局发布新政策通知",
            "summary": "新医保政策将于下月实施，涉及体外诊断试剂的报销标准调整。",
            "publish_date": f"{test_date}T08:00:00Z",
        },
        {
            "source": "Shanghai Securities News",
            "url": "https://example.com/financial-1",
            "category": "financial_reports",
            "companies": ["迈瑞医疗", "Mindray"],
            "title": "迈瑞医疗发布2023年度财报",
            "summary": "公司实现营业收入增长15%，净利润创历史新高。",
            "publish_date": f"{test_date}T09:30:00Z",
        },
        {
            "source": "China Business Journal",
            "url": "https://example.com/financial-2",
            "category": "financial_reports",
            "companies": ["迈瑞医疗", "Mindray"],
            "title": "迈瑞医疗季度业绩超预期",
            "summary": "第四季度业绩表现强劲，超市场预期。",
            "publish_date": f"{test_date}T10:00:00Z",
        },
        {
            "source": "Industry News",
            "url": "https://example.com/product-launch-1",
            "category": "product_launches",
            "companies": ["安图生物", "Autobio"],
            "title": "安图生物新产品获NMPA批准",
            "summary": "公司最新研发的COVID-19检测试剂获得注册证。",
            "publish_date": f"{test_date}T11:00:00Z",
        },
        {
            "source": "Government Portal",
            "url": "https://example.com/bidding-1",
            "category": "bidding_tendering",
            "companies": ["达安基因", "Da An Gene"],
            "title": "广东省医疗器械集中采购公告",
            "summary": "本次集采涉及多个IVD产品类别。",
            "publish_date": f"{test_date}T12:00:00Z",
        },
        {
            "source": "NHC Website",
            "url": "https://example.com/nhc-policy-1",
            "category": "nhc_policy",
            "companies": [],
            "title": "卫健委印发医疗质量管理办法",
            "summary": "新办法将加强对体外诊断试剂使用的质量控制。",
            "publish_date": f"{test_date}T13:00:00Z",
        },
        {
            "source": "Media Outlet",
            "url": "https://example.com/industry-1",
            "category": "industry_media",
            "companies": ["华大基因", "Huada Gene"],
            "title": "IVD行业市场分析报告",
            "summary": "2024年IVD市场预计保持稳定增长。",
            "publish_date": f"{test_date}T14:00:00Z",
        },
    ]

    for record_data in records:
        ivd_db.insert_record(**record_data)

    return records


@pytest.fixture
def digest_config():
    return DigestConfig(
        subject_format="Test Digest - {date}",
        intro_text="This is a test digest for validation.",
        default_recipients=["test@example.com"],
    )


@pytest.fixture
def email_builder(ivd_db, digest_config):
    return EmailDigestBuilder(db=ivd_db, config=digest_config)


def test_digest_config_from_env(monkeypatch):
    """Test loading configuration from environment variables."""
    monkeypatch.setenv("IVD_DIGEST_SUBJECT_FORMAT", "Custom Subject - {date}")
    monkeypatch.setenv("IVD_DIGEST_INTRO_TEXT", "Custom intro text")
    monkeypatch.setenv("IVD_DIGEST_RECIPIENTS", "user1@example.com,user2@example.com")

    config = DigestConfig.from_env()

    assert config.subject_format == "Custom Subject - {date}"
    assert config.intro_text == "Custom intro text"
    assert config.default_recipients == ["user1@example.com", "user2@example.com"]


def test_build_digest_structure(email_builder, sample_records):
    """Test that digest data is properly structured."""
    digest_data = email_builder.build_digest("2024-01-15")

    assert digest_data["digest_date"] == "2024-01-15"
    assert digest_data["total_count"] == len(sample_records)
    assert digest_data["category_count"] == 6
    assert digest_data["company_count"] >= 5
    assert "categories" in digest_data


def test_category_ordering(email_builder, sample_records):
    """Test that categories appear in the correct priority order."""
    digest_data = email_builder.build_digest("2024-01-15")
    categories = list(digest_data["categories"].keys())

    expected_order = [
        "nhsa_policy",
        "nhc_policy",
        "financial_reports",
        "product_launches",
        "bidding_tendering",
        "industry_media",
    ]

    for i, category in enumerate(expected_order):
        if category in categories:
            assert categories.index(category) == i, (
                f"Category {category} not in expected position"
            )


def test_records_grouped_by_company(email_builder, sample_records):
    """Test that records are properly grouped by company within categories."""
    digest_data = email_builder.build_digest("2024-01-15")

    financial_category = digest_data["categories"]["financial_reports"]
    assert "迈瑞医疗" in financial_category["records_by_company"]

    mindray_records = financial_category["records_by_company"]["迈瑞医疗"]
    assert len(mindray_records) == 2

    titles = [r["title"] for r in mindray_records]
    assert "迈瑞医疗发布2023年度财报" in titles
    assert "迈瑞医疗季度业绩超预期" in titles


def test_deduplication(ivd_db, email_builder):
    """Test that duplicate records are not repeated in the digest."""
    test_date = "2024-01-20"

    record_data = {
        "source": "Test Source",
        "url": "https://example.com/duplicate-test",
        "category": "financial_reports",
        "companies": ["Test Company"],
        "title": "Test Record",
        "summary": "Test summary",
        "publish_date": f"{test_date}T10:00:00Z",
    }

    ivd_db.insert_record(**record_data)
    ivd_db.insert_record(**record_data)

    digest_data = email_builder.build_digest(test_date)

    assert digest_data["total_count"] == 1

    financial_category = digest_data["categories"]["financial_reports"]
    test_company_records = financial_category["records_by_company"]["Test Company"]
    assert len(test_company_records) == 1


def test_chinese_character_support(email_builder, sample_records):
    """Test that Chinese characters are properly handled in the digest."""
    digest_data = email_builder.build_digest("2024-01-15")
    html_content = email_builder.render_html(digest_data)
    text_content = email_builder.render_text(digest_data)

    chinese_terms = [
        "华大基因",
        "迈瑞医疗",
        "医保局",
        "卫健委",
        "财报",
        "招标采购",
    ]

    for term in chinese_terms:
        assert term in html_content, f"Chinese term '{term}' not found in HTML"
        assert term in text_content, f"Chinese term '{term}' not found in text"


def test_html_rendering(email_builder, sample_records):
    """Test HTML rendering produces valid output."""
    digest_data = email_builder.build_digest("2024-01-15")
    html_content = email_builder.render_html(digest_data)

    assert "<!DOCTYPE html>" in html_content
    assert 'charset="UTF-8"' in html_content
    assert "IVD Monitor Daily Digest" in html_content
    assert "2024-01-15" in html_content

    assert "Financial Reports 财报资讯" in html_content
    assert "NHSA Policy 医保政策" in html_content

    assert "迈瑞医疗" in html_content
    assert "华大基因" in html_content

    assert 'href="https://example.com/financial-1"' in html_content


def test_text_rendering(email_builder, sample_records):
    """Test plaintext rendering produces valid output."""
    digest_data = email_builder.build_digest("2024-01-15")
    text_content = email_builder.render_text(digest_data)

    assert "IVD Monitor Daily Digest - 2024-01-15" in text_content
    assert "Total Records :" in text_content
    assert "Financial Reports 财报资讯" in text_content
    assert "NHSA Policy 医保政策" in text_content

    assert "迈瑞医疗" in text_content
    assert "华大基因" in text_content

    assert "https://example.com/financial-1" in text_content


def test_category_display_names(email_builder, sample_records):
    """Test that category display names include both English and Chinese."""
    digest_data = email_builder.build_digest("2024-01-15")

    financial_category = digest_data["categories"]["financial_reports"]
    assert "财报资讯" in financial_category["display_name"]

    nhsa_category = digest_data["categories"]["nhsa_policy"]
    assert "医保政策" in nhsa_category["display_name"]


def test_failed_sources_metadata(email_builder, sample_records):
    """Test that failed sources are included in metadata."""
    failed = ["RSS Feed A", "RSS Feed B"]
    digest_data = email_builder.build_digest("2024-01-15", failed_sources=failed)

    assert digest_data["failed_sources"] == failed

    html_content = email_builder.render_html(digest_data)
    assert "Failed Sources:" in html_content
    assert "RSS Feed A" in html_content


def test_csv_export(email_builder, sample_records):
    """Test CSV export functionality."""
    csv_content = email_builder.export_to_csv("2024-01-15")

    assert "id,category,companies,title,summary,source,publish_date,url" in csv_content

    assert "华大基因;Huada Gene" in csv_content
    assert "迈瑞医疗;Mindray" in csv_content

    assert "医保局发布新政策通知" in csv_content
    assert "nhsa_policy" in csv_content


def test_render_digest_returns_both_formats(email_builder, sample_records):
    """Test that render_digest returns both HTML and text."""
    html_content, text_content = email_builder.render_digest("2024-01-15")

    assert "<!DOCTYPE html>" in html_content
    assert "IVD Monitor Daily Digest - 2024-01-15" in text_content

    assert "华大基因" in html_content
    assert "华大基因" in text_content


def test_empty_digest(email_builder):
    """Test digest generation with no records."""
    digest_data = email_builder.build_digest("2024-01-01")

    assert digest_data["total_count"] == 0
    assert digest_data["category_count"] == 0
    assert len(digest_data["categories"]) == 0

    html_content = email_builder.render_html(digest_data)
    text_content = email_builder.render_text(digest_data)

    assert "Total Records" in html_content
    assert "Total Records" in text_content


def test_uncategorized_companies(ivd_db, email_builder):
    """Test handling of records with no company associations."""
    test_date = "2024-01-25"

    ivd_db.insert_record(
        source="Test Source",
        url="https://example.com/no-company",
        category="industry_media",
        companies=[],
        title="Industry Update",
        summary="General industry news",
        publish_date=f"{test_date}T10:00:00Z",
    )

    digest_data = email_builder.build_digest(test_date)

    industry_category = digest_data["categories"]["industry_media"]
    assert "Uncategorized" in industry_category["records_by_company"]


def test_date_format_handling(email_builder, ivd_db):
    """Test that different date formats are handled correctly."""
    test_date = date(2024, 1, 30)

    ivd_db.insert_record(
        source="Test Source",
        url="https://example.com/date-test",
        category="financial_reports",
        companies=["Test Corp"],
        title="Date Test Record",
        summary="Testing date handling",
        publish_date=test_date,
    )

    digest_data = email_builder.build_digest(test_date)
    assert digest_data["total_count"] == 1
    assert digest_data["digest_date"] == "2024-01-30"

    digest_data_str = email_builder.build_digest("2024-01-30")
    assert digest_data_str["total_count"] == 1


def test_preview_digest_formats(email_builder, sample_records):
    """Test preview_digest with different output formats."""
    html_preview = email_builder.preview_digest("2024-01-15", output_format="html")
    assert "<!DOCTYPE html>" in html_preview

    text_preview = email_builder.preview_digest("2024-01-15", output_format="text")
    assert "IVD Monitor Daily Digest" in text_preview

    csv_preview = email_builder.preview_digest("2024-01-15", output_format="csv")
    assert "id,category,companies" in csv_preview


def test_subject_format_with_date(email_builder):
    """Test that subject line is formatted correctly with date."""
    digest_data = email_builder.build_digest("2024-01-15")
    assert digest_data["subject"] == "Test Digest - 2024-01-15"


def test_default_recipients_present(email_builder):
    """Test that default recipients from configuration are preserved."""
    digest_data = email_builder.build_digest("2024-01-15")
    assert digest_data["recipients"] == ["test@example.com"]


def test_generated_timestamp_present(email_builder, sample_records):
    """Test that generated timestamp is included."""
    digest_data = email_builder.build_digest("2024-01-15")
    assert "generated_at" in digest_data
    assert "UTC" in digest_data["generated_at"]


def test_record_count_per_category(email_builder, sample_records):
    """Test that record counts per category are accurate."""
    digest_data = email_builder.build_digest("2024-01-15")

    financial = digest_data["categories"]["financial_reports"]
    assert financial["count"] == 2

    nhsa = digest_data["categories"]["nhsa_policy"]
    assert nhsa["count"] == 1

    nhc = digest_data["categories"]["nhc_policy"]
    assert nhc["count"] == 1


def test_company_sorting_within_category(email_builder, ivd_db):
    """Test that companies are sorted alphabetically within each category."""
    test_date = "2024-02-01"

    companies = ["Zebra Medical", "Alpha Diagnostics", "Beta Biotech"]
    for company in companies:
        ivd_db.insert_record(
            source="Test Source",
            url=f"https://example.com/{company.replace(' ', '-')}",
            category="financial_reports",
            companies=[company],
            title=f"{company} Update",
            summary="Company update",
            publish_date=f"{test_date}T10:00:00Z",
        )

    digest_data = email_builder.build_digest(test_date)
    financial = digest_data["categories"]["financial_reports"]

    company_names = list(financial["records_by_company"].keys())
    assert company_names == sorted(company_names)
    assert company_names == ["Alpha Diagnostics", "Beta Biotech", "Zebra Medical"]


def test_multiple_companies_per_record(ivd_db, email_builder):
    """Test that records with multiple companies appear in all relevant groups."""
    test_date = "2024-02-05"

    ivd_db.insert_record(
        source="Test Source",
        url="https://example.com/multi-company",
        category="financial_reports",
        companies=["Company A", "Company B", "Company C"],
        title="Multi-Company Partnership",
        summary="Three companies announce partnership",
        publish_date=f"{test_date}T10:00:00Z",
    )

    digest_data = email_builder.build_digest(test_date)
    financial = digest_data["categories"]["financial_reports"]

    assert "Company A" in financial["records_by_company"]
    assert "Company B" in financial["records_by_company"]
    assert "Company C" in financial["records_by_company"]

    for company in ["Company A", "Company B", "Company C"]:
        records = financial["records_by_company"][company]
        assert len(records) == 1
        assert records[0]["title"] == "Multi-Company Partnership"
