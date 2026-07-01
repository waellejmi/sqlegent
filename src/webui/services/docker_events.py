from __future__ import annotations

import json
from typing import Any

from docker_connection.discovery import detect_database_containers


def build_docker_snapshot() -> dict[str, Any]:
    status, containers = detect_database_containers()
    return {
        "docker_status": status.value,
        "containers": [
            {
                "id": item.container_id,
                "name": item.container_name,
                "db_type": item.db_type,
                "host": item.host,
                "port": item.port,
                "database": item.database,
                "username": item.username,
                "connectable": bool(item.connectable),
                "running": bool(item.is_running),
            }
            for item in containers
        ],
    }


def as_sse(*, event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
