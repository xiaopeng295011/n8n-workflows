"""Tests for IVD categorization functionality."""

import pytest

from src.ivd_monitor.categorization import CategoryClassifier, enrich_record_with_category, enrich_records


@pytest.fixture
def classifier():
    """Create a CategoryClassifier instance for testing."""
    return CategoryClassifier()


def test_financial_report_categorization(classifier):
    """Test categorization of financial reports."""
    category = classifier.categorize(
        source="cninfo",
        title="迈瑞医疗2023年第三季度财报发布",
        summary="公司营收增长25%，净利润增长30%",
    )
    assert category == CategoryClassifier.CATEGORY_FINANCIAL


def test_product_launch_categorization(classifier):
    """Test categorization of product launches."""
    category = classifier.categorize(
        source="generic_news",
        title="新型化学发光免疫诊断系统获批上市",
        summary="该产品获得NMPA批准，将于下月正式发布",
    )
    assert category == CategoryClassifier.CATEGORY_PRODUCT_LAUNCH


def test_bidding_categorization(classifier):
    """Test categorization of bidding/tendering content."""
    category = classifier.categorize(
        source="bidding_platform",
        title="某省医疗器械集中采购招标公告",
        summary="本次招标涉及体外诊断试剂多个品类",
    )
    assert category == CategoryClassifier.CATEGORY_BIDDING


def test_nhsa_policy_categorization(classifier):
    """Test categorization of NHSA policy content."""
    category = classifier.categorize(
        source="nhsa",
        title="国家医保局发布新版医保目录",
        summary="多项诊断项目纳入医保支付范围",
    )
    assert category == CategoryClassifier.CATEGORY_NHSA_POLICY


def test_nhc_policy_categorization(classifier):
    """Test categorization of NHC policy content."""
    category = classifier.categorize(
        source="nhc_official",
        title="国家卫健委发布最新临床诊疗指南",
        summary="更新了多项疾病的诊疗规范和标准",
    )
    assert category == CategoryClassifier.CATEGORY_NHC_POLICY


def test_industry_media_categorization(classifier):
    """Test categorization of industry media content."""
    category = classifier.categorize(
        source="medtech_media",
        title="2023年IVD行业市场分析报告",
        summary="深度解析当前行业发展趋势和未来方向",
    )
    assert category == CategoryClassifier.CATEGORY_INDUSTRY_MEDIA


def test_source_based_categorization(classifier):
    """Test that source-based rules take precedence."""
    category = classifier.categorize(
        source="eastmoney",  # Financial source
        title="某公司产品获批上市",  # Product launch keywords
    )
    # Source rule should take precedence
    assert category == CategoryClassifier.CATEGORY_FINANCIAL


def test_keyword_based_categorization(classifier):
    """Test categorization based on keywords when source is generic."""
    category = classifier.categorize(
        source="generic_news",
        title="迈瑞医疗公布2023年年报",
        content="公司年度财务报告显示，营收和利润双增长",
    )
    assert category == CategoryClassifier.CATEGORY_FINANCIAL


def test_chinese_language_keywords(classifier):
    """Test categorization with Chinese language keywords."""
    category = classifier.categorize(
        source="news_source",
        title="最新招标公告",
        summary="医疗器械集中采购项目开始招标",
    )
    assert category == CategoryClassifier.CATEGORY_BIDDING


def test_mixed_language_categorization(classifier):
    """Test categorization with mixed Chinese-English content."""
    category = classifier.categorize(
        source="industry_site",
        title="Product Launch: New FDA approved diagnostic system",
        summary="The product received FDA clearance and NMPA approval",
    )
    assert category == CategoryClassifier.CATEGORY_PRODUCT_LAUNCH


def test_metadata_override_category(classifier):
    """Test that explicit metadata category is respected."""
    metadata = {"category": CategoryClassifier.CATEGORY_FINANCIAL}
    category = classifier.categorize(
        source="unknown_source",
        title="Generic title with no keywords",
        metadata=metadata,
    )
    assert category == CategoryClassifier.CATEGORY_FINANCIAL


def test_default_to_industry_media(classifier):
    """Test that unknown content defaults to industry media."""
    category = classifier.categorize(
        source="unknown_source",
        title="Some generic title without specific keywords",
    )
    assert category == CategoryClassifier.CATEGORY_INDUSTRY_MEDIA


def test_url_based_categorization(classifier):
    """Test categorization can use URL as additional signal."""
    category = classifier.categorize(
        source="generic_source",
        title="Important announcement",
        url="https://www.cninfo.com.cn/report/2023",
    )
    # URL contains cninfo which is a financial source
    assert category == CategoryClassifier.CATEGORY_FINANCIAL


def test_title_weighted_over_content(classifier):
    """Test that title keywords are weighted more than content."""
    category = classifier.categorize(
        source="news",
        title="产品获批上市 新品推出",  # Product launch keywords
        content="财报 年报 业绩 营收 利润 ",  # Fewer financial keywords
    )
    # Title should be weighted more heavily
    assert category == CategoryClassifier.CATEGORY_PRODUCT_LAUNCH


