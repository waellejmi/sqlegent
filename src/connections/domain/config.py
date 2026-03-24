"""Connection configuration models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DatabaseType(str, Enum):
    """Supported database types."""

    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


@dataclass
class TcpEndpoint:
    """TCP/IP connection endpoint."""

    host: str = ""
    port: str = ""
    database: str = ""
    username: str = ""
    password: str | None = None
    kind: str = "tcp"


@dataclass
class FileEndpoint:
    """File-based connection endpoint (e.g., SQLite)."""

    path: str = ""
    kind: str = "file"


@dataclass
class ConnectionConfig:
    """Database connection configuration."""

    name: str
    db_type: str = "postgresql"
    endpoint: TcpEndpoint | FileEndpoint = field(default_factory=TcpEndpoint)
    source: str | None = None  # e.g., "docker" for auto-discovered containers
    extra_options: dict[str, str] = field(default_factory=dict)

    @property
    def tcp_endpoint(self) -> TcpEndpoint | None:
        """Get TCP endpoint if applicable."""
        if isinstance(self.endpoint, TcpEndpoint):
            return self.endpoint
        return None

    @property
    def file_endpoint(self) -> FileEndpoint | None:
        """Get file endpoint if applicable."""
        if isinstance(self.endpoint, FileEndpoint):
            return self.endpoint
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data: dict[str, Any] = {
            "name": self.name,
            "db_type": self.db_type,
            "source": self.source,
            "extra_options": dict(self.extra_options),
        }

        if isinstance(self.endpoint, FileEndpoint):
            data["endpoint"] = {
                "kind": "file",
                "path": self.endpoint.path,
            }
        else:
            data["endpoint"] = {
                "kind": "tcp",
                "host": self.endpoint.host,
                "port": self.endpoint.port,
                "database": self.endpoint.database,
                "username": self.endpoint.username,
                "password": self.endpoint.password,
            }

        return data
