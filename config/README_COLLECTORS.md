# IVD Monitor Collector Configuration

This directory contains configuration files that define metadata, behavior, and
operational parameters for IVD monitor data collectors.

## Configuration File: `ivd_sources.yaml`

The `ivd_sources.yaml` file declares:

1. **Source metadata**: each collector's ID, name, type, and categorization
2. **Pagination strategies**: how to fetch multiple pages (API params vs HTML)
3. **Rate limits**: delays (in milliseconds) between requests to avoid throttling
4. **Fallback strategies**: instructions for switching to backup endpoints or HTML
   parsing when JSON APIs fail
5. **Required parameters**: what query parameters each collector needs

## Structure

```yaml
sources:
  <source_id>:
    enabled: true | false
    source_name: <display name>
    source_type: <data type classification>
    default_category: <database category>
    page_size: <records per page>
    max_pages: <max pages to fetch in one run>
    rate_limit_delay_ms: <milliseconds between requests>
    description: <notes about the upstream source>
    fallback_strategy: <instructions when the primary endpoint fails>
```

## Source Types

- **financial_reports**: company financial disclosures, quarterly reports, event
  announcements (from CNInfo, SSE, SZSE)
- **product_launches**: new medical device approvals, registrations, and product
  listings from NMPA
- **reimbursement_policy**: policy updates from the National Healthcare Security
  Administration (NHSA) affecting device coverage and pricing
- **health_commission_policy**: regulatory notices from the National Health
  Commission (NHC) on standards, guidelines, and compliance

## Enabling/Disabling Sources

Toggle the `enabled` flag in the YAML file to control whether a collector runs
during scheduled ingestion. For example, to disable the Shanghai Stock Exchange
collector:

```yaml
financial.shanghai_exchange:
  enabled: false
  ...
```

## Extending with New Collectors

1. Create a new collector class in `src/ivd_monitor/sources/financial/` or
   `src/ivd_monitor/sources/regulatory/` that inherits from `BaseCollector`.
2. Add a corresponding entry in `ivd_sources.yaml` with a unique `source_id`.
3. Write unit tests in `tests/ivd_monitor/sources/` with representative fixtures.
4. Document query parameters, rate limits, and fallback strategies in
   `Documentation/IVD_MONITOR_SOURCES.md`.

## Testing

Run collector tests with:

```bash
pytest tests/ivd_monitor/sources/
```

These tests use fixtures from `tests/ivd_monitor/sources/fixtures/` which contain
saved JSON and HTML payloads with Chinese text.

## Rate Limit Guidelines

- **Financial sources (CNInfo, SSE, SZSE)**: 200–300 ms delays are safe
- **Regulatory sources (NMPA, NHSA, NHC)**: 400–500 ms delays recommended
- Adjust delays based on observed HTTP 429 responses or errors during high-volume
  ingestion

## Fallback Strategy Notes

If an official JSON endpoint stops responding or changes schemas:

1. Check the `fallback_strategy` field in the config for guidance
2. Switch to HTML parsing by modifying the collector's `_fetch_page` method
3. Capture fresh HTML samples in `tests/ivd_monitor/sources/fixtures/` and update
   tests
4. Update the `Description/IVD_MONITOR_SOURCES.md` documentation with the new
   approach
