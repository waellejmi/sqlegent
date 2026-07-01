"""Docker container auto-detection for database connections.
yoinked from this great project https://github.com/Maxteabag/sqlit
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping
from urllib.parse import quote

from .docker import DockerCredentials, DockerDetector

__all__ = [
    "ContainerStatus",
    "DetectedContainer",
    "DockerStatus",
    "detect_database_containers",
    "container_to_sqlalchemy_uri",
    "get_docker_status",
]


@dataclass(frozen=True)
class DockerDatabaseSpec:
    db_type: str
    default_port: str
    requires_auth: bool
    detector: DockerDetector


class DockerStatus(Enum):
    """Status of Docker availability."""

    AVAILABLE = "available"
    NOT_RUNNING = "not_running"
    NOT_INSTALLED = "not_installed"
    NOT_ACCESSIBLE = "not_accessible"


class ContainerStatus(Enum):
    """Status of a Docker container."""

    RUNNING = "running"
    EXITED = "exited"


@dataclass
class DetectedContainer:
    """A detected database container with connection details."""

    container_id: str
    container_name: str
    db_type: str
    host: str
    port: int | None
    username: str | None
    password: str | None
    database: str | None
    status: ContainerStatus = ContainerStatus.RUNNING
    connectable: bool | None = None

    @property
    def is_running(self) -> bool:
        return self.status == ContainerStatus.RUNNING

    def __post_init__(self) -> None:
        if self.connectable is None:
            self.connectable = self.is_running and self.port is not None


def _mysql_post_process(
    creds: DockerCredentials, env_vars: Mapping[str, str]
) -> DockerCredentials:
    user = creds.user
    if not user and (
        env_vars.get("MYSQL_ALLOW_EMPTY_PASSWORD")
        or env_vars.get("MYSQL_RANDOM_ROOT_PASSWORD")
    ):
        user = "root"
    return DockerCredentials(
        user=user, password=creds.password, database=creds.database
    )


def _mariadb_post_process(
    creds: DockerCredentials, env_vars: Mapping[str, str]
) -> DockerCredentials:
    user = creds.user
    if not user and (
        env_vars.get("MYSQL_ALLOW_EMPTY_PASSWORD")
        or env_vars.get("MYSQL_RANDOM_ROOT_PASSWORD")
    ):
        user = "root"
    return DockerCredentials(
        user=user, password=creds.password, database=creds.database
    )


def _oracle_post_process(
    creds: DockerCredentials, env_vars: Mapping[str, str]
) -> DockerCredentials:
    user = creds.user
    password = creds.password
    database = creds.database

    app_user = env_vars.get("APP_USER")
    app_password = env_vars.get("APP_USER_PASSWORD")
    if app_user and not app_password:
        user = "SYSTEM"
        password = env_vars.get("ORACLE_PASSWORD")

    if isinstance(database, str) and "," in database:
        database = database.split(",", 1)[0]

    return DockerCredentials(user=user, password=password, database=database)


DOCKER_DATABASE_SPECS: tuple[DockerDatabaseSpec, ...] = (
    DockerDatabaseSpec(
        db_type="postgresql",
        default_port="5432",
        requires_auth=True,
        detector=DockerDetector(
            image_patterns=("postgres",),
            env_vars={
                "user": ("POSTGRES_USER",),
                "password": ("POSTGRES_PASSWORD",),
                "database": ("POSTGRES_DB",),
            },
            default_user="postgres",
        ),
    ),
    DockerDatabaseSpec(
        db_type="mysql",
        default_port="3306",
        requires_auth=True,
        detector=DockerDetector(
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
    ),
    DockerDatabaseSpec(
        db_type="mariadb",
        default_port="3306",
        requires_auth=True,
        detector=DockerDetector(
            image_patterns=("mariadb",),
            env_vars={
                "user": ("MARIADB_USER", "MYSQL_USER"),
                "password": (
                    "MARIADB_PASSWORD",
                    "MARIADB_ROOT_PASSWORD",
                    "MYSQL_PASSWORD",
                    "MYSQL_ROOT_PASSWORD",
                ),
                "database": ("MARIADB_DATABASE", "MYSQL_DATABASE"),
            },
            default_user="root",
            default_user_requires_password=True,
            preferred_host="127.0.0.1",
            post_process=_mariadb_post_process,
        ),
    ),
    DockerDatabaseSpec(
        db_type="mssql",
        default_port="1433",
        requires_auth=True,
        detector=DockerDetector(
            image_patterns=("mcr.microsoft.com/mssql",),
            env_vars={
                "user": (),
                "password": ("SA_PASSWORD", "MSSQL_SA_PASSWORD"),
                "database": (),
            },
            default_user="sa",
        ),
    ),
    DockerDatabaseSpec(
        db_type="oracle",
        default_port="1521",
        requires_auth=True,
        detector=DockerDetector(
            image_patterns=("gvenzl/oracle-free", "oracle/database"),
            env_vars={
                "user": ("APP_USER",),
                "password": ("APP_USER_PASSWORD", "ORACLE_PASSWORD"),
                "database": ("ORACLE_DATABASE",),
            },
            default_user="SYSTEM",
            default_database="FREEPDB1",
            post_process=_oracle_post_process,
        ),
    ),
)


def _get_spec(db_type: str) -> DockerDatabaseSpec:
    for spec in DOCKER_DATABASE_SPECS:
        if spec.db_type == db_type:
            return spec
    raise ValueError(f"Unsupported Docker db_type: {db_type}")


def _iter_docker_detectors() -> list[tuple[str, DockerDetector]]:
    return [(spec.db_type, spec.detector) for spec in DOCKER_DATABASE_SPECS]


def get_docker_status() -> DockerStatus:
    try:
        import docker  # pyright: ignore[reportMissingModuleSource]
    except ImportError:
        return DockerStatus.NOT_INSTALLED

    try:
        client = docker.from_env()
        client.ping()
        return DockerStatus.AVAILABLE
    except Exception as exc:
        error_str = str(exc).lower()
        if "permission denied" in error_str:
            return DockerStatus.NOT_ACCESSIBLE
        if "connection refused" in error_str or "connect" in error_str:
            return DockerStatus.NOT_RUNNING
        return DockerStatus.NOT_RUNNING


def _get_db_type_from_image(image_name: str) -> str | None:
    for db_type, detector in _iter_docker_detectors():
        if detector.match_image(image_name):
            return db_type
    return None


def _get_host_port(container: object, container_port: int) -> int | None:
    ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
    bindings = ports.get(f"{container_port}/tcp")
    if bindings and len(bindings) > 0:
        host_port = bindings[0].get("HostPort")
        if host_port:
            return int(host_port)
    return None


def _get_single_mapped_host_port(container: object) -> int | None:
    ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
    mapped_ports: set[int] = set()
    for port_key, bindings in ports.items():
        if not port_key.endswith("/tcp") or not bindings:
            continue
        for binding in bindings:
            host_port = binding.get("HostPort")
            if host_port:
                mapped_ports.add(int(host_port))
    if len(mapped_ports) == 1:
        return mapped_ports.pop()
    return None


def _get_exposed_tcp_ports(container: object) -> list[int]:
    exposed = container.attrs.get("Config", {}).get("ExposedPorts") or {}
    exposed_ports: list[int] = []
    for port_key in exposed.keys():
        if not port_key.endswith("/tcp"):
            continue
        port_str = port_key.split("/")[0]
        if port_str.isdigit():
            exposed_ports.append(int(port_str))
    return exposed_ports


def _get_container_image_name(container: object) -> str | None:
    try:
        image_tags = container.image.tags
        if image_tags:
            return str(image_tags[0])
    except Exception:
        pass
    try:
        config_image = container.attrs.get("Config", {}).get("Image")
        if isinstance(config_image, str):
            return config_image
        if config_image:
            return str(config_image)
    except Exception:
        pass
    try:
        return str(container.image.short_id)
    except Exception:
        return None


def _get_container_env_vars(container: object) -> dict[str, str]:
    env_list = container.attrs.get("Config", {}).get("Env", [])
    env_dict: dict[str, str] = {}
    for env in env_list:
        if "=" in env:
            key, value = env.split("=", 1)
            env_dict[key] = value
    return env_dict


def _detect_containers_with_status(
    client: object, status_filter: str, container_status: ContainerStatus
) -> list[DetectedContainer]:
    try:
        containers = client.containers.list(filters={"status": status_filter})
    except Exception:
        return []

    detected: list[DetectedContainer] = []
    for container in containers:
        image_name = _get_container_image_name(container)
        if not image_name:
            continue

        db_type = _get_db_type_from_image(image_name)
        if not db_type:
            continue

        spec = _get_spec(db_type)
        detector = spec.detector
        default_port = int(spec.default_port) if spec.default_port else None

        host_port = None
        if container_status == ContainerStatus.RUNNING:
            if default_port:
                host_port = _get_host_port(container, default_port)
            if host_port is None:
                host_port = _get_single_mapped_host_port(container)

            network_mode = container.attrs.get("HostConfig", {}).get("NetworkMode")
            if host_port is None and network_mode == "host" and default_port:
                exposed_ports = _get_exposed_tcp_ports(container)
                if len(exposed_ports) == 1:
                    host_port = exposed_ports[0]
                else:
                    host_port = default_port

        env_vars = _get_container_env_vars(container)
        credentials = detector.get_credentials(env_vars)
        if credentials.database is None:
            database_label = container.labels.get("db.name")
            credentials = DockerCredentials(
                user=credentials.user,
                password=credentials.password,
                database=database_label,
            )

        container_name = container.name
        if container_name.startswith("/"):
            container_name = container_name[1:]

        host = detector.preferred_host
        password = credentials.password
        if password is None and not spec.requires_auth:
            password = ""

        detected.append(
            DetectedContainer(
                container_id=container.short_id,
                container_name=container_name,
                db_type=db_type,
                host=host,
                port=host_port,
                username=credentials.user,
                password=password,
                database=credentials.database,
                status=container_status,
                connectable=container_status == ContainerStatus.RUNNING
                and host_port is not None,
            )
        )

    return detected


def detect_database_containers() -> tuple[DockerStatus, list[DetectedContainer]]:
    status = get_docker_status()
    if status != DockerStatus.AVAILABLE:
        return status, []

    try:
        import docker  # pyright: ignore[reportMissingModuleSource]

        client = docker.from_env()
    except Exception:
        return DockerStatus.NOT_ACCESSIBLE, []

    running = _detect_containers_with_status(client, "running", ContainerStatus.RUNNING)
    exited = _detect_containers_with_status(client, "exited", ContainerStatus.EXITED)
    return DockerStatus.AVAILABLE, running + exited


def container_to_sqlalchemy_uri(container: DetectedContainer) -> str:
    port = str(container.port) if container.port else ""
    host = container.host or "localhost"
    db_type = container.db_type.lower()
    database = container.database or ""
    username = container.username or ""
    password = container.password or ""

    auth_segment = ""
    if username:
        auth_segment = username
        if password:
            if db_type == "oracle":
                password = quote(password)
            auth_segment = f"{auth_segment}:{password}"
        auth_segment = f"{auth_segment}@"

    host_segment = f"{host}:{port}" if port else host

    if db_type == "postgresql":
        if not database:
            database = "postgres"
        return f"postgresql+psycopg2://{auth_segment}{host_segment}/{database}"

    if db_type in {"mysql", "mariadb"}:
        if not database:
            database = "mysql"
        return f"mysql+pymysql://{auth_segment}{host_segment}/{database}"

    if db_type == "mssql":
        if not database:
            database = "mssql"
        return f"mssql+pymssql://{auth_segment}{host_segment}/{database}"

    if db_type == "oracle":
        if not database:
            database = "oracle"
        return (
            f"oracle+oracledb://{auth_segment}{host_segment}/?service_name={database}"
        )

    raise ValueError(
        f"Docker/connection URI conversion is not implemented for db_type='{db_type}'."
    )
