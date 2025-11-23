# IVD Monitor: Procurement and Media Scrapers

## Overview

The IVD Monitor includes configurable scrapers for collecting procurement notices from Chinese government portals and industry media articles from IVD-related news sources. This document describes the architecture, configuration, and extension points for these collectors.

## Architecture

### Components

1. **Base Collector (`src/ivd_monitor/sources/base.py`)**
   - Abstract base class for all collectors
   - Provides HTTP client protocol, rate limiting, HTML parsing utilities
   - Defines `CollectedRecord` structure for normalized output

2. **Configuration System (`src/ivd_monitor/sources/config.py`)**
   - `SourceConfig`: Individual source configuration
   - `SourcesConfiguration`: Complete configuration for all sources
   - Decorator-based collector registry
   - Configuration loading from JSON files

3. **Procurement Collectors (`src/ivd_monitor/sources/procurement/`)**
   - `ConfigurableProcurementCollector`: Flexible collector supporting both JSON and HTML scraping
   - Handles pagination, field extraction via CSS selectors or JSON paths, and regional metadata

4. **Media Collectors (`src/ivd_monitor/sources/media/`)**
   - `RSSFeedCollector`: RSS/Atom feed parser
   - `IndustryMediaCollector`: Supports both RSS and HTML scraping modes

5. **HTTP Client (`src/ivd_monitor/sources/http_client.py`)**
   - `HttpxClient`: Production HTTP client using httpx library
   - Supports timeouts, redirects, custom headers

## Configuration

### Configuration File Structure

The configuration file is located at `config/ivd_sources.json` and follows this structure:

```json
{
  "sources": [
    {
      "source_id": "unique_identifier",
      "collector_type": "procurement|rss_feed|industry_media",
      "enabled": true,
      "region": "CN|CN-11|CN-31|CN-44",
      "category": "Procurement|Industry Media",
      "rate_limit_delay": 1.0,
      "extra_params": {
        // Collector-specific parameters
      }
    }
  ]
}
```

### Procurement Collector Parameters

#### JSON Mode

```json
{
  "source_id": "cn_ccgp_procurement",
  "collector_type": "procurement",
  "enabled": true,
  "region": "CN",
  "extra_params": {
    "mode": "json",
    "list_url_template": "https://api.example.com/notices?page={page}",
    "pagination": {
      "start": 1,
      "pages": 3
    },
    "json_list_path": ["data", "items"],
    "fields": {
      "title": {"path": "title"},
      "url": {"path": "url"},
      "publish_date": {
        "path": "publishDate",
        "date_format": "%Y-%m-%d %H:%M:%S"
      },
      "summary": {"path": "brief", "optional": true},
      "status": {"path": "bidStatus", "optional": true},
      "budget": {"path": "budgetAmount", "optional": true}
    },
    "base_url": "https://example.com"
  }
}
```

#### HTML Mode

```json
{
  "source_id": "cn_beijing_procurement",
  "collector_type": "procurement",
  "enabled": true,
  "region": "CN-11",
  "extra_params": {
    "mode": "html",
    "list_url_template": "https://example.com/notices",
    "pagination": {
      "start": 1,
      "pages": 2,
      "type": "query",
      "param": "page"
    },
    "fields": {
      "item_selector": {"selector": "ul.notices > li"},
      "title": {"selector": "a.title"},
      "url": {"selector": "a.title", "attr": "href"},
      "publish_date": {
        "selector": "span.date",
        "date_format": "%Y-%m-%d"
      },
      "status": {"selector": "span.status", "optional": true}
    },
    "base_url": "https://example.com"
  }
}
```

### RSS Feed Collector Parameters

```json
{
  "source_id": "ivd_news_rss",
  "collector_type": "rss_feed",
  "enabled": true,
  "region": "CN",
  "extra_params": {
    "feed_url": "https://www.ivdnews.cn/feed",
    "category": "Industry Media",
    "timezone": "Asia/Shanghai",
    "base_url": "https://www.ivdnews.cn"
  }
}
```

### Industry Media Collector Parameters

```json
{
  "source_id": "med_device_html",
  "collector_type": "industry_media",
  "enabled": true,
  "region": "CN",
  "extra_params": {
    "mode": "html",
    "list_url": "https://www.example.com/articles",
    "item_selector": "div.article",
    "title_selector": "h2 a",
    "url_selector": "h2 a",
    "summary_selector": "p.summary",
    "date_selector": "time",
    "date_format": "%Y-%m-%d",
    "base_url": "https://www.example.com"
  }
}
```

