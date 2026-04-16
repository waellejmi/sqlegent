import json
import logging
from dataclasses import dataclass
from typing import Any

from config.app_config import AppConfig
from context_layer.chunking import (
    build_context_text,
    build_instruction_chunks,
    build_query_memory_text,
    build_schema_chunks,
)
from context_layer.embedder import build_local_embedder
from context_layer.md_loader import load_or_build_semantic_model
from context_layer.store import ContextStore, SearchHit
from utils.helpers import _hash, get_db_fingerprint, to_json
from utils.logger_setup import LoggerSetup

logger = LoggerSetup.get_logger(__name__, logging.INFO)


@dataclass
class RetrievedContext:
    schema_hits: list[SearchHit]
    instruction_hits: list[SearchHit]
    query_memory_hits: list[SearchHit]
    schema_text: str
    instruction_text: str
    query_memory_text: str


class ContextLayerService:
    def __init__(self) -> None:
        self._config = AppConfig()
        self._store = ContextStore(self._config.CONTEXT_STORE_PATH)
        self._embedder = build_local_embedder()

    @property
    def embedding_profile_id(self) -> str:
        return self._embedder.profile.id

    def resolve_semantic_profile(
        self, semantic_profile: str | None = None
    ) -> str | None:
        profile = (semantic_profile or "").strip()
        if profile:
            return profile

        default_profile = (self._config.CONTEXT_DEFAULT_SEMANTIC_PROFILE or "").strip()
        if default_profile:
            return default_profile

        return None

    def index_semantic_context(
        self,
        database,
        table_names: list[str],
        semantic_profile: str | None = None,
    ) -> dict[str, Any]:
        if not self._config.ENABLE_CONTEXT_LAYER:
            return {"indexed": False, "reason": "context layer disabled"}

        resolved_profile = self.resolve_semantic_profile(semantic_profile)
        if self._config.CONTEXT_REQUIRE_SEMANTIC_PROFILE and not resolved_profile:
            return {
                "indexed": False,
                "reason": "semantic profile is required",
                "semantic_profile": None,
            }

        semantic_model = load_or_build_semantic_model(
            database,
            table_names,
            semantic_profile=resolved_profile,
        )
        semantic_dict = {
            "models": semantic_model.models,
            "relationships": semantic_model.relationships,
            "instructions": semantic_model.instructions,
        }
        schema_hash = _hash(to_json(semantic_dict))

        schema_chunks = build_schema_chunks(semantic_dict)
        instruction_chunks = build_instruction_chunks(semantic_dict)
        all_chunks = schema_chunks + instruction_chunks

        vectors = self._embedder.embed_texts([chunk.content for chunk in all_chunks])
        for chunk, embedding in zip(all_chunks, vectors, strict=False):
            chunk.embedding = embedding

        project_id = self._config.CONTEXT_PROJECT_ID
        db_fingerprint = get_db_fingerprint()

        inserted = self._store.replace_chunks(
            project_id=project_id,
            db_fingerprint=db_fingerprint,
            embedding_model=self.embedding_profile_id,
            chunks=all_chunks,
            channels=["schema", "instructions"],
        )

        stats = {
            "schema_chunks": len(schema_chunks),
            "instruction_chunks": len(instruction_chunks),
            "total_chunks": inserted,
            "semantic_profile": resolved_profile,
        }
        self._store.update_index_state(
            project_id=project_id,
            db_fingerprint=db_fingerprint,
            embedding_model=self.embedding_profile_id,
            schema_hash=schema_hash,
            stats=stats,
        )

        logger.info(
            "Context indexed: project=%s db=%s chunks=%s",
            project_id,
            db_fingerprint,
            inserted,
        )
        return {
            "indexed": True,
            "project_id": project_id,
            "db_fingerprint": db_fingerprint,
            "embedding_profile": self.embedding_profile_id,
            "semantic_profile": resolved_profile,
            **stats,
        }

    def retrieve_context(self, question: str) -> RetrievedContext:
        empty = RetrievedContext(
            schema_hits=[],
            instruction_hits=[],
            query_memory_hits=[],
            schema_text="Schema context: none",
            instruction_text="Instruction context: none",
            query_memory_text="Query memory examples: none",
        )
        if not self._config.ENABLE_CONTEXT_LAYER:
            return empty

        if not question.strip():
            return empty

        query_embedding = self._embedder.embed_query(question)
        if not query_embedding:
            return empty

        project_id = self._config.CONTEXT_PROJECT_ID
        db_fingerprint = get_db_fingerprint()

        schema_hits = (
            self._store.search_chunks(
                project_id=project_id,
                db_fingerprint=db_fingerprint,
                embedding_model=self.embedding_profile_id,
                channel="schema",
                query_embedding=query_embedding,
                top_k=self._config.SCHEMA_CONTEXT_TOP_K,
                min_similarity=self._config.SCHEMA_CONTEXT_MIN_SIMILARITY,
            )
            if self._config.ENABLE_SCHEMA_CONTEXT
            else []
        )

        instruction_hits = (
            self._store.search_chunks(
                project_id=project_id,
                db_fingerprint=db_fingerprint,
                embedding_model=self.embedding_profile_id,
                channel="instructions",
                query_embedding=query_embedding,
                top_k=self._config.INSTRUCTION_CONTEXT_TOP_K,
                min_similarity=self._config.INSTRUCTION_CONTEXT_MIN_SIMILARITY,
            )
            if self._config.ENABLE_INSTRUCTION_CONTEXT
            else []
        )

        query_memory_hits = (
            self._store.search_query_memory(
                project_id=project_id,
                db_fingerprint=db_fingerprint,
                embedding_model=self.embedding_profile_id,
                query_embedding=query_embedding,
                top_k=self._config.QUERY_MEMORY_TOP_K,
                min_similarity=self._config.QUERY_MEMORY_MIN_SIMILARITY,
                require_verified=self._config.QUERY_MEMORY_REQUIRE_VERIFIED,
            )
            if self._config.ENABLE_QUERY_MEMORY
            else []
        )

        schema_text = build_context_text(
            hits=schema_hits,
            max_chars=self._config.SCHEMA_CONTEXT_MAX_CHARS,
            title="Schema context",
        )
        instruction_text = build_context_text(
            hits=instruction_hits,
            max_chars=self._config.INSTRUCTION_CONTEXT_MAX_CHARS,
            title="Instruction context",
        )
        query_memory_text = build_query_memory_text(
            hits=query_memory_hits,
            max_chars=self._config.QUERY_MEMORY_MAX_CHARS,
        )

        return RetrievedContext(
            schema_hits=schema_hits,
            instruction_hits=instruction_hits,
            query_memory_hits=query_memory_hits,
            schema_text=schema_text,
            instruction_text=instruction_text,
            query_memory_text=query_memory_text,
        )

    def record_verified_query(
        self,
        *,
        question: str,
        sql: str,
        tables: list[str],
        row_count: int,
        is_verified: bool,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if (
            not self._config.ENABLE_CONTEXT_LAYER
            or not self._config.ENABLE_QUERY_MEMORY
        ):
            return None

        if self._config.QUERY_MEMORY_REQUIRE_NON_EMPTY and row_count <= 0:
            return None

        if self._config.QUERY_MEMORY_REQUIRE_VERIFIED and not is_verified:
            return None

        question = question.strip()
        sql = sql.strip()
        if not question or not sql:
            return None

        embedding = self._embedder.embed_query(question)
        if not embedding:
            return None

        return self._store.upsert_query_memory(
            project_id=self._config.CONTEXT_PROJECT_ID,
            db_fingerprint=get_db_fingerprint(),
            embedding_model=self.embedding_profile_id,
            question=question,
            sql=sql,
            tables=tables,
            row_count=row_count,
            is_verified=is_verified,
            embedding=embedding,
            metadata=metadata or {},
            max_rows_per_db=self._config.QUERY_MEMORY_MAX_ROWS_PER_DB,
        )

    def record_failed_query(
        self,
        *,
        question: str,
        sql: str | None,
        status: str,
        error_message: str | None,
        retry_count: int,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if (
            not self._config.ENABLE_CONTEXT_LAYER
            or not self._config.ENABLE_FAILED_QUERY_LOG
        ):
            return None

        return self._store.log_failed_query(
            project_id=self._config.CONTEXT_PROJECT_ID,
            db_fingerprint=get_db_fingerprint(),
            question=question,
            sql=sql,
            status=status,
            error_message=error_message,
            retry_count=retry_count,
            metadata=metadata or {},
            max_rows_per_db=self._config.FAILED_QUERY_LOG_MAX_ROWS_PER_DB,
        )

    def get_stats(self) -> dict[str, Any]:
        return self._store.get_stats(
            project_id=self._config.CONTEXT_PROJECT_ID,
            db_fingerprint=get_db_fingerprint(),
        )


_context_service: ContextLayerService | None = None


def get_context_service() -> ContextLayerService:
    global _context_service
    if _context_service is None:
        _context_service = ContextLayerService()
    return _context_service


def safe_parse_row_count(db_output: str | None) -> int:
    if not db_output:
        return 0

    lowered = db_output.lower()
    if "0 rows" in lowered:
        return 0

    try:
        parsed = json.loads(db_output)
        if isinstance(parsed, list):
            return len(parsed)
        if isinstance(parsed, dict):
            if isinstance(parsed.get("rows"), list):
                return len(parsed["rows"])
            if isinstance(parsed.get("data"), list):
                return len(parsed["data"])
    except Exception:
        pass

    if "rows returned" in lowered:
        chunks = lowered.replace("\n", " ").split()
        for idx, token in enumerate(chunks):
            if token == "rows" and idx > 0:
                try:
                    return int(chunks[idx - 1])
                except Exception:
                    continue

    return 1


def extract_tables_from_sql(sql: str) -> list[str]:
    sql = (sql or "").strip()
    if not sql:
        return []

    try:
        import sqlglot
        from sqlglot import exp
    except Exception:
        return []

    try:
        parsed = sqlglot.parse_one(sql)
    except Exception:
        return []

    names: set[str] = set()
    for table in parsed.find_all(exp.Table):
        table_name = table.name
        schema_name = table.db
        if table_name and schema_name:
            names.add(f"{schema_name}.{table_name}")
        elif table_name:
            names.add(table_name)

    return sorted(names)
