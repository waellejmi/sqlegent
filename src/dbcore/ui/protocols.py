"""UI protocol definitions used by dbcore modules."""

from __future__ import annotations

from typing import Any, Protocol


class AppProtocol(Protocol):
    services: Any

    def notify(
        self,
        message: str,
        *,
        severity: str = "information",
        timeout: float | int | None = None,
    ) -> Any: ...

    def push_screen(
        self, screen: Any, callback: Any = None, wait_for_dismiss: bool = False
    ) -> Any: ...
    def pop_screen(self) -> Any: ...
    def call_from_thread(self, callback: Any, *args: Any, **kwargs: Any) -> Any: ...


class TextualAppProtocol(AppProtocol, Protocol):
    def emit_debug_event(self, name: str, **data: Any) -> Any: ...


class ConnectionsProtocol(Protocol):
    current_config: Any
    current_connection: Any
    current_provider: Any


class ConnectionMixinHost(TextualAppProtocol, Protocol):
    connections: list[Any]
