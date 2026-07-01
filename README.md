# sql-agent

`sql-agent` is a database assistant that turns natural language into SQL, runs the query, and explains the result. It also has a conversation mode, a web UI, Docker database discovery, and a context layer for remembering schemas and past queries.

## Main entrypoints

- `src/main.py` — CLI entrypoint.
- `src/webui/main.py` — web UI server.
- `src/mcp_server.py` — MCP server exposing database tools.

## Setup

Install the project with `uv` first:

```bash
uv sync
uv pip install -e .
```

If you want extra database drivers and UI support in one step, use:

```bash
uv sync --extra postgres --extra embedding --extra webui --extra mariadb --extra mssql
```

## Run

Start the web app with:

```bash
uv run src/webui/main.py
```

You can also run the CLI with:

```bash
uv run src/main.py
```

## Project layout

- `src/agent/` — the NL2SQL pipeline. This is the SQL agent that finds tables, reads schema, generates SQL, runs it, retries when needed, and explains results.
- `src/orchestrator/` — the conversation agent. This is the chat layer that decides when to call the SQL pipeline or other tools.
- `src/tools/` — database tools used by the agents, including schema lookup, query execution, metadata caching, and the NL2SQL tool wrapper.
- `src/app/` — runtime helpers shared by CLI, web UI, and MCP server, including agent execution, state setup, persistence, and context operations.
- `src/context_layer/` — semantic context storage and retrieval. This is where schema memory, instruction memory, and query memory are managed.
- `src/docker_connection/` — Docker auto-discovery and Docker-to-connection helpers.
- `src/cli/` — terminal flows for starting the app and configuring the active database target.
- `src/webui/` — FastAPI app, routes, templates, and browser-facing services.
- `src/config/` — application and database configuration.
- `src/llm/` — model selection and LLM wiring.
- `src/utils/` — shared helpers for logging, formatting, node labels, and message handling.

## How the system fits together

1. The CLI or web UI chooses a database target.
2. The SQL agent reads schema and context, then generates a query.
3. The query is validated and executed through SQLAlchemy-backed tools.
4. The orchestrator can wrap the SQL agent in a chat flow for multi-turn conversations.
5. The context layer can store and retrieve useful schema or query memory over time.

## Semantic files

- `semantic/` — semantic models and MDL files used by the context layer.

## Notes

- The repo is centered around SQLAlchemy for database access.
- Docker support is only used for auto-discovering running database containers.
- The codebase is split by responsibility, not by database type.

## Docker test containers

To test Docker container discovery, run:

```bash
docker compose -f infra/docker/compose-chinook.yaml up -d
```

This starts 6 Chinook containers, one for each supported dialect.
