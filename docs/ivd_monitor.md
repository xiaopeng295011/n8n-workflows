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

## Registering new collectors

The scraper core provides a reusable framework for ingesting regulatory sources. To add a new collector:

1. Create a subclass of `src.ivd_monitor.collector.BaseCollector` (or `SyncCollector` if third-party libraries are synchronous).
2. Implement the `_collect_records(self, stats)` method to return a list of `RawRecord` instances. Use `self.normalize_date(value)` for publish dates and `self.fetch_url(url, stats=stats)` for HTTP requests with retry/backoff configured by `CollectorConfig`.
3. Define a `CollectorConfig` with appropriate name, timeout, retry, and header overrides and pass it to the collector constructor. Custom metadata can be included for logging and auditing.
4. Register the collector with `CollectorManager`, either programmatically or via dependency injection in the ingestion runner: `manager.register(MyCollector(config))`.
5. Run the manager with `await manager.collect_all()` to execute all registered collectors concurrently. The manager returns a `CollectorManagerResult` containing merged records, per-collector stats, and error summaries for logging and the ingestion audit table.

All collector logs are routed through the `ivd_monitor` logger and written to `logs/ivd_monitor.log`. Ensure `src.ivd_monitor.logging_config.setup_logging()` is called during application startup to initialise structured logging before running collectors.
