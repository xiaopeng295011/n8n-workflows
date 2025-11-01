import sqlite3
from datetime import date

import pytest

from src.ivd_monitor.database import IVDDatabase


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "ivd_monitor.db"


@pytest.fixture
def ivd_db(db_path):
    db = IVDDatabase(db_path=str(db_path))
    db.initialize()
    return db


def test_initialize_creates_schema(db_path):
    db = IVDDatabase(db_path=str(db_path))
    db.initialize()

    conn = sqlite3.connect(str(db_path))
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()

    assert "records" in tables
    assert "ingestion_runs" in tables
    assert "records_fts" in tables


def test_insert_and_deduplicate_by_url(ivd_db, db_path):
    first = ivd_db.insert_record(
        source="rss-feed",
        url="https://example.com/device-1",
        category="Regulatory",
        companies=["Acme Medical"],
        title="Device Update",
        summary="Initial summary",
        content_html="<p>Device update content</p>",
        publish_date="2023-11-01T08:00:00Z",
    )
    assert first.status == "inserted"

    second = ivd_db.insert_record(
        source="rss-feed",
        url="https://example.com/device-1",
        category="Regulatory",
        companies=["Acme Medical"],
        title="Device Update",
        summary="Initial summary",
        content_html="<p>Device update content</p>",
        publish_date="2023-11-01T08:00:00Z",
    )
    assert second.status == "duplicate"
    assert second.duplicate_of == first.record_id

    third = ivd_db.insert_record(
        source="rss-feed",
        url="https://example.com/device-1",
        category="Regulatory",
        companies=["Acme Medical"],
        title="Device Update",
        summary="Updated summary",
        content_html="<p>Updated content</p>",
        publish_date="2023-11-02T09:30:00Z",
    )
    assert third.status == "updated"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT summary, content_html, publish_date FROM records WHERE id = ?", (first.record_id,)).fetchone()
    finally:
        conn.close()

    assert row["summary"] == "Updated summary"
    assert row["content_html"] == "<p>Updated content</p>"
    assert row["publish_date"] == "2023-11-02T09:30:00Z"


def test_insert_duplicate_by_content_hash(ivd_db):
    first = ivd_db.insert_record(
        source="feeds",
        url="https://source-a.example/item-1",
        category="Compliance",
        companies=["MedCo"],
        title="Alert",
        summary="Important alert",
        content_html="<article>Important alert</article>",
        publish_date="2023-10-10T12:00:00Z",
    )
    assert first.status == "inserted"

    duplicate = ivd_db.insert_record(
        source="feeds",
        url="https://source-b.example/item-2",
        category="Compliance",
        companies=["MedCo"],
        title="Alert",
        summary="Important alert",
        content_html="<article>Important alert</article>",
        publish_date="2023-10-10T13:00:00Z",
    )

    assert duplicate.status == "duplicate"
    assert duplicate.duplicate_of == first.record_id

    conn = sqlite3.connect(str(ivd_db.db_path))
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM records").fetchone()
    finally:
        conn.close()

    assert count == 1


def test_query_helpers_and_metrics(ivd_db):
    run_id = ivd_db.start_ingestion_run("rss")

    ivd_db.insert_record(
        source="rss",
        url="https://example.com/report-1",
        category="Regulatory",
        companies=["Acme", "MedCo"],
        title="Regulatory Alert",
        summary="Summary A",
        content_html="<p>A</p>",
        publish_date="2023-11-01T08:00:00Z",
        ingestion_run_id=run_id,
    )
    ivd_db.insert_record(
        source="rss",
        url="https://example.com/report-2",
        category="Finance",
        companies=["Acme"],
        title="Finance News",
        summary="Summary B",
        content_html="<p>B</p>",
        publish_date="2023-11-01T12:00:00Z",
        ingestion_run_id=run_id,
    )
    ivd_db.insert_record(
        source="rss",
        url="https://example.com/report-3",
        category="Regulatory",
        companies=["Globex"],
        title="Reg Update",
        summary="Summary C",
        content_html="<p>C</p>",
        publish_date="2023-11-02T09:00:00Z",
        ingestion_run_id=run_id,
    )
    ivd_db.complete_ingestion_run(run_id)

    day_records = ivd_db.get_records_for_day(date(2023, 11, 1))
    assert len(day_records) == 2

    acme_day = ivd_db.get_records_for_day(date(2023, 11, 1), company="Acme")
    assert len(acme_day) == 2

    regulatory = ivd_db.get_records_by_category("Regulatory")
    assert len(regulatory) == 2

    acme_records = ivd_db.get_records_by_company("Acme")
    assert len(acme_records) == 2

    metrics = ivd_db.get_ingestion_metrics()
    assert metrics["total_runs"] == 1
    assert metrics["records_processed"] == 3
    assert metrics["new_records"] == 3
    assert metrics["duplicate_records"] == 0
