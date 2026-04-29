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
    model_config = {"extra": "allow"}


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
    data = {}
    for key, value in config.__dict__.items():
        if key in ["ROOT_DIR", "RUNTIME_SETTINGS_PATH"] or key.startswith("_"):
            continue
        data[key] = (
            str(value) if isinstance(value, __import__("pathlib").Path) else value
        )
    return data


@router.put("/config/app")
def update_app_config(payload: SettingsUpdateRequest) -> dict[str, object]:
    config = AppConfig()
    updated_fields = payload.model_dump(exclude_none=True)

    for key, value in updated_fields.items():
        if hasattr(config, key) and key not in ["ROOT_DIR", "RUNTIME_SETTINGS_PATH"]:
            original_val = getattr(config, key)
            if (
                isinstance(original_val, __import__("pathlib").Path)
                and value is not None
            ):
                setattr(config, key, __import__("pathlib").Path(value))
            elif isinstance(original_val, int) and value is not None:
                setattr(config, key, int(value))
            elif isinstance(original_val, float) and value is not None:
                setattr(config, key, float(value))
            elif isinstance(original_val, bool) and value is not None:
                setattr(config, key, bool(value))
            else:
                setattr(config, key, value)

    config.save_runtime_settings()

    return {
        "updated": updated_fields,
        "note": "Settings saved to runtime config.",
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


@router.get("/context/profiles")
def context_profiles() -> dict[str, list[str]]:
    config = AppConfig()
    mdl_dir = config.MDL_DIR
    profiles = ["."]  # root profile for _baseline.generated.yaml
    if mdl_dir.exists() and mdl_dir.is_dir():
        for d in mdl_dir.iterdir():
            if d.is_dir():
                profiles.append(d.name)
    return {"profiles": profiles}


@router.get("/context/files/{profile}")
def context_files(profile: str) -> dict[str, list[str]]:
    config = AppConfig()

    if profile == ".":
        profile_dir = config.MDL_DIR
        # Only direct files in root
        files = [
            f.name for f in profile_dir.iterdir() if f.is_file() and f.suffix == ".yaml"
        ]
        return {"files": files}

    profile_dir = config.MDL_DIR / profile
    files = []
    if profile_dir.exists() and profile_dir.is_dir():
        for f in profile_dir.rglob(config.MDL_FILE_GLOB):
            if f.is_file():
                # return relative path to profile dir
                files.append(str(f.relative_to(profile_dir)))
    return {"files": files}


@router.get("/context/files/{profile}/{file_path:path}")
def context_file_content(profile: str, file_path: str) -> dict[str, str]:
    config = AppConfig()
    target_file = config.MDL_DIR / profile / file_path

    # Basic path traversal protection
    try:
        target_file = target_file.resolve()
        if not str(target_file).startswith(str((config.MDL_DIR / profile).resolve())):
            raise HTTPException(status_code=400, detail="Invalid path")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = target_file.read_text(encoding="utf-8")
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


class SaveMemoryRequest(BaseModel):
    history_id: str | None = None
    question: str
    sql: str
    db_output: str | None


@router.post("/memory/save")
def save_memory(req: SaveMemoryRequest):
    from context_layer.service import (
        get_context_service,
        extract_tables_from_sql,
        safe_parse_row_count,
    )

    service = get_context_service()
    if not service:
        raise HTTPException(status_code=500, detail="Context layer disabled")

    row_count = safe_parse_row_count(req.db_output)
    memory_id = service.record_verified_query(
        question=req.question,
        sql=req.sql,
        tables=extract_tables_from_sql(req.sql),
        row_count=row_count,
        is_verified=True,
        metadata={"source": "webui"},
    )

    if req.history_id:
        from webui.history_store import HistoryStore

        try:
            HistoryStore().mark_saved(req.history_id, status=1)
        except Exception:
            pass

    return {"status": "ok", "memory_id": memory_id}


@router.post("/memory/reject")
def reject_memory(req: SaveMemoryRequest):
    if req.history_id:
        from webui.history_store import HistoryStore

        try:
            HistoryStore().mark_saved(req.history_id, status=-1)
        except Exception:
            pass
    return {"status": "ok"}


@router.get("/history")
def get_chat_history() -> dict[str, object]:
    from webui.history_store import HistoryStore

    store = HistoryStore()
    return {"history": store.get_history()}


@router.delete("/history/{history_id}")
def delete_chat_history(history_id: str) -> dict[str, str]:
    from webui.history_store import HistoryStore

    try:
        HistoryStore().delete_interaction(history_id)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
