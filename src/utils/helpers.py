import hashlib
import json
from collections.abc import Sequence
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


def _normalize_table_name(raw_name: Any) -> str:
    name = normalize_whitespace(str(raw_name))
    return name.strip(" \t\n\r\"'`[]{}()")


def normalize_table_names(table_names: str | Sequence[Any]) -> list[str]:
    if isinstance(table_names, str):
        raw_names: Sequence[Any] = table_names.split(",")
    else:
        raw_names = table_names

    normalized: list[str] = []
    seen: set[str] = set()

    for raw_name in raw_names:
        clean_name = _normalize_table_name(raw_name)
        clean_key = clean_name.casefold()
        if not clean_name or clean_key in seen:
            continue
        seen.add(clean_key)
        normalized.append(clean_name)

    normalized.sort(key=str.casefold)
    return normalized


def normalize_table_names_csv(table_names: str | Sequence[Any]) -> str:
    return ",".join(normalize_table_names(table_names))


def _canonicalize_table_names(
    table_names: str | list[str],
    available_tables: list[str],
) -> list[str]:
    normalized_tables = normalize_table_names(table_names)
    available_lookup = {table.casefold(): table for table in available_tables}

    canonical_tables: list[str] = []
    seen: set[str] = set()
    for table_name in normalized_tables:
        canonical_name = available_lookup.get(table_name.casefold(), table_name)
        canonical_key = canonical_name.casefold()
        if canonical_key in seen:
            continue
        seen.add(canonical_key)
        canonical_tables.append(canonical_name)

    return canonical_tables
