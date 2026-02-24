from typing import Literal

from langchain.messages import AIMessage
from langgraph.graph import END, MessagesState
from langgraph.prebuilt import ToolNode

from agent.prompts import CHECK_QUERY, GENERATE_QUERY
from llm.model import model
from tools.database import (
    db,
    get_schema_tool,
    list_tables_tool,
    run_query_tool_with_interrupt,
)

get_schema_node = ToolNode([get_schema_tool], name="get_schema")

run_query_node = ToolNode([run_query_tool_with_interrupt], name="run_query")


def list_tables(state: MessagesState):
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


def call_get_schema(state: MessagesState):
    llm_with_tools = model.bind_tools([get_schema_tool], tool_choice="any")
    response = llm_with_tools.invoke(state["messages"])

    return {"messages": [response]}


def generate_query(state: MessagesState):
    system_message = {
        "role": "system",
        "content": GENERATE_QUERY.format(
            dialect=db.dialect,
            top_k=5,
        ),
    }
    llm_with_tools = model.bind_tools([run_query_tool_with_interrupt])
    response = llm_with_tools.invoke([system_message] + state["messages"])

    return {"messages": [response]}


def check_query(state: MessagesState):
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

    return {"messages": [response]}


def should_continue(state: MessagesState) -> Literal["check_query", END]:
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "check_query"
    else:
        return END
