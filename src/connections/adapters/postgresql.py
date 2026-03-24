"""PostgreSQL connection adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..domain.config import ConnectionConfig


def connect_postgresql(config: ConnectionConfig) -> Any:
    """Connect to PostgreSQL database using psycopg2.

    Args:
        config: Connection configuration

    Returns:
        Database connection object

    Raises:
        ImportError: If psycopg2 is not installed
        ValueError: If configuration is invalid
    """
    try:
        import psycopg2
    except ImportError as e:
        raise ImportError(
            "PostgreSQL driver not found. Install it with: pip install psycopg2-binary"
        ) from e

    endpoint = config.tcp_endpoint
    if endpoint is None:
        raise ValueError("PostgreSQL connections require a TCP-style endpoint.")

    connect_args: dict[str, Any] = {
        "connect_timeout": 10,
        "database": endpoint.database or "postgres",
    }

    if endpoint.host:
        connect_args["host"] = endpoint.host
        connect_args["port"] = int(endpoint.port or "5432")

    if endpoint.username:
        connect_args["user"] = endpoint.username

    if endpoint.password is not None:
        connect_args["password"] = endpoint.password

    # Add any extra options
    connect_args.update(config.extra_options)

    conn = psycopg2.connect(**connect_args)
    # Enable autocommit to avoid "transaction aborted" errors on failed statements
    conn.autocommit = True

    return conn
