from __future__ import annotations

import argparse
import json

from config.app_config import AppConfig
from context_layer.service import get_context_service
from context_layer.store import SearchHit


def _hit_to_dict(hit: SearchHit) -> dict:
    return {
        "id": hit.id,
        "name": hit.name,
        "score": round(hit.score, 4),
        "source_type": hit.source_type,
        "metadata": hit.metadata,
    }


def _print_hits(title: str, hits: list[SearchHit]) -> None:
    print(f"\n{title}: {len(hits)} hit(s)")
    if not hits:
        return
    for index, hit in enumerate(hits, start=1):
        print(
            f"  [{index}] {hit.name} | score={hit.score:.4f} | source={hit.source_type}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retrieve semantic context for a question."
    )
    parser.add_argument("question", nargs="?", help="Natural language question")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON instead of plain text.",
    )
    parser.add_argument(
        "--include-text",
        help="include details of the retrieved context in the JSON output",
        action="store_true",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    question = (args.question or "").strip()
    if not question:
        question = input("Question: ").strip()

    if not question:
        print("Question cannot be empty.")
        return 1

    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER:
        print("Context layer is disabled in AppConfig.")
        return 1

    service = get_context_service()
    retrieved = service.retrieve_context(question)

    if args.json:
        payload = {
            "question": question,
            "embedding_profile": service.embedding_profile_id,
            "schema_hits": [_hit_to_dict(hit) for hit in retrieved.schema_hits],
            "instruction_hits": [
                _hit_to_dict(hit) for hit in retrieved.instruction_hits
            ],
            "query_memory_hits": [
                _hit_to_dict(hit) for hit in retrieved.query_memory_hits
            ],
        }
        if args.include_text:
            payload["schema_text"] = retrieved.schema_text
            payload["instruction_text"] = retrieved.instruction_text
            payload["query_memory_text"] = retrieved.query_memory_text

        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    print(f"Embedding profile: {service.embedding_profile_id}")
    _print_hits("Schema", retrieved.schema_hits)
    _print_hits("Instructions", retrieved.instruction_hits)
    _print_hits("Query memory", retrieved.query_memory_hits)

    if args.include_text:
        print("\n--- Schema Context ---")
        print(retrieved.schema_text)
        print("\n--- Instruction Context ---")
        print(retrieved.instruction_text)
        print("\n--- Query Memory Context ---")
        print(retrieved.query_memory_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
