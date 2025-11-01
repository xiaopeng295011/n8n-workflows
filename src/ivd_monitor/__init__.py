"""IVD Monitor package namespace."""

from importlib import import_module
from typing import Any

__all__ = [
    "IVDDatabase",
    "CompanyMatcher",
    "CategoryClassifier",
    "EmailDigestBuilder",
    "DigestConfig",
    "enrich_record_with_companies",
    "enrich_record_with_category",
    "enrich_records",
]


def __getattr__(name: str) -> Any:
    if name == "IVDDatabase":
        module = import_module("src.ivd_monitor.database")
        return getattr(module, name)
    elif name == "CompanyMatcher" or name == "enrich_record_with_companies":
        module = import_module("src.ivd_monitor.company_matching")
        return getattr(module, name)
    elif name in ("CategoryClassifier", "enrich_record_with_category", "enrich_records"):
        module = import_module("src.ivd_monitor.categorization")
        return getattr(module, name)
    elif name in ("EmailDigestBuilder", "DigestConfig"):
        module = import_module("src.ivd_monitor.email_builder")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
