import logging
import uuid

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from mcp.server.fastmcp import FastMCP

from agent.graph import agent
from agent.state import AgentState
from config.db_config import DBConfig
from tools.database import db
from tools.metadata_cache import invalidate_metadata_cache
from utils.logger_setup import LoggerSetup

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


def _build_initial_state(
    question: str,
) -> AgentState:
    return AgentState(
        messages=[HumanMessage(content=question)],
        user_question=question,
        last_query=None,
        previous_queries=[],
        analysis_result=None,
        skip_decision=None,
        db_output=None,
        retry_count=0,
    )


def _make_config(
    bypass_cache: bool = False,
    invalidate_cache: bool = False,
) -> RunnableConfig:
    return RunnableConfig(
        configurable={
            "thread_id": str(uuid.uuid4()),
            "metadata_bypass_cache": bypass_cache,
            "metadata_invalidate_cache": invalidate_cache,
        },
        callbacks=[UsageMetadataCallbackHandler()],
    )


def _extract_content(msg: AIMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    parts = [
        block if isinstance(block, str) else block.get("text", "")
        for block in msg.content
    ]
    return "".join(parts)


async def _run_agent_auto_accept(
    initial_state: AgentState, config: RunnableConfig
) -> str:
    input_state: AgentState | Command = initial_state

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
    messages = final_state.values.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return _extract_content(msg)

    return "Agent completed but produced no output."


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
    initial_state = _build_initial_state(question)
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
        initial_state = _build_initial_state(question)

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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
