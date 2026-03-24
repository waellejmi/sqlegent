"""Example usage of the database connection and docker discovery features.

This script demonstrates how to:
1. Detect running database containers with Docker auto-discovery
2. Create manual connections to PostgreSQL and MySQL databases
3. Execute queries against discovered databases
"""

from connections.discovery import (
    detect_database_containers,
    get_docker_status,
    DockerStatus,
)
from connections.providers.registry import get_providers_registry
from connections.domain.config import ConnectionConfig, TcpEndpoint
from connections.adapters import connect_postgresql, connect_mysql


def example_docker_discovery():
    """Example: Discover running database containers."""
    print("=" * 60)
    print("Docker Auto-Discovery Example")
    print("=" * 60)

    # Check Docker status
    docker_status = get_docker_status()
    print(f"\nDocker Status: {docker_status.value}")

    if docker_status != DockerStatus.AVAILABLE:
        print("Docker is not available. Cannot auto-discover containers.")
        return

    # Get the providers registry
    providers = get_providers_registry()

    # Detect database containers
    status, containers = detect_database_containers(providers)

    if not containers:
        print("\nNo database containers detected.")
        return

    print(f"\nFound {len(containers)} database container(s):\n")

    for container in containers:
        print(f"Container: {container.get_display_name()}")
        print(f"  ID: {container.container_id}")
        print(f"  Type: {container.db_type}")
        print(f"  Status: {container.status.value}")
        print(f"  Host: {container.host}")
        print(f"  Port: {container.port}")
        print(f"  Database: {container.database or '(default)'}")
        print(f"  Username: {container.username or '(none)'}")
        print(f"  Connectable: {container.connectable}")
        print()


def example_manual_postgresql_connection():
    """Example: Manually create a PostgreSQL connection."""
    print("=" * 60)
    print("Manual PostgreSQL Connection Example")
    print("=" * 60)

    # Create a connection config
    config = ConnectionConfig(
        name="my_postgres_db",
        db_type="postgresql",
        endpoint=TcpEndpoint(
            host="localhost",
            port="5432",
            database="mydb",
            username="myuser",
            password="mypassword",
        ),
    )

    print(f"\nConnection Config: {config.name}")
    print(f"  Database Type: {config.db_type}")
    print(f"  Host: {config.endpoint.host}")
    print(f"  Port: {config.endpoint.port}")

    try:
        # Connect to the database
        conn = connect_postgresql(config)
        print("\n✓ Successfully connected to PostgreSQL!")

        # Execute a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"\nPostgreSQL version: {version[0]}")

        cursor.close()
        conn.close()
    except ImportError as e:
        print(f"\n✗ Error: {e}")
        print("  Install with: pip install psycopg2-binary")
    except Exception as e:
        print(f"\n✗ Connection failed: {e}")


def example_manual_mysql_connection():
    """Example: Manually create a MySQL connection."""
    print("=" * 60)
    print("Manual MySQL Connection Example")
    print("=" * 60)

    # Create a connection config
    config = ConnectionConfig(
        name="my_mysql_db",
        db_type="mysql",
        endpoint=TcpEndpoint(
            host="127.0.0.1",
            port="3306",
            database="mydb",
            username="root",
            password="mypassword",
        ),
    )

    print(f"\nConnection Config: {config.name}")
    print(f"  Database Type: {config.db_type}")
    print(f"  Host: {config.endpoint.host}")
    print(f"  Port: {config.endpoint.port}")

    try:
        # Connect to the database
        conn = connect_mysql(config)
        print("\n✓ Successfully connected to MySQL!")

        # Execute a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION();")
        version = cursor.fetchone()
        print(f"\nMySQL version: {version[0]}")

        cursor.close()
        conn.close()
    except ImportError as e:
        print(f"\n✗ Error: {e}")
        print("  Install with: pip install PyMySQL")
    except Exception as e:
        print(f"\n✗ Connection failed: {e}")


def example_connect_to_discovered_container():
    """Example: Connect to an auto-discovered container."""
    print("=" * 60)
    print("Connect to Auto-Discovered Container Example")
    print("=" * 60)

    # Check Docker status
    docker_status = get_docker_status()
    if docker_status != DockerStatus.AVAILABLE:
        print("Docker is not available.")
        return

    # Get providers and detect containers
    providers = get_providers_registry()
    status, containers = detect_database_containers(providers)

    # Filter for running PostgreSQL containers
    postgres_containers = [
        c for c in containers if c.db_type == "postgresql" and c.is_running
    ]

    if not postgres_containers:
        print("\nNo running PostgreSQL containers found.")
        return

    # Use the first container
    container = postgres_containers[0]
    print(f"\nUsing container: {container.get_display_name()}")

    # Create a connection config from the container
    from connections.discovery.docker_detector import container_to_connection_config

    config = container_to_connection_config(container)

    try:
        # Connect
        conn = connect_postgresql(config)
        print(f"\n✓ Successfully connected to {container.container_name}!")

        # Query the database
        cursor = conn.cursor()
        cursor.execute("SELECT current_database();")
        db_name = cursor.fetchone()
        print(f"  Current database: {db_name[0]}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"\n✗ Connection failed: {e}")


if __name__ == "__main__":
    # Run examples
    example_docker_discovery()
    print("\n")

    # Uncomment to test manual connections:
    # example_manual_postgresql_connection()
    # print("\n")
    # example_manual_mysql_connection()
    # print("\n")
    # example_connect_to_discovered_container()
