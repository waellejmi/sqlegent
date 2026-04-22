import json

from config.app_config import AppConfig
from context_layer.service import get_context_service


def resolve_semantic_profile_arg(semantic_profile: str | None) -> str | None:
    explicit = (semantic_profile or "").strip()
    if explicit:
        return explicit

    default_profile = (AppConfig().CONTEXT_DEFAULT_SEMANTIC_PROFILE or "").strip()
    if default_profile:
        return default_profile

    return None


def run_context_index_once(semantic_profile: str | None = None) -> None:
    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER:
        return

    if not config.CONTEXT_AUTO_INDEX_ON_STARTUP:
        return

    resolved_profile = resolve_semantic_profile_arg(semantic_profile)
    if config.CONTEXT_REQUIRE_SEMANTIC_PROFILE and not resolved_profile:
        print("Skipping startup context indexing: semantic profile required.")
        return

    from tools.database import db

    service = get_context_service()
    table_names = list(db.get_usable_table_names())
    summary = service.index_semantic_context(
        db,
        table_names,
        semantic_profile=resolved_profile,
    )
    print(f"Context index summary: {summary}")


def run_context_reindex(semantic_profile: str | None = None) -> None:
    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER:
        print("Context layer disabled in AppConfig.")
        return

    resolved_profile = resolve_semantic_profile_arg(semantic_profile)
    if config.CONTEXT_REQUIRE_SEMANTIC_PROFILE and not resolved_profile:
        print(
            "Semantic profile is required. Pass --semantic-profile <name> or set CONTEXT_DEFAULT_SEMANTIC_PROFILE."
        )
        return

    from tools.database import db

    service = get_context_service()
    table_names = list(db.get_usable_table_names())
    summary = service.index_semantic_context(
        db,
        table_names,
        semantic_profile=resolved_profile,
    )
    print(f"Reindex done: {summary}")


def print_context_stats() -> None:
    config = AppConfig()
    if not config.ENABLE_CONTEXT_LAYER:
        print("Context layer disabled in AppConfig.")
        return

    stats = get_context_service().get_stats()
    print(json.dumps(stats, indent=2))
