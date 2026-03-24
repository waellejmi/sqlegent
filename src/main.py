import asyncio
import json
import logging
import readline
import uuid
from pathlib import Path

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from config.db_config import DBConfig

db_config = DBConfig()


def _normalize_sqlite_uri_from_input(raw_path: str) -> str:
    path = Path(raw_path).expanduser().resolve()
    return db_config.sqlite_path_to_uri(path)


def _connection_config_to_uri(connection) -> str:
    db_type = str(connection.db_type).lower()
    endpoint = connection.tcp_endpoint
    file_endpoint = connection.file_endpoint

    if db_type in {"sqlite", "duckdb"}:
        if file_endpoint is None or not file_endpoint.path:
            raise ValueError(f"{db_type} connection does not include a file path.")
        return db_config.sqlite_path_to_uri(file_endpoint.path)

    if endpoint is None:
        raise ValueError(f"{db_type} connection does not include a TCP endpoint.")

    host = endpoint.host or "localhost"
    port = endpoint.port or ""
    database = endpoint.database or ""
    username = endpoint.username or ""
    password = endpoint.password or ""

    auth_segment = ""
    if username:
        auth_segment = username
        if password:
            auth_segment = f"{auth_segment}:{password}"
        auth_segment = f"{auth_segment}@"

    host_segment = f"{host}:{port}" if port else host

    if db_type == "postgresql":
        if not database:
            database = "postgres"
        return f"postgresql+psycopg2://{auth_segment}{host_segment}/{database}"

    if db_type in {"mysql", "mariadb"}:
        if not database:
            database = "mysql"
        return f"mysql+pymysql://{auth_segment}{host_segment}/{database}"

    raise ValueError(
        f"Docker/connection URI conversion is not implemented for db_type='{db_type}'."
    )


def _pick_docker_connection_uri() -> str:
    from sqlit.domains.connections.discovery.docker_detector import (
        DockerStatus,
        container_to_connection_config,
        detect_database_containers,
    )

    status, containers = detect_database_containers()

    if status == DockerStatus.NOT_INSTALLED:
        raise RuntimeError(
            "Docker SDK is not installed. Install with: pip install docker"
        )
    if status == DockerStatus.NOT_RUNNING:
        raise RuntimeError("Docker is not running.")
    if status == DockerStatus.NOT_ACCESSIBLE:
        raise RuntimeError(
            "Docker is not accessible (permission denied or daemon unreachable)."
        )

    running = [c for c in containers if c.is_running and c.connectable]
    supported_db_types = {"sqlite", "duckdb", "postgresql", "mysql", "mariadb"}
    running = [c for c in running if c.db_type in supported_db_types]
    if not running:
        raise RuntimeError(
            "No connectable running containers were found for supported db types: "
            f"{', '.join(sorted(supported_db_types))}."
        )

    print("\nDetected Docker database containers:")
    for idx, container in enumerate(running, start=1):
        port = container.port if container.port is not None else "-"
        db = container.database or "-"
        print(
            f"[{idx}] {container.container_name} | type={container.db_type} | host={container.host} | port={port} | db={db}"
        )

    choice_raw = input("Pick container number: ").strip()
    if not choice_raw.isdigit():
        raise ValueError("Invalid selection. Please provide a number.")
    choice = int(choice_raw)
    if choice < 1 or choice > len(running):
        raise ValueError("Selection out of range.")

    selected = running[choice - 1]
    config = container_to_connection_config(selected)
    return _connection_config_to_uri(config)


def configure_database_target() -> str:
    current_uri = db_config.get_database_uri()
    while True:
        print("\n=== Database Target Configuration ===")
        print(f"Current active URI: {current_uri}")
        print("Select target source:")
        print("[1] SQLite file path")
        print("[2] Direct SQLAlchemy URI")
        print("[3] Docker auto discovery")
        print("[Enter] Keep current")

        choice = input("Choice: ").strip()
        if choice == "":
            print("Keeping current database target.")
            return current_uri

        try:
            if choice == "1":
                default_path = str(db_config.DEFAULT_SQLITE_PATH)
                raw_path = (
                    input(f"SQLite file path [{default_path}]: ").strip()
                    or default_path
                )
                selected_uri = _normalize_sqlite_uri_from_input(raw_path)
            elif choice == "2":
                raw_uri = input("SQLAlchemy URI: ").strip()
                if not raw_uri:
                    raise ValueError("URI cannot be empty.")
                selected_uri = raw_uri
            elif choice == "3":
                selected_uri = _pick_docker_connection_uri()
            else:
                raise ValueError("Unsupported choice.")

            db_config.set_database_uri(selected_uri)
            print(
                f"Saved active database URI to {db_config.CONFIG_FILE}: {selected_uri}"
            )
            return selected_uri
        except Exception as exc:
            print(f"Configuration error: {exc}")


