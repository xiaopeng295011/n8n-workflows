"""IVD Monitor package namespace."""

from importlib import import_module
from typing import Any

_DYNAMIC_IMPORTS = {
    "IVDDatabase": ("src.ivd_monitor.database", "IVDDatabase"),
    "BaseCollector": ("src.ivd_monitor.collector", "BaseCollector"),
    "SyncCollector": ("src.ivd_monitor.collector", "SyncCollector"),
    "CollectorManager": ("src.ivd_monitor.collector_manager", "CollectorManager"),
    "CollectorConfig": ("src.ivd_monitor.models", "CollectorConfig"),
    "CollectorStats": ("src.ivd_monitor.models", "CollectorStats"),
    "CollectorError": ("src.ivd_monitor.models", "CollectorError"),
    "CollectionResult": ("src.ivd_monitor.models", "CollectionResult"),
    "CollectorManagerResult": ("src.ivd_monitor.models", "CollectorManagerResult"),
    "RawRecord": ("src.ivd_monitor.models", "RawRecord"),
    "ExampleRSSCollector": ("src.ivd_monitor.example_collector", "ExampleRSSCollector"),
}

__all__ = sorted(_DYNAMIC_IMPORTS.keys())


def __getattr__(name: str) -> Any:
    if name in _DYNAMIC_IMPORTS:
        module_name, attr = _DYNAMIC_IMPORTS[name]
        module = import_module(module_name)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return list(__all__)
