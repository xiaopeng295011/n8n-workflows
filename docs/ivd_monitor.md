# IVD Monitor Database

The IVD (In Vitro Diagnostics) monitor stores recently ingested regulatory and market intelligence records in a dedicated SQLite database. This database is separate from the existing workflow index (`workflow_db.py`) and only holds news-style records that power IVD-specific reporting and digest generation.

## Bootstrapping the database

The schema can be created locally or in CI using the module CLI helper:

```bash
python -m src.ivd_monitor.database --init
```

By default this creates `database/ivd_monitor.db`. You can provide an alternate location with `--db-path` if you need an isolated copy for testing.

## Schema overview

### `records`

| Column         | Type    | Notes |
| -------------- | ------- | ----- |
| `id`           | INTEGER | Primary key |
| `source`       | TEXT    | Origin feed identifier (e.g. RSS, Watchlist) |
| `source_type`  | TEXT    | Optional classification for the source |
| `category`     | TEXT    | High-level topic grouping |
| `companies`    | TEXT    | JSON encoded list of company names |
| `title`        | TEXT    | Article or alert title |
| `summary`      | TEXT    | Short description or excerpt |
| `content_html` | TEXT    | Normalised HTML body |
| `publish_date` | TEXT    | ISO8601 UTC timestamp for publication |
| `url`          | TEXT    | Canonical source URL |
| `url_hash`     | TEXT    | SHA-256 of the canonical URL (unique) |
| `region`       | TEXT    | Optional geographic region |
| `scraped_at`   | TEXT    | ISO8601 UTC timestamp when the record was ingested |
| `metadata`     | TEXT    | JSON encoded auxiliary data |
| `content_hash` | TEXT    | SHA-256 hash of the title/summary/content for deduplication |
| `created_at`   | TEXT    | Record creation timestamp |
| `updated_at`   | TEXT    | Last update timestamp |

### `records_fts`

An FTS5 virtual table kept in sync with triggers on the main table. It indexes `title`, `summary`, and `content_html` for search and deduplication support.

### `ingestion_runs`

Captures metadata for each ingestion execution (start/end timestamps, total processed, and deduplication counts). The helper methods in `IVDDatabase` automatically maintain these counters when provided an ingestion run ID.

## Working with the helper class

`src.ivd_monitor.database.IVDDatabase` exposes:

- `start_ingestion_run` / `complete_ingestion_run` for auditing
- `insert_record` which hashes URLs/content, enforces uniqueness, and reports whether the item was inserted, updated, or discarded as a duplicate
- Query helpers for retrieving records by day, category, or company, as well as ingestion metric summaries and FTS search

Because this IVD database is standalone, it can be initialised without touching the existing `workflows.db` index. Running the CLI command only affects `database/ivd_monitor.db` unless you override the path explicitly.

## Enrichment pipeline

Records should be enriched with company matches and digest categories before they are persisted. See [`docs/ivd_company_matching.md`](./ivd_company_matching.md) for detailed guidance on:

- Maintaining the IVD company dataset (`config/ivd_companies.json`)
- Configuring the `CompanyMatcher` heuristics and overrides
- Updating categorisation rules handled by `CategoryClassifier`
- Running the enrichment-specific test suites

## Email digest preview

The daily digest email is generated with reusable Jinja2 templates located in `templates/ivd`. To preview the HTML, plaintext, or CSV output locally without sending an email, use the helper CLI:

```bash
python -m src.ivd_monitor.email_builder --date 2024-01-15 --format html --output digest.html
python -m src.ivd_monitor.email_builder --date 2024-01-15 --format text
python -m src.ivd_monitor.email_builder --date 2024-01-15 --format csv --output digest.csv
```

The preview command reads configuration from environment variables when available (see `.env.ivd.example` for a starting point):

- `IVD_DIGEST_SUBJECT_FORMAT` — subject template with `{date}` placeholder
- `IVD_DIGEST_INTRO_TEXT` — introductory paragraph displayed at the top of the digest
- `IVD_DIGEST_RECIPIENTS` — comma-separated default recipient list for downstream transport

### Email client compatibility

The HTML template renders with inline CSS optimised for common desktop and mobile clients (Outlook, Apple Mail, Gmail). Layout uses table-based sections, conservative typography, and UTF-8 encoding so that Simplified Chinese characters render correctly. When embedding the output in your email transport, ensure the message is sent as multipart/alternative (HTML + plaintext) to preserve accessibility and fallback behaviour.
