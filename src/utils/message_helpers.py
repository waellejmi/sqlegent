from __future__ import annotations

from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
)

from config.app_config import AppConfig


def _prompt_messages(system_content: str, user_content: str | None = None):
    app_config = AppConfig()
    if app_config.LLM_PROVIDER == "google":
        return [
            SystemMessage(content=system_content),
            HumanMessage(content=user_content or "Proceed with the task."),
        ]
    return [SystemMessage(content=system_content)]


def extract_message_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content

    parts = [
        block if isinstance(block, str) else block.get("text", "")
        for block in message.content
    ]
    return "".join(parts)


def extract_last_ai_message(final_state_values: dict[str, Any]) -> str | None:
    messages = final_state_values.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return extract_message_text(msg)
    return None


def stream_chunk_to_text(message_chunk: AIMessageChunk) -> str:
    if isinstance(message_chunk.content, str):
        return message_chunk.content
    if isinstance(message_chunk.content, list):
        parts: list[str] = []
        for block in message_chunk.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def ai_message_to_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content

    parts: list[str] = []
    for block in message.content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            parts.append(str(block.get("text", "")))
    return "".join(parts)
