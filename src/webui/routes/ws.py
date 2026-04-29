from __future__ import annotations

import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agent_runtime import run_agent_with_interrupt, stream_chunk_to_text
from app.state_factory import build_initial_state, make_runnable_config

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

            config = make_runnable_config(
                bypass_cache=bool(request.get("bypass_cache", False)),
                invalidate_cache=bool(request.get("invalidate_cache", False)),
                usage_callback=usage_callback,
            )
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
            final_answer = values.get("final_answer") or ""
            analysis = values.get("analysis_result")
            analysis_status = getattr(analysis, "status", None)

            await websocket.send_json(
                {
                    "type": "final",
                    "answer": final_answer,
                    "sql": values.get("last_query"),
                    "status": analysis_status,
                    "usage": getattr(usage_callback, "usage_metadata", None),
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
