"""Basic error modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static


class ErrorScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("enter", "close", "OK", priority=True),
        Binding("escape", "close", "Close", priority=True),
    ]

    def __init__(self, title: str, message: str):
        super().__init__()
        self.title_text = title
        self.message = message

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.title_text}[/]\n\n{self.message}")

    def action_close(self) -> None:
        self.dismiss(None)
