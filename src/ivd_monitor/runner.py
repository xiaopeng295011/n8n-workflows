"""IVD Monitor pipeline runner.

Orchestrates the full IVD monitoring pipeline: data collection, enrichment,
persistence, and digest generation. Supports dry-run mode, custom date ranges,
and comprehensive error handling with per-source failure tracking.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .categorization import CategoryClassifier, enrich_records
from .company_matching import CompanyMatcher
from .database import IVDDatabase
from .email_builder import DigestConfig, EmailDigestBuilder


@dataclass
class CollectorConfig:
    """Configuration for data collectors."""

    sources: List[Dict[str, Any]] = field(default_factory=list)
    timeout: int = 30
    max_retries: int = 3
    user_agent: str = "IVD-Monitor/1.0"

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "CollectorConfig":
        """Load collector configuration from JSON file."""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Collector config not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            sources=data.get("sources", []),
            timeout=data.get("timeout", 30),
            max_retries=data.get("max_retries", 3),
            user_agent=data.get("user_agent", "IVD-Monitor/1.0"),
        )

    @classmethod
    def default(cls) -> "CollectorConfig":
        """Return default configuration with placeholder sources."""
        return cls(
            sources=[
                {
                    "name": "example_rss_feed",
                    "type": "rss",
                    "url": "https://example.com/feed",
                    "enabled": False,
                },
                {
                    "name": "example_scraper",
                    "type": "scraper",
                    "url": "https://example.com/news",
                    "enabled": False,
                },
            ]
        )


@dataclass
class CollectionResult:
    """Result of a data collection operation."""

    source_name: str
    status: str
    records: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class CollectorManager:
    """Manages data collection from configured sources."""

    def __init__(self, config: CollectorConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

    def collect_all(self) -> List[CollectionResult]:
        """Collect data from all configured sources.

        Returns:
            List of CollectionResult objects, one per source
        """
        results: List[CollectionResult] = []

        for source_config in self.config.sources:
            if not source_config.get("enabled", True):
                self.logger.info(f"Skipping disabled source: {source_config.get('name')}")
                continue

            result = self._collect_from_source(source_config)
            results.append(result)

        return results

    def _collect_from_source(self, source_config: Dict[str, Any]) -> CollectionResult:
        """Collect data from a single source.

        This is a placeholder implementation. In production, this would:
        - Instantiate the appropriate collector based on source type
        - Fetch and parse data
        - Handle retries and timeouts
        - Return structured records
        """
        source_name = source_config.get("name", "unknown")
        source_type = source_config.get("type", "unknown")

        self.logger.info(f"Collecting from source: {source_name} (type: {source_type})")

        try:
            # Placeholder: In production, implement actual collection logic
            # For now, return empty success result
            return CollectionResult(
                source_name=source_name,
                status="success",
                records=[],
                metadata={
                    "source_type": source_type,
                    "url": source_config.get("url", ""),
                    "collected_at": datetime.utcnow().isoformat() + "Z",
                },
            )
        except Exception as e:
            self.logger.error(f"Failed to collect from {source_name}: {e}")
            return CollectionResult(
                source_name=source_name,
                status="failed",
                error=str(e),
                metadata={"source_type": source_type},
            )


@dataclass
class RunSummary:
    """Summary of a pipeline run."""

    run_id: int
    started_at: str
    completed_at: str
    total_sources: int
    successful_sources: int
    failed_sources: List[str] = field(default_factory=list)
    total_records_collected: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_duplicate: int = 0
    digest_generated: bool = False
    digest_output_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def exit_code(self) -> int:
        """Return appropriate exit code based on run status."""
        if self.errors:
            return 1
        if self.failed_sources:
            return 2
        return 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_sources": self.total_sources,
            "successful_sources": self.successful_sources,
            "failed_sources": self.failed_sources,
            "total_records_collected": self.total_records_collected,
            "records_inserted": self.records_inserted,
            "records_updated": self.records_updated,
            "records_duplicate": self.records_duplicate,
            "digest_generated": self.digest_generated,
            "digest_output_path": self.digest_output_path,
            "errors": self.errors,
            "exit_code": self.exit_code(),
        }


class IVDMonitorRunner:
    """Main pipeline orchestrator for IVD monitoring."""

    def __init__(
        self,
        db: Optional[IVDDatabase] = None,
        collector_config: Optional[CollectorConfig] = None,
        digest_config: Optional[DigestConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.db = db or IVDDatabase()
        self.collector_config = collector_config or CollectorConfig.default()
        self.digest_config = digest_config or DigestConfig.from_env()
        self.logger = logger or logging.getLogger(__name__)

        self.company_matcher = CompanyMatcher()
        self.category_classifier = CategoryClassifier()
        self.collector_manager = CollectorManager(self.collector_config, logger=self.logger)

    def run(
        self,
        *,
        target_date: Optional[Union[str, date, datetime]] = None,
        dry_run: bool = False,
        output_dir: Optional[Path] = None,
        digest_formats: Optional[List[str]] = None,
    ) -> RunSummary:
        """Execute the full IVD monitoring pipeline.

        Args:
            target_date: Date to generate digest for (defaults to today)
            dry_run: If True, collect and process but don't persist to database
            output_dir: Directory to write digest outputs
            digest_formats: List of formats to generate ('html', 'text', 'csv')

        Returns:
            RunSummary with execution metrics and status
        """
        if target_date is None:
            target_date = date.today()
        elif isinstance(target_date, str):
            target_date = datetime.fromisoformat(target_date.replace("Z", "")).date()
        elif isinstance(target_date, datetime):
            target_date = target_date.date()

        if digest_formats is None:
            digest_formats = ["html", "text"]

        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        started_at = datetime.utcnow().isoformat() + "Z"
        self.logger.info(f"Starting IVD monitor run for date: {target_date}")
        self.logger.info(f"Dry run mode: {dry_run}")

        run_id = 0
        if not dry_run:
            run_id = self.db.start_ingestion_run(
                source="ivd_monitor_runner",
                metadata={"target_date": str(target_date), "dry_run": dry_run},
            )

        summary = RunSummary(
            run_id=run_id,
            started_at=started_at,
            completed_at="",
            total_sources=0,
            successful_sources=0,
        )

        try:
            # Step 1: Collect data from all sources
            self.logger.info("Step 1: Collecting data from sources...")
            collection_results = self.collector_manager.collect_all()
            summary.total_sources = len(collection_results)

            # Step 2: Process and enrich collected records
            self.logger.info("Step 2: Processing and enriching records...")
            all_records: List[Dict[str, Any]] = []
            for result in collection_results:
                if result.status == "success":
                    summary.successful_sources += 1
                    all_records.extend(result.records)
                else:
                    summary.failed_sources.append(result.source_name)
                    if result.error:
                        self.logger.error(f"Source {result.source_name} failed: {result.error}")

            summary.total_records_collected = len(all_records)
            self.logger.info(f"Collected {len(all_records)} records from {summary.successful_sources} sources")

            # Enrich records with company matching and categorization
            if all_records:
                enriched_records = enrich_records(
                    all_records,
                    company_matcher=self.company_matcher,
                    category_classifier=self.category_classifier,
                )
                self.logger.info(f"Enriched {len(enriched_records)} records")
            else:
                enriched_records = []
                self.logger.warning("No records collected")

            # Step 3: Persist to database
            if not dry_run and enriched_records:
                self.logger.info("Step 3: Persisting records to database...")
                for record in enriched_records:
                    try:
                        result = self.db.insert_record(
                            source=record.get("source", "unknown"),
                            url=record.get("url", ""),
                            source_type=record.get("source_type"),
                            category=record.get("category"),
                            companies=record.get("companies", []),
                            title=record.get("title"),
                            summary=record.get("summary"),
                            content_html=record.get("content_html"),
                            publish_date=record.get("publish_date"),
                            region=record.get("region"),
                            scraped_at=record.get("scraped_at"),
                            metadata=record.get("metadata"),
                            ingestion_run_id=run_id,
                        )

                        if result.status == "inserted":
                            summary.records_inserted += 1
                        elif result.status == "updated":
                            summary.records_updated += 1
                        elif result.status == "duplicate":
                            summary.records_duplicate += 1

                    except Exception as e:
                        error_msg = f"Failed to insert record: {e}"
                        self.logger.error(error_msg)
                        summary.errors.append(error_msg)

                self.logger.info(
                    f"Persisted: {summary.records_inserted} inserted, "
                    f"{summary.records_updated} updated, "
                    f"{summary.records_duplicate} duplicates"
                )
            elif dry_run:
                self.logger.info("Step 3: Skipping database persistence (dry run mode)")

            # Step 4: Generate email digest
            self.logger.info("Step 4: Generating email digest...")
            try:
                digest_builder = EmailDigestBuilder(
                    db=self.db,
                    config=self.digest_config,
                )

                digest_data = digest_builder.build_digest(
                    target_date,
                    failed_sources=summary.failed_sources if summary.failed_sources else None,
                )

                if output_dir:
                    self._write_digest_outputs(
                        digest_builder,
                        digest_data,
                        output_dir,
                        target_date,
                        digest_formats,
                    )
                    summary.digest_generated = True
                    summary.digest_output_path = str(output_dir)
                    self.logger.info(f"Digest written to {output_dir}")
                else:
                    summary.digest_generated = True
                    self.logger.info("Digest generated (no output path specified)")

            except Exception as e:
                error_msg = f"Failed to generate digest: {e}"
                self.logger.error(error_msg)
                summary.errors.append(error_msg)

            # Step 5: Complete the run
            completed_at = datetime.utcnow().isoformat() + "Z"
            summary.completed_at = completed_at

            if not dry_run:
                status = "completed" if not summary.errors else "completed_with_errors"
                self.db.complete_ingestion_run(
                    run_id,
                    status=status,
                    metadata={
                        "failed_sources": summary.failed_sources,
                        "errors": summary.errors,
                    },
                )

            self.logger.info(f"Run completed: {summary.exit_code()} exit code")
            return summary

        except Exception as e:
            error_msg = f"Pipeline failed: {e}"
            self.logger.exception(error_msg)
            summary.errors.append(error_msg)
            summary.completed_at = datetime.utcnow().isoformat() + "Z"

            if not dry_run and run_id:
                self.db.complete_ingestion_run(
                    run_id,
                    status="failed",
                    metadata={"errors": summary.errors},
                )

            return summary

    def _write_digest_outputs(
        self,
        builder: EmailDigestBuilder,
        digest_data: Dict[str, Any],
        output_dir: Path,
        target_date: Union[str, date],
        formats: List[str],
    ) -> None:
        """Write digest outputs in requested formats."""
        date_str = str(target_date) if isinstance(target_date, (str, date)) else target_date.strftime("%Y-%m-%d")

        if "html" in formats:
            html_content = builder.render_html(digest_data)
            html_path = output_dir / f"digest_{date_str}.html"
            html_path.write_text(html_content, encoding="utf-8")
            self.logger.info(f"Wrote HTML digest: {html_path}")

        if "text" in formats:
            text_content = builder.render_text(digest_data)
            text_path = output_dir / f"digest_{date_str}.txt"
            text_path.write_text(text_content, encoding="utf-8")
            self.logger.info(f"Wrote text digest: {text_path}")

        if "csv" in formats:
            csv_content = builder.export_to_csv(target_date)
            csv_path = output_dir / f"digest_{date_str}.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            self.logger.info(f"Wrote CSV digest: {csv_path}")


def setup_logging(verbose: bool = False, log_file: Optional[Path] = None) -> logging.Logger:
    """Configure structured logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers,
    )

    return logging.getLogger(__name__)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for IVD monitor runner."""
    parser = argparse.ArgumentParser(
        description="IVD Monitor pipeline runner - orchestrates data collection, enrichment, and digest generation"
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to collector configuration JSON file",
    )

    parser.add_argument(
        "--db-path",
        type=Path,
        help="Path to IVD database (default: database/ivd_monitor.db)",
    )

    parser.add_argument(
        "--date",
        help="Target date for digest generation (YYYY-MM-DD, default: today)",
    )

    parser.add_argument(
        "--date-range",
        nargs=2,
        metavar=("START", "END"),
        help="Date range for processing (YYYY-MM-DD YYYY-MM-DD)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without persisting to database",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output directory for digest files",
    )

    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["html", "text", "csv"],
        default=["html", "text"],
        help="Digest output formats (default: html text)",
    )

    parser.add_argument(
        "--log-file",
        type=Path,
        help="Write logs to file",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary as JSON",
    )

    args = parser.parse_args(argv)

    # Setup logging
    logger = setup_logging(verbose=args.verbose, log_file=args.log_file)

    try:
        # Load collector config
        if args.config:
            collector_config = CollectorConfig.from_file(args.config)
        else:
            collector_config = CollectorConfig.default()
            logger.warning("No collector config provided, using default (no active sources)")

        # Initialize database
        db = IVDDatabase(db_path=args.db_path) if args.db_path else IVDDatabase()

        # Initialize runner
        runner = IVDMonitorRunner(
            db=db,
            collector_config=collector_config,
            digest_config=DigestConfig.from_env(),
            logger=logger,
        )

        # Handle date range or single date
        if args.date_range:
            start_date = datetime.strptime(args.date_range[0], "%Y-%m-%d").date()
            end_date = datetime.strptime(args.date_range[1], "%Y-%m-%d").date()

            logger.info(f"Processing date range: {start_date} to {end_date}")
            current_date = start_date
            summaries: List[RunSummary] = []

            while current_date <= end_date:
                logger.info(f"Processing date: {current_date}")
                summary = runner.run(
                    target_date=current_date,
                    dry_run=args.dry_run,
                    output_dir=args.output,
                    digest_formats=args.formats,
                )
                summaries.append(summary)
                current_date += timedelta(days=1)

            # Aggregate summaries
            total_exit_code = max(s.exit_code() for s in summaries)

            if args.json:
                print(json.dumps([s.to_dict() for s in summaries], indent=2))
            else:
                logger.info(f"Completed {len(summaries)} runs with exit code: {total_exit_code}")

            return total_exit_code

        else:
            # Single date run
            summary = runner.run(
                target_date=args.date,
                dry_run=args.dry_run,
                output_dir=args.output,
                digest_formats=args.formats,
            )

            if args.json:
                print(json.dumps(summary.to_dict(), indent=2))
            else:
                logger.info(f"Run summary: {summary.successful_sources}/{summary.total_sources} sources successful")
                logger.info(
                    f"Records: {summary.records_inserted} inserted, "
                    f"{summary.records_updated} updated, "
                    f"{summary.records_duplicate} duplicates"
                )
                if summary.failed_sources:
                    logger.warning(f"Failed sources: {', '.join(summary.failed_sources)}")
                if summary.errors:
                    logger.error(f"Errors: {len(summary.errors)}")

            return summary.exit_code()

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
