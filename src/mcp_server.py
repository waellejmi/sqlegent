import logging

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from mcp.server.fastmcp import FastMCP

from app.agent_runtime import build_agent, extract_last_ai_message
from app.state_factory import build_initial_state, make_runnable_config
from config.db_config import DBConfig
from context_layer.service import extract_tables_from_sql, get_context_service
from tools.database import db
from tools.metadata_cache import invalidate_metadata_cache
from utils.logger_setup import LoggerSetup

LoggerSetup.configure_logging()
logger = LoggerSetup.get_logger(__name__, logging.INFO)


def connect_to_database() -> None:
    try:
        tables = db.get_usable_table_names()
        logger.info(f"Database connected. Tables: {tables}")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise


connect_to_database()

mcp = FastMCP("sql-mcp-server")

agent = build_agent()


def _make_config(
    bypass_cache: bool = False,
    invalidate_cache: bool = False,
) -> RunnableConfig:
    return make_runnable_config(
        bypass_cache=bypass_cache,
        invalidate_cache=invalidate_cache,
        usage_callback=UsageMetadataCallbackHandler(),
    )


async def _run_agent_auto_accept(initial_state: dict, config: RunnableConfig) -> str:
    input_state: dict | Command = initial_state

    while True:
        resume_required = False
        async for _, chunk in agent.astream(
            input_state,
            stream_mode="updates",
            config=config,
        ):
            if "__interrupt__" in chunk:
                logger.info("Auto-accepting SQL execution interrupt.")
                input_state = Command(resume={"type": "accept"})
                resume_required = True
                break

        if not resume_required:
            break

    final_state = agent.get_state(config)
    answer = extract_last_ai_message(final_state.values)
    return answer or "Agent completed but produced no output."


@mcp.tool()
async def ask_database(
    question: str,
    bypass_cache: bool = False,
    invalidate_cache: bool = False,
) -> str:
    """
    Answer a natural language question about the database.

    Runs the full SQL agent pipeline: table discovery, schema retrieval,
    query generation, validation, execution, and result explanation.
    Returns a natural language answer.

    Args:
        question: A natural language question about the data.

    Returns:
        A natural language answer based on the query results.
    """
    logger.info(f"ask_database called with: {question!r}")
    config = _make_config(
        bypass_cache=bypass_cache,
        invalidate_cache=invalidate_cache,
    )
    initial_state = build_initial_state(question)
    return await _run_agent_auto_accept(initial_state, config)


@mcp.tool()
async def generate_sql(
    question: str,
    bypass_cache: bool = False,
    invalidate_cache: bool = False,
) -> str:
    """
    Generate a validated SQL query for a natural language question without executing it.

    Runs the agent pipeline through query generation and validation, then stops.
    Does not execute the query against the database.

    Args:
        question: A natural language question about the data.

    Returns:
        A validated SQL query string.
    """
    logger.info(f"generate_sql called with: {question!r}")

    from config.app_config import AppConfig

    original_default = AppConfig.__dataclass_fields__["EXECUTE_SQL_QUERIES"].default
    AppConfig.__dataclass_fields__["EXECUTE_SQL_QUERIES"].default = False

    try:
        config = _make_config(
            bypass_cache=bypass_cache,
            invalidate_cache=invalidate_cache,
        )
        initial_state = build_initial_state(question)

        async for _ in agent.astream(
            initial_state,
            stream_mode="updates",
            config=config,
        ):
            pass

        final_state = agent.get_state(config)
        last_query = final_state.values.get("last_query")

        if not last_query:
            return "Could not generate a SQL query for the given question."

        return last_query
    finally:
        AppConfig.__dataclass_fields__["EXECUTE_SQL_QUERIES"].default = original_default


@mcp.tool()
async def invalidate_cache(scope: str = "current") -> str:
    """
    Invalidate metadata cache entries.

    Args:
        scope: "current" to clear active database entries, "all" to clear all entries.

    Returns:
        Message describing number of deleted cache entries.
    """
    normalized_scope = scope.strip().lower()
    if normalized_scope not in {"current", "all"}:
        return 'Invalid scope. Use "current" or "all".'

    if normalized_scope == "all":
        deleted = invalidate_metadata_cache()
        return (
            f"Invalidated metadata cache for all databases. Deleted entries: {deleted}."
        )

    current_database_uri = DBConfig().get_database_uri()
    deleted = invalidate_metadata_cache(current_database_uri)
    return (
        f"Invalidated metadata cache for current database. Deleted entries: {deleted}."
    )


@mcp.tool()
async def context_reindex(semantic_profile: str = "") -> str:
    """
    Rebuild semantic context index from live schema and MDL YAML files.
    """
    from config.app_config import AppConfig

    if not AppConfig().ENABLE_CONTEXT_LAYER:
        return "Context layer disabled in AppConfig."

    service = get_context_service()
    profile = service.resolve_semantic_profile(semantic_profile)
    if AppConfig().CONTEXT_REQUIRE_SEMANTIC_PROFILE and not profile:
        return (
            "Semantic profile is required. Configure CONTEXT_DEFAULT_SEMANTIC_PROFILE "
            "or pass semantic_profile."
        )

    table_names = list(db.get_usable_table_names())
    summary = service.index_semantic_context(
        db,
        table_names,
        semantic_profile=profile,
    )
    return f"Context reindex done: {summary}"


@mcp.tool()
async def context_stats() -> str:
    """
    Return context layer stats for active project/database.
    """
    from config.app_config import AppConfig

    if not AppConfig().ENABLE_CONTEXT_LAYER:
        return "Context layer disabled in AppConfig."

    return str(get_context_service().get_stats())


@mcp.tool()
async def confirm_sql_pair(question: str, sql: str, row_count: int = 1) -> str:
    """
    Persist a verified NL->SQL pair into query memory.
    """
    from config.app_config import AppConfig

    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER or not config.ENABLE_QUERY_MEMORY:
        return "Query memory disabled in AppConfig."

    memory_id = get_context_service().record_verified_query(
        question=question,
        sql=sql,
        tables=extract_tables_from_sql(sql),
        row_count=max(0, int(row_count)),
        is_verified=True,
        metadata={"source": "mcp", "confirmed": True},
    )
    if not memory_id:
        return "Pair did not meet storage policy (check verification/non-empty rules)."
    return f"Stored verified pair id: {memory_id}"


@mcp.tool()
async def log_failed_request(
    question: str,
    status: str,
    sql: str = "",
    error_message: str = "",
    retry_count: int = 0,
) -> str:
    """
    Persist a failed request event (only when ENABLE_FAILED_QUERY_LOG is true).
    """
    from config.app_config import AppConfig

    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER or not config.ENABLE_FAILED_QUERY_LOG:
        return "Failed-query logging disabled in AppConfig."

    failure_id = get_context_service().record_failed_query(
        question=question,
        sql=sql or None,
        status=status,
        error_message=error_message or None,
        retry_count=max(0, int(retry_count)),
        metadata={"source": "mcp"},
    )
    if not failure_id:
        return "Failed request was not stored."
    return f"Stored failed request id: {failure_id}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
