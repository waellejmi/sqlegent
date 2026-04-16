import logging

from langchain.tools import tool
from langchain_community.tools.sql_database.tool import (
    InfoSQLDatabaseTool,
    QuerySQLDatabaseTool,
)
from langchain_community.utilities import SQLDatabase
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from sqlglot import exp, parse

from config.app_config import AppConfig
from config.db_config import DBConfig
from tools.metadata_cache import (
    get_cached_metadata,
    invalidate_metadata_cache,
    set_cached_metadata,
)
from utils.helpers import normalize_table_names_csv
from utils.logger_setup import LoggerSetup

logger = LoggerSetup.get_logger(__name__, logging.INFO)


ALLOWED = (
    exp.Select,
    exp.With,
)

# SQLAlchemy and sqlglot use differant  names for some dialects
SQLGLOT_COMPLIANET_DIALECTS = {
    "mssql": "tsql",
    "postgresql": "postgres",
    "mariadb": "mysql",
}


def validate_sql(query: str, dialect: str = None) -> bool:
    try:
        statements = parse(query, read=dialect)

    except Exception as e:
        logger.error(f"Parser Error: {e}")
        return False

    if len(statements) != 1:
        return False

    ast = statements[0]

    if not isinstance(ast, ALLOWED):
        return False

    return True


def _build_database_components():
    database_uri = DBConfig().get_database_uri()
    database = SQLDatabase.from_uri(database_uri, sample_rows_in_table_info=1)
    get_schema = InfoSQLDatabaseTool(db=database)
    run_query = QuerySQLDatabaseTool(db=database)

    return database, get_schema, run_query


db, get_schema_tool, run_query_tool = _build_database_components()


def _get_config_flag(
    config: RunnableConfig | None, flag: str, default: bool = False
) -> bool:
    if not config:
        return default
    configurable = config.get("configurable") if isinstance(config, dict) else None
    if not isinstance(configurable, dict):
        return default
    return bool(configurable.get(flag, default))


def list_tables_with_cache(
    *, bypass_cache: bool = False, invalidate_cache: bool = False
) -> list[str]:
    if invalidate_cache:
        invalidate_metadata_cache(DBConfig().get_database_uri())

    cached = get_cached_metadata(
        operation="list_tables",
        operation_args=None,
        bypass_cache=bypass_cache,
    )
    if cached is not None:
        return list(cached)

    table_names = db.get_usable_table_names()
    set_cached_metadata(
        operation="list_tables",
        operation_args=None,
        value=table_names,
        bypass_cache=bypass_cache,
    )
    return table_names


@tool(
    get_schema_tool.name,
    description=get_schema_tool.description,
    args_schema=get_schema_tool.args_schema,
)
def get_schema_tool_with_cache(table_names: str, config: RunnableConfig | None = None):
    bypass_cache = _get_config_flag(config, "metadata_bypass_cache", False)
    normalized_table_names = normalize_table_names_csv(table_names)
    operation_args = {"table_names": normalized_table_names}

    cached = get_cached_metadata(
        operation="get_schema",
        operation_args=operation_args,
        bypass_cache=bypass_cache,
    )
    if cached is not None:
        return cached

    tool_input = {"table_names": normalized_table_names}
    tool_response = get_schema_tool.invoke(tool_input, config)
    set_cached_metadata(
        operation="get_schema",
        operation_args=operation_args,
        value=tool_response,
        bypass_cache=bypass_cache,
    )
    return tool_response


@tool(
    run_query_tool.name,
    description=run_query_tool.description,
    args_schema=run_query_tool.args_schema,
)
def run_query_tool_with_interrupt(query: str, config: RunnableConfig | None = None):
    # static check
    dialect = SQLGLOT_COMPLIANET_DIALECTS.get(db.dialect, db.dialect)
    if not validate_sql(query, dialect=dialect):
        raise ValueError(
            "Failed the static check. Only SELECT and WITH statements are allowed. No multiple statements allowed."
        )
    # human interruption
    tool_input = {"query": query}
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
