from typing import Annotated

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agent.graph import agent as nl2sql_agent
from config.app_config import AppConfig


from app.state_factory import build_initial_state


@tool
def call_nl2sql_tool(
    user_question: Annotated[
        str, "The user's question or intent to be resolved against the database."
    ],
    config: RunnableConfig,
) -> str:
    """
    Invokes the specialized NL2SQL Subagent to answer questions requiring database access.
    Pass the user's question. The subagent will analyze the schema, query the DB, and return a final formatted answer.
    """
    initial_state = build_initial_state(user_question)

    # We pass the same config to the subagent so thread_id is preserved for its memory
    result = nl2sql_agent.invoke(initial_state, config=config)

    return result.get("final_answer", "Error: No final answer produced by subagent.")
