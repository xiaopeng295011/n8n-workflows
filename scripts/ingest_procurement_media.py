#!/usr/bin/env python3
"""Ingestion script for procurement and media sources.

This script loads configured sources from config/ivd_sources.json,
collects records from enabled collectors, and stores them in the
IVD monitor database with automatic deduplication.

Usage:
    python scripts/ingest_procurement_media.py [--config PATH] [--db-path PATH]
"""

import argparse
import logging
import sys
from pathlib import Path

from src.ivd_monitor.database import IVDDatabase
from src.ivd_monitor.sources import build_collectors_from_config, load_sources_configuration
from src.ivd_monitor.sources.http_client import HttpxClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Main ingestion entrypoint."""
    parser = argparse.ArgumentParser(description="Ingest procurement and media records")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/ivd_sources.json"),
        help="Path to sources configuration file",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Path to IVD monitor database",
    )
    parser.add_argument(
        "--source-id",
        type=str,
        help="Only run specific source by ID",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP request timeout in seconds",
    )
    args = parser.parse_args()

    db = IVDDatabase(db_path=str(args.db_path) if args.db_path else None)
    logger.info(f"Using database at {db.db_path}")

    if not args.config.exists():
        logger.error(f"Configuration file not found: {args.config}")
        return 1

    config = load_sources_configuration(args.config)
    logger.info(f"Loaded configuration with {len(config.sources)} sources")

    http_client = HttpxClient(timeout=args.timeout)
    collectors = build_collectors_from_config(config, http_client)

    if args.source_id:
        collectors = [c for c in collectors if c.source_id == args.source_id]
        if not collectors:
            logger.error(f"Source ID not found: {args.source_id}")
            return 1

    logger.info(f"Running {len(collectors)} enabled collectors")

    total_records = 0
    total_new = 0
    total_updated = 0
    total_duplicate = 0
    failed_collectors = []

    for collector in collectors:
        logger.info(f"Starting collection: {collector.source_id}")
        run_id = db.start_ingestion_run(source=collector.source_id)

        try:
            collected_count = 0
            for record in collector.collect():
                result = db.insert_record(
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
                collected_count += 1

                if result.status == "inserted":
                    total_new += 1
                elif result.status == "updated":
                    total_updated += 1
                elif result.status == "duplicate":
                    total_duplicate += 1

            total_records += collected_count
            db.complete_ingestion_run(run_id, status="completed")
            logger.info(
                f"Completed {collector.source_id}: "
                f"{collected_count} records collected"
            )

        except Exception as e:
            logger.error(f"Failed to collect from {collector.source_id}: {e}")
            db.complete_ingestion_run(
                run_id,
                status="failed",
                metadata={"error": str(e)},
            )
            failed_collectors.append(collector.source_id)

    logger.info("=" * 60)
    logger.info("Ingestion Summary")
    logger.info("=" * 60)
    logger.info(f"Total records processed: {total_records}")
    logger.info(f"New records: {total_new}")
    logger.info(f"Updated records: {total_updated}")
    logger.info(f"Duplicate records: {total_duplicate}")

    if failed_collectors:
        logger.warning(f"Failed collectors: {', '.join(failed_collectors)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
