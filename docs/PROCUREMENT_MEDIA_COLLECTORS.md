# Procurement and Media Collectors: Feature Overview

## Summary

This feature adds comprehensive data collection capabilities for Chinese government procurement portals and IVD industry media sources to the IVD monitor system. It enables automated gathering of procurement notices and industry news with configurable sources, regional metadata, and robust deduplication.

## Architecture

### Components Added

1. **Base Collector Framework** (`src/ivd_monitor/sources/base.py`)
   - Abstract base class for all collectors
   - HTTP client protocol and utilities
   - Rate limiting and retry logic
   - HTML parsing helpers
   - Standardized `CollectedRecord` output format

2. **Configuration System** (`src/ivd_monitor/sources/config.py`)
   - JSON-based source configuration
   - Decorator-based collector registration
   - Dynamic collector instantiation
   - Enable/disable functionality

3. **Procurement Collectors** (`src/ivd_monitor/sources/procurement/`)
   - `ConfigurableProcurementCollector`: Flexible collector supporting JSON and HTML
   - Handles national and provincial portals
   - Extracts titles, bid status, budget, publish dates, URLs
   - Regional metadata tagging

4. **Media Collectors** (`src/ivd_monitor/sources/media/`)
   - `RSSFeedCollector`: RSS/Atom feed parser
   - `IndustryMediaCollector`: HTML scraping with RSS fallback
   - Tagged with `industry_media` source_type

5. **HTTP Client** (`src/ivd_monitor/sources/http_client.py`)
   - Production-ready httpx-based client
   - Timeout and redirect handling

6. **Ingestion Script** (`scripts/ingest_procurement_media.py`)
   - CLI tool for running collectors
   - Automatic database ingestion
   - Logging and error reporting

## Configuration

### Default Sources (`config/ivd_sources.json`)

The initial deployment includes:

**Procurement Sources:**
- **China Government Procurement Network** (`cn_ccgp_procurement`)
  - Region: `CN` (National)
  - Mode: JSON API
  - Collects medical device procurement notices

- **Beijing Procurement Portal** (`cn_beijing_procurement`)
  - Region: `CN-11` (Beijing)
  - Mode: HTML scraping
  
- **Shanghai Procurement Portal** (`cn_shanghai_procurement`)
  - Region: `CN-31` (Shanghai)
  - Mode: JSON API

- **Guangdong Procurement Portal** (`cn_guangdong_procurement`)
  - Region: `CN-44` (Guangdong)
  - Mode: JSON API

**Media Sources:**
- **IVD News RSS Feed** (`ivd_news_rss`)
  - RSS feed collector
  - Source type: `industry_media`
  
- **Medical Device Innovation Platform** (`med_device_innovation_html`)
  - HTML scraping
  - Source type: `industry_media`

### Enabling/Disabling Sources

Simply edit `config/ivd_sources.json`:

```json
{
  "source_id": "cn_shanghai_procurement",
  "enabled": false
}
```

No code changes required; the collector will be skipped on the next run.

## Regional Metadata

Regional codes follow ISO 3166-2:CN:

- `CN` - National level
- `CN-11` - Beijing Municipality  
- `CN-31` - Shanghai Municipality
- `CN-44` - Guangdong Province

Records are automatically tagged with region metadata for filtering in reports:

```python
# Query Beijing procurement records
beijing_records = db.get_records_for_day(
    date.today(),
    category="Procurement",
    region="CN-11"
)
```

## Deduplication

Three levels of deduplication:

1. **Collection-time**: URL-based deduplication within a single collector run
2. **Database URL hash**: Prevents duplicate URLs across runs
3. **Database content hash**: Detects identical content from different URLs

## Usage

### Running Collectors

```bash
# Collect from all enabled sources
python scripts/ingest_procurement_media.py

# Collect from specific source
python scripts/ingest_procurement_media.py --source-id cn_beijing_procurement

# Custom configuration
python scripts/ingest_procurement_media.py --config /path/to/config.json
```

### Programmatic Usage

