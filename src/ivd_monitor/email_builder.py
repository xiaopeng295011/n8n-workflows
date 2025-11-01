"""Email digest builder for IVD monitor.

Queries the database for a specific day's records, organizes them by category
and company, and renders both HTML and plaintext email digests using Jinja2
templates. Supports configuration for subject lines, intro text, and metadata
injection while keeping content generation independent of email transport.
"""

from __future__ import annotations

import csv
import io
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .categorization import CategoryClassifier
from .database import IVDDatabase


@dataclass
class DigestConfig:
    """Configuration for email digest generation."""

    subject_format: str = "IVD Monitor Daily Digest - {date}"
    intro_text: str = (
        "Welcome to your daily IVD Monitor digest. "
        "Below is a summary of today's regulatory intelligence, market updates, "
        "and industry news organized by category and company."
    )
    default_recipients: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.default_recipients is None:
            self.default_recipients = []
        else:
            self.default_recipients = [
                recipient.strip() for recipient in self.default_recipients if recipient.strip()
            ]

    @classmethod
    def from_env(cls) -> "DigestConfig":
        """Load configuration from environment variables."""
        recipients_raw = os.environ.get("IVD_DIGEST_RECIPIENTS")
        recipients: Optional[List[str]]
        if recipients_raw:
            recipients = [part.strip() for part in recipients_raw.split(",") if part.strip()]
        else:
            recipients = []

        return cls(
            subject_format=os.environ.get(
                "IVD_DIGEST_SUBJECT_FORMAT",
                "IVD Monitor Daily Digest - {date}",
            ),
            intro_text=os.environ.get(
                "IVD_DIGEST_INTRO_TEXT",
                (
                    "Welcome to your daily IVD Monitor digest. "
                    "Below is a summary of today's regulatory intelligence, market updates, "
                    "and industry news organized by category and company."
                ),
            ),
            default_recipients=recipients,
        )


