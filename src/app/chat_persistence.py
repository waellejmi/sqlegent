from __future__ import annotations

import json
import pathlib
from typing import Any

from langchain_core.messages import AnyMessage, ToolMessage
from sqlalchemy.engine import make_url

from config.db_config import DBConfig
from webui.history_store import HistoryStore


def extract_database_identity() -> tuple[str | None, str | None]:
    uri = DBConfig().get_database_uri()
    if not uri:
        return None, None

    url = make_url(uri)
    db_dialect = url.drivername.split("+")[0].lower()

    if db_dialect in {"sqlite", "duckdb"}:
        if url.database:
            db_name = pathlib.Path(url.database).name
        else:
            db_name = "db.sqlite"
    else:
        db_name = url.database or None

    return db_name, db_dialect


def extract_tool_payload(messages: list[AnyMessage]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue

        content = message.content
        if isinstance(content, dict):
            payload = content
        elif isinstance(content, str):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            payload = parsed
        else:
            continue

        if "answer" in payload:
            return payload

    return None


def save_chat_history(
    *,
    question: str,
    answer: str | None,
    sql: str | None,
    db_output: str | None,
) -> str:
    db_name, db_dialect = extract_database_identity()
    store = HistoryStore()
    return store.add_interaction(
        question=question,
        sql=sql,
        db_output=db_output,
        answer=answer,
        db_name=db_name,
        db_dialect=db_dialect,
    )