```python
from pathlib import Path
from src.ivd_monitor.database import IVDDatabase
from src.ivd_monitor.sources import (
    build_collectors_from_config,
    load_sources_configuration,
    HttpxClient,
)

db = IVDDatabase()
config = load_sources_configuration(Path("config/ivd_sources.json"))
http_client = HttpxClient()

collectors = build_collectors_from_config(config, http_client)

for collector in collectors:
    run_id = db.start_ingestion_run(source=collector.source_id)
    for record in collector.collect():
        db.insert_record(
            source=record.source,
            source_type=record.source_type,
            category=record.category,
            title=record.title,
            url=record.url,
            summary=record.summary,
            publish_date=record.publish_date,
            region=record.region,
            metadata=record.metadata,
            ingestion_run_id=run_id,
        )
    db.complete_ingestion_run(run_id)
```

## Testing

### Running Tests

```bash
# Run all IVD monitor tests
pytest tests/ivd_monitor/ -v

# Run specific test module
pytest tests/ivd_monitor/test_procurement_collectors.py -v
pytest tests/ivd_monitor/test_media_collectors.py -v
pytest tests/ivd_monitor/test_sources_configuration.py -v
```

### Test Coverage

Tests include:
- JSON and HTML parsing
- Deduplication across pages
- Field extraction with regex
- Date normalization
- URL resolution
- Error handling
- Configuration loading
- Disabled source behavior

### Mock Responses

Stored responses in `tests/data/`:
- `procurement/ccgp_page1.json` - Sample CCGP response
- `procurement/ccgp_page2.json` - Duplicate detection test
- `media/sample_rss.xml` - Sample RSS feed
- `media/industry_list.html` - Sample HTML article list

## Anti-Bot Considerations

### Rate Limiting

Default: 1 second between requests. Configurable per source:

```json
{
  "source_id": "cn_ccgp_procurement",
  "rate_limit_delay": 2.0
}
```

### User-Agent

Default User-Agent header mimics common browsers. For stricter portals, consider:
- User-Agent rotation
- Residential proxies
- Headless browser automation (Playwright/Selenium)

### CAPTCHA Handling

Some portals may implement CAPTCHA:
- Start with simple HTTP requests
- Increase rate limits if blocked
- Use browser automation for JavaScript-heavy sites
- Consider CAPTCHA-solving services for production (not included)

**Recommendation**: Monitor for HTTP 403/429 errors and adjust accordingly.

## Adding New Provincial Portals

### Quick Guide

1. **Identify portal characteristics**
   - JSON API or HTML?
   - Pagination mechanism?
   - Date format?
   - CSS selectors or JSON paths?

2. **Add configuration entry**
   
```json
{
  "source_id": "cn_jiangsu_procurement",
  "collector_type": "procurement",
  "enabled": true,
  "region": "CN-32",
  "extra_params": {
    "mode": "json",
    "list_url_template": "https://portal.gov.cn/api?page={page}",
    "pagination": {"start": 1, "pages": 3},
    "json_list_path": ["data", "items"],
    "fields": {
      "title": {"path": "title"},
      "url": {"path": "url"},
      "publish_date": {"path": "date", "date_format": "%Y-%m-%d"}
    },
    "base_url": "https://portal.gov.cn"
  }
}
```

3. **Test with mock response**

Create `tests/data/procurement/jiangsu.json` and test:

```python
def test_jiangsu_collector():
    mock_client = MockHttpClient({"jiangsu": SAMPLE_JSON})
    # ... test collector
```

4. **Enable in production**

Set `"enabled": true` and run the ingestion script.

See [docs/ivd_monitor_scrapers.md](./ivd_monitor_scrapers.md) for detailed instructions.

## Downstream Reporting

### Source Type Filtering

Records are tagged with `source_type`:
- `procurement` - Government procurement notices
- `industry_media` - Industry news and articles

```python
# Get all industry media records
conn = db._connect()
media_records = conn.execute(
    "SELECT * FROM records WHERE source_type = ?",
    ("industry_media",)
).fetchall()
```

### Digest Generation

Group records by source type for structured digests:

```python
# Pseudocode for daily digest
procurement_notices = filter(records, source_type="procurement")
media_articles = filter(records, source_type="industry_media")

digest = {
    "procurement": {
        "national": filter(procurement_notices, region="CN"),
        "beijing": filter(procurement_notices, region="CN-11"),
        "shanghai": filter(procurement_notices, region="CN-31"),
        "guangdong": filter(procurement_notices, region="CN-44"),
    },
    "industry_media": media_articles,
}
```

