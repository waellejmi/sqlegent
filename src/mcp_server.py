import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from mcp.server.fastmcp import FastMCP

from agent.graph import agent
from agent.state import AgentState
from tools.database import db
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


def _build_initial_state(question: str) -> AgentState:
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


def _make_config() -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": str(uuid.uuid4())})


def _extract_content(msg: AIMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    # content can be a list of blocks — join text parts
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
async def ask_database(question: str) -> str:
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
    config = _make_config()
    initial_state = _build_initial_state(question)
    return await _run_agent_auto_accept(initial_state, config)


@mcp.tool()
async def generate_sql(question: str) -> str:
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
        config = _make_config()
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


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
