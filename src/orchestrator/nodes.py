from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from config.app_config import AppConfig
from llm.model import get_model
from orchestrator.prompts import ORCHESTRATOR_SYSTEM_PROMPT
from orchestrator.state import OrchestratorState
from orchestrator.tools import call_nl2sql_tool

tools = [call_nl2sql_tool]
tool_node = ToolNode(tools)


def chat_node(state: OrchestratorState):
    llm = get_model()
    llm_with_tools = llm.bind_tools(tools)

    messages = state["messages"]

    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT)] + messages

    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}
