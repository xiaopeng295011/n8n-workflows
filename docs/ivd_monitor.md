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
