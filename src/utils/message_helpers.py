from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk


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
