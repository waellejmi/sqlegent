import logging

from langchain.messages import AIMessage
from langgraph.prebuilt import ToolNode
from langgraph.types import Command

from agent.prompts import (
    ANALYZE_RESULT,
    CHECK_QUERY,
    EXPLAIN_RESULT,
    GENERATE_QUERY,
    HANDLE_IRRELEVANT_RESULT,
    REGENERATE_QUERY_ON_EMPTY_RESULT,
    REGENERATE_QUERY_ON_ERROR,
    SHOULD_SKIP,
)
from agent.state import AgentState, AnalysisResult, SkipDecision
from config.app_config import AppConfig
from llm.model import model
from tools.database import (
    db,
    get_schema_tool,
    list_tables_tool,
    run_query_tool_with_interrupt,
)
from utils.logger_setup import LoggerSetup

logger = LoggerSetup.get_logger(__name__, logging.DEBUG)

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


def skip_pipeline(state: AgentState):
    system_message = {
        "role": "system",
        "content": SHOULD_SKIP,
    }
    structured_model = model.with_structured_output(SkipDecision)
    result = structured_model.invoke([system_message] + state["messages"])

    logger.debug(f"Skip Decision: {result}")
    return {
        "skip_decision": result,
    }


def should_skip(state: AgentState):
    if state["skip_decision"] and state["skip_decision"].skip:
        return "explain_result"

    return "call_get_schema"


def call_get_schema(state: AgentState):
    llm_with_tools = model.bind_tools([get_schema_tool])

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
    logger.debug(f"Schema Tool Response: {response}")
    return {"messages": [response]}


def generate_query(state: AgentState):
    system_message = {
        "role": "system",
        "content": GENERATE_QUERY.format(
            dialect=db.dialect,
            top_k=5,
        ),
    }
    llm_with_tools = model.bind_tools(
        [run_query_tool_with_interrupt], tool_choice="any"
    )

    if state["analysis_result"] is not None and state["analysis_result"].status in [
        "error",
        "empty_result",
    ]:
        original_messages = [m for m in state["messages"] if m.type == "human"]
        user_message = {
            "role": "user",
            "content": REGEN_PROMPTS[state["analysis_result"].status].format(
                query=state["last_query"],
                explanation=state["analysis_result"].explanation,
            ),
        }

        response = llm_with_tools.invoke(
            [system_message] + original_messages + [user_message]
        )

        current_retry_count = state["retry_count"] + 1
        return {"messages": [response], "retry_count": current_retry_count}

    response = llm_with_tools.invoke([system_message] + state["messages"])
    logger.debug(f"Generated Query: {response}")

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

    logger.debug(f"Check Query Response: {response}")
    logger.debug(f"Checked Query: {last_query}")

    return {
        "messages": [response],
        "last_query": last_query,
        "previous_queries": [last_query],
    }


def should_execute(state: AgentState):
    if not AppConfig().EXECUTE_SQL_QUERIES:
        return "explain_result"
    return "run_query"


run_query_node = ToolNode([run_query_tool_with_interrupt], name="run_query")


def analyze_result(state: AgentState):
    db_output = state["messages"][-1].content or "Empty, 0 rows returned"

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

    logger.debug(f"Analysis Result: {response.model_dump_json()}")

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
    if not AppConfig().EXECUTE_SQL_QUERIES:
        logger.debug(
            "SQL execution is disabled. Skipping query execution and explanation."
        )
        logger.debug(f"Last Query: {state['last_query']}")
        return {"query": state["last_query"]}

    if state["skip_decision"] and state["skip_decision"].skip:
        explanation = f"The agent decided to skip executing the query because: {state['skip_decision'].reason}"
        logger.debug(f"Skip Explanation: {explanation}")
        return {"messages": [AIMessage(content=explanation)]}

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
    logger.debug(f"Explanation: {response}")
    return {"messages": [response]}
