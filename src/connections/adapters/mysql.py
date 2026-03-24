"""MySQL connection adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..domain.config import ConnectionConfig


def connect_mysql(config: ConnectionConfig) -> Any:
    """Connect to MySQL database using PyMySQL.

    Args:
        config: Connection configuration

    Returns:
        Database connection object

    Raises:
        ImportError: If PyMySQL is not installed
        ValueError: If configuration is invalid
    """
    try:
        import pymysql
    except ImportError as e:
        raise ImportError(
            "MySQL driver not found. Install it with: pip install PyMySQL"
        ) from e

    endpoint = config.tcp_endpoint
    if endpoint is None:
        raise ValueError("MySQL connections require a TCP-style endpoint.")

    port = int(endpoint.port or "3306")
    host = endpoint.host

    # Use 127.0.0.1 instead of localhost to force TCP connection
    # (localhost causes MySQL to try Unix socket which doesn't exist on host)
    if host and host.lower() == "localhost":
        host = "127.0.0.1"

    connect_args: dict[str, Any] = {
        "host": host,
        "port": port,
        "database": endpoint.database or None,
        "user": endpoint.username,
        "password": endpoint.password,
        "connect_timeout": 10,
        "autocommit": True,
        "charset": "utf8mb4",
    }

    # Add any extra options
    connect_args.update(config.extra_options)

    conn = pymysql.connect(**connect_args)

    return conn
