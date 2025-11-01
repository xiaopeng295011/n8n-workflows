# IVD Company Matching and Categorization

This document describes the company matching and categorization system for the IVD Monitor, including how to maintain the company dataset and extend categorization rules.

## Overview

The enrichment pipeline adds two critical pieces of metadata to ingested records before they're persisted in the database:

1. **Companies** - A JSON array of canonical company names detected in the content
2. **Category** - A normalized category string for digest grouping

Both systems support Chinese and English text, fuzzy matching, aliases, and configurable overrides.

## Company Matching

### Dataset Location

The company dataset is stored in `config/ivd_companies.json`. This JSON file contains structured information about IVD companies:

```json
{
  "companies": [
    {
      "name": "迈瑞医疗",
      "english_name": "Mindray Medical",
      "stock_code": "300760.SZ",
      "aliases": ["迈瑞", "Mindray", "深圳迈瑞"],
      "keywords": ["生化分析", "血液分析", "免疫分析"]
    }
  ]
}
```

### Fields

- **name** (required): Canonical Chinese company name
- **english_name** (optional): Official English name
- **stock_code** (optional): Stock exchange ticker
- **aliases** (optional): Alternative names, abbreviations, or common references
- **keywords** (optional): Product/technology keywords associated with the company

### Matching Strategies

The `CompanyMatcher` class uses multiple strategies in priority order:

1. **Manual Overrides** - Exact pattern matches from configuration or record metadata
2. **Metadata Hints** - Explicit company lists in record metadata
3. **Exact Matches** - Substring matching against canonical names
4. **Alias Matches** - Substring matching against configured aliases
5. **Keyword Associations** - Multiple keyword matches suggest a company (requires 2+ keywords to reduce false positives)
6. **Fuzzy Matching** - Uses `rapidfuzz` for typo tolerance and partial matches

### Usage

```python
from src.ivd_monitor import CompanyMatcher

# Create matcher with default configuration
matcher = CompanyMatcher()

# Match companies in text
companies = matcher.match_companies(
    text="迈瑞医疗今日发布新产品",
    title="新品发布会",
    summary="迈瑞推出创新诊断设备"
)
# Returns: ["迈瑞医疗"]

# With custom thresholds and blacklist
matcher = CompanyMatcher(
    match_threshold=90,
    partial_threshold=85,
    blacklist=["测试公司", "示例企业"]
)

# Get full company info
info = matcher.get_company_info("迈瑞医疗")
# Returns: {"name": "迈瑞医疗", "english_name": "Mindray Medical", ...}
```

### Record Metadata Overrides

You can override matching behavior per-record using metadata:

```python
record = {
    "title": "Product announcement",
    "content_html": "<p>Content</p>",
    "metadata": {
        # Force specific companies
        "companies_override": ["迈瑞医疗", "安图生物"],
        
        # Add hints (included if recognized)
        "company_hints": ["华大基因"],
        
        # Pattern-based overrides
        "company_overrides": {
            "特殊简称": "迈瑞医疗"
        },
        
        # Blacklist specific companies
        "company_blacklist": ["不相关公司"],
        
        # Blacklist text patterns
        "company_blacklist_terms": ["测试", "示例"]
    }
}
```

### Adding New Companies

To add a new company to the dataset:

1. Open `config/ivd_companies.json`
2. Add a new entry to the `companies` array:

```json
{
  "name": "新公司名称",
  "english_name": "New Company Name",
  "stock_code": "123456.SH",
  "aliases": ["别名1", "别名2", "Alias1"],
  "keywords": ["关键词1", "关键词2", "keyword1"]
}
```

3. Test your changes:

```bash
python -m pytest tests/test_ivd_company_matching.py -v
```

4. Commit the changes with a clear description

### Guidelines for Company Entries

- **Name**: Use the most official Chinese name
- **English Name**: Use the official English corporate name
- **Stock Code**: Include exchange suffix (.SZ for Shenzhen, .SH for Shanghai, .HK for Hong Kong)
- **Aliases**: Include common abbreviations, alternative names, and English variants
- **Keywords**: Focus on distinctive products or technologies, not generic terms
- **Avoid Generic Terms**: Don't use keywords that apply to many companies (e.g., "医疗器械", "IVD")

## Categorization

### Categories

The system supports six predefined categories:

1. **financial_reports** - Financial results, earnings, revenue reports
2. **product_launches** - New product announcements, approvals, launches
3. **bidding_tendering** - Government procurement, tenders, contract awards
4. **nhsa_policy** - National Healthcare Security Administration policies (医保局)
5. **nhc_policy** - National Health Commission policies (卫健委)
6. **industry_media** - General industry news, analysis, commentary

### Classification Rules

The `CategoryClassifier` uses two types of rules:

#### Source-Based Rules

Maps source identifiers to categories (highest priority):

```python
"cninfo" -> financial_reports
"医保局" -> nhsa_policy
"招标" -> bidding_tendering
```

#### Keyword-Based Rules

Regex patterns matched against title/summary/content:

```python
financial_reports: r"财报|年报|季报|业绩|营收"
product_launches: r"上市|新品|获批|NMPA|FDA"
bidding_tendering: r"招标|中标|采购|集采"
```

### Usage

```python
from src.ivd_monitor import CategoryClassifier

classifier = CategoryClassifier()

category = classifier.categorize(
    source="cninfo",
    title="迈瑞医疗2023年第三季度财报",
    summary="业绩增长25%"
)
# Returns: "financial_reports"

# Get display name
display = classifier.get_category_display_name(category, language="zh")
# Returns: "财报资讯"
```

