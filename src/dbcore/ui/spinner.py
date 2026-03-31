"""Simple spinner helpers used by dbcore UI controllers."""

from __future__ import annotations

from typing import Any, Callable

SPINNER_FRAMES = ["-", "\\", "|", "/"]


class Spinner:
    def __init__(
        self,
        app: Any,
        on_tick: Callable[[str], None] | None = None,
        interval: float = 0.1,
    ) -> None:
        self.app = app
        self.on_tick = on_tick
        self.interval = interval

    def start(self) -> None:
        if callable(self.on_tick):
            self.on_tick(SPINNER_FRAMES[0])

    def stop(self) -> None:
        return None
