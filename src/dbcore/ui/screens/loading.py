"""Minimal loading modal screen."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static


class LoadingScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

    def __init__(self, message: str, on_cancel: Callable[[], None] | None = None):
        super().__init__()
        self.message = message
        self._on_cancel = on_cancel

    def compose(self) -> ComposeResult:
        yield Static(self.message)

    def action_cancel(self) -> None:
        if self._on_cancel is not None:
            self._on_cancel()
