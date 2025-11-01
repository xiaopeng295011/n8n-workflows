"""Categorization module for IVD records.

Provides utilities to map source identifiers and textual cues to the digest
categories used by the IVD monitor. The classifier combines source-based rules
with keyword heuristics and supports manual overrides via metadata.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence


class CategoryClassifier:
    """Classifies records into predefined digest categories."""

    CATEGORY_FINANCIAL = "financial_reports"
    CATEGORY_PRODUCT_LAUNCH = "product_launches"
    CATEGORY_BIDDING = "bidding_tendering"
    CATEGORY_NHSA_POLICY = "nhsa_policy"
    CATEGORY_NHC_POLICY = "nhc_policy"
    CATEGORY_INDUSTRY_MEDIA = "industry_media"
    CATEGORY_UNKNOWN = "unknown"

    ALL_CATEGORIES = [
        CATEGORY_FINANCIAL,
        CATEGORY_PRODUCT_LAUNCH,
        CATEGORY_BIDDING,
        CATEGORY_NHSA_POLICY,
        CATEGORY_NHC_POLICY,
        CATEGORY_INDUSTRY_MEDIA,
    ]

    TITLE_WEIGHT = 5
    SUMMARY_WEIGHT = 3
    CONTENT_WEIGHT = 1

    CATEGORY_SYNONYMS: Dict[str, set[str]] = {
        CATEGORY_FINANCIAL: {
            "financial",
            "finance",
            "financial report",
            "financial reports",
            "financial_report",
            "financial_reports",
            "财报",
            "财务",
            "财报资讯",
            "财务报告",
            "业绩",
        },
        CATEGORY_PRODUCT_LAUNCH: {
            "product",
            "product launch",
            "product_launch",
            "launch",
            "approval",
            "产品上市",
            "新品",
            "获批",
        },
        CATEGORY_BIDDING: {
            "bidding",
            "tender",
            "招标",
            "招标采购",
            "集中采购",
            "采购",
        },
        CATEGORY_NHSA_POLICY: {
            "nhsa",
            "medical insurance",
            "医保",
            "医保政策",
            "医保局",
            "medical security",
        },
        CATEGORY_NHC_POLICY: {
            "nhc",
            "卫健委",
            "卫生健康委",
            "health commission",
        },
        CATEGORY_INDUSTRY_MEDIA: {
            "industry",
            "industry media",
            "媒体",
            "行业媒体",
            "市场分析",
            "analysis",
        },
    }

    def __init__(self, custom_rules: Optional[Dict[str, Any]] = None) -> None:
        self.custom_rules = custom_rules or {}
        self._alias_lookup = self._build_alias_lookup()
        self._init_rules()

    def _build_alias_lookup(self) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        for canonical, synonyms in self.CATEGORY_SYNONYMS.items():
            for alias in {canonical, *synonyms}:
                lookup[alias.lower()] = canonical
        return lookup

    def normalize_category_name(self, category: Optional[str]) -> Optional[str]:
        """Normalise a category string (English or Chinese) to canonical form."""
        if not category:
            return None
        normalized = category.strip().lower()
        return self._alias_lookup.get(normalized)

    def _init_rules(self) -> None:
        """Initialise source and keyword rules."""
        self.source_rules: Dict[str, str] = {
            # Financial
            "cninfo": self.CATEGORY_FINANCIAL,
            "eastmoney": self.CATEGORY_FINANCIAL,
            "东方财富": self.CATEGORY_FINANCIAL,
            "巨潮资讯": self.CATEGORY_FINANCIAL,
            "investor": self.CATEGORY_FINANCIAL,
            "financial": self.CATEGORY_FINANCIAL,
            # NHSA
            "nhsa": self.CATEGORY_NHSA_POLICY,
            "医保局": self.CATEGORY_NHSA_POLICY,
            "医疗保障局": self.CATEGORY_NHSA_POLICY,
            # NHC
            "nhc": self.CATEGORY_NHC_POLICY,
            "卫健委": self.CATEGORY_NHC_POLICY,
            "卫生健康委": self.CATEGORY_NHC_POLICY,
            # Bidding
            "招标": self.CATEGORY_BIDDING,
            "采购": self.CATEGORY_BIDDING,
            "集采": self.CATEGORY_BIDDING,
            "bidding": self.CATEGORY_BIDDING,
            "tender": self.CATEGORY_BIDDING,
            # Industry media (handled by fallback/keywords)
        }

        self.keyword_rules: Dict[str, List[str]] = {
            self.CATEGORY_FINANCIAL: [
                r"财报|年报|季报|业绩|营收|利润|净利",
                r"财务报告|经营报告|股东大会|投资者",
                r"financial\s+report|earnings|revenue|profit",
                r"公告.*业绩|披露.*财务",
            ],
            self.CATEGORY_PRODUCT_LAUNCH: [
                r"上市|新品|推出|问世",
                r"获批|批准|注册证|NMPA|FDA",
                r"产品.*上市|新产品|产品发布",
                r"launch|approval|clearance",
            ],
            self.CATEGORY_BIDDING: [
                r"招标|中标|投标|采购",
                r"集采|集中采购|带量采购",
                r"中标.*公告|招标.*公告|成交.*公告",
                r"bidding|tender|procurement",
            ],
            self.CATEGORY_NHSA_POLICY: [
                r"医保局|医疗保障局",
                r"医保.*政策|医保.*目录|医保.*支付",
                r"医保.*谈判|医保.*准入|医保.*价格",
                r"DRG|DIP|医保.*基金",
            ],
            self.CATEGORY_NHC_POLICY: [
                r"卫健委|卫生健康委",
                r"卫生.*政策|医疗.*管理|医院.*管理",
                r"临床.*指南|诊疗.*规范|技术.*标准",
                r"疫情.*防控|公共卫生",
            ],
            self.CATEGORY_INDUSTRY_MEDIA: [
                r"行业.*分析|市场.*分析|趋势.*分析",
                r"专家.*解读|深度.*解析|观察",
                r"行业.*动态|市场.*动态",
            ],
        }

        if self.custom_rules:
            if "sources" in self.custom_rules:
                self.source_rules.update(self.custom_rules["sources"])
            if "keywords" in self.custom_rules:
                for category, patterns in self.custom_rules["keywords"].items():
                    if category in self.keyword_rules:
                        self.keyword_rules[category].extend(patterns)
                    else:
                        self.keyword_rules[category] = list(patterns)

    def categorize(
        self,
        *,
        source: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        content: Optional[str] = None,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Categorise a record using source and textual cues."""
        metadata_dict: Dict[str, Any]
        if isinstance(metadata, dict):
            metadata_dict = metadata
        else:
            metadata_dict = {}

        for key in ("category_override", "category"):
            if key in metadata_dict:
                normalized = self.normalize_category_name(metadata_dict[key])
                if normalized:
                    return normalized

        category = self._categorize_by_source(source, url=url)
        if category:
            return category

        category = self._categorize_by_keywords_weighted(title, summary, content)
        if category:
            return category

        return self.CATEGORY_INDUSTRY_MEDIA

    def _categorize_by_source(self, source: str, *, url: Optional[str]) -> Optional[str]:
        source_lower = source.lower()
        for pattern, category in self.source_rules.items():
            if pattern.lower() in source_lower:
                return category
        if url:
            url_lower = url.lower()
            for pattern, category in self.source_rules.items():
                if pattern.lower() in url_lower:
                    return category
        return None

    def _categorize_by_keywords_weighted(
        self, title: Optional[str], summary: Optional[str], content: Optional[str]
    ) -> Optional[str]:
        """Categorize using weighted scoring for title, summary, content."""
        if not any([title, summary, content]):
            return None

        scores: Dict[str, float] = {category: 0.0 for category in self.ALL_CATEGORIES}

        for category, patterns in self.keyword_rules.items():
            for pattern in patterns:
                if title:
                    title_matches = len(re.findall(pattern, title, flags=re.IGNORECASE))
                    scores[category] += title_matches * self.TITLE_WEIGHT
                if summary:
                    summary_matches = len(re.findall(pattern, summary, flags=re.IGNORECASE))
                    scores[category] += summary_matches * self.SUMMARY_WEIGHT
                if content:
                    content_matches = len(re.findall(pattern, content, flags=re.IGNORECASE))
                    scores[category] += content_matches * self.CONTENT_WEIGHT

        category, score = max(scores.items(), key=lambda item: item[1])
        if score > 0:
            return category
        return None

    def get_category_display_name(self, category: str, *, language: str = "en") -> str:
        """Return human friendly display name for a category."""
        display_names = {
            self.CATEGORY_FINANCIAL: {"en": "Financial Reports", "zh": "财报资讯"},
            self.CATEGORY_PRODUCT_LAUNCH: {"en": "Product Launches", "zh": "产品上市"},
            self.CATEGORY_BIDDING: {"en": "Bidding & Tendering", "zh": "招标采购"},
            self.CATEGORY_NHSA_POLICY: {"en": "NHSA Policy", "zh": "医保政策"},
            self.CATEGORY_NHC_POLICY: {"en": "NHC Policy", "zh": "卫健委政策"},
            self.CATEGORY_INDUSTRY_MEDIA: {"en": "Industry Media", "zh": "行业媒体"},
            self.CATEGORY_UNKNOWN: {"en": "Unknown", "zh": "未分类"},
        }
        category_key = self.normalize_category_name(category) or category
        names = display_names.get(category_key, display_names[self.CATEGORY_UNKNOWN])
        return names.get(language, names["en"])


