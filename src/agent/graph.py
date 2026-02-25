from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from agent.nodes import (
    call_get_schema,
    check_query,
    generate_query,
    get_schema_node,
    list_tables,
    run_query_node,
    should_continue,
)

builder = StateGraph(MessagesState)
builder.add_node(list_tables)
builder.add_node(call_get_schema)
builder.add_node(get_schema_node, "get_schema")
builder.add_node(generate_query)
builder.add_node(check_query)
builder.add_node(run_query_node, "run_query")

builder.add_edge(START, "list_tables")
builder.add_edge("list_tables", "call_get_schema")
builder.add_edge("call_get_schema", "get_schema")
builder.add_edge("get_schema", "generate_query")
builder.add_conditional_edges(
    "generate_query", should_continue, {"check_query": "check_query", "END": END}
)
builder.add_edge("check_query", "run_query")
builder.add_edge("run_query", "generate_query")

checkpointer = InMemorySaver()
agent = builder.compile(checkpointer=checkpointer)

# Go to mermaid.live to visualize the graph
print(agent.get_graph().draw_mermaid())
