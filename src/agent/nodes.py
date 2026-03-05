from langchain.messages import AIMessage
from langgraph.prebuilt import ToolNode

from agent.prompts import (
    ANALYZE_RESULT,
    CHECK_QUERY,
    EXPLAIN_RESULT,
    GENERATE_QUERY,
    HANDLE_IRRELEVANT_RESULT,
    REGENERATE_QUERY_ON_EMPTY_RESULT,
    REGENERATE_QUERY_ON_ERROR,
)
from agent.state import AgentState, AnalysisResult
from config.app_config import AppConfig
from llm.model import model
from tools.database import (
    db,
    get_schema_tool,
    list_tables_tool,
    run_query_tool_with_interrupt,
)

REGEN_PROMPTS = {
    "error": REGENERATE_QUERY_ON_ERROR,
    "empty_result": REGENERATE_QUERY_ON_EMPTY_RESULT,
}

get_schema_node = ToolNode([get_schema_tool], name="get_schema")


def list_tables(state: AgentState):
    tool_call = {
        "name": "sql_db_list_tables",
        "args": {},
        "id": "abc123",
        "type": "tool_call",
    }
    tool_call_message = AIMessage(content="", tool_calls=[tool_call])
    tool_message = list_tables_tool.invoke(tool_call)
    response = AIMessage(f"Available tables: {tool_message.content}")

    return {"messages": [tool_call_message, tool_message, response]}


def call_get_schema(state: AgentState):
    llm_with_tools = model.bind_tools([get_schema_tool], tool_choice="any")

    if (
        state["analysis_result"] is not None
        and state["analysis_result"].status == "irrelevant"
    ):
        user_message = {
            "role": "user",
            "content": HANDLE_IRRELEVANT_RESULT.format(
                user_question=state["user_question"],
                query=state["last_query"],
                database_output=state["messages"][-1].content,
                explanation=state["analysis_result"].explanation,
            ),
        }
        response = llm_with_tools.invoke([user_message] + state["messages"])
        current_retry_count = state["retry_count"] + 1
        return {"messages": [response], "retry_count": current_retry_count}

    response = llm_with_tools.invoke(state["messages"])

    return {"messages": [response]}


def generate_query(state: AgentState):
    system_message = {
        "role": "system",
        "content": GENERATE_QUERY.format(
            dialect=db.dialect,
            top_k=5,
        ),
    }
    llm_with_tools = model.bind_tools([run_query_tool_with_interrupt])

    if state["analysis_result"] is not None and state["analysis_result"].status in [
        "error",
        "empty_result",
    ]:
        user_message = {
            "role": "user",
            "content": REGEN_PROMPTS[state["analysis_result"].status].format(
                query=state["last_query"],
                explanation=state["analysis_result"].explanation,
            ),
        }

        response = llm_with_tools.invoke(
            [system_message, user_message] + state["messages"]
        )

        current_retry_count = state["retry_count"] + 1
        return {"messages": [response], "retry_count": current_retry_count}

    response = llm_with_tools.invoke([system_message] + state["messages"])

    return {"messages": [response]}


def check_query(state: AgentState):
    system_message = {
        "role": "system",
        "content": CHECK_QUERY.format(dialect=db.dialect),
    }

    tool_call = state["messages"][-1].tool_calls[0]
    user_message = {"role": "user", "content": tool_call["args"]["query"]}
    llm_with_tools = model.bind_tools(
        [run_query_tool_with_interrupt], tool_choice="any"
    )
    response = llm_with_tools.invoke([system_message, user_message])
    response.id = state["messages"][-1].id
    last_query = response.tool_calls[0]["args"]["query"]

    return {
        "messages": [response],
        "last_query": last_query,
        "previous_queries": [last_query],
    }


run_query_node = ToolNode([run_query_tool_with_interrupt], name="run_query")


def analyze_result(state: AgentState):
    db_output = state["messages"][-1].content

    system_message = {
        "role": "system",
        "content": ANALYZE_RESULT.format(
            user_input=state["user_question"],
            query_executed=state["last_query"],
            database_output=db_output,
            retry_count=state["retry_count"],
        ),
    }
    structured_llm = model.with_structured_output(AnalysisResult)

    response = structured_llm.invoke([system_message])

    return {
        "db_output": db_output,
        "analysis_result": response,
    }


def should_retry(state: AgentState):
    analysis_result = state.get("analysis_result")

    if state["retry_count"] < AppConfig().MAX_SQL_RETRIES:
        if analysis_result.status == "irrelevant":
            return "call_get_schema"
        if analysis_result.status in ["error", "empty_result"]:
            return "generate_query"
        # explicit exit to prevent repeated queries
        if (
            len(state["previous_queries"]) > 1
            and state["last_query"] in state["previous_queries"][:-1]
        ):
            return "explain_result"

    return "explain_result"


def explain_result(state: AgentState):
    system_message = {
        "role": "system",
        "content": EXPLAIN_RESULT.format(
            user_question=state["user_question"],
            query=state["last_query"],
            status=state["analysis_result"].status,
            database_output=state["db_output"],
            explanation=state["analysis_result"].explanation,
        ),
    }
    response = model.invoke([system_message] + state["messages"])
    return {"messages": [response]}
