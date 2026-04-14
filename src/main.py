import asyncio
import json
import logging
import readline
import uuid

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessageChunk
from langgraph.types import Command

from cli.connections import configure_database_target
from config.app_config import AppConfig
from config.db_config import DBConfig
from context_layer.service import (
    extract_tables_from_sql,
    get_context_service,
    safe_parse_row_count,
)

logging.basicConfig(level=logging.INFO, format=" %(levelname)s - %(message)s")


def build_agent():
    from agent.graph import agent

    return agent


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

    if AppConfig().SHOW_NODE_HISTORY:
        print("\n--- Full Node History ---")
        for i, state in enumerate(agent.get_state_history(config)):
            print(f"Checkpoint {i}: next={state.next} ")

    final_state = agent.get_state(config)
    values = final_state.values

    if AppConfig().ENABLE_CONTEXT_LAYER and AppConfig().CLI_ASK_RESULT_CONFIRMATION:
        analysis_result = values.get("analysis_result")
        if analysis_result and analysis_result.status == "success":
            question = values.get("user_question") or ""
            sql = values.get("last_query") or ""
            db_output = values.get("db_output")
            row_count = safe_parse_row_count(db_output)

            confirmation = (
                await asyncio.to_thread(input, "\nWas result correct? [y/N]: ")
            ).strip()
            is_verified = confirmation.lower() in {"y", "yes"}

            if is_verified:
                service = get_context_service()
                memory_id = service.record_verified_query(
                    question=question,
                    sql=sql,
                    tables=extract_tables_from_sql(sql),
                    row_count=row_count,
                    is_verified=True,
                    metadata={"source": "cli"},
                )
                if memory_id:
                    print(f"Stored verified NL->SQL memory id: {memory_id}")
    if AppConfig().ENABLE_CONTEXT_LAYER and AppConfig().ENABLE_FAILED_QUERY_LOG:
        service = get_context_service()
        analysis_result = values.get("analysis_result")
        if analysis_result and analysis_result.status != "success":
            service.record_failed_query(
                question=values.get("user_question") or "",
                sql=values.get("last_query"),
                status=analysis_result.status,
                error_message=analysis_result.explanation,
                retry_count=int(values.get("retry_count", 0)),
                metadata={"source": "cli"},
            )


def _run_context_index_once() -> None:
    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER:
        return

    if not config.CONTEXT_AUTO_INDEX_ON_STARTUP:
        return

    from tools.database import db

    service = get_context_service()
    table_names = list(db.get_usable_table_names())
    summary = service.index_semantic_context(db, table_names)
    print(f"Context index summary: {summary}")


def _run_context_reindex() -> None:
    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER:
        print("Context layer disabled in AppConfig.")
        return

    from tools.database import db

    service = get_context_service()
    table_names = list(db.get_usable_table_names())
    summary = service.index_semantic_context(db, table_names)
    print(f"Reindex done: {summary}")


def _print_context_stats() -> None:
    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER:
        print("Context layer disabled in AppConfig.")
        return

    stats = get_context_service().get_stats()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="sqlgent CLI")
    parser.add_argument(
        "--context-reindex",
        action="store_true",
        help="Rebuild semantic context index and exit.",
    )
    parser.add_argument(
        "--context-stats",
        action="store_true",
        help="Print context layer stats and exit.",
    )
    args = parser.parse_args()

    if args.context_reindex:
        _run_context_reindex()
        raise SystemExit(0)

    if args.context_stats:
        _print_context_stats()
        raise SystemExit(0)

    db_config = DBConfig()
    selected_uri = configure_database_target(db_config)
    print(f"Using database target: {selected_uri}")

    _run_context_index_once()

    usage_callback = UsageMetadataCallbackHandler()
    config = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
            "metadata_bypass_cache": False,
            "metadata_invalidate_cache": False,
        },
        "callbacks": [usage_callback],
    }
    questions = {
        "success": "Which genre on average has the longest tracks?",
        "empty_result": "give me the names of all employees born after 1990-01-01",
        "skipped": "What is the airspeed velocity of an unladen swallow?",
        "complex1": "Which 5 artists generated the most revenue, and what is their total revenue and number of tracks sold?",
        "complex2": "Which customers spent more than the average customer spending, and what is their total amount spent?",
        "instruction_test": "List top 4 most bought tracks of all time.",
        "northwind": "Find the top 3 employees who generated the highest total revenue from orders in 1997, including the employee’s full name, total revenue, and the number of distinct customers they served. Only include orders where the total order amount exceeds $5,000.",
    }
    question = questions["instruction_test"]

    initial_state = {
        "messages": [{"role": "user", "content": question}],
        "user_question": question,
        "last_query": None,
        "previous_queries": [],
        "analysis_result": None,
        "skip_decision": None,
        "db_output": None,
        "retry_count": 0,
        "schema_context": None,
        "instruction_context": None,
        "query_memory_context": None,
    }

    asyncio.run(run_agent(initial_state, config))

    print("\n--- Token Usage ---")
    print(usage_callback.usage_metadata)
