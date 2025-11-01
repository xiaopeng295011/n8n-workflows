"""IVD Monitor package namespace."""

from importlib import import_module
from typing import Any

__all__ = ["IVDDatabase"]


def __getattr__(name: str) -> Any:
    if name == "IVDDatabase":
        module = import_module("src.ivd_monitor.database")
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
