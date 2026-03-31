"""Minimal file picker screen interface."""

from __future__ import annotations

from enum import Enum

from textual.screen import ModalScreen


class FilePickerMode(str, Enum):
    OPEN = "open"
    DIRECTORY = "directory"


class FilePickerScreen(ModalScreen[str | None]):
    def __init__(
        self,
        *,
        mode: FilePickerMode = FilePickerMode.OPEN,
        title: str = "Select File",
        start_path: str | None = None,
        file_extensions: list[str] | None = None,
    ):
        super().__init__()
        self.mode = mode
        self.title = title
        self.start_path = start_path
        self.file_extensions = file_extensions or []