class EmailDigestBuilder:
    """Builds email digests from IVD monitor data."""

    CATEGORY_DISPLAY_NAMES = {
        CategoryClassifier.CATEGORY_FINANCIAL: "Financial Reports 财报资讯",
        CategoryClassifier.CATEGORY_PRODUCT_LAUNCH: "Product Launches 产品上市",
        CategoryClassifier.CATEGORY_BIDDING: "Bidding & Tendering 招标采购",
        CategoryClassifier.CATEGORY_NHSA_POLICY: "NHSA Policy 医保政策",
        CategoryClassifier.CATEGORY_NHC_POLICY: "NHC Policy 卫健委政策",
        CategoryClassifier.CATEGORY_INDUSTRY_MEDIA: "Industry Media 行业媒体",
        CategoryClassifier.CATEGORY_UNKNOWN: "Other Updates 其他动态",
        "unknown": "Other Updates 其他动态",
    }

    CATEGORY_ORDER = [
        CategoryClassifier.CATEGORY_NHSA_POLICY,
        CategoryClassifier.CATEGORY_NHC_POLICY,
        CategoryClassifier.CATEGORY_FINANCIAL,
        CategoryClassifier.CATEGORY_PRODUCT_LAUNCH,
        CategoryClassifier.CATEGORY_BIDDING,
        CategoryClassifier.CATEGORY_INDUSTRY_MEDIA,
        CategoryClassifier.CATEGORY_UNKNOWN,
        "unknown",
    ]

    def __init__(
        self,
        db: Optional[IVDDatabase] = None,
        config: Optional[DigestConfig] = None,
        template_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.db = db or IVDDatabase()
        self.config = config or DigestConfig()
        self.classifier = CategoryClassifier()

        if template_dir is None:
            project_root = Path(__file__).parent.parent.parent
            template_dir = project_root / "templates" / "ivd"
        else:
            template_dir = Path(template_dir)

        self.template_dir = template_dir
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def build_digest(
        self,
        target_date: Union[str, date, datetime],
        *,
        failed_sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build digest data structure for a specific day.

        Args:
            target_date: The date to generate the digest for
            failed_sources: Optional list of source names that failed to fetch

        Returns:
            Dictionary containing organized digest data
        """
        if isinstance(target_date, (date, datetime)):
            date_str = target_date.strftime("%Y-%m-%d")
        else:
            date_str = target_date

        records = self.db.get_records_for_day(target_date)

        organized, unique_keys = self._organize_records(records)

        digest_data = {
            "digest_date": date_str,
            "subject": self.config.subject_format.format(date=date_str),
            "intro_text": self.config.intro_text,
            "categories": organized,
            "total_count": len(unique_keys),
            "category_count": len([c for c in organized if organized[c]["count"] > 0]),
            "company_count": len(self._get_unique_companies(records)),
            "failed_sources": failed_sources or [],
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "recipients": list(self.config.default_recipients),
        }

        return digest_data

    def _organize_records(self, records: List[Dict[str, Any]]) -> tuple[Dict[str, Any], set[Any]]:
        """Organize records by category and company.
        
        Returns:
            Tuple of (organized_data, unique_record_keys)
        """
        categorized: Dict[str, Dict[str, Any]] = {}
        seen_keys: set[Any] = set()

        for record in records:
            record_key = record.get("id") or record.get("url")
            if record_key in seen_keys:
                continue
            seen_keys.add(record_key)

            category = record.get("category") or "unknown"
            companies = record.get("companies", []) or ["Uncategorized"]

            processed_record = self._format_record(record)

            category_bucket = categorized.setdefault(
                category,
                {
                    "records_by_company": defaultdict(list),
                    "unique_records": set(),
                },
            )
            category_bucket["unique_records"].add(record_key)

            for company in companies:
                category_bucket["records_by_company"][company].append(processed_record)

        result: Dict[str, Any] = {}
        for category_key in self.CATEGORY_ORDER:
            if category_key in categorized:
                company_records = categorized[category_key]["records_by_company"]
                sorted_companies = sorted(company_records.keys())
                result[category_key] = {
                    "display_name": self.CATEGORY_DISPLAY_NAMES.get(
                        category_key, category_key
                    ),
                    "count": len(categorized[category_key]["unique_records"]),
                    "records_by_company": {
                        company: company_records[company]
                        for company in sorted_companies
                    },
                }

        for category_key in sorted(categorized.keys()):
            if category_key not in result:
                company_records = categorized[category_key]["records_by_company"]
                sorted_companies = sorted(company_records.keys())
                result[category_key] = {
                    "display_name": self.CATEGORY_DISPLAY_NAMES.get(
                        category_key, category_key
                    ),
                    "count": len(categorized[category_key]["unique_records"]),
                    "records_by_company": {
                        company: company_records[company]
                        for company in sorted_companies
                    },
                }

        return result, seen_keys

    def _format_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Format a record for display in the digest."""
        publish_date = record.get("publish_date", "")
        if publish_date:
            if "T" in publish_date:
                publish_date = publish_date.split("T")[0]

        return {
            "id": record.get("id"),
            "title": record.get("title", "Untitled"),
            "summary": record.get("summary", ""),
            "url": record.get("url", ""),
            "source": record.get("source", "Unknown"),
            "publish_date": publish_date,
        }

    def _get_unique_companies(self, records: List[Dict[str, Any]]) -> set[str]:
        """Extract unique company names from records."""
        companies = set()
        for record in records:
            for company in record.get("companies", []):
                companies.add(company)
        return companies

    def render_html(self, digest_data: Dict[str, Any]) -> str:
        """Render HTML email from digest data."""
        template = self.jinja_env.get_template("ivd_digest.html")
        return template.render(**digest_data)

    def render_text(self, digest_data: Dict[str, Any]) -> str:
        """Render plaintext email from digest data."""
        template = self.jinja_env.get_template("ivd_digest.txt")
        return template.render(**digest_data)

    def render_digest(
        self,
        target_date: Union[str, date, datetime],
        *,
        failed_sources: Optional[List[str]] = None,
    ) -> tuple[str, str]:
        """Render both HTML and plaintext versions of the digest.

        Args:
            target_date: The date to generate the digest for
            failed_sources: Optional list of source names that failed to fetch

        Returns:
            Tuple of (html_content, text_content)
        """
        digest_data = self.build_digest(target_date, failed_sources=failed_sources)
        html_content = self.render_html(digest_data)
        text_content = self.render_text(digest_data)
        return html_content, text_content

    def export_to_csv(
        self,
        target_date: Union[str, date, datetime],
    ) -> str:
        """Export digest data to CSV format.

        Args:
            target_date: The date to export data for

        Returns:
            CSV content as string
        """
        records = self.db.get_records_for_day(target_date)

        output = io.StringIO()
        fieldnames = [
            "id",
            "category",
            "companies",
            "title",
            "summary",
            "source",
            "publish_date",
            "url",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            writer.writerow(
                {
                    "id": record.get("id", ""),
                    "category": record.get("category", ""),
                    "companies": ";".join(record.get("companies", [])),
                    "title": record.get("title", ""),
                    "summary": record.get("summary", ""),
                    "source": record.get("source", ""),
                    "publish_date": record.get("publish_date", ""),
                    "url": record.get("url", ""),
                }
            )

        return output.getvalue()

    def preview_digest(
        self,
        target_date: Union[str, date, datetime],
        *,
        failed_sources: Optional[List[str]] = None,
        output_format: str = "html",
    ) -> str:
        """Preview digest in specified format.

        Args:
            target_date: The date to preview
            failed_sources: Optional list of failed sources
            output_format: 'html', 'text', or 'csv'

        Returns:
            Rendered content in requested format
        """
        if output_format == "csv":
            return self.export_to_csv(target_date)
        elif output_format == "text":
            digest_data = self.build_digest(target_date, failed_sources=failed_sources)
            return self.render_text(digest_data)
        else:
            digest_data = self.build_digest(target_date, failed_sources=failed_sources)
            return self.render_html(digest_data)


def main() -> None:
    """CLI helper for previewing digest locally."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Preview IVD Monitor email digest")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date to generate digest for (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--format",
        choices=["html", "text", "csv"],
        default="html",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (defaults to stdout)",
    )
    parser.add_argument(
        "--db-path",
        help="Path to IVD database",
    )
    parser.add_argument(
        "--failed-sources",
        nargs="+",
        help="List of failed source names to include in metadata",
    )

    args = parser.parse_args()

    db = IVDDatabase(db_path=args.db_path) if args.db_path else IVDDatabase()
    config = DigestConfig.from_env()
    builder = EmailDigestBuilder(db=db, config=config)

    try:
        content = builder.preview_digest(
            args.date,
            failed_sources=args.failed_sources,
            output_format=args.format,
        )

        if args.output:
            output_path = Path(args.output)
            output_path.write_text(content, encoding="utf-8")
            print(f"Digest written to {output_path}", file=sys.stderr)
        else:
            print(content)

    except Exception as e:
        print(f"Error generating digest: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
