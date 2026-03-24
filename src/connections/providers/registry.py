"""Provider registry for database connections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .docker import DockerCredentials, DockerDetector

# Provider registry
_PROVIDERS: dict[str, dict[str, Any]] = {}


def register_provider(
    db_type: str,
    display_name: str,
    default_port: str,
    docker_detector: DockerDetector | None = None,
    requires_auth: bool = True,
    connect_func: Any = None,
) -> None:
    """Register a database provider.

    Args:
        db_type: Database type identifier (e.g., "postgresql", "mysql")
        display_name: Human-readable display name
        default_port: Default port number as string
        docker_detector: Docker detection configuration
        requires_auth: Whether the database requires authentication
        connect_func: Function to connect to the database
    """
    _PROVIDERS[db_type] = {
        "display_name": display_name,
        "default_port": default_port,
        "docker_detector": docker_detector,
        "requires_auth": requires_auth,
        "connect_func": connect_func,
    }


def get_provider_config(db_type: str) -> dict[str, Any]:
    """Get provider configuration for a database type."""
    if db_type not in _PROVIDERS:
        raise ValueError(f"Unknown database type: {db_type}")
    return _PROVIDERS[db_type]


def get_supported_db_types() -> list[str]:
    """Get list of supported database types."""
    return list(_PROVIDERS.keys())


def get_providers_registry() -> dict[str, dict[str, Any]]:
    """Get the entire providers registry."""
    return _PROVIDERS


# Register PostgreSQL provider
def _mysql_post_process(
    creds: DockerCredentials, env_vars: Mapping[str, str]
) -> DockerCredentials:
    """Post-process MySQL credentials from Docker environment."""
    user = creds.user
    if not user and (
        env_vars.get("MYSQL_ALLOW_EMPTY_PASSWORD")
        or env_vars.get("MYSQL_RANDOM_ROOT_PASSWORD")
    ):
        user = "root"
    return DockerCredentials(
        user=user, password=creds.password, database=creds.database
    )


register_provider(
    db_type="postgresql",
    display_name="PostgreSQL",
    default_port="5432",
    docker_detector=DockerDetector(
        image_patterns=("postgres",),
        env_vars={
            "user": ("POSTGRES_USER",),
            "password": ("POSTGRES_PASSWORD",),
            "database": ("POSTGRES_DB",),
        },
        default_user="postgres",
    ),
    requires_auth=True,
)

# Register MySQL provider
register_provider(
    db_type="mysql",
    display_name="MySQL",
    default_port="3306",
    docker_detector=DockerDetector(
        image_patterns=("mysql",),
        env_vars={
            "user": ("MYSQL_USER",),
            "password": ("MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"),
            "database": ("MYSQL_DATABASE",),
        },
        default_user="root",
        default_database="",
        default_user_requires_password=True,
        preferred_host="127.0.0.1",
        post_process=_mysql_post_process,
    ),
    requires_auth=True,
)
