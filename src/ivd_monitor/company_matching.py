"""Company matching module for IVD records.

Provides fuzzy matching, alias resolution and keyword heuristics to identify
companies mentioned in ingested content. The matcher is driven by the
``config/ivd_companies.json`` dataset and can be customised with overrides and
blacklists to fine-tune behaviour for specific sources.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from rapidfuzz import fuzz, process

DEFAULT_COMPANY_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "ivd_companies.json"
DEFAULT_MATCH_THRESHOLD = 85
DEFAULT_PARTIAL_THRESHOLD = 90


@dataclass
class CompanyMatch:
    """Represents a matched company with associated metadata."""

    company_name: str
    matched_text: str
    score: float
    match_type: str  # "exact", "fuzzy", "alias", "keyword", "hint", "override"


def _unique_preserve_order(values: Iterable[str]) -> List[str]:
    """Return unique truthy values while preserving their first-seen order."""
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        if not value:
            continue
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


class CompanyMatcher:
    """Matches company names in text using fuzzy matching and heuristics."""

    def __init__(
        self,
        *,
        config_path: Optional[Path] = None,
        match_threshold: int = DEFAULT_MATCH_THRESHOLD,
        partial_threshold: int = DEFAULT_PARTIAL_THRESHOLD,
        manual_overrides: Optional[Dict[str, str]] = None,
        blacklist: Optional[Sequence[str]] = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path else DEFAULT_COMPANY_CONFIG_PATH
        self.match_threshold = match_threshold
        self.partial_threshold = partial_threshold
        self.manual_overrides = {k: v for k, v in (manual_overrides or {}).items()}
        self.blacklist = set(blacklist or [])

        self._companies: List[Dict[str, Any]] = []
        self._company_lookup: Dict[str, str] = {}
        self._alias_lookup: Dict[str, str] = {}
        self._keyword_lookup: Dict[str, str] = {}
        self._load_companies()

    def _load_companies(self) -> None:
        """Load company data from configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Company config not found at {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._companies = data.get("companies", [])

        for company in self._companies:
            name = company["name"]
            self._company_lookup[name.lower()] = name

            english_name = company.get("english_name")
            if english_name:
                self._company_lookup[english_name.lower()] = name

            for alias in company.get("aliases", []):
                self._alias_lookup[alias.lower()] = name

            for keyword in company.get("keywords", []):
                self._keyword_lookup[keyword.lower()] = name

    def _canonicalize_name(self, name: Optional[str]) -> Optional[str]:
        """Return canonical company name for supplied identifier."""
        if not name:
            return None
        lowered = name.lower()
        if lowered in self._company_lookup:
            return self._company_lookup[lowered]
        if lowered in self._alias_lookup:
            return self._alias_lookup[lowered]
        for company in self._companies:
            if company["name"].lower() == lowered:
                return company["name"]
            english_name = company.get("english_name")
            if english_name and english_name.lower() == lowered:
                return company["name"]
        return None

    def normalize_names(self, names: Sequence[str]) -> List[str]:
        """Normalise a sequence of company identifiers to canonical names."""
        canonical = [self._canonicalize_name(str(name)) or str(name) for name in names]
        return _unique_preserve_order(canonical)

    def match_companies(
        self,
        text: Optional[str],
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Match companies mentioned in provided textual content.

        Args:
            text: Main body text to analyse
            title: Optional title text (weighted more heavily)
            summary: Optional summary text
            metadata: Optional metadata containing overrides/blacklists

        Returns:
            Sorted list of canonical company names identified in the content
        """
        if not isinstance(metadata, dict):
            metadata = {}
        else:
            metadata = dict(metadata)  # shallow copy to avoid mutation

        override_list = metadata.get("companies_override")
        if isinstance(override_list, (list, tuple, set)):
            normalized_override = self.normalize_names([str(item) for item in override_list])
            if normalized_override:
                return sorted(normalized_override)

        text_value = text or ""
        if not text_value and not title and not summary and not metadata.get("company_hints"):
            return []

        combined_text = self._combine_text(text_value, title, summary)
        matches: Dict[str, CompanyMatch] = {}

        # Pattern overrides (global + record-level)
        pattern_overrides: Dict[str, str] = {}
        for pattern, company_name in self.manual_overrides.items():
            canonical = self._canonicalize_name(company_name) or str(company_name)
            pattern_overrides[pattern.lower()] = canonical
        metadata_pattern_overrides = metadata.get("company_overrides")
        if isinstance(metadata_pattern_overrides, dict):
            for pattern, company_name in metadata_pattern_overrides.items():
                canonical = self._canonicalize_name(str(company_name)) or str(company_name)
                pattern_overrides[pattern.lower()] = canonical

        # Blacklists
        text_blacklist_terms: Set[str] = set(self.blacklist)
        metadata_blacklist_terms = metadata.get("company_blacklist_terms")
        if isinstance(metadata_blacklist_terms, (list, tuple, set)):
            text_blacklist_terms.update(str(term) for term in metadata_blacklist_terms)

        name_blacklist: Set[str] = set()
        metadata_name_blacklist = metadata.get("company_blacklist")
        if isinstance(metadata_name_blacklist, (list, tuple, set)):
            for entry in metadata_name_blacklist:
                canonical = self._canonicalize_name(str(entry)) or str(entry)
                name_blacklist.add(canonical)

        # Manual pattern overrides
        if pattern_overrides:
            override_matches = self._match_overrides(combined_text, pattern_overrides)
            for match in override_matches:
                if match.company_name not in name_blacklist:
                    matches[match.company_name] = match

        # Metadata hints force inclusion if recognised
        hints = metadata.get("company_hints")
        if isinstance(hints, (list, tuple, set)):
            for hint in hints:
                canonical = self._canonicalize_name(str(hint)) or str(hint)
                if canonical and canonical not in name_blacklist:
                    matches[canonical] = CompanyMatch(
                        company_name=canonical,
                        matched_text=str(hint),
                        score=100.0,
                        match_type="hint",
                    )

        # Exact name matches
        for match in self._match_exact(combined_text):
            if match.company_name in name_blacklist:
                continue
            matches.setdefault(match.company_name, match)

        # Alias matches
        for match in self._match_aliases(combined_text):
            if match.company_name in name_blacklist:
                continue
            matches.setdefault(match.company_name, match)

        # Keyword associations
        for match in self._match_keywords(combined_text, name_blacklist):
            existing = matches.get(match.company_name)
            if not existing or match.score > existing.score:
                matches[match.company_name] = match

        # Fuzzy matching
        fuzzy_matches = self._match_fuzzy(combined_text, exclude=set(matches.keys()), blacklist=name_blacklist)
        for match in fuzzy_matches:
            if match.company_name in name_blacklist:
                continue
            matches.setdefault(match.company_name, match)

        # Apply text blacklist filters and return sorted unique names
        filtered = {
            name: match
            for name, match in matches.items()
            if not self._is_blacklisted(match.matched_text, text_blacklist_terms)
        }
        return sorted(filtered.keys())

    def _combine_text(
        self,
        text: Optional[str],
        title: Optional[str],
        summary: Optional[str],
    ) -> str:
        """Combine text components with title/summary weighted higher."""
        parts: List[str] = []
        if title:
            parts.extend([title, title])
        if summary:
            parts.extend([summary, summary])
        if text:
            parts.append(text)
        return " ".join(parts)

    def _match_overrides(self, text: str, overrides: Dict[str, str]) -> List[CompanyMatch]:
        """Match using manual override patterns."""
        matches: List[CompanyMatch] = []
        text_lower = text.lower()
        for pattern, company_name in overrides.items():
            if pattern in text_lower:
                matches.append(
                    CompanyMatch(
                        company_name=company_name,
                        matched_text=pattern,
                        score=100.0,
                        match_type="override",
                    )
                )
        return matches

    def _match_exact(self, text: str) -> List[CompanyMatch]:
        """Match using exact substring matching."""
        matches: List[CompanyMatch] = []
        text_lower = text.lower()
        for company_key, company_name in self._company_lookup.items():
            if company_key in text_lower:
                pattern = re.compile(re.escape(company_key), re.IGNORECASE)
                found = pattern.search(text)
                matched_text = found.group(0) if found else company_key
                matches.append(
                    CompanyMatch(
                        company_name=company_name,
                        matched_text=matched_text,
                        score=100.0,
                        match_type="exact",
                    )
                )
        return matches

    def _match_aliases(self, text: str) -> List[CompanyMatch]:
        """Match using alias substring matching."""
        matches: List[CompanyMatch] = []
        text_lower = text.lower()
        for alias_key, company_name in self._alias_lookup.items():
            if alias_key in text_lower:
                pattern = re.compile(re.escape(alias_key), re.IGNORECASE)
                found = pattern.search(text)
                matched_text = found.group(0) if found else alias_key
                matches.append(
                    CompanyMatch(
                        company_name=company_name,
                        matched_text=matched_text,
                        score=95.0,
                        match_type="alias",
                    )
                )
        return matches

    def _match_keywords(self, text: str, blacklist: Set[str]) -> List[CompanyMatch]:
        """Match using product keyword associations."""
        matches: List[CompanyMatch] = []
        text_lower = text.lower()
        keyword_counts: Dict[str, tuple[int, str]] = {}
        for keyword, company_name in self._keyword_lookup.items():
            if keyword in text_lower and company_name not in blacklist:
                count, first_keyword = keyword_counts.get(company_name, (0, keyword))
                keyword_counts[company_name] = (count + 1, first_keyword)
        for company_name, (count, keyword) in keyword_counts.items():
            if count >= 2:
                score = min(70.0 + (count * 5), 90.0)
                matches.append(
                    CompanyMatch(
                        company_name=company_name,
                        matched_text=keyword,
                        score=score,
                        match_type="keyword",
                    )
                )
        return matches

    def _match_fuzzy(self, text: str, *, exclude: Set[str], blacklist: Set[str]) -> List[CompanyMatch]:
        """Match using fuzzy string matching with exclusion and blacklist support."""
        matches: List[CompanyMatch] = []
        searchable_terms = {**self._company_lookup, **self._alias_lookup}
        available_terms = {term: name for term, name in searchable_terms.items() if name not in exclude and name not in blacklist}
        if not available_terms:
            return matches
        segments = self._extract_segments(text)
        for segment in segments:
            if len(segment) < 2:
                continue
            results = process.extract(
                segment,
                available_terms.keys(),
                scorer=fuzz.partial_ratio,
                limit=3,
                score_cutoff=self.partial_threshold,
            )
            for matched_term, score, _ in results:
                company_name = available_terms[matched_term]
                if company_name in exclude or company_name in blacklist:
                    continue
                matches.append(
                    CompanyMatch(
                        company_name=company_name,
                        matched_text=segment,
                        score=float(score),
                        match_type="fuzzy",
                    )
                )
                exclude.add(company_name)
        return matches

    def _extract_segments(self, text: str) -> List[str]:
        """Split text into candidate segments for fuzzy matching."""
        segments = re.split(r"[，。、；：！？\s,.:;!?()\[\]{}]+", text)
        return [segment.strip() for segment in segments if 2 <= len(segment.strip()) <= 24]

    def _is_blacklisted(self, text: str, blacklist_terms: Set[str]) -> bool:
        """Determine if matched text contains blacklisted substrings."""
        lowered = text.lower()
        return any(term.lower() in lowered for term in blacklist_terms)

    def get_company_info(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Return the configuration entry for a canonical company name."""
        for company in self._companies:
            if company["name"] == company_name:
                return company
        return None


def enrich_record_with_companies(
    record: Dict[str, Any],
    *,
    matcher: Optional[CompanyMatcher] = None,
    text_fields: Sequence[str] = ("title", "summary", "content_html"),
) -> Dict[str, Any]:
    """Populate the ``companies`` field on a record dict using matching heuristics."""
    matcher = matcher or CompanyMatcher()
    texts: List[str] = []
    for field in text_fields:
        value = record.get(field)
        if value:
            texts.append(str(value))
    combined_text = " ".join(texts)
    companies = matcher.match_companies(
        combined_text,
        title=record.get("title"),
        summary=record.get("summary"),
        metadata=record.get("metadata"),
    )
    record["companies"] = companies
    return record
