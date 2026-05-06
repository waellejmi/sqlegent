import argparse
import asyncio

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessageChunk

from app.agent_runtime import run_agent_with_interrupt, stream_chunk_to_text
from app.context_ops import (
    print_context_stats,
    run_context_index_once,
    run_context_reindex,
)
from app.state_factory import build_initial_state, make_runnable_config
from cli.connections import configure_database_target
from cli.interactive import (
    display_streaming_content,
    display_transition,
    get_user_interrupt_response,
)
from cli.questions import DEFAULT_QUESTION_KEY, DEFAULT_QUESTIONS
from config.app_config import AppConfig
from config.db_config import DBConfig
from context_layer.service import (
    extract_tables_from_sql,
    get_context_service,
    safe_parse_row_count,
)
from utils.logger_setup import LoggerSetup

LoggerSetup.configure_logging()


def _on_stream_message(message: AIMessageChunk) -> None:
    text = stream_chunk_to_text(message)
    if text:
        display_streaming_content(text)


def _build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--semantic-profile",
        type=str,
        default=None,
        help=(
            "Semantic profile name to scope YAML loading, e.g. '--semantic-profile chinook'."
        ),
    )
    parser.add_argument(
        "--use-default",
        "--default",
        dest="use_default",
        action="store_true",
        help=(
            f"Use built-in default question ({DEFAULT_QUESTION_KEY}) instead of prompting."
        ),
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Enable the conversational Orchestrator",
    )
    return parser


def _pick_question(use_default: bool) -> str:
    if use_default:
        return DEFAULT_QUESTIONS[DEFAULT_QUESTION_KEY]

    while True:
        question = input("Question: ").strip()
        if question:
            return question
        print("Question cannot be empty.")


def _persist_cli_outcome(values: dict) -> None:
    if AppConfig().ENABLE_CONTEXT_LAYER and AppConfig().ASK_RESULT_CONFIRMATION:
        analysis_result = values.get("analysis_result")
        # In chat mode, values might not have analysis_result directly.
        if analysis_result and analysis_result.status == "success":
            question = values.get("user_question") or ""
            sql = values.get("last_query") or ""
            db_output = values.get("db_output")
            row_count = safe_parse_row_count(db_output)

            confirmation = input("\nWas result correct? [y/N]: ").strip()
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


async def _run_cli_agent(question: str, is_chat: bool) -> None:
    print("--- Starting Agent ---")
    usage = UsageMetadataCallbackHandler()
    config = make_runnable_config(usage_callback=usage)

    if is_chat:
        from langchain_core.messages import HumanMessage

        while True:
            initial_state = {"messages": [HumanMessage(content=question)]}
            agent, final_state = await run_agent_with_interrupt(
                input_state=initial_state,
                config=config,
                interrupt_handler=get_user_interrupt_response,
                on_message=_on_stream_message,
                on_transition=display_transition,
            )

            print()  # Add a newline after the agent's response
            question = input("User: ").strip()
            if question == ":q":
                print("Exiting chat...")
                break
            while not question:
                question = input("User: ").strip()
    else:
        initial_state = build_initial_state(question)
        agent, final_state = await run_agent_with_interrupt(
            input_state=initial_state,
            config=config,
            interrupt_handler=get_user_interrupt_response,
            on_message=_on_stream_message,
            on_transition=display_transition,
        )

        if AppConfig().SHOW_NODE_HISTORY:
            print("\n--- Full Node History ---")
            for i, state in enumerate(agent.get_state_history(config)):
                print(f"Checkpoint {i}: next={state.next} ")

        _persist_cli_outcome(final_state.values)

    print("\n--- Token Usage ---")
    print(usage.usage_metadata)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.chat:
        AppConfig.ENABLE_ORCHESTRATOR = True

    if args.context_reindex:
        db_config = DBConfig()
        selected_uri = configure_database_target(db_config)
        print(f"Using database target: {selected_uri}")
        run_context_reindex(args.semantic_profile)
        return 0

    if args.context_stats:
        print_context_stats()
        return 0

    db_config = DBConfig()
    selected_uri = configure_database_target(db_config)
    print(f"Using database target: {selected_uri}")

    run_context_index_once(args.semantic_profile)

    question = _pick_question(args.use_default)
    asyncio.run(_run_cli_agent(question, is_chat=args.chat))
    return 0