### Metadata Extraction

Procurement metadata includes:
- `bid_status` - Tender status (招标公告, 中标公告, etc.)
- `budget` - Budget amount if present
- `portal` - Source portal identifier

```python
# Query by bid status
conn = db._connect()
tender_notices = conn.execute(
    "SELECT * FROM records WHERE json_extract(metadata, '$.bid_status') = ?",
    ("招标公告",)
).fetchall()
```

## Troubleshooting

### No Records Collected

1. Verify source is enabled (`"enabled": true`)
2. Check URL accessibility (manually visit the URL)
3. Inspect response structure (JSON paths or selectors)
4. Review logs for errors

### Date Parsing Issues

- Verify `date_format` matches actual format
- Check timezone (default: `Asia/Shanghai`)
- Use `"optional": true` if dates aren't always present

### HTTP Timeouts

- Increase timeout: `--timeout 60.0`
- Check network connectivity
- Consider rate limiting on portal side

### Duplicate Detection Not Working

- Ensure URLs are normalized (scheme, trailing slashes)
- Check `base_url` configuration for relative URLs
- Review deduplication logic in tests

## Performance Considerations

- **Rate Limiting**: Respect portal rate limits to avoid blocking
- **Pagination**: Limit pages collected (`"pages": 3`) to balance freshness and load
- **Timeout**: Adjust per portal characteristics
- **Concurrency**: Current implementation is sequential; consider async for future optimization

## Future Enhancements

1. **Browser Automation**: Playwright/Selenium for JavaScript-heavy sites
2. **Proxy Rotation**: For high-volume or geo-restricted scraping
3. **Incremental Collection**: Track last collection timestamp
4. **Webhook Notifications**: Alert on failures or anomalies
5. **Monitoring Dashboard**: Web UI for collector status
6. **CAPTCHA Integration**: Automated CAPTCHA solving

## Documentation

- [IVD Monitor Database](./ivd_monitor.md) - Database schema and API
- [Scraper Configuration Guide](./ivd_monitor_scrapers.md) - Detailed configuration reference
- [Ingestion Script README](../scripts/README.md) - CLI usage and scheduling

## Dependencies

Added to `requirements.txt`:
- `httpx>=0.25.0,<1.0.0` - Modern HTTP client
- `beautifulsoup4>=4.12.0,<5.0.0` - HTML parsing
- `lxml>=4.9.0,<6.0.0` - XML/HTML parser backend

## Acceptance Criteria

✅ **Procurement collectors implemented**
- China Government Procurement Network (CCGP)
- Beijing, Shanghai, Guangdong provincial portals
- Pagination handling
- Regional metadata tagging

✅ **Parsing logic implemented**
- Notice titles, bid status, budget extraction
- Publish date normalization
- Canonical URL resolution
- Graceful HTML and JSON handling

✅ **Industry media collectors implemented**
- RSS feed collector
- HTML scraping collector
- Tagged with `industry_media` source_type

✅ **Configuration system implemented**
- `config/ivd_sources.json` for all sources
- Easy enable/disable without code changes
- Extensible for future sources

✅ **Unit tests with stored responses**
- Deduplication tests
- Field extraction accuracy tests
- Mock responses in `tests/data/`

✅ **Documentation provided**
- Anti-bot/CAPTCHA considerations documented
- Guide for adding new provincial URLs
- Regional metadata usage explained

✅ **Acceptance validation**
- Test runs produce structured records
- Correct categories and region tags
- Configuration toggles work without code edits

## Validation

Run the test suite:

```bash
pytest tests/ivd_monitor/ -v
```

Run a test ingestion:

```bash
python scripts/ingest_procurement_media.py --source-id cn_ccgp_procurement
```

Verify records in database:

```python
from src.ivd_monitor.database import IVDDatabase
db = IVDDatabase()
metrics = db.get_ingestion_metrics()
print(metrics)
```

## Contact

For questions or issues with the procurement and media collectors:
- Review the detailed documentation in `docs/ivd_monitor_scrapers.md`
- Check the test suite for examples
- Inspect configuration in `config/ivd_sources.json`
