import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from config.app_config import AppConfig
from utils.helpers import _hash, get_db_fingerprint, normalize_args
from utils.logger_setup import LoggerSetup

logger = LoggerSetup.get_logger(__name__, logging.INFO)


class MetadataCacheStore:
    def __init__(self, cache_path: Path):
        self._cache_path = cache_path
        self._lock = threading.Lock()
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._cache_path, timeout=5)

    def _ensure_db(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata_cache (
                    cache_key TEXT PRIMARY KEY,
                    db_fingerprint TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    args_hash TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_metadata_cache_db_operation
                ON metadata_cache (db_fingerprint, operation)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_metadata_cache_expires
                ON metadata_cache (expires_at)
                """
            )

    def get(self, cache_key: str) -> Any | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT value_json, expires_at FROM metadata_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None

            value_json, expires_at = row
            now = int(time.time())
            if expires_at is not None and expires_at <= now:
                conn.execute(
                    "DELETE FROM metadata_cache WHERE cache_key = ?", (cache_key,)
                )
                return None

            return json.loads(value_json)

    def set(
        self,
        *,
        cache_key: str,
        db_fingerprint: str,
        operation: str,
        args_hash: str,
        value: Any,
        ttl_seconds: int | None,
    ) -> None:
        now = int(time.time())
        expires_at = (
            now + ttl_seconds if ttl_seconds is not None and ttl_seconds > 0 else None
        )

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                    INSERT INTO metadata_cache (
                        cache_key,
                        db_fingerprint,
                        operation,
                        args_hash,
                        value_json,
                        created_at,
                        expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        value_json=excluded.value_json,
                        created_at=excluded.created_at,
                        expires_at=excluded.expires_at
                    """,
                (
                    cache_key,
                    db_fingerprint,
                    operation,
                    args_hash,
                    json.dumps(value),
                    now,
                    expires_at,
                ),
            )

    def invalidate(self, db_fingerprint: str | None = None) -> int:
        with self._lock, self._connect() as conn:
            if db_fingerprint is None:
                cursor = conn.execute("DELETE FROM metadata_cache")
            else:
                cursor = conn.execute(
                    "DELETE FROM metadata_cache WHERE db_fingerprint = ?",
                    (db_fingerprint,),
                )
            return cursor.rowcount


def build_cache_key(
    *,
    database_uri: str | None,
    operation: str,
    operation_args: dict[str, Any] | None,
) -> tuple[str, str, str]:
    db_fingerprint = get_db_fingerprint(database_uri)
    normalized_args = normalize_args(operation_args)
    args_hash = _hash(normalized_args)
    cache_key = _hash(f"{db_fingerprint}|{operation}|{args_hash}")
    return cache_key, db_fingerprint, args_hash


_cache_store = MetadataCacheStore(AppConfig().METADATA_CACHE_PATH)


def get_cached_metadata(
    *,
    operation: str,
    operation_args: dict[str, Any] | None = None,
    database_uri: str | None = None,
    bypass_cache: bool = False,
) -> Any | None:
    if not AppConfig().METADATA_CACHE_ENABLED:
        return None

    if AppConfig().METADATA_CACHE_BYPASS_DEFAULT or bypass_cache:
        logger.debug(f"metadata cache bypassed for operation={operation}")
        return None

    cache_key, _, _ = build_cache_key(
        database_uri=database_uri,
        operation=operation,
        operation_args=operation_args,
    )
    cached = _cache_store.get(cache_key)
    if cached is None:
        logger.debug(f"metadata cache miss for operation={operation}")
    else:
        logger.debug(f"metadata cache hit for operation={operation}")
    return cached


def set_cached_metadata(
    *,
    operation: str,
    value: Any,
    operation_args: dict[str, Any] | None = None,
    database_uri: str | None = None,
    bypass_cache: bool = False,
) -> None:
    if not AppConfig().METADATA_CACHE_ENABLED:
        return

    if AppConfig().METADATA_CACHE_BYPASS_DEFAULT or bypass_cache:
        logger.debug(
            f"metadata cache write skipped by bypass for operation={operation}"
        )
        return

    cache_key, db_fingerprint, args_hash = build_cache_key(
        database_uri=database_uri,
        operation=operation,
        operation_args=operation_args,
    )
    _cache_store.set(
        cache_key=cache_key,
        db_fingerprint=db_fingerprint,
        operation=operation,
        args_hash=args_hash,
        value=value,
        ttl_seconds=AppConfig().METADATA_CACHE_TTL_SECONDS,
    )


def invalidate_metadata_cache(database_uri: str | None = None) -> int:
    db_fingerprint = None if database_uri is None else get_db_fingerprint(database_uri)
    deleted = _cache_store.invalidate(db_fingerprint)
    target = "all databases" if db_fingerprint is None else "active database"
    logger.info(f"metadata cache invalidated for {target}; entries deleted={deleted}")
    return deleted