def enrich_record_with_category(
    record: Dict[str, Any],
    *,
    classifier: Optional[CategoryClassifier] = None,
) -> Dict[str, Any]:
    """Populate the ``category`` field on a record dict using the classifier."""
    classifier = classifier or CategoryClassifier()
    category = classifier.categorize(
        source=record.get("source", ""),
        title=record.get("title"),
        summary=record.get("summary"),
        content=record.get("content_html"),
        url=record.get("url"),
        metadata=record.get("metadata"),
    )
    record["category"] = category
    return record


def enrich_records(
    records: Sequence[Dict[str, Any]],
    *,
    company_matcher: Optional[Any] = None,
    category_classifier: Optional[CategoryClassifier] = None,
) -> List[Dict[str, Any]]:
    """Enrich multiple records with company matches and categories."""
    category_classifier = category_classifier or CategoryClassifier()

    if company_matcher is None:
        from src.ivd_monitor.company_matching import CompanyMatcher

        company_matcher = CompanyMatcher()

    enriched_records: List[Dict[str, Any]] = []
    for record in records:
        enriched = dict(record)
        if enriched.get("companies"):
            enriched["companies"] = company_matcher.normalize_names(enriched["companies"])
        else:
            companies = company_matcher.match_companies(
                enriched.get("content_html"),
                title=enriched.get("title"),
                summary=enriched.get("summary"),
                metadata=enriched.get("metadata"),
            )
            enriched["companies"] = companies

        category = category_classifier.categorize(
            source=enriched.get("source", ""),
            title=enriched.get("title"),
            summary=enriched.get("summary"),
            content=enriched.get("content_html"),
            url=enriched.get("url"),
            metadata=enriched.get("metadata"),
        )
        enriched["category"] = category

        enriched_records.append(enriched)

    return enriched_records
