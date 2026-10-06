from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent_runtime import run_agent_with_interrupt
from app.chat_persistence import extract_tool_payload, save_chat_history
from app.state_factory import build_initial_state, make_runnable_config
from utils.message_helpers import extract_last_ai_message, stream_chunk_to_text
from webui.history_store import HistoryStore

router = APIRouter()


def _extract_total_tokens(usage: Any) -> int:
    if not isinstance(usage, dict):
        return 0

    total = 0

    def _collect(entry: Any) -> None:
        nonlocal total
        if not isinstance(entry, dict):
            return
        value = entry.get("total_tokens")
        if isinstance(value, int) and value > 0:
            total += value

    _collect(usage)
    for item in usage.values():
        _collect(item)
    return total


@router.websocket("/chat/{session_id}")
async def chat_socket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    active_task: asyncio.Task | None = None
    pending_interrupt_future: asyncio.Future | None = None

    async def run_chat_question(question: str) -> None:
        nonlocal pending_interrupt_future
        usage_callback = None
        try:
            from langchain_core.callbacks.usage import UsageMetadataCallbackHandler

            usage_callback = UsageMetadataCallbackHandler()
        except Exception:
            usage_callback = None

        config = make_runnable_config(thread_id=session_id, usage_callback=usage_callback)
        from config.app_config import AppConfig

        if AppConfig().ENABLE_ORCHESTRATOR:
            from langchain_core.messages import HumanMessage

            initial_state = {"messages": [HumanMessage(content=question)]}
            # If using Postgres/SqliteSaver, the checkpointer will automatically append to this thread_id
        else:
            initial_state = build_initial_state(question)

        async def on_message(message_chunk):
            # Don't stream tokens during chat execution to UI - they get logged
            # as intermediate steps and final answer handles the output
            text = stream_chunk_to_text(message_chunk)
            if text:
                await websocket.send_json(
                    {
                        "type": "token",
                        "text": text,
                    }
                )

        async def on_transition(node_name: str):
            await websocket.send_json(
                {
                    "type": "transition",
                    "node": node_name,
                }
            )

        async def interrupt_handler(interrupt_info):
            nonlocal pending_interrupt_future
            if pending_interrupt_future is not None and not pending_interrupt_future.done():
                pending_interrupt_future.cancel()
            pending_interrupt_future = asyncio.get_running_loop().create_future()
            await websocket.send_json(
                {
                    "type": "interrupt",
                    "payload": interrupt_info,
                }
            )
            return await pending_interrupt_future

        try:
            _, final_state = await run_agent_with_interrupt(
                input_state=initial_state,
                config=config,
                interrupt_handler=interrupt_handler,
                on_message=on_message,
                on_transition=on_transition,
            )
        except asyncio.CancelledError:
            if pending_interrupt_future is not None and not pending_interrupt_future.done():
                pending_interrupt_future.cancel()
            pending_interrupt_future = None
            await websocket.send_json(
                {
                    "type": "cancelled",
                    "message": "Request cancelled by user.",
                }
            )
            await websocket.send_json({"type": "done"})
            return
        except Exception as exc:
            if pending_interrupt_future is not None and not pending_interrupt_future.done():
                pending_interrupt_future.cancel()
            pending_interrupt_future = None
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(exc),
                }
            )
            await websocket.send_json({"type": "done"})
            return

        pending_interrupt_future = None
        values = final_state.values
        payload = extract_tool_payload(values.get("messages", []))
        analysis_status = payload.get("analysis_status") if payload else None
        final_answer = (
            payload.get("answer")
            if payload and payload.get("answer")
            else values.get("final_answer") or ""
        )
        if not final_answer:
            final_answer = extract_last_ai_message(values)
        sql = payload.get("sql") if payload else values.get("last_query")
        db_output = payload.get("db_output") if payload else values.get("db_output")

        history_id = save_chat_history(
            question=question,
            answer=final_answer,
            sql=sql,
            db_output=db_output,
            session_id=session_id,
        )
        usage_metadata = getattr(usage_callback, "usage_metadata", None)
        token_delta = _extract_total_tokens(usage_metadata)
        session_token_total = HistoryStore().increment_session_tokens(
            session_id=session_id,
            delta_tokens=token_delta,
        )

        await websocket.send_json(
            {
                "type": "final",
                "answer": final_answer,
                "sql": sql,
                "db_output": db_output,
                "status": analysis_status,
                "usage": usage_metadata,
                "session_token_total": session_token_total,
                "history_id": history_id,
                "ask_result_confirmation": AppConfig().ASK_RESULT_CONFIRMATION
                and AppConfig().ENABLE_CONTEXT_LAYER,
            }
        )
        await websocket.send_json({"type": "done"})

    try:
        while True:
            if active_task is not None and active_task.done():
                active_task = None

            request = await websocket.receive_json()
            req_type = request.get("type")

            if req_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if req_type == "interrupt_response":
                if pending_interrupt_future is None or pending_interrupt_future.done():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "No interrupt is currently pending.",
                        }
                    )
                    continue

                payload = request.get("payload", {"type": "accept"})
                pending_interrupt_future.set_result(payload)
                continue

            if req_type == "cancel":
                if active_task is None or active_task.done():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "No running request to cancel.",
                        }
                    )
                    continue

                if pending_interrupt_future is not None and not pending_interrupt_future.done():
                    pending_interrupt_future.cancel()
                active_task.cancel()
                await websocket.send_json({"type": "cancelling"})
                continue

            if req_type == "ask":
                if active_task is not None and not active_task.done():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "A request is already running. Stop it before sending a new one.",
                        }
                    )
                    continue

                question = str(request.get("question") or "").strip()
                if not question:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Question is required.",
                        }
                    )
                    continue

                active_task = asyncio.create_task(run_chat_question(question))
                continue

            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Unsupported message type.",
                }
            )

    except WebSocketDisconnect:
        if pending_interrupt_future is not None and not pending_interrupt_future.done():
            pending_interrupt_future.cancel()
        if active_task is not None and not active_task.done():
            active_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_task
        return
    except Exception as exc:
        if pending_interrupt_future is not None and not pending_interrupt_future.done():
            pending_interrupt_future.cancel()
        if active_task is not None and not active_task.done():
            active_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_task
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(exc),
                }
            )
        with contextlib.suppress(Exception):
            await websocket.close()
