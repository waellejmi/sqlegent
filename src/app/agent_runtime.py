from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessageChunk
from langgraph.types import Command


async def build_agent():
    from app.checkpointer import get_async_checkpointer
    from config.app_config import AppConfig

    checkpointer = await get_async_checkpointer()

    if AppConfig().ENABLE_ORCHESTRATOR:
        from orchestrator.graph import builder
    else:
        from agent.graph import builder

    return builder.compile(checkpointer=checkpointer)


async def run_agent_with_interrupt(
    *,
    input_state: dict[str, Any] | Command,
    config: dict[str, Any],
    interrupt_handler: Callable[[Any], Awaitable[dict[str, Any]]],
    on_message: Callable[[AIMessageChunk], None | Awaitable[None]] | None = None,
    on_transition: Callable[[str], None | Awaitable[None]] | None = None,
):
    agent = await build_agent()

    stream_mode: list[str] = (
        ["updates", "messages", "debug"] if on_message else ["updates", "debug"]
    )

    while True:
        resume_required = False
        async for stream_tuple in agent.astream(
            input_state,
            stream_mode=stream_mode,
            config=config,
            subgraphs=True,
        ):
            # In LangGraph with subgraphs=True and multiple stream modes,
            # the yielded tuple is (namespace, mode, chunk)
            if isinstance(stream_tuple, tuple) and len(stream_tuple) == 3:
                _namespace, mode, chunk = stream_tuple
            elif isinstance(stream_tuple, tuple) and len(stream_tuple) == 2:
                mode, chunk = stream_tuple
            else:
                continue

            if mode == "debug" and on_transition:
                if chunk.get("type") == "task":
                    node_name = chunk.get("payload", {}).get("name")
                    if node_name:
                        maybe_awaitable = on_transition(node_name)
                        if inspect.isawaitable(maybe_awaitable):
                            await maybe_awaitable
                continue

            if mode == "messages" and on_message:
                message, metadata = chunk

                # Prevent double printing: if Orchestrator is enabled, it acts as the voice.
                # We suppress the internal subagent's AIMessage from 'explain_result'.
                from config.app_config import AppConfig

                if AppConfig().ENABLE_ORCHESTRATOR:
                    if metadata and metadata.get("langgraph_node") == "explain_result":
                        continue

                if isinstance(message, AIMessageChunk) and message.content:
                    maybe_awaitable = on_message(message)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                continue

            if mode != "updates":
                continue

            if "__interrupt__" in chunk:
                interrupt_info = chunk["__interrupt__"][0].value
                user_response = await interrupt_handler(interrupt_info)
                input_state = Command(resume=user_response)
                resume_required = True
                break

        if not resume_required:
            break

    final_state = await agent.aget_state(config)
    return agent, final_state
