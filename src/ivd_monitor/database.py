"""IVD monitor database interface.

Provides schema management, ingestion utilities and query helpers for
medical device intelligence feeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence, Union

ISO_TIMESTAMP_SUFFIX = "Z"

if TYPE_CHECKING:
    from .categorization import CategoryClassifier
    from .company_matching import CompanyMatcher

_COMPANY_MATCHER: Optional["CompanyMatcher"] = None
_CATEGORY_CLASSIFIER: Optional["CategoryClassifier"] = None


def _get_company_matcher() -> "CompanyMatcher":
    global _COMPANY_MATCHER
    if _COMPANY_MATCHER is None:
        from .company_matching import CompanyMatcher

        _COMPANY_MATCHER = CompanyMatcher()
    return _COMPANY_MATCHER


def _get_category_classifier() -> "CategoryClassifier":
    global _CATEGORY_CLASSIFIER
    if _CATEGORY_CLASSIFIER is None:
        from .categorization import CategoryClassifier

        _CATEGORY_CLASSIFIER = CategoryClassifier()
    return _CATEGORY_CLASSIFIER


def _utc_now() -> str:
    """Return a UTC timestamp string with second precision."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + ISO_TIMESTAMP_SUFFIX


def _normalise_url(url: str) -> str:
    return url.strip().lower()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass
class RecordOperationResult:
    """Represents the outcome of an insert/upsert operation."""

    status: str
    record_id: int
    duplicate_of: Optional[int] = None
    message: Optional[str] = None
    ingestion_run_id: Optional[int] = None