def test_enrich_record_function(classifier):
    """Test the enrich_record_with_category function."""
    record = {
        "source": "cninfo",
        "title": "公司财报发布",
        "summary": "年度业绩报告",
    }
    enriched = enrich_record_with_category(record, classifier=classifier)
    assert "category" in enriched
    assert enriched["category"] == CategoryClassifier.CATEGORY_FINANCIAL


def test_enrich_records_batch(classifier):
    """Test enriching multiple records at once."""
    records = [
        {
            "source": "cninfo",
            "title": "财报发布",
            "content_html": "<p>业绩报告</p>",
        },
        {
            "source": "generic",
            "title": "产品获批上市",
            "summary": "新品获得NMPA批准",
            "content_html": "<p>新品上市</p>",
        },
    ]
    enriched = enrich_records(records, category_classifier=classifier)
    assert len(enriched) == 2
    assert enriched[0]["category"] == CategoryClassifier.CATEGORY_FINANCIAL
    assert enriched[1]["category"] == CategoryClassifier.CATEGORY_PRODUCT_LAUNCH


def test_custom_categorization_rules():
    """Test adding custom categorization rules."""
    custom_rules = {
        "sources": {
            "custom_source": CategoryClassifier.CATEGORY_FINANCIAL,
        },
        "keywords": {
            CategoryClassifier.CATEGORY_PRODUCT_LAUNCH: [r"特殊关键词"],
        },
    }
    classifier = CategoryClassifier(custom_rules=custom_rules)

    category = classifier.categorize(source="custom_source", title="Test")
    assert category == CategoryClassifier.CATEGORY_FINANCIAL

    category2 = classifier.categorize(
        source="generic", title="包含特殊关键词的标题"
    )
    assert category2 == CategoryClassifier.CATEGORY_PRODUCT_LAUNCH


def test_all_category_constants_valid(classifier):
    """Test that all category constants are valid."""
    for category in CategoryClassifier.ALL_CATEGORIES:
        assert isinstance(category, str)
        assert len(category) > 0


def test_category_display_names(classifier):
    """Test getting display names for categories."""
    en_name = classifier.get_category_display_name(
        CategoryClassifier.CATEGORY_FINANCIAL, language="en"
    )
    assert en_name == "Financial Reports"

    zh_name = classifier.get_category_display_name(
        CategoryClassifier.CATEGORY_FINANCIAL, language="zh"
    )
    assert zh_name == "财报资讯"


def test_multiple_keyword_matches(classifier):
    """Test that multiple matching keywords improve confidence."""
    # Content with many financial keywords
    category = classifier.categorize(
        source="generic",
        title="Important announcement",
        content="公司发布年度财报，营收增长，净利润上升，业绩优异",
    )
    assert category == CategoryClassifier.CATEGORY_FINANCIAL


def test_bidding_chinese_keywords(classifier):
    """Test Chinese bidding/tendering keywords."""
    category = classifier.categorize(
        source="generic",
        title="中标结果公示",
        summary="某医院医疗设备采购项目中标公告",
    )
    assert category == CategoryClassifier.CATEGORY_BIDDING


def test_medical_insurance_categorization(classifier):
    """Test medical insurance related content categorization."""
    category = classifier.categorize(
        source="policy_source",
        title="医保支付政策调整",
        content="医疗保障局发布新的医保目录调整方案",
    )
    assert category == CategoryClassifier.CATEGORY_NHSA_POLICY


def test_drg_dip_keywords(classifier):
    """Test DRG/DIP medical payment keywords."""
    category = classifier.categorize(
        source="generic",
        title="DRG付费改革政策解读",
    )
    assert category == CategoryClassifier.CATEGORY_NHSA_POLICY


def test_clinical_guideline_categorization(classifier):
    """Test clinical guideline categorization."""
    category = classifier.categorize(
        source="generic",
        title="最新临床诊疗指南发布",
        summary="卫生健康委发布疾病诊疗规范",
    )
    assert category == CategoryClassifier.CATEGORY_NHC_POLICY


def test_market_analysis_categorization(classifier):
    """Test market analysis content categorization."""
    category = classifier.categorize(
        source="analysis_platform",
        title="2023年IVD市场趋势分析",
        content="专家深度解读行业发展动态",
    )
    assert category == CategoryClassifier.CATEGORY_INDUSTRY_MEDIA


def test_enrich_records_includes_companies():
    """Test that enrich_records adds both companies and categories."""
    records = [
        {
            "source": "cninfo",
            "title": "迈瑞医疗财报",
            "content_html": "<p>业绩增长</p>",
        }
    ]
    enriched = enrich_records(records)
    assert len(enriched) == 1
    assert "category" in enriched[0]
    assert "companies" in enriched[0]
    assert "迈瑞医疗" in enriched[0]["companies"]
    assert enriched[0]["category"] == CategoryClassifier.CATEGORY_FINANCIAL
