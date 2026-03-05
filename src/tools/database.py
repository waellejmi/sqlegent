from langchain.tools import tool
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from config.db_config import DBConfig
from llm.model import model

db = SQLDatabase.from_uri(f"sqlite:///{DBConfig().DB_PATH}")


def get_db_stats():
    return {
        "dialect": db.dialect,
        "tables": db.get_usable_table_names(),
        "sample": db.run("SELECT * FROM Artist LIMIT 5;"),
    }


toolkit = SQLDatabaseToolkit(db=db, llm=model)
tools = toolkit.get_tools()

list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")
get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")


@tool(
    run_query_tool.name,
    description=run_query_tool.description,
    args_schema=run_query_tool.args_schema,
)
def run_query_tool_with_interrupt(config: RunnableConfig, **tool_input):
    request = {
        "action": run_query_tool.name,
        "args": tool_input,
        "description": "Please review the tool call",
    }
    response = interrupt([request])
    if response["type"] == "accept":
        final_query_input = tool_input
    elif response["type"] == "edit":
        tool_input = response["edited_query"]
        final_query_input = {"query": tool_input}
    elif response["type"] == "response":
        return f"User cancelled the query and provided this feedback: {response['feedback']}"

    elif response["type"] == "reject":
        raise RuntimeError("User rejected the tool call")
    else:
        raise ValueError(f"Unsupported interrupt response type: {response['type']}")
    try:
        tool_response = run_query_tool.invoke(final_query_input, config)
        return tool_response

    except Exception as e:
        return (
            f"Error executing SQL: {str(e)}\n"
            "Please analyze this error, correct the query, and try again."
        )
