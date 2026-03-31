"""No-op tree builder fallbacks.

These are lightweight placeholders so import resolution remains stable
while tree code is migrated.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def refresh_tree_chunked(app: Any, on_done: Callable[[], None] | None = None) -> None:
    if on_done is not None:
        try:
            on_done()
        except Exception:
            pass


def update_connection_state(app: Any, old_config: Any, new_config: Any) -> None:
    return None


def clear_connecting_indicator(app: Any, previous_config: Any) -> None:
    return None


def ensure_connecting_indicator(app: Any, config: Any) -> None:
    return None


def update_connecting_indicator(app: Any) -> None:
    return None


def remove_connection_nodes(app: Any, names: set[str]) -> None:
    return None
