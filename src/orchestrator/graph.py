from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import tools_condition

from config.app_config import AppConfig
from orchestrator.nodes import chat_node, tool_node
from orchestrator.state import OrchestratorState

builder = StateGraph(OrchestratorState)

builder.add_node("chat", chat_node)
builder.add_node("tools", tool_node)

builder.add_edge(START, "chat")

builder.add_conditional_edges(
    "chat",
    tools_condition,
)

builder.add_edge("tools", "chat")

# We no longer compile with the synchronous checkpointer globally.
# The builder is exported and compiled with an async checkpointer in agent_runtime.py.
# We compile a dummy agent just for graph visualization if needed.
agent = builder.compile()

if AppConfig().SHOW_AGENT_GRAPH and AppConfig().ENABLE_ORCHESTRATOR:
    print(agent.get_graph().draw_mermaid())
