from __future__ import annotations

import contextlib

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
            sql = values.get("last_query")
            db_output = values.get("db_output")

            try:
                from webui.history_store import HistoryStore
                from config.db_config import DBConfig

                db_name = None
                db_dialect = None
                try:
                    db_cfg = DBConfig()
                    uri = db_cfg.get_database_uri()
                    if uri:
                        parts = uri.split("://")
                        if len(parts) >= 2:
                            full_dialect = parts[0]
                            db_dialect = full_dialect.split("+")[0].lower()
                            rest = parts[1]
                            
                            if db_dialect in ["sqlite", "duckdb"]:
                                path_segment = rest
                                if rest.startswith("///"):
                                    path_segment = rest[3:]
                                elif rest.startswith("//"):
                                    path_segment = rest[2:]
                                elif rest.startswith("/"):
                                    path_segment = rest[1:]
                                segments = path_segment.split("/")
                                db_name = segments[-1] if segments[-1] else "db.sqlite"
                            else:
                                segments = rest.split("/")
                                potential_db = segments[-1]
                                if "?service_name=" in potential_db:
                                    db_name = potential_db.split("?service_name=")[1]
                                else:
                                    db_name = potential_db
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Could not get DB config for history: %s", e)

                store = HistoryStore()
                history_id = store.add_interaction(
                    question, sql, db_output, final_answer, db_name, db_dialect
                )
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning("Failed to save history: %s", e)
                history_id = None

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