def build_agent():
    from agent.graph import agent

    return agent


logging.basicConfig(level=logging.INFO, format=" %(levelname)s - %(message)s")


def display_streaming_content(content: str) -> None:
    print(content, end="", flush=True)


# FIX:fix prefilled text not working some environments (Different behavior of readline in Linux/Windows and terminal emulators )
async def get_user_input(interrupt_info) -> dict:
    print("\n" + "=" * 30)
    print("INTERRUPTED:")
    try:
        print(json.dumps(interrupt_info, indent=2))
    except TypeError:
        print(interrupt_info)

    prompt = "\nHow would you like to proceed? \n[a]ccept  [e]dit  [r]eject [f]eedback \nChoice: "
    choice = (await asyncio.to_thread(input, prompt)).strip().lower()

    if choice.startswith("e"):
        current_query = interrupt_info[0].get("args").get("query")

        def input_with_prefill(prompt, text):
            def hook():
                readline.insert_text(text)
                readline.redisplay()

            readline.set_pre_input_hook(hook)
            try:
                return input(prompt)
            finally:
                readline.set_pre_input_hook(None)

        new_query = await asyncio.to_thread(
            input_with_prefill, "Edit query: ", current_query
        )

        return {"type": "edit", "edited_query": new_query}

    elif choice.startswith("f"):
        feedback = await asyncio.to_thread(input, "Feedback for the agent: \n")
        return {"type": "response", "feedback": feedback}

    elif choice.startswith("r"):
        return {"type": "reject"}

    return {"type": "accept"}


async def run_agent(input_state: dict, config: dict):
    print("--- Starting Agent ---")
    agent = build_agent()

    while True:
        resume_required = False
        async for mode, chunk in agent.astream(
            input_state,
            stream_mode=["updates", "messages"],
            config=config,
        ):
            if mode == "messages":
                msg, _ = chunk
                if isinstance(msg, AIMessageChunk) and msg.content:
                    display_streaming_content(msg.content)
            if mode == "updates":
                if "__interrupt__" in chunk:
                    interrupt_info = chunk["__interrupt__"][0].value
                    user_response = await get_user_input(interrupt_info)
                    input_state = Command(resume=user_response)
                    resume_required = True
                    print("\n--- Resuming Agent ---")
                    break
                else:
                    current_node = next(iter(chunk.keys()), None)
                    if current_node:
                        print(f"\n[Transition] -> {current_node}")
        if not resume_required:
            break

    print("\n--- Full Node History ---")
    for i, state in enumerate(agent.get_state_history(config)):
        print(f"Checkpoint {i}: next={state.next} ")


if __name__ == "__main__":
    selected_uri = configure_database_target()
    print(f"Using database target: {selected_uri}")

    usage_callback = UsageMetadataCallbackHandler()
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "callbacks": [usage_callback],
    }
    questions = {
        "success": "Which genre on average has the longest tracks?",
        "empty_result": "give me the names of all employees born after 1990-01-01",
        "skipped": "What is the airspeed velocity of an unladen swallow?",
        "complex1": "Which 5 artists generated the most revenue, and what is their total revenue and number of tracks sold?",
        "complex2": "Which customers spent more than the average customer spending, and what is their total amount spent?",
        "northwind": "Find the top 3 employees who generated the highest total revenue from orders in 1997, including the employee’s full name, total revenue, and the number of distinct customers they served. Only include orders where the total order amount exceeds $5,000.",
    }
    question = questions["complex1"]

    initial_state = {
        "messages": [{"role": "user", "content": question}],
        "user_question": question,
        "last_query": None,
        "previous_queries": [],
        "analysis_result": None,
        "retry_count": 0,
    }

    asyncio.run(run_agent(initial_state, config))

    print("\n--- Token Usage ---")
    print(usage_callback.usage_metadata)