## Field Extraction

### JSON Path Extraction

Use dot-separated paths to navigate JSON structures:

```json
{
  "title": {"path": "data.notice.title"},
  "url": {"path": "data.notice.link"}
}
```

### HTML Selector Extraction

Use CSS selectors to extract data from HTML:

```json
{
  "title": {"selector": "div.notice h2 a"},
  "url": {"selector": "div.notice h2 a", "attr": "href"},
  "date": {"selector": "span.publish-date"}
}
```

### Regex Extraction

Use regex patterns to extract specific values:

```json
{
  "budget": {
    "path": "description",
    "regex": "预算[：:]\\s*(\\d+万元)",
    "optional": true
  }
}
```

## Regional Metadata

Regional codes follow ISO 3166-2:CN standard:

- `CN` - National level
- `CN-11` - Beijing Municipality
- `CN-31` - Shanghai Municipality
- `CN-44` - Guangdong Province

The `region` field is automatically populated in collected records and indexed for filtering in downstream reports.

## Deduplication

All collectors implement URL-based deduplication within a single collection run. The database layer (`IVDDatabase.insert_record`) provides additional deduplication:

1. **URL Hash**: Prevents duplicate URLs across runs
2. **Content Hash**: Detects identical content from different URLs
3. **Update Detection**: Updates existing records when content changes

## Anti-Bot and CAPTCHA Considerations

### Rate Limiting

Configure `rate_limit_delay` (in seconds) per source:

```json
{
  "source_id": "slow_portal",
  "rate_limit_delay": 3.0
}
```

### User-Agent Rotation

The base collector uses a default User-Agent header. For sites with strict bot detection:

1. Implement a custom HTTP client with User-Agent rotation
2. Use residential proxies if necessary (not included by default)

### CAPTCHA Handling

Some provincial portals may implement CAPTCHA challenges:

- **JavaScript Challenges**: May require headless browser (Playwright/Selenium)
- **Image CAPTCHA**: May require manual intervention or CAPTCHA-solving services
- **Cloudflare Protection**: May require additional headers or cookies

**Recommendation**: Start with simple HTTP requests. If blocked, consider:
1. Increasing rate limits
2. Adding realistic headers
3. Using browser automation for problematic sites

## Adding New Provincial URLs

### Step 1: Identify Portal Characteristics

- Determine if the portal uses JSON API or HTML rendering
- Identify pagination mechanism
- Note date format and timezone
- Find CSS selectors or JSON paths for key fields

### Step 2: Add Configuration Entry

Add a new source entry to `config/ivd_sources.json`:

```json
{
  "source_id": "cn_jiangsu_procurement",
  "collector_type": "procurement",
  "enabled": true,
  "region": "CN-32",
  "category": "Procurement",
  "extra_params": {
    "mode": "json",
    "list_url_template": "https://jiangsu-portal.gov.cn/api/notices?page={page}",
    "pagination": {"start": 1, "pages": 3},
    "json_list_path": ["data", "notices"],
    "fields": {
      "title": {"path": "title"},
      "url": {"path": "detailUrl"},
      "publish_date": {
        "path": "publishTime",
        "date_format": "%Y-%m-%d %H:%M:%S"
      }
    },
    "base_url": "https://jiangsu-portal.gov.cn"
  }
}
```

### Step 3: Test the Configuration

Create a test case with stored response:

```python
# tests/ivd_monitor/test_new_portal.py
def test_jiangsu_procurement_collector():
    mock_client = MockHttpClient({"jiangsu": SAMPLE_RESPONSE})
    
    # Load config and build collector
    config = load_sources_configuration(Path("config/ivd_sources.json"))
    collectors = build_collectors_from_config(config, mock_client)
    
    jiangsu_collector = next(c for c in collectors if c.source_id == "cn_jiangsu_procurement")
    records = list(jiangsu_collector.collect())
    
    assert len(records) > 0
```

### Step 4: Enable the Collector

Set `"enabled": true` in the configuration file. The collector will automatically be included in the next ingestion run.

## Disabling Specific Scrapers

### Temporary Disable

Set `"enabled": false` in the configuration:

```json
{
  "source_id": "cn_shanghai_procurement",
  "enabled": false
}
```

No code changes are required; the collector will be skipped during configuration loading.

### Permanent Removal

Remove the entire source entry from `config/ivd_sources.json`.

## Integration with Ingestion Pipeline

### Example Ingestion Script

