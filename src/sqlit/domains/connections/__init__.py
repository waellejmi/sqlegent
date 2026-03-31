"""Compatibility alias for dbcore connection modules."""

from importlib import import_module
from pathlib import Path

_dbcore_connections = import_module("dbcore.connections")
_local_path = str(Path(__file__).resolve().parent)
__path__ = [_local_path, *list(getattr(_dbcore_connections, "__path__", []))]
