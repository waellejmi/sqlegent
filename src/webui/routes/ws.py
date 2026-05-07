from __future__ import annotations

import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent_runtime import run_agent_with_interrupt
from app.chat_persistence import extract_tool_payload, save_chat_history
from app.state_factory import build_initial_state, make_runnable_config
from utils.message_helpers import stream_chunk_to_text

router = APIRouter()


async def _ws_interrupt_handler(websocket: WebSocket, interrupt_info):
    await websocket.send_json(
        {
            "type": "interrupt",
            "payload": interrupt_info,
        }
    )

    while True:
        payload = await websocket.receive_json()
        if payload.get("type") == "interrupt_response":
            return payload.get("payload", {"type": "accept"})


@router.websocket("/chat/{session_id}")
async def chat_socket(websocket: WebSocket, session_id: str):
    del session_id
    await websocket.accept()

    try:
        while True:
            request = await websocket.receive_json()
            req_type = request.get("type")

            if req_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if req_type != "ask":
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Unsupported message type.",
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

            usage_callback = None
            try:
                from langchain_core.callbacks.usage import UsageMetadataCallbackHandler

                usage_callback = UsageMetadataCallbackHandler()
            except Exception:
                usage_callback = None

            config = make_runnable_config(usage_callback=usage_callback)
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

            try:
                _, final_state = await run_agent_with_interrupt(
                    input_state=initial_state,
                    config=config,
                    interrupt_handler=lambda info: _ws_interrupt_handler(
                        websocket, info
                    ),
                    on_message=on_message,
                    on_transition=on_transition,
                )
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": str(exc),
                    }
                )
                await websocket.send_json({"type": "done"})
                continue

            values = final_state.values
            payload = extract_tool_payload(values.get("messages", []))
            analysis_status = payload.get("analysis_status") if payload else None
            final_answer = (
                payload.get("answer")
                if payload and payload.get("answer")
                else values.get("final_answer") or ""
            )
            sql = payload.get("sql") if payload else values.get("last_query")
            db_output = (
                payload.get("db_output") if payload else values.get("db_output")
            )

            history_id = save_chat_history(
                question=question,
                answer=final_answer,
                sql=sql,
                db_output=db_output,
            )

            from config.app_config import AppConfig

            await websocket.send_json(
                {
                    "type": "final",
                    "answer": final_answer,
                    "sql": sql,
                    "db_output": db_output,
                    "status": analysis_status,
                    "usage": getattr(usage_callback, "usage_metadata", None),
                    "history_id": history_id,
                    "ask_result_confirmation": AppConfig().ASK_RESULT_CONFIRMATION
                    and AppConfig().ENABLE_CONTEXT_LAYER,
                }
            )
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        return
    except Exception as exc:
        with contextlib.suppress(Exception):
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(exc),
                }
            )
        with contextlib.suppress(Exception):
            await websocket.close()
