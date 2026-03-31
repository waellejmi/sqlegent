"""Minimal idle scheduler used by dbcore UI mixins."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class Priority(Enum):
    NORMAL = 0


@dataclass
class _IdleScheduler:
    def request_idle_callback(
        self,
        callback: Callable[[], Any],
        *,
        priority: Priority = Priority.NORMAL,
        name: str | None = None,
    ) -> None:
        callback()

    def cancel_all(self, name: str | None = None) -> None:
        return None


_SCHEDULER = _IdleScheduler()


def get_idle_scheduler() -> _IdleScheduler:
    return _SCHEDULER
