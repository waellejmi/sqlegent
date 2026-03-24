# Database Connections Module

This module provides database connection management and Docker auto-discovery for the SQL Agent.

## Features

- **Docker Auto-Discovery**: Automatically detect running database containers (PostgreSQL, MySQL)
- **Manual Connection Management**: Create and manage database connections programmatically
- **Multiple Database Support**: PostgreSQL and MySQL (extensible to other databases)
- **Connection Configuration**: Flexible configuration model for various connection types

## Installation

The required dependencies are already included in the project's `pyproject.toml`:

```bash
# Install all dependencies
uv sync

# Or install specific database drivers
pip install psycopg2-binary  # For PostgreSQL
pip install PyMySQL           # For MySQL
pip install docker            # For Docker auto-discovery
```

## Quick Start

### Docker Auto-Discovery

Automatically detect and connect to running database containers:

```python
from connections.discovery import detect_database_containers, get_docker_status
from connections.providers.registry import get_providers_registry

# Check if Docker is available
docker_status = get_docker_status()
print(f"Docker Status: {docker_status.value}")

# Detect containers
providers = get_providers_registry()
status, containers = detect_database_containers(providers)

for container in containers:
    print(f"Found: {container.get_display_name()}")
    print(f"  Type: {container.db_type}")
    print(f"  Port: {container.port}")
```

### Manual Connection - PostgreSQL

```python
from connections.domain.config import ConnectionConfig, TcpEndpoint
from connections.adapters import connect_postgresql

# Create configuration
config = ConnectionConfig(
    name="my_postgres",
    db_type="postgresql",
    endpoint=TcpEndpoint(
        host="localhost",
        port="5432",
        database="mydb",
        username="postgres",
        password="password",
    ),
)

# Connect
conn = connect_postgresql(config)
cursor = conn.cursor()
cursor.execute("SELECT version();")
print(cursor.fetchone())
conn.close()
```

### Manual Connection - MySQL

```python
from connections.domain.config import ConnectionConfig, TcpEndpoint
from connections.adapters import connect_mysql

# Create configuration
config = ConnectionConfig(
    name="my_mysql",
    db_type="mysql",
    endpoint=TcpEndpoint(
        host="127.0.0.1",
        port="3306",
        database="mydb",
        username="root",
        password="password",
    ),
)

# Connect
conn = connect_mysql(config)
cursor = conn.cursor()
cursor.execute("SELECT VERSION();")
print(cursor.fetchone())
conn.close()
```

### Connect to Auto-Discovered Container

```python
from connections.discovery import detect_database_containers
from connections.discovery.docker_detector import container_to_connection_config
from connections.providers.registry import get_providers_registry
from connections.adapters import connect_postgresql

# Detect containers
providers = get_providers_registry()
status, containers = detect_database_containers(providers)

# Get first PostgreSQL container
postgres = [c for c in containers if c.db_type == "postgresql"][0]

# Convert to connection config
config = container_to_connection_config(postgres)

# Connect
conn = connect_postgresql(config)
```

## Module Structure

```
src/connections/
├── __init__.py                 # Public API exports
├── adapters/                   # Database connection adapters
│   ├── postgresql.py           # PostgreSQL adapter
│   └── mysql.py                # MySQL adapter
├── discovery/                  # Docker auto-discovery
│   ├── __init__.py
│   └── docker_detector.py      # Container detection logic
├── domain/                     # Core domain models
│   ├── __init__.py
│   └── config.py               # Connection configuration models
├── providers/                  # Database provider registry
│   ├── __init__.py
│   ├── docker.py               # Docker detection helpers
│   └── registry.py             # Provider registration
├── example_usage.py            # Usage examples
└── README.md                   # This file
```

## API Reference

### Docker Discovery

#### `get_docker_status() -> DockerStatus`
Check if Docker is available and running.

Returns:
- `DockerStatus.AVAILABLE`: Docker is running
- `DockerStatus.NOT_RUNNING`: Docker daemon not running
- `DockerStatus.NOT_INSTALLED`: Docker not installed
- `DockerStatus.NOT_ACCESSIBLE`: Permission issues

