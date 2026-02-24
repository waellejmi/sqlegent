from langchain.tools import tool
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from llm.model import model
from utils.env_config import MyConfig

db = SQLDatabase.from_uri(f"sqlite:///{MyConfig().DB_PATH}")


def get_db_stats():
    return {
        "dialect": db.dialect,
        "tables": db.get_usable_table_names(),
        "sample": db.run("SELECT * FROM Artist LIMIT 5;"),
    }


toolkit = SQLDatabaseToolkit(db=db, llm=model)
tools = toolkit.get_tools()

get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")
list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")


# Wrapper around run_query_tool to allow interruption
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
        tool_response = run_query_tool.invoke(tool_input, config)
    elif response["type"] == "edit":
        tool_input = response["args"]["args"]
        tool_response = run_query_tool.invoke(tool_input, config)
    elif response["type"] == "response":
        user_feedback = response["args"]
        tool_response = user_feedback

    elif response["type"] == "reject":
        raise RuntimeError("User rejected the tool call")
    else:
        raise ValueError(f"Unsupported interrupt response type: {response['type']}")

    return tool_response