class IVDDatabase:
    """High-level helper for the IVD monitor SQLite database."""

    DEFAULT_DB_PATH = Path("database/ivd_monitor.db")

    def __init__(self, db_path: Optional[Union[str, Path]] = None, auto_initialize: bool = True) -> None:
        path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        if not path.is_absolute():
            path = Path.cwd() / path
        self.db_path = path
        if auto_initialize:
            self.initialize()

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def initialize(self) -> None:
        """Initialise database directory and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._apply_pragmas(conn)
            self._create_schema(conn)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _apply_pragmas(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA temp_store=MEMORY")

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                source_type TEXT,
                category TEXT,
                companies TEXT,
                title TEXT,
                summary TEXT,
                content_html TEXT,
                publish_date TEXT,
                url TEXT NOT NULL,
                url_hash TEXT NOT NULL UNIQUE,
                region TEXT,
                scraped_at TEXT,
                metadata TEXT,
                content_hash TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ingestion_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                total_records INTEGER NOT NULL DEFAULT 0,
                new_records INTEGER NOT NULL DEFAULT 0,
                updated_records INTEGER NOT NULL DEFAULT 0,
                duplicate_records INTEGER NOT NULL DEFAULT 0,
                metadata TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
                title,
                summary,
                content_html,
                content='records',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
                INSERT INTO records_fts(rowid, title, summary, content_html)
                VALUES (new.id, new.title, new.summary, new.content_html);
            END;

            CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
                INSERT INTO records_fts(records_fts, rowid, title, summary, content_html)
                VALUES('delete', old.id, old.title, old.summary, old.content_html);
            END;

            CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
                INSERT INTO records_fts(records_fts, rowid, title, summary, content_html)
                VALUES('delete', old.id, old.title, old.summary, old.content_html);
                INSERT INTO records_fts(rowid, title, summary, content_html)
                VALUES (new.id, new.title, new.summary, new.content_html);
            END;

            CREATE INDEX IF NOT EXISTS idx_records_publish_date ON records(publish_date);
            CREATE INDEX IF NOT EXISTS idx_records_category ON records(category);
            CREATE INDEX IF NOT EXISTS idx_records_region ON records(region);
            CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);
            CREATE INDEX IF NOT EXISTS idx_runs_started_at ON ingestion_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_runs_status ON ingestion_runs(status);
            """
        )

    # ------------------------------------------------------------------
    # Ingestion run helpers
    # ------------------------------------------------------------------
    def start_ingestion_run(self, source: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> int:
        payload = {
            "source": source,
            "started_at": _utc_now(),
            "metadata": self._to_json(metadata),
        }
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO ingestion_runs (source, started_at, metadata)
                VALUES (:source, :started_at, :metadata)
                """,
                payload,
            )
            run_id = cur.lastrowid
            conn.commit()
        return run_id

    def complete_ingestion_run(
        self,
        run_id: int,
        *,
        status: str = "completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE ingestion_runs
                   SET status = ?,
                       completed_at = ?,
                       metadata = COALESCE(?, metadata)
                 WHERE id = ?
                """,
                (
                    status,
                    _utc_now(),
                    self._to_json(metadata),
                    run_id,
                ),
            )
            conn.commit()

    def _increment_ingestion_run(
        self,
        conn: sqlite3.Connection,
        run_id: int,
        *,
        total: int = 0,
        new: int = 0,
        updated: int = 0,
        duplicate: int = 0,
    ) -> None:
        conn.execute(
            """
            UPDATE ingestion_runs
               SET total_records = total_records + ?,
                   new_records = new_records + ?,
                   updated_records = updated_records + ?,
                   duplicate_records = duplicate_records + ?
             WHERE id = ?
            """,
            (total, new, updated, duplicate, run_id),
        )

    # ------------------------------------------------------------------
    # Record ingestion
    # ------------------------------------------------------------------
    def _enrich_record_fields(
        self,
        *,
        source: str,
        url: str,
        title: Optional[str],
        summary: Optional[str],
        content_html: Optional[str],
        category: Optional[str],
        companies: Optional[Sequence[str]],
        metadata: Optional[Dict[str, Any]],
    ) -> tuple[List[str], str]:
        """Return canonical companies and category for the supplied record data."""
        matcher = _get_company_matcher()
        classifier = _get_category_classifier()

        metadata_dict: Dict[str, Any]
        if isinstance(metadata, dict):
            metadata_dict = metadata
        else:
            metadata_dict = {}

        if companies:
            canonical_companies = matcher.normalize_names(list(companies))
        else:
            canonical_companies = matcher.match_companies(
                content_html,
                title=title,
                summary=summary,
                metadata=metadata_dict,
            )

        normalized_category = classifier.normalize_category_name(category)
        if not normalized_category:
            normalized_category = classifier.categorize(
                source=source,
                title=title,
                summary=summary,
                content=content_html,
                url=url,
                metadata=metadata_dict,
            )

        return canonical_companies, normalized_category

    def insert_record(
        self,
        *,
        source: str,
        url: str,
        source_type: Optional[str] = None,
        category: Optional[str] = None,
        companies: Optional[Sequence[str]] = None,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        content_html: Optional[str] = None,
        publish_date: Optional[Union[str, date, datetime]] = None,
        region: Optional[str] = None,
        scraped_at: Optional[Union[str, datetime]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ingestion_run_id: Optional[int] = None,
    ) -> RecordOperationResult:
        if not url:
            raise ValueError("url is required")
        if not source:
            raise ValueError("source is required")

        canonical_companies, normalized_category = self._enrich_record_fields(
            source=source,
            url=url,
            title=title,
            summary=summary,
            content_html=content_html,
            category=category,
            companies=companies,
            metadata=metadata,
        )
        companies = canonical_companies
        category = normalized_category

        url_hash = _hash_text(_normalise_url(url))
        content_components = [title or "", summary or "", content_html or ""]
        content_hash = _hash_text("\u241f".join(part.strip() for part in content_components))

        publish_date_str = self._normalize_timestamp(publish_date)
        scraped_at_str = self._normalize_timestamp(scraped_at, default_to_now=True)

        companies_json = self._to_json(list(companies) if companies else [])
        metadata_json = self._to_json(metadata)

        payload = {
            "source": source,
            "source_type": source_type,
            "category": category,
            "companies": companies_json,
            "title": title,
            "summary": summary,
            "content_html": content_html,
            "publish_date": publish_date_str,
            "url": url,
            "url_hash": url_hash,
            "region": region,
            "scraped_at": scraped_at_str,
            "metadata": metadata_json,
            "content_hash": content_hash,
            "updated_at": _utc_now(),
        }

        with self._connect() as conn:
            conn.execute("BEGIN")
            existing = conn.execute(
                "SELECT id, content_hash FROM records WHERE url_hash = ?",
                (url_hash,),
            ).fetchone()

            duplicate_of = None
            status: str
            record_id: int

            if existing:
                record_id = int(existing["id"])
                if existing["content_hash"] != content_hash:
                    conn.execute(
                        """
                        UPDATE records
                           SET source = :source,
                               source_type = :source_type,
                               category = :category,
                               companies = :companies,
                               title = :title,
                               summary = :summary,
                               content_html = :content_html,
                               publish_date = :publish_date,
                               url = :url,
                               region = :region,
                               scraped_at = :scraped_at,
                               metadata = :metadata,
                               content_hash = :content_hash,
                               updated_at = :updated_at
                         WHERE id = :id
                        """,
                        {**payload, "id": record_id},
                    )
                    status = "updated"
                else:
                    conn.execute(
                        """
                        UPDATE records
                           SET scraped_at = :scraped_at,
                               metadata = COALESCE(:metadata, metadata),
                               updated_at = :updated_at
                         WHERE id = :id
                        """,
                        {"scraped_at": scraped_at_str, "metadata": metadata_json, "updated_at": payload["updated_at"], "id": record_id},
                    )
                    duplicate_of = record_id
                    status = "duplicate"
            else:
                duplicate_candidate = conn.execute(
                    "SELECT id FROM records WHERE content_hash = ?",
                    (content_hash,),
                ).fetchone()
                if duplicate_candidate:
                    record_id = int(duplicate_candidate["id"])
                    duplicate_of = record_id
                    status = "duplicate"
                    conn.execute(
                        """
                        UPDATE records
                           SET scraped_at = :scraped_at,
                               metadata = COALESCE(:metadata, metadata),
                               updated_at = :updated_at
                         WHERE id = :id
                        """,
                        {"scraped_at": scraped_at_str, "metadata": metadata_json, "updated_at": payload["updated_at"], "id": record_id},
                    )
                else:
                    cur = conn.execute(
                        """
                        INSERT INTO records (
                            source, source_type, category, companies, title,
                            summary, content_html, publish_date, url, url_hash,
                            region, scraped_at, metadata, content_hash, updated_at
                        ) VALUES (
                            :source, :source_type, :category, :companies, :title,
                            :summary, :content_html, :publish_date, :url, :url_hash,
                            :region, :scraped_at, :metadata, :content_hash, :updated_at
                        )
                        """,
                        payload,
                    )
                    record_id = int(cur.lastrowid)
                    status = "inserted"

            if ingestion_run_id is not None:
                increments = {
                    "inserted": (1, 1, 0, 0),
                    "updated": (1, 0, 1, 0),
                    "duplicate": (1, 0, 0, 1),
                }[status]
                self._increment_ingestion_run(
                    conn,
                    ingestion_run_id,
                    total=increments[0],
                    new=increments[1],
                    updated=increments[2],
                    duplicate=increments[3],
                )

            conn.commit()

        return RecordOperationResult(
            status=status,
            record_id=record_id,
            duplicate_of=duplicate_of,
            ingestion_run_id=ingestion_run_id,
            message=self._result_message(status, duplicate_of),
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def get_records_for_day(
        self,
        day: Union[str, date, datetime],
        *,
        category: Optional[str] = None,
        company: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        day_str = self._extract_date(day)
        query = ["SELECT * FROM records WHERE date(publish_date) = ?"]
        params: List[Any] = [day_str]
        if category:
            query.append("AND category = ?")
            params.append(category)
        if region:
            query.append("AND region = ?")
            params.append(region)

        with self._connect() as conn:
            rows = conn.execute(" ".join(query), params).fetchall()

        records = [self._row_to_dict(row) for row in rows]
        if company:
            company_lower = company.lower()
            records = [
                record
                for record in records
                if any(company_lower == entry.lower() for entry in record.get("companies", []))
            ]
        return records

    def get_records_by_category(
        self,
        category: str,
        *,
        start_date: Optional[Union[str, date, datetime]] = None,
        end_date: Optional[Union[str, date, datetime]] = None,
    ) -> List[Dict[str, Any]]:
        query = ["SELECT * FROM records WHERE category = ?"]
        params: List[Any] = [category]
        if start_date:
            query.append("AND date(publish_date) >= ?")
            params.append(self._extract_date(start_date))
        if end_date:
            query.append("AND date(publish_date) <= ?")
            params.append(self._extract_date(end_date))

        with self._connect() as conn:
            rows = conn.execute(" ".join(query), params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_records_by_company(
        self,
        company: str,
        *,
        start_date: Optional[Union[str, date, datetime]] = None,
        end_date: Optional[Union[str, date, datetime]] = None,
        categories: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        query = ["SELECT * FROM records"]
        params: List[Any] = []
        filters: List[str] = []
        if start_date:
            filters.append("date(publish_date) >= ?")
            params.append(self._extract_date(start_date))
        if end_date:
            filters.append("date(publish_date) <= ?")
            params.append(self._extract_date(end_date))
        category_list: Optional[List[str]] = None
        if categories:
            category_list = list(categories)
            if category_list:
                placeholders = ",".join("?" for _ in category_list)
                filters.append(f"category IN ({placeholders})")
                params.extend(category_list)
        if filters:
            query.append("WHERE" + " AND ".join(filters))

        with self._connect() as conn:
            rows = conn.execute(" ".join(query), params).fetchall()

        company_lower = company.lower()
        results: List[Dict[str, Any]] = []
        for row in rows:
            record = self._row_to_dict(row)
            companies_list = [entry.lower() for entry in record.get("companies", [])]
            if company_lower in companies_list:
                results.append(record)
        return results

    def get_ingestion_metrics(
        self,
        *,
        start_date: Optional[Union[str, date, datetime]] = None,
        end_date: Optional[Union[str, date, datetime]] = None,
    ) -> Dict[str, Any]:
        query = ["SELECT * FROM ingestion_runs"]
        params: List[Any] = []
        filters: List[str] = []
        if start_date:
            filters.append("date(started_at) >= ?")
            params.append(self._extract_date(start_date))
        if end_date:
            filters.append("date(started_at) <= ?")
            params.append(self._extract_date(end_date))
        if filters:
            query.append("WHERE" + " AND ".join(filters))

        with self._connect() as conn:
            rows = conn.execute(" ".join(query), params).fetchall()

        total_runs = len(rows)
        totals = {
            "total_runs": total_runs,
            "records_processed": 0,
            "new_records": 0,
            "updated_records": 0,
            "duplicate_records": 0,
        }
        for row in rows:
            totals["records_processed"] += row["total_records"] or 0
            totals["new_records"] += row["new_records"] or 0
            totals["updated_records"] += row["updated_records"] or 0
            totals["duplicate_records"] += row["duplicate_records"] or 0
        return totals

    def search_records(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Full-text search across title, summary and content."""
        sql = (
            "SELECT records.* FROM records "
            "JOIN records_fts ON records_fts.rowid = records.id "
            "WHERE records_fts MATCH ? ORDER BY records.publish_date DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, (query, limit)).fetchall()
        return [self._row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["companies"] = self._from_json(data.get("companies"), default=[])
        data["metadata"] = self._from_json(data.get("metadata"), default={})
        return data

    @staticmethod
    def _to_json(value: Optional[Any]) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value, sort_keys=True)

    @staticmethod
    def _from_json(value: Optional[str], default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    def _normalize_timestamp(
        self,
        value: Optional[Union[str, date, datetime]],
        default_to_now: bool = False,
    ) -> Optional[str]:
        if value is None:
            return _utc_now() if default_to_now else None
        if isinstance(value, datetime):
            if value.tzinfo:
                value = value.astimezone(timezone.utc).replace(tzinfo=None)
            return value.replace(microsecond=0).isoformat() + ISO_TIMESTAMP_SUFFIX
        if isinstance(value, date):
            return datetime.combine(value, datetime.min.time()).isoformat() + ISO_TIMESTAMP_SUFFIX
        text = value.strip()
        if not text:
            return _utc_now() if default_to_now else None
        return text

    @staticmethod
    def _extract_date(value: Union[str, date, datetime]) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if "T" in value:
            return value.split("T")[0]
        return value

    @staticmethod
    def _result_message(status: str, duplicate_of: Optional[int]) -> Optional[str]:
        if status == "inserted":
            return "record inserted"
        if status == "updated":
            return "existing record updated"
        if status == "duplicate" and duplicate_of is not None:
            return f"duplicate of record {duplicate_of}"
        return None


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="IVD monitor database helper")
    parser.add_argument("--init", action="store_true", help="Initialise the IVD database schema")
    parser.add_argument("--db-path", help="Override database path", default=None)
    args = parser.parse_args(argv)

    db = IVDDatabase(db_path=args.db_path, auto_initialize=False)
    if args.init:
        db.initialize()
        print(f"Initialised IVD database at {db.db_path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
