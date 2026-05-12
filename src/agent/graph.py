from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    analyze_result,
    call_get_schema,
    explain_result,
    generate_query,
    get_schema_for_candidate_tables,
    list_tables,
    question_synthesis,
    retrieve_context,
    run_query,
    should_execute,
    should_retry,
    should_skip,
    skip_pipeline,
)
from agent.state import SqlAgentState
from config.app_config import AppConfig

builder = StateGraph(SqlAgentState)
builder.add_node(question_synthesis)
builder.add_node(list_tables)
builder.add_node(retrieve_context)
builder.add_node(skip_pipeline)
builder.add_node(call_get_schema)
builder.add_node("get_schema", get_schema_for_candidate_tables)
builder.add_node(generate_query)
builder.add_node("run_query", run_query)
builder.add_node(analyze_result)
builder.add_node(explain_result)

builder.add_edge(START, "question_synthesis")
builder.add_edge("question_synthesis", "list_tables")
builder.add_edge("list_tables", "retrieve_context")
builder.add_edge("retrieve_context", "skip_pipeline")


builder.add_conditional_edges(
    "skip_pipeline",
    should_skip,
    {"explain_result": "explain_result", "call_get_schema": "call_get_schema"},
)

builder.add_edge("call_get_schema", "get_schema")
builder.add_edge("get_schema", "generate_query")

builder.add_conditional_edges(
    "generate_query",
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

agent = builder.compile()

# Go to mermaid.live to visualize the graph
if AppConfig().SHOW_AGENT_GRAPH:
    print(agent.get_graph().draw_mermaid())
