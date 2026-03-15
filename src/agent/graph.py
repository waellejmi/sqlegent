from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    analyze_result,
    call_get_schema,
    check_query,
    explain_result,
    generate_query,
    get_schema_node,
    list_tables,
    run_query_node,
    should_execute,
    should_retry,
    should_skip,
    skip_pipeline,
)
from agent.state import AgentState

builder = StateGraph(AgentState)
builder.add_node(list_tables)
builder.add_node(skip_pipeline)
builder.add_node(call_get_schema)
builder.add_node(get_schema_node, "get_schema")
builder.add_node(generate_query)
builder.add_node(check_query)
builder.add_node(run_query_node, "run_query")
builder.add_node(analyze_result)
builder.add_node(explain_result)

builder.add_edge(START, "list_tables")
builder.add_edge("list_tables", "skip_pipeline")

builder.add_conditional_edges(
    "skip_pipeline",
    should_skip,
    {"explain_result": "explain_result", "call_get_schema": "call_get_schema"},
)

builder.add_edge("call_get_schema", "get_schema")
builder.add_edge("get_schema", "generate_query")
builder.add_edge("generate_query", "check_query")

builder.add_conditional_edges(
    "check_query",
    should_execute,
    {"explain_result": "explain_result", "run_query": "run_query"},
)

builder.add_edge("run_query", "analyze_result")

builder.add_conditional_edges(
    "analyze_result",
    should_retry,
    {
        "explain_result": "explain_result",
        "call_get_schema": "call_get_schema",
        "generate_query": "generate_query",
    },
)

builder.add_edge("explain_result", END)

checkpointer = InMemorySaver()
agent = builder.compile(checkpointer=checkpointer)

# Go to mermaid.live to visualize the graph
print(agent.get_graph().draw_mermaid())
