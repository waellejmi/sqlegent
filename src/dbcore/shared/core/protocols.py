"""Protocols for dependency injection in dbcore services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dbcore.connections.app.credentials import CredentialsService
    from dbcore.connections.domain.config import ConnectionConfig


@runtime_checkable
class QueryExecutorProtocol(Protocol):
    def execute_query(
        self, conn: Any, query: str, max_rows: int | None = None
    ) -> tuple[list[str], list[tuple], bool]: ...
    def execute_non_query(self, conn: Any, query: str) -> int: ...


@runtime_checkable
class ProviderFactoryProtocol(Protocol):
    def __call__(self, db_type: str) -> Any: ...


@runtime_checkable
class HistoryStoreProtocol(Protocol):
    def save_query(self, connection_name: str, query: str) -> None: ...
    def load_for_connection(self, connection_name: str) -> list: ...
    def load_all(self) -> list: ...


@runtime_checkable
class TunnelFactoryProtocol(Protocol):
    def __call__(self, config: ConnectionConfig) -> tuple[Any, str, int]: ...


@runtime_checkable
class ConnectionStoreProtocol(Protocol):
    is_persistent: bool

    def load_all(self, load_credentials: bool = True) -> list[ConnectionConfig]: ...
    def save_all(self, connections: list[ConnectionConfig]) -> None: ...
    def set_credentials_service(self, service: CredentialsService) -> None: ...


@runtime_checkable
class SettingsStoreProtocol(Protocol):
    def load_all(self) -> dict: ...
    def save_all(self, settings: dict) -> None: ...
