"""Minimal message modal screen."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static


class MessageScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("enter", "enter", "OK", priority=True),
        Binding("escape", "close", "Close", priority=True),
    ]

    def __init__(
        self,
        title: str,
        message: str,
        *,
        enter_label: str = "OK",
        on_enter: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.title_text = title
        self.message = message
        self.enter_label = enter_label
        self._on_enter = on_enter

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.title_text}[/]\n\n{self.message}")

    def action_enter(self) -> None:
        if self._on_enter is not None:
            self._on_enter()
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
