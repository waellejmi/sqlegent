"""Basic confirm modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static


class ConfirmScreen(ModalScreen[bool | None]):
    BINDINGS = [
        Binding("y", "confirm", "Yes", priority=True),
        Binding("enter", "confirm", "Yes", show=False),
        Binding("n", "cancel", "No", priority=True),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, title: str, message: str | None = None):
        super().__init__()
        self.title_text = title
        self.message = message or ""

    def compose(self) -> ComposeResult:
        text = (
            self.title_text
            if not self.message
            else f"{self.title_text}\n\n{self.message}"
        )
        yield Static(text)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(None)
