import uuid
from typing import Any

from context_layer.store import ChunkRecord, SearchHit


def build_schema_chunks(semantic_model: dict[str, Any]) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []

    for model in semantic_model.get("models", []):
        model_name = model.get("name") or "unknown_model"
        table_name = model.get("table") or model_name
        description = model.get("description") or ""
        aliases = model.get("aliases") or []
        columns = model.get("columns") or []

        column_lines = []
        for column in columns:
            if not isinstance(column, dict):
                continue
            col_name = column.get("name") or ""
            col_type = column.get("type") or ""
            col_desc = column.get("description") or ""
            line = f"{col_name} ({col_type})"
            if col_desc:
                line += f": {col_desc}"
            column_lines.append(line)

        summary_content = (
            f"Model: {model_name}\n"
            f"Physical table: {table_name}\n"
            f"Description: {description}\n"
            f"Aliases: {', '.join(aliases) if aliases else 'None'}"
        )
        chunks.append(
            ChunkRecord(
                id=str(uuid.uuid4()),
                channel="schema",
                source_type="model_summary",
                name=model_name,
                content=summary_content,
                embedding=[],
                metadata={
                    "model": model_name,
                    "table": table_name,
                    "kind": "summary",
                },
            )
        )

        if column_lines:
            columns_content = f"Model: {model_name}\nColumns:\n" + "\n".join(
                f"- {line}" for line in column_lines
            )
            chunks.append(
                ChunkRecord(
                    id=str(uuid.uuid4()),
                    channel="schema",
                    source_type="model_columns",
                    name=f"{model_name}.columns",
                    content=columns_content,
                    embedding=[],
                    metadata={
                        "model": model_name,
                        "table": table_name,
                        "kind": "columns",
                    },
                )
            )

    for relation in semantic_model.get("relationships", []):
        if not isinstance(relation, dict):
            continue
        from_model = relation.get("from_model") or relation.get("fromModel") or ""
        to_model = relation.get("to_model") or relation.get("toModel") or ""
        rel_type = relation.get("type") or ""
        join_info = relation.get("join") or {}
        join_from = join_info.get("from_column") or join_info.get("fromColumn") or ""
        join_to = join_info.get("to_column") or join_info.get("toColumn") or ""
        rel_description = relation.get("description") or ""

        if not from_model or not to_model:
            continue

        content = (
            f"Relationship: {from_model} -> {to_model}\n"
            f"Type: {rel_type}\n"
            f"Join: {from_model}.{join_from} = {to_model}.{join_to}\n"
            f"Description: {rel_description}"
        )
        chunks.append(
            ChunkRecord(
                id=str(uuid.uuid4()),
                channel="schema",
                source_type="relationship",
                name=f"{from_model}->{to_model}",
                content=content,
                embedding=[],
                metadata={
                    "from_model": from_model,
                    "to_model": to_model,
                    "kind": "relationship",
                },
            )
        )

    return chunks


def build_instruction_chunks(semantic_model: dict[str, Any]) -> list[ChunkRecord]:
    chunks: list[ChunkRecord] = []
    for instruction in semantic_model.get("instructions", []):
        if not isinstance(instruction, dict):
            continue

        scope = instruction.get("scope") or "sql"
        text = (instruction.get("instruction") or "").strip()
        question_hint = (instruction.get("question") or "").strip()
        if not text:
            continue

        content = (
            f"Scope: {scope}\n"
            f"Question Hint: {question_hint or 'global'}\n"
            f"Instruction: {text}"
        )
        chunks.append(
            ChunkRecord(
                id=str(uuid.uuid4()),
                channel="instructions",
                source_type="instruction",
                name=instruction.get("id") or str(uuid.uuid4()),
                content=content,
                embedding=[],
                metadata={
                    "scope": scope,
                    "is_default": bool(instruction.get("is_default", False)),
                    "question": question_hint,
                },
            )
        )
    return chunks


def build_context_text(
    *,
    hits: list[SearchHit],
    max_chars: int,
    title: str,
) -> str:
    if not hits:
        return f"{title}: none"

    lines = [f"{title}:"]
    budget = max_chars
    for index, hit in enumerate(hits, start=1):
        block = f"[{index}] {hit.name} (score={hit.score:.3f})\n{hit.content}"
        if len(block) > budget:
            remaining = max(0, budget - 20)
            if remaining == 0:
                break
            block = block[:remaining] + "\n..."
            lines.append(block)
            break

        lines.append(block)
        budget -= len(block)
        if budget <= 0:
            break

    return "\n\n".join(lines)


def build_query_memory_text(hits: list[SearchHit], max_chars: int) -> str:
    if not hits:
        return "Query memory examples: none"

    lines = ["Query memory examples (verified NL->SQL):"]
    budget = max_chars
    for index, hit in enumerate(hits, start=1):
        question = str(hit.metadata.get("question", "")).strip()
        sql = str(hit.metadata.get("sql", "")).strip()
        block = f"Example {index} (score={hit.score:.3f})\nQ: {question}\nSQL:\n{sql}"
        if len(block) > budget:
            remaining = max(0, budget - 20)
            if remaining == 0:
                break
            block = block[:remaining] + "\n..."
            lines.append(block)
            break

        lines.append(block)
        budget -= len(block)
        if budget <= 0:
            break

    return "\n\n".join(lines)