### Adding Custom Rules

```python
custom_rules = {
    "sources": {
        "my_custom_source": CategoryClassifier.CATEGORY_FINANCIAL
    },
    "keywords": {
        CategoryClassifier.CATEGORY_PRODUCT_LAUNCH: [
            r"特殊关键词|special keyword"
        ]
    }
}

classifier = CategoryClassifier(custom_rules=custom_rules)
```

### Metadata Overrides

Force a specific category per-record:

```python
record = {
    "source": "generic",
    "title": "Title",
    "metadata": {
        "category": "financial_reports"  # or "财报"
    }
}
```

## Integration with Database

### Before Insertion

Enrich records before calling `insert_record()`:

```python
from src.ivd_monitor import IVDDatabase, CompanyMatcher, CategoryClassifier, enrich_records

db = IVDDatabase()
matcher = CompanyMatcher()
classifier = CategoryClassifier()

raw_records = [
    {
        "source": "cninfo",
        "url": "https://example.com/report",
        "title": "迈瑞医疗财报",
        "summary": "业绩增长",
        "content_html": "<p>详细内容</p>",
        "publish_date": "2023-11-01T08:00:00Z"
    }
]

# Enrich with companies and categories
enriched = enrich_records(raw_records, company_matcher=matcher, category_classifier=classifier)

# Insert enriched records
for record in enriched:
    db.insert_record(
        source=record["source"],
        url=record["url"],
        category=record["category"],
        companies=record["companies"],
        title=record["title"],
        summary=record["summary"],
        content_html=record["content_html"],
        publish_date=record["publish_date"]
    )
```

### Querying Enriched Data

```python
# Query by company
mindray_records = db.get_records_by_company("迈瑞医疗")

# Query by category
financial_records = db.get_records_by_category("financial_reports")

# Combined filters
records = db.get_records_by_company(
    "迈瑞医疗",
    categories=["financial_reports", "product_launches"],
    start_date="2023-11-01",
    end_date="2023-11-30"
)
```

## Testing

### Running Tests

```bash
# Company matching tests
python -m pytest tests/test_ivd_company_matching.py -v

# Categorization tests
python -m pytest tests/test_ivd_categorization.py -v

# Integration tests
python -m pytest tests/test_ivd_enrichment_integration.py -v

# All enrichment tests
python -m pytest tests/test_ivd_*.py -v
```

### Test Coverage

The test suite covers:

- ✅ Exact Chinese company matching
- ✅ Exact English company matching
- ✅ Alias resolution
- ✅ Multi-company detection
- ✅ Keyword-based matching
- ✅ Fuzzy matching with typos
- ✅ Mixed language content
- ✅ Blacklist filtering
- ✅ Manual overrides
- ✅ Category classification (all 6 categories)
- ✅ Source-based categorization
- ✅ Keyword-based categorization
- ✅ Chinese language support
- ✅ Edge cases (no companies, empty text, etc.)
- ✅ Database persistence
- ✅ Query functionality

## Performance Considerations

### Company Matching

- The matcher loads the company dataset once on initialization
- Exact and alias matching is O(n) where n = number of companies
- Fuzzy matching is more expensive; adjust thresholds to balance accuracy vs. speed
- Consider caching matcher instances for high-volume scenarios

### Categorization

- Source-based rules are fastest (simple dictionary lookup)
- Keyword-based rules use regex matching (moderate cost)
- Title and summary are weighted more heavily than content

## Maintenance Workflow

### Regular Updates

1. **Monitor False Positives/Negatives**: Review enriched records periodically
2. **Add New Companies**: When new IVD companies emerge or get listed
3. **Update Aliases**: Add common abbreviations you see in real content
4. **Refine Keywords**: Add distinctive product terms, remove generic ones
5. **Adjust Thresholds**: Fine-tune matching thresholds based on observed performance

### Version Control

All company dataset changes should be:

- Committed with clear descriptions
- Tested before merging
- Documented in commit messages (e.g., "Add 3 new companies", "Update aliases for 迈瑞医疗")

### Contribution Guidelines

When contributing company data:

1. Verify the company is relevant to IVD (in vitro diagnostics)
2. Use official company names and stock codes
3. Test that aliases don't create false positives
4. Ensure keywords are distinctive (not generic industry terms)
5. Add at least one test case for significant changes

## Troubleshooting

### Company Not Detected

1. Check if company is in `config/ivd_companies.json`
2. Verify the exact spelling in your content
3. Try adding the variant as an alias
4. Check if it's being filtered by blacklist
5. Lower fuzzy matching thresholds temporarily to debug

### False Positive Matches

1. Add problematic terms to blacklist
2. Use per-record `company_blacklist` in metadata
3. Increase keyword threshold (requires more keywords to match)
4. Remove overly generic keywords from company config

### Wrong Category Assigned

1. Check if source matches a source rule (they take precedence)
2. Verify keyword patterns in categorization rules
3. Add source to appropriate source rule list
4. Use `category_override` in metadata for specific records

### Performance Issues

1. Cache matcher/classifier instances
2. Increase fuzzy matching thresholds
3. Reduce number of fuzzy matching attempts
4. Process records in batches instead of one-by-one

## API Reference

See inline documentation in:

- `src/ivd_monitor/company_matching.py` - `CompanyMatcher` class and helper functions
- `src/ivd_monitor/categorization.py` - `CategoryClassifier` class and helper functions
- `src/ivd_monitor/__init__.py` - Public API exports

All public APIs include type hints and docstrings for IDE integration.
