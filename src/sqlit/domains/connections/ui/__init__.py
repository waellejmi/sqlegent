"""Compatibility alias for dbcore UI modules."""

from importlib import import_module

_dbcore_ui = import_module("dbcore.ui")
__path__ = list(getattr(_dbcore_ui, "__path__", []))
