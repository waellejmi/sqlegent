import json
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agent.graph import agent as nl2sql_agent
from app.state_factory import build_initial_state
from tools.database import run_query_tool_with_interrupt


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

    result = nl2sql_agent.invoke(initial_state, config=config)
    analysis_result = result.get("analysis_result")
    payload = {
        "question": user_question,
        **(
            {
                "answer": result.get(
                    "final_answer", "Error: No final answer produced by subagent."
                )
            }
            if result.get("final_answer") != "ORCHESTRATOR_FORMAT_REQUIRED"
            else {}
        ),
        "sql": result.get("last_query"),
        "db_output": result.get("db_output"),
        "analysis_status": getattr(analysis_result, "status", None),
        "analysis_explanation": getattr(analysis_result, "explanation", None),
    }

    return json.dumps(payload, ensure_ascii=False)


@tool
def quick_fix_query_tool(patched_sql_query: Annotated[str, "The patched sql query"]):
    """
    Executes a SQL query after applying minor, deterministic refinements.

    Call this when a previous SQL execution result was valid but requires
    small adjustments (e.g., changing sort order, removing result limits,
    or fixing formatting) to meet the user's specific output requirements.

    Do not use for complex logic changes or structural redesigns.
    """

    return run_query_tool_with_interrupt.invoke({"query": patched_sql_query})
