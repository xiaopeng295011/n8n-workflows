"""Collector manager for orchestrating multiple collectors."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from .collector import BaseCollector
from .logging_config import get_logger, setup_logging
from .models import (
    CollectionResult,
    CollectorError,
    CollectorManagerResult,
    CollectorStats,
    RawRecord,
)

logger = get_logger("collector_manager")


class CollectorManager:
    """Orchestrates execution of multiple collectors concurrently.
    
    The manager runs all registered collectors in parallel using asyncio,
    collates their results, and provides structured error summaries for
    logging and audit purposes.
    """

    def __init__(self, collectors: Optional[List[BaseCollector]] = None) -> None:
        """Initialize manager with collectors.
        
        Args:
            collectors: List of collector instances to manage
        """
        self.collectors = collectors or []

    def register(self, collector: BaseCollector) -> None:
        """Register a collector with the manager.
        
        Args:
            collector: Collector instance to register
        """
        if collector not in self.collectors:
            self.collectors.append(collector)
            logger.info(f"Registered collector: {collector.name}")

    def unregister(self, collector: BaseCollector) -> None:
        """Unregister a collector from the manager.
        
        Args:
            collector: Collector instance to unregister
        """
        if collector in self.collectors:
            self.collectors.remove(collector)
            logger.info(f"Unregistered collector: {collector.name}")

    async def collect_all(
        self,
        *,
        fail_fast: bool = False,
        skip_disabled: bool = True,
    ) -> CollectorManagerResult:
        """Execute all registered collectors concurrently.
        
        Args:
            fail_fast: If True, stop on first collector failure
            skip_disabled: If True, skip collectors with enabled=False
            
        Returns:
            CollectorManagerResult with merged records and error summaries
        """
        active_collectors = [
            c for c in self.collectors
            if not skip_disabled or c.enabled
        ]

        if not active_collectors:
            logger.warning("No active collectors to run")
            return CollectorManagerResult(
                records=[],
                errors=[],
                stats={},
                success=True,
            )

        logger.info(f"Starting collection with {len(active_collectors)} collectors")

        if fail_fast:
            results = await self._collect_fail_fast(active_collectors)
        else:
            results = await self._collect_all_concurrent(active_collectors)

        all_records: List[RawRecord] = []
        all_errors: List[CollectorError] = []
        all_stats = {}
        overall_success = True

        for result in results:
            all_records.extend(result.records)
            all_stats[result.collector_name] = result.stats

            if not result.success:
                overall_success = False

            if result.stats:
                all_errors.extend(result.stats.errors)

        logger.info(
            f"Collection completed: "
            f"{len(all_records)} records, "
            f"{len(all_errors)} errors, "
            f"{len(active_collectors)} collectors"
        )

        if all_errors:
            logger.warning(f"Collection had {len(all_errors)} errors:")
            for error in all_errors[:10]:  # Log first 10 errors
                logger.warning(
                    f"  - {error.collector_name}: {error.error_type} - {error.message}"
                )
            if len(all_errors) > 10:
                logger.warning(f"  ... and {len(all_errors) - 10} more errors")

        return CollectorManagerResult(
            records=all_records,
            errors=all_errors,
            stats=all_stats,
            success=overall_success,
        )

    async def _collect_all_concurrent(
        self,
        collectors: List[BaseCollector],
    ) -> List:
        """Run all collectors concurrently, capturing all results."""
        tasks = [collector.collect() for collector in collectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                collector = collectors[i]
                error = CollectorError(
                    collector_name=collector.name,
                    error_type=type(result).__name__,
                    message=str(result),
                )
                logger.error(
                    f"Collector {collector.name} raised exception: {result}"
                )

                stats = CollectorStats(
                    collector_name=collector.name,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                )
                stats.add_error(error)

                processed_results.append(
                    CollectionResult(
                        collector_name=collector.name,
                        records=[],
                        stats=stats,
                        success=False,
                        error_message=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    async def _collect_fail_fast(
        self,
        collectors: List[BaseCollector],
    ) -> List:
        """Run collectors concurrently but fail on first error."""
        tasks = [collector.collect() for collector in collectors]
        results = await asyncio.gather(*tasks)
        return results
