import math
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.helpers import (
    from_json,
    normalize_whitespace,
    to_json,
)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0

    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return -1.0

    return dot / (norm_a * norm_b)


@dataclass
class ChunkRecord:
    id: str
    channel: str
    source_type: str
    name: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass
class SearchHit:
    id: str
    name: str
    content: str
    score: float
    source_type: str
    metadata: dict[str, Any]


class ContextStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def _ensure_db(self) -> None:
        if isinstance(self._db_path, str):
            self._db_path = Path(self._db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS context_chunks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    db_fingerprint TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_context_chunks_scope
                ON context_chunks (project_id, db_fingerprint, embedding_model, channel)
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_memory (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    db_fingerprint TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    question TEXT NOT NULL,
                    question_norm TEXT NOT NULL,
                    sql TEXT NOT NULL,
                    tables_json TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    is_verified INTEGER NOT NULL,
                    embedding_json TEXT NOT NULL,
                    meta_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_query_memory_scope
                ON query_memory (project_id, db_fingerprint, embedding_model, is_verified)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_query_memory_unique
                ON query_memory (project_id, db_fingerprint, question_norm, sql)
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failed_queries (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    db_fingerprint TEXT NOT NULL,
                    question TEXT NOT NULL,
                    sql TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    retry_count INTEGER NOT NULL,
                    meta_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_failed_queries_scope
                ON failed_queries (project_id, db_fingerprint, created_at)
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS context_index_state (
                    project_id TEXT NOT NULL,
                    db_fingerprint TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    stats_json TEXT NOT NULL,
                    indexed_at INTEGER NOT NULL,
                    PRIMARY KEY (project_id, db_fingerprint, embedding_model)
                )
                """
            )

    def replace_chunks(
        self,
        *,
        project_id: str,
        db_fingerprint: str,
        embedding_model: str,
        chunks: list[ChunkRecord],
        channels: list[str] | None = None,
    ) -> int:
        target_channels = sorted(channels or {chunk.channel for chunk in chunks})
        if not target_channels:
            return 0

        now = int(time.time())

        placeholders = ",".join("?" for _ in target_channels)
        sql_delete = (
            "DELETE FROM context_chunks "
            "WHERE project_id = ? AND db_fingerprint = ? AND embedding_model = ? "
            f"AND channel IN ({placeholders})"
        )
        delete_args = [project_id, db_fingerprint, embedding_model, *target_channels]

        rows = [
            (
                chunk.id,
                project_id,
                db_fingerprint,
                embedding_model,
                chunk.channel,
                chunk.source_type,
                chunk.name,
                chunk.content,
                to_json(chunk.embedding),
                to_json(chunk.metadata),
                now,
            )
            for chunk in chunks
            if chunk.channel in target_channels
        ]

        with self._lock:
            with self._connect() as conn:
                conn.execute(sql_delete, delete_args)
                if rows:
                    conn.executemany(
                        """
                        INSERT INTO context_chunks (
                            id, project_id, db_fingerprint, embedding_model, channel,
                            source_type, name, content, embedding_json, meta_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )

        return len(rows)

    def search_chunks(
        self,
        *,
        project_id: str,
        db_fingerprint: str,
        embedding_model: str,
        channel: str,
        query_embedding: list[float],
        top_k: int,
        min_similarity: float,
    ) -> list[SearchHit]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, name, source_type, content, embedding_json, meta_json
                    FROM context_chunks
                    WHERE project_id = ?
                      AND db_fingerprint = ?
                      AND embedding_model = ?
                      AND channel = ?
                    """,
                    (project_id, db_fingerprint, embedding_model, channel),
                ).fetchall()

        scored: list[SearchHit] = []
        for row in rows:
            record_id, name, source_type, content, embedding_json, meta_json = row
            embedding = from_json(embedding_json, default=[])
            score = cosine_similarity(query_embedding, embedding)
            if score < min_similarity:
                continue
            scored.append(
                SearchHit(
                    id=record_id,
                    name=name,
                    source_type=source_type,
                    content=content,
                    score=score,
                    metadata=from_json(meta_json, default={}),
                )
            )

        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def upsert_query_memory(
        self,
        *,
        project_id: str,
        db_fingerprint: str,
        embedding_model: str,
        question: str,
        sql: str,
        tables: list[str],
        row_count: int,
        is_verified: bool,
        embedding: list[float],
        metadata: dict[str, Any],
        max_rows_per_db: int,
    ) -> str:
        now = int(time.time())
        memory_id = str(uuid.uuid4())
        question_norm = normalize_whitespace(question).lower()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO query_memory (
                        id, project_id, db_fingerprint, embedding_model, question,
                        question_norm, sql, tables_json, row_count, is_verified,
                        embedding_json, meta_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, db_fingerprint, question_norm, sql)
                    DO UPDATE SET
                        row_count = excluded.row_count,
                        is_verified = excluded.is_verified,
                        embedding_json = excluded.embedding_json,
                        meta_json = excluded.meta_json,
                        created_at = excluded.created_at
                    """,
                    (
                        memory_id,
                        project_id,
                        db_fingerprint,
                        embedding_model,
                        question,
                        question_norm,
                        sql,
                        to_json(tables),
                        row_count,
                        1 if is_verified else 0,
                        to_json(embedding),
                        to_json(metadata),
                        now,
                    ),
                )

                self._trim_rows(
                    conn,
                    table="query_memory",
                    project_id=project_id,
                    db_fingerprint=db_fingerprint,
                    max_rows=max_rows_per_db,
                )

        return memory_id

    def search_query_memory(
        self,
        *,
        project_id: str,
        db_fingerprint: str,
        embedding_model: str,
        query_embedding: list[float],
        top_k: int,
        min_similarity: float,
        require_verified: bool,
    ) -> list[SearchHit]:
        verified_filter = "AND is_verified = 1" if require_verified else ""
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT id, question, sql, tables_json, embedding_json, meta_json, row_count, is_verified
                    FROM query_memory
                    WHERE project_id = ?
                      AND db_fingerprint = ?
                      AND embedding_model = ?
                      {verified_filter}
                    """,
                    (project_id, db_fingerprint, embedding_model),
                ).fetchall()

        scored: list[SearchHit] = []
        for row in rows:
            (
                memory_id,
                question,
                sql,
                tables_json,
                embedding_json,
                meta_json,
                row_count,
                is_verified,
            ) = row
            score = cosine_similarity(
                query_embedding, from_json(embedding_json, default=[])
            )
            if score < min_similarity:
                continue

            tables = from_json(tables_json, default=[])
            metadata = from_json(meta_json, default={})
            payload = {
                "question": question,
                "sql": sql,
                "tables": tables,
                "row_count": row_count,
                "is_verified": bool(is_verified),
                **metadata,
            }
            scored.append(
                SearchHit(
                    id=memory_id,
                    name="query_memory",
                    source_type="nl_sql_pair",
                    content=to_json(payload),
                    score=score,
                    metadata=payload,
                )
            )

        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def log_failed_query(
        self,
        *,
        project_id: str,
        db_fingerprint: str,
        question: str,
        sql: str | None,
        status: str,
        error_message: str | None,
        retry_count: int,
        metadata: dict[str, Any],
        max_rows_per_db: int,
    ) -> str:
        failure_id = str(uuid.uuid4())
        now = int(time.time())

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO failed_queries (
                        id, project_id, db_fingerprint, question, sql, status,
                        error_message, retry_count, meta_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        failure_id,
                        project_id,
                        db_fingerprint,
                        question,
                        sql,
                        status,
                        error_message,
                        retry_count,
                        to_json(metadata),
                        now,
                    ),
                )

                self._trim_rows(
                    conn,
                    table="failed_queries",
                    project_id=project_id,
                    db_fingerprint=db_fingerprint,
                    max_rows=max_rows_per_db,
                )

        return failure_id

    def update_index_state(
        self,
        *,
        project_id: str,
        db_fingerprint: str,
        embedding_model: str,
        schema_hash: str,
        stats: dict[str, Any],
    ) -> None:
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO context_index_state (
                        project_id, db_fingerprint, embedding_model, schema_hash, stats_json, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, db_fingerprint, embedding_model)
                    DO UPDATE SET
                        schema_hash = excluded.schema_hash,
                        stats_json = excluded.stats_json,
                        indexed_at = excluded.indexed_at
                    """,
                    (
                        project_id,
                        db_fingerprint,
                        embedding_model,
                        schema_hash,
                        to_json(stats),
                        now,
                    ),
                )

    def get_index_state(
        self,
        *,
        project_id: str,
        db_fingerprint: str,
        embedding_model: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT schema_hash, stats_json, indexed_at
                    FROM context_index_state
                    WHERE project_id = ? AND db_fingerprint = ? AND embedding_model = ?
                    """,
                    (project_id, db_fingerprint, embedding_model),
                ).fetchone()
        if row is None:
            return None
        schema_hash, stats_json, indexed_at = row
        return {
            "schema_hash": schema_hash,
            "stats": from_json(stats_json, default={}),
            "indexed_at": indexed_at,
        }

    def get_stats(self, *, project_id: str, db_fingerprint: str) -> dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                chunk_counts = conn.execute(
                    """
                    SELECT channel, COUNT(*)
                    FROM context_chunks
                    WHERE project_id = ? AND db_fingerprint = ?
                    GROUP BY channel
                    """,
                    (project_id, db_fingerprint),
                ).fetchall()

                query_memory_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM query_memory
                    WHERE project_id = ? AND db_fingerprint = ?
                    """,
                    (project_id, db_fingerprint),
                ).fetchone()[0]

                failed_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM failed_queries
                    WHERE project_id = ? AND db_fingerprint = ?
                    """,
                    (project_id, db_fingerprint),
                ).fetchone()[0]

        return {
            "chunks": {channel: count for channel, count in chunk_counts},
            "query_memory": int(query_memory_count),
            "failed_queries": int(failed_count),
        }

    def _trim_rows(
        self,
        conn: sqlite3.Connection,
        *,
        table: str,
        project_id: str,
        db_fingerprint: str,
        max_rows: int,
    ) -> None:
        if max_rows <= 0:
            return

        count = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE project_id = ? AND db_fingerprint = ?
            """,
            (project_id, db_fingerprint),
        ).fetchone()[0]

        over = int(count) - max_rows
        if over <= 0:
            return

        conn.execute(
            f"""
            DELETE FROM {table}
            WHERE id IN (
                SELECT id
                FROM {table}
                WHERE project_id = ? AND db_fingerprint = ?
                ORDER BY created_at ASC
                LIMIT ?
            )
            """,
            (project_id, db_fingerprint, over),
        )
