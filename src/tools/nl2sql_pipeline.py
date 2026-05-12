import json
from typing import Annotated

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agent.graph import agent as nl2sql_agent
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

    result = nl2sql_agent.invoke(initial_state, config=config)
    analysis_result = result.get("analysis_result")
    payload = {
        "question": user_question,
        "answer": result.get(
            "final_answer", "Error: No final answer produced by subagent."
        ),
        "sql": result.get("last_query"),
        "db_output": result.get("db_output"),
        "analysis_status": getattr(analysis_result, "status", None),
        "analysis_explanation": getattr(analysis_result, "explanation", None),
    }

    return json.dumps(payload, ensure_ascii=False)
