from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from cli.connections import connection_config_to_uri, normalize_sqlite_uri_from_input
from config.app_config import AppConfig
from config.db_config import DBConfig
from dbcore.connections.discovery.docker_detector import (
    DockerStatus,
    container_to_connection_config,
    detect_database_containers,
)

router = APIRouter()


class ActivateConnectionRequest(BaseModel):
    uri: str = Field(min_length=1)


class NewConnectionRequest(BaseModel):
    mode: str = Field(description="sqlite_path|direct_uri")
    value: str = Field(default="")


class ContextReindexRequest(BaseModel):
    semantic_profile: str | None = None


class SettingsUpdateRequest(BaseModel):
    HUMAN_SQL_REVIEW: bool | None = None
    EXECUTE_SQL_QUERIES: bool | None = None
    CONTEXT_AUTO_INDEX_ON_STARTUP: bool | None = None
    CLI_ASK_RESULT_CONFIRMATION: bool | None = None


class RelationshipsImportRequest(BaseModel):
    name: str = Field(min_length=1)
    content: str = Field(min_length=1)


_relationships_store: list[dict[str, str]] = []


def _serialize_detected_containers() -> tuple[str, list[dict[str, object]]]:
    status, containers = detect_database_containers()
    payload: list[dict[str, object]] = []
    for item in containers:
        payload.append(
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
        )
    return status.value, payload


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/connections")
def list_connections() -> dict[str, object]:
    db_config = DBConfig()
    return {
        "active_uri": db_config.get_database_uri(),
        "default_sqlite_path": str(db_config.DEFAULT_SQLITE_PATH),
        "config_file": str(db_config.CONFIG_FILE),
    }


@router.post("/connections")
def create_connection(payload: NewConnectionRequest) -> dict[str, str]:
    db_config = DBConfig()
    mode = payload.mode.strip().lower()
    value = payload.value.strip()

    if mode == "sqlite_path":
        selected_uri = normalize_sqlite_uri_from_input(value, db_config)
    elif mode == "direct_uri":
        if not value:
            raise HTTPException(status_code=400, detail="URI cannot be empty.")
        selected_uri = value
    else:
        raise HTTPException(status_code=400, detail="Unsupported mode.")

    db_config.set_database_uri(selected_uri)
    return {"active_uri": selected_uri}


@router.post("/connections/activate")
def activate_connection(payload: ActivateConnectionRequest) -> dict[str, str]:
    db_config = DBConfig()
    db_config.set_database_uri(payload.uri.strip())
    return {"active_uri": db_config.get_database_uri()}


@router.get("/connections/docker")
def list_docker_connections() -> dict[str, object]:
    status, containers = _serialize_detected_containers()
    return {
        "docker_status": status,
        "containers": containers,
    }


@router.post("/connections/docker/{container_id}/activate")
def activate_docker_connection(container_id: str) -> dict[str, str]:
    status, containers = detect_database_containers()
    if status != DockerStatus.AVAILABLE:
        raise HTTPException(
            status_code=503, detail=f"Docker unavailable: {status.value}"
        )

    for item in containers:
        if item.container_id != container_id:
            continue
        connection = container_to_connection_config(item)
        uri = connection_config_to_uri(connection, DBConfig())
        DBConfig().set_database_uri(uri)
        return {"active_uri": uri}

    raise HTTPException(status_code=404, detail="Container not found.")


@router.get("/config/app")
def get_app_config() -> dict[str, object]:
    config = AppConfig()
    return {
        "HUMAN_SQL_REVIEW": config.HUMAN_SQL_REVIEW,
        "EXECUTE_SQL_QUERIES": config.EXECUTE_SQL_QUERIES,
        "CONTEXT_AUTO_INDEX_ON_STARTUP": config.CONTEXT_AUTO_INDEX_ON_STARTUP,
        "CLI_ASK_RESULT_CONFIRMATION": config.CLI_ASK_RESULT_CONFIRMATION,
        "ENABLE_CONTEXT_LAYER": config.ENABLE_CONTEXT_LAYER,
        "CONTEXT_STORE_PATH": str(config.CONTEXT_STORE_PATH),
    }


@router.put("/config/app")
def update_app_config(payload: SettingsUpdateRequest) -> dict[str, object]:
    # Runtime config is dataclass constants today. Stub response for UI wiring.
    return {
        "updated": payload.model_dump(exclude_none=True),
        "note": "Runtime AppConfig update is not persisted yet.",
    }


@router.post("/context/reindex")
def context_reindex(payload: ContextReindexRequest) -> dict[str, object]:
    from app.context_ops import run_context_reindex

    run_context_reindex(payload.semantic_profile)
    return {"queued": False, "status": "done"}


@router.get("/context/stats")
def context_stats() -> dict[str, object]:
    from context_layer.service import get_context_service

    return get_context_service().get_stats()


@router.get("/relationships")
def list_relationships() -> dict[str, object]:
    return {"items": _relationships_store}


@router.post("/relationships/import")
def import_relationships(payload: RelationshipsImportRequest) -> dict[str, object]:
    record = {
        "name": payload.name.strip(),
        "content": payload.content.strip(),
    }
    _relationships_store.append(record)
    return {"stored": True, "count": len(_relationships_store)}


@router.post("/relationships/rebuild")
def rebuild_relationships() -> dict[str, object]:
    return {"rebuilt": True, "count": len(_relationships_store)}
