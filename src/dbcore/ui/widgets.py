"""UI widget compatibility shims for dbcore imports."""

from __future__ import annotations

from typing import Any


class Dialog:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> Dialog:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class FilterInput:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def show(self) -> None:
        pass

    def hide(self) -> None:
        pass

    def set_filter(self, text: str, match_count: int, total: int) -> None:
        pass


class ContextFooter:
    def set_bindings(self, left: list[Any], right: list[Any]) -> None:
        pass


def flash_widget(widget: Any) -> None:
    return None