#### `detect_database_containers(providers_registry) -> tuple[DockerStatus, list[DetectedContainer]]`
Scan for running and stopped database containers.

### Connection Management

#### `ConnectionConfig`
Main configuration class for database connections.

**Fields:**
- `name`: Connection name
- `db_type`: Database type ("postgresql", "mysql")
- `endpoint`: TcpEndpoint or FileEndpoint
- `source`: Optional source ("docker" for auto-discovered)
- `extra_options`: Additional connection options

#### `TcpEndpoint`
TCP/IP connection endpoint.

**Fields:**
- `host`: Server hostname
- `port`: Port number
- `database`: Database name
- `username`: Username
- `password`: Password (optional)

### Connection Adapters

#### `connect_postgresql(config: ConnectionConfig) -> Any`
Connect to PostgreSQL database using psycopg2.

#### `connect_mysql(config: ConnectionConfig) -> Any`
Connect to MySQL database using PyMySQL.

## Docker Detection

### Supported Images

The module automatically detects the following Docker images:

**PostgreSQL:**
- `postgres:*`
- Environment variables: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- Default user: `postgres`
- Default port: `5432`

**MySQL:**
- `mysql:*`
- Environment variables: `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`
- Default user: `root`
- Default port: `3306`

### Detection Process

1. Check if Docker is installed and running
2. List all containers (running and stopped)
3. Match container images against known database patterns
4. Extract connection details from environment variables
5. Determine mapped ports for running containers
6. Return list of detected containers with connection info

## Adding New Database Types

To add support for a new database:

1. **Register Provider** in `providers/registry.py`:
```python
register_provider(
    db_type="newdb",
    display_name="NewDB",
    default_port="1234",
    docker_detector=DockerDetector(
        image_patterns=("newdb",),
        env_vars={
            "user": ("NEWDB_USER",),
            "password": ("NEWDB_PASSWORD",),
            "database": ("NEWDB_DATABASE",),
        },
        default_user="admin",
    ),
    requires_auth=True,
)
```

2. **Create Adapter** in `adapters/newdb.py`:
```python
def connect_newdb(config: ConnectionConfig) -> Any:
    import newdb_driver
    endpoint = config.tcp_endpoint
    conn = newdb_driver.connect(
        host=endpoint.host,
        port=int(endpoint.port or "1234"),
        database=endpoint.database,
        user=endpoint.username,
        password=endpoint.password,
    )
    return conn
```

3. **Export** in `adapters/__init__.py`
4. **Update** `domain/config.py` DatabaseType enum

## Examples

See `example_usage.py` for complete working examples:

```bash
cd src
python -m connections.example_usage
```

## Testing

To test Docker auto-discovery, start a test database container:

```bash
# PostgreSQL
docker run -d -p 5432:5432 \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_USER=testuser \
  -e POSTGRES_DB=testdb \
  --name test-postgres \
  postgres:latest

# MySQL
docker run -d -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=testpass \
  -e MYSQL_DATABASE=testdb \
  --name test-mysql \
  mysql:latest
```

Then run the discovery:

```bash
python -m connections.example_usage
```

## Troubleshooting

### Docker Permission Denied
```
DockerStatus.NOT_ACCESSIBLE
```
**Solution**: Add your user to the docker group:
```bash
sudo usermod -aG docker $USER
# Log out and back in
```

### Driver Not Found
```
ImportError: PostgreSQL driver not found
```
**Solution**: Install the database driver:
```bash
pip install psycopg2-binary  # PostgreSQL
pip install PyMySQL           # MySQL
```

### Container Not Detected
- Verify container is running: `docker ps`
- Check image name matches patterns in registry
- Ensure environment variables are set correctly

## Credits

This module is extracted from the [sqlit](https://github.com/Maxteabag/sqlit) project, which is a comprehensive TUI for SQL databases. We extracted only the connection and Docker discovery logic without the UI components.

## License

This code is derived from sqlit (MIT License).
