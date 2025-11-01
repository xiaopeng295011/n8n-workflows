# IVD Monitor Ingestion Scripts

## Overview

This directory contains scripts for ingesting procurement and media data into the IVD monitor database.

## Usage

### Ingest Procurement and Media Records

The `ingest_procurement_media.py` script collects records from configured sources and stores them in the IVD monitor database.

#### Basic Usage

```bash
python scripts/ingest_procurement_media.py
```

This will:
- Load sources from `config/ivd_sources.json`
- Collect records from all enabled sources
- Store records in `database/ivd_monitor.db`
- Handle deduplication automatically

#### Custom Configuration Path

```bash
python scripts/ingest_procurement_media.py --config /path/to/custom_sources.json
```

#### Custom Database Path

```bash
python scripts/ingest_procurement_media.py --db-path /path/to/custom_db.db
```

#### Run Specific Source Only

```bash
python scripts/ingest_procurement_media.py --source-id cn_beijing_procurement
```

#### Adjust HTTP Timeout

```bash
python scripts/ingest_procurement_media.py --timeout 60.0
```

### Scheduling with Cron

To run the ingestion script daily at 2 AM:

```bash
# Edit crontab
crontab -e

# Add this line:
0 2 * * * cd /path/to/n8n-workflows && /path/to/python scripts/ingest_procurement_media.py >> logs/ingestion.log 2>&1
```

### Viewing Ingestion Metrics

After running the script, you can query ingestion metrics:

```python
from src.ivd_monitor.database import IVDDatabase

db = IVDDatabase()
metrics = db.get_ingestion_metrics()

print(f"Total runs: {metrics['total_runs']}")
print(f"Records processed: {metrics['records_processed']}")
print(f"New records: {metrics['new_records']}")
print(f"Duplicates: {metrics['duplicate_records']}")
```

## Exit Codes

- `0`: Success
- `1`: Configuration error or collection failure

## Logging

The script logs to stdout with the following format:

```
2024-03-01 10:00:00 - __main__ - INFO - Starting collection: cn_ccgp_procurement
2024-03-01 10:00:05 - __main__ - INFO - Completed cn_ccgp_procurement: 42 records collected
```

## Troubleshooting

### Configuration File Not Found

```
ERROR - Configuration file not found: config/ivd_sources.json
```

**Solution**: Create the configuration file or specify the correct path with `--config`.

### Source ID Not Found

```
ERROR - Source ID not found: invalid_source
```

**Solution**: Check available source IDs in `config/ivd_sources.json`.

### HTTP Timeout

```
ERROR - Failed to collect from cn_shanghai_procurement: Timeout
```

**Solution**: Increase timeout with `--timeout 60.0` or check network connectivity.

### No Records Collected

Check if:
1. The source is enabled in configuration (`"enabled": true`)
2. The portal is accessible (try accessing the URL manually)
3. Field selectors are correct (inspect the response structure)

## See Also

- [IVD Monitor Database Documentation](../docs/ivd_monitor.md)
- [Scraper Configuration Guide](../docs/ivd_monitor_scrapers.md)
