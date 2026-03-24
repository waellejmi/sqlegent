"""Compatibility alias for dbcore connection modules."""

from importlib import import_module

_dbcore_connections = import_module("dbcore.connections")
__path__ = list(getattr(_dbcore_connections, "__path__", []))
