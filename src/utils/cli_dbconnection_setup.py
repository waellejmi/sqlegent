from pathlib import Path

from config.db_config import DBConfig


def _normalize_sqlite_uri_from_input(raw_path: str, db_config: DBConfig) -> str:
    path = Path(raw_path).expanduser().resolve()
    return db_config.sqlite_path_to_uri(path)


def _connection_config_to_uri(connection, db_config: DBConfig) -> str:
    db_type = str(connection.db_type).lower()
    endpoint = connection.tcp_endpoint
    file_endpoint = connection.file_endpoint

    if db_type in {"sqlite", "duckdb"}:
        if file_endpoint is None or not file_endpoint.path:
            raise ValueError(f"{db_type} connection does not include a file path.")
        return db_config.sqlite_path_to_uri(file_endpoint.path)

    if endpoint is None:
        raise ValueError(f"{db_type} connection does not include a TCP endpoint.")

    host = endpoint.host or "localhost"
    port = endpoint.port or ""
    database = endpoint.database or ""
    username = endpoint.username or ""
    password = endpoint.password or ""

    auth_segment = ""
    if username:
        auth_segment = username
        if password:
            if db_type == "oracle":
                from urllib.parse import quote

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

    if db_type == "mssql":
        if not database:
            database = "mssql"
        return f"mssql+pymssql://{auth_segment}{host_segment}/{database}"

    raise ValueError(
        f"Docker/connection URI conversion is not implemented for db_type='{db_type}'."
    )


def _pick_docker_connection_uri(db_config: DBConfig) -> str:
    from dbcore.connections.discovery.docker_detector import (
        DockerStatus,
        container_to_connection_config,
        detect_database_containers,
    )

    status, containers = detect_database_containers()

    if status == DockerStatus.NOT_INSTALLED:
        raise RuntimeError(
            "Docker SDK is not installed. Install with: pip install docker"
        )
    if status == DockerStatus.NOT_RUNNING:
        raise RuntimeError("Docker is not running.")
    if status == DockerStatus.NOT_ACCESSIBLE:
        raise RuntimeError(
            "Docker is not accessible (permission denied or daemon unreachable)."
        )

    running = [c for c in containers if c.is_running and c.connectable]
    supported_db_types = {
        "sqlite",
        "mssql",
        "postgresql",
        "mysql",
        "mariadb",
        "oracle",
        "duckdb",
    }
    running = [c for c in running if c.db_type in supported_db_types]
    if not running:
        raise RuntimeError(
            "No connectable running containers were found for supported db types: "
            f"{', '.join(sorted(supported_db_types))}."
        )

    print("\nDetected Docker database containers:")
    for idx, container in enumerate(running, start=1):
        port = container.port if container.port is not None else "-"
        db = container.database or "-"
        print(
            f"[{idx}] {container.container_name} | type={container.db_type} | host={container.host} | port={port} | db={db}"
        )

    choice_raw = input("Pick container number: ").strip()
    if not choice_raw.isdigit():
        raise ValueError("Invalid selection. Please provide a number.")
    choice = int(choice_raw)
    if choice < 1 or choice > len(running):
        raise ValueError("Selection out of range.")

    selected = running[choice - 1]
    connection = container_to_connection_config(selected)
    breakpoint()
    return _connection_config_to_uri(connection, db_config)


def configure_database_target(db_config: DBConfig) -> str:
    current_uri = db_config.get_database_uri()
    while True:
        print("\n=== Database Target Configuration ===")
        print(f"Current active URI: {current_uri}")
        print("Select target source:")
        print("[1] SQLite file path")
        print("[2] Direct SQLAlchemy URI")
        print("[3] Docker auto discovery")
        print("[Enter] Keep current")

        choice = input("Choice: ").strip()
        if choice == "":
            print("Keeping current database target.")
            return current_uri

        try:
            if choice == "1":
                default_path = str(db_config.DEFAULT_SQLITE_PATH)
                raw_path = (
                    input(f"SQLite file path [{default_path}]: ").strip()
                    or default_path
                )
                selected_uri = _normalize_sqlite_uri_from_input(raw_path, db_config)
            elif choice == "2":
                raw_uri = input("SQLAlchemy URI: ").strip()
                if not raw_uri:
                    raise ValueError("URI cannot be empty.")
                selected_uri = raw_uri
            elif choice == "3":
                selected_uri = _pick_docker_connection_uri(db_config)
            else:
                raise ValueError("Unsupported choice.")
            db_config.set_database_uri(selected_uri)
            print(
                f"Saved active database URI to {db_config.CONFIG_FILE}: {selected_uri}"
            )
            return selected_uri
        except Exception as exc:
            print(f"Configuration error: {exc}")
