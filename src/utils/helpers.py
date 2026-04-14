import hashlib
import json
from typing import Any

from config.db_config import DBConfig


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_db_fingerprint(database_uri: str | None = None) -> str:
    uri = database_uri or DBConfig().get_database_uri()
    return _hash(uri)


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def from_json(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return default


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalize_args(operation_args: dict[str, Any] | None) -> str:
    payload = operation_args or {}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
