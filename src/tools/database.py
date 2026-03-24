from langchain.tools import tool
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from sqlglot import exp, parse

from config.app_config import AppConfig
from config.db_config import DBConfig
from llm.model import model

ALLOWED = (
    exp.Select,
    exp.With,
)


def validate_sql(query: str) -> bool:
    try:
        statements = parse(query)
    except Exception:
        return False

    if len(statements) != 1:
        return False

    ast = statements[0]

    if not isinstance(ast, ALLOWED):
        return False

    return True


def _build_database_components():
    database_uri = DBConfig().get_database_uri()
    database = SQLDatabase.from_uri(database_uri)
    toolkit_instance = SQLDatabaseToolkit(db=database, llm=model)
    toolkit_tools = toolkit_instance.get_tools()
    list_tables = next(
        tool for tool in toolkit_tools if tool.name == "sql_db_list_tables"
    )
    get_schema = next(tool for tool in toolkit_tools if tool.name == "sql_db_schema")
    run_query = next(tool for tool in toolkit_tools if tool.name == "sql_db_query")
    return database, list_tables, get_schema, run_query


db, list_tables_tool, get_schema_tool, run_query_tool = _build_database_components()


def get_db_stats():
    return {
        "dialect": db.dialect,
        "tables": db.get_usable_table_names(),
        "sample": db.run("SELECT * FROM Artist LIMIT 5;"),
    }


@tool(
    run_query_tool.name,
    description=run_query_tool.description,
    args_schema=run_query_tool.args_schema,
)
def run_query_tool_with_interrupt(config: RunnableConfig, **tool_input):
    # static check
    if not validate_sql(tool_input["query"]):
        return "Failed the static check. Only SELECT and WITH statements are allowed. No multiple statements allowed."
    # human interruption
    if not AppConfig().HUMAN_SQL_REVIEW:
        final_query_input = tool_input
    else:
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