```python
from pathlib import Path
from src.ivd_monitor.database import IVDDatabase
from src.ivd_monitor.sources import build_collectors_from_config, load_sources_configuration
from src.ivd_monitor.sources.http_client import HttpxClient

db = IVDDatabase()
config = load_sources_configuration(Path("config/ivd_sources.json"))
http_client = HttpxClient(timeout=30.0)

collectors = build_collectors_from_config(config, http_client)

for collector in collectors:
    run_id = db.start_ingestion_run(source=collector.source_id)
    
    try:
        for record in collector.collect():
            db.insert_record(
                source=record.source,
                source_type=record.source_type,
                category=record.category,
                title=record.title,
                url=record.url,
                summary=record.summary,
                content_html=record.content_html,
                publish_date=record.publish_date,
                region=record.region,
                companies=record.companies,
                metadata=record.metadata,
                ingestion_run_id=run_id,
            )
        
        db.complete_ingestion_run(run_id, status="completed")
    except Exception as e:
        db.complete_ingestion_run(run_id, status="failed", metadata={"error": str(e)})
```

## Testing

### Running Tests

```bash
pytest tests/ivd_monitor/ -v
```

### Creating Mock Responses

Store sample responses in `tests/data/`:

- `tests/data/procurement/` - Procurement portal responses
- `tests/data/media/` - RSS feeds and HTML pages

Example:

```json
// tests/data/procurement/new_portal.json
{
  "data": {
    "items": [
      {
        "title": "Sample Procurement Notice",
        "url": "/notice/12345",
        "publishDate": "2024-03-01 10:00:00"
      }
    ]
  }
}
```

## Downstream Reporting

Records collected by these scrapers are stored in the IVD Monitor database with the following fields populated:

- `source`: Collector source_id
- `source_type`: "procurement" or "industry_media"
- `category`: High-level grouping (e.g., "Procurement", "Industry Media")
- `region`: Geographic region code
- `metadata`: JSON object with additional fields (bid_status, budget, portal, etc.)

### Querying by Source Type

```python
db = IVDDatabase()

# Get all procurement records
procurement_records = db.get_records_by_category("Procurement")

# Get all industry media records
conn = db._connect()
media_records = conn.execute(
    "SELECT * FROM records WHERE source_type = ?",
    ("industry_media",)
).fetchall()
```

### Regional Filtering

```python
# Get Beijing procurement records
beijing_records = db.get_records_for_day(
    date.today(),
    category="Procurement",
    region="CN-11"
)

# Get all Shanghai records
conn = db._connect()
shanghai_records = conn.execute(
    "SELECT * FROM records WHERE region = ?",
    ("CN-31",)
).fetchall()
```

### Generating Digests

Records with `source_type="industry_media"` can be grouped separately in daily/weekly digests:

```python
# Pseudocode for digest generation
procurement_section = filter(records, source_type="procurement")
media_section = filter(records, source_type="industry_media")

digest = {
    "procurement_notices": summarize(procurement_section),
    "industry_news": summarize(media_section)
}
```

## Troubleshooting

### Collector Returns No Records

1. Check if the collector is enabled in configuration
2. Verify the URL is accessible (check HTTP response)
3. Inspect the response structure (JSON paths or HTML selectors)
4. Review test cases for similar portals

### Date Parsing Errors

- Verify `date_format` matches the actual format in the response
- Check timezone settings (default is `Asia/Shanghai`)
- Use `optional: true` if dates are not always present

### URL Resolution Issues

- Ensure `base_url` is set for relative URLs
- Check if URLs need scheme prepending (http/https)
- Verify the `url` field path or selector is correct

### Rate Limiting or Blocking

- Increase `rate_limit_delay`
- Add realistic User-Agent headers
- Consider using proxies or browser automation for heavily protected sites

## Future Enhancements

1. **Browser Automation**: Add support for Playwright/Selenium for JavaScript-heavy sites
2. **Proxy Rotation**: Implement proxy pool for high-volume scraping
3. **CAPTCHA Solving**: Integrate CAPTCHA-solving services for protected portals
4. **Incremental Collection**: Track last collection timestamp to fetch only new records
5. **Webhook Notifications**: Alert on collection failures or anomalies
6. **Dashboard**: Web UI for monitoring collector status and metrics

## References

- [IVD Monitor Database Documentation](./ivd_monitor.md)
- [China Government Procurement Network](http://www.ccgp.gov.cn)
- [ISO 3166-2:CN Regional Codes](https://en.wikipedia.org/wiki/ISO_3166-2:CN)
