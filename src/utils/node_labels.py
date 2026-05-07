NODE_FRIENDLY_NAMES = {
    "chat": "Thinking...",
    "tools": "Querying Database...",
    "sql_pipeline": "Querying Database...",
    "question_synthesis": "Synthesizing Question...",
    "list_tables": "Viewing Tables...",
    "retrieve_context": "Retrieving Context...",
    "skip_pipeline": "Checking Requirements...",
    "call_get_schema": "Selecting Tables...",
    "get_schema": "Getting Schemas...",
    "generate_query": "Generating Query...",
    "run_query": "Executing Query...",
    "analyze_result": "Analyzing Result...",
    "explain_result": "Formatting Result...",
}


def get_friendly_node_name(node_name: str | None) -> str | None:
    if not node_name:
        return None
    return NODE_FRIENDLY_NAMES.get(node_name)
