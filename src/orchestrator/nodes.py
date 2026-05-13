from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from llm.model import get_model
from orchestrator.prompts import ORCHESTRATOR_SYSTEM_PROMPT
from orchestrator.state import OrchestratorState
from tools.database import get_schema_tool_with_cache, list_tables_with_cache
from tools.nl2sql_pipeline import call_nl2sql_tool, quick_fix_query_tool

tools = [
    call_nl2sql_tool,
    get_schema_tool_with_cache,
    list_tables_with_cache,
    quick_fix_query_tool,
]
tool_node = ToolNode(tools)


def chat_node(state: OrchestratorState):
    llm = get_model()
    llm_with_tools = llm.bind_tools(tools)

    messages = state["messages"]

    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT)] + messages

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}
