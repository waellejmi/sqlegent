"""Compatibility shim for startup profiling helpers."""

from sqlit.shared.app.startup_profiler import configure, enable_import_timing, span

__all__ = ["configure", "enable_import_timing", "span"]
