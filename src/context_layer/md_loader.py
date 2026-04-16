import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.app_config import AppConfig


@dataclass
class SemanticModel:
    models: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    instructions: list[dict[str, Any]]


def load_yaml_documents(root_dir: Path, file_glob: str) -> list[dict[str, Any]]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError("Missing dependency 'pyyaml'.") from exc

    if not root_dir.exists():
        return []

    docs: list[dict[str, Any]] = []
    for path in sorted(root_dir.glob(file_glob)):
        if path.name.startswith("_baseline.generated"):
            continue
        if not path.is_file():
            continue

        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            docs.append(loaded)
    return docs


def load_yaml_documents_for_profile(
    *,
    root_dir: Path,
    file_glob: str,
    semantic_profile: str | None,
) -> list[dict[str, Any]]:
    config = AppConfig()

    profile = (semantic_profile or "").strip()
    common_dir = root_dir / config.MDL_COMMON_SUBDIR
    databases_dir = root_dir / config.MDL_DATABASES_SUBDIR

    docs: list[dict[str, Any]] = []

    if profile:
        docs.extend(load_yaml_documents(common_dir, file_glob))
        docs.extend(load_yaml_documents(databases_dir / profile, file_glob))

        if docs:
            return docs

        # Backward-compatible fallback: allow profile-tagged files directly under semantic/.
        lowered = profile.lower()
        for path in sorted(root_dir.glob(file_glob)):
            if path.name.startswith("_baseline.generated"):
                continue
            if not path.is_file():
                continue
            if common_dir in path.parents or databases_dir in path.parents:
                continue
            if lowered not in path.stem.lower():
                continue

            try:
                import yaml
            except Exception as exc:  # pragma: no cover - import guard
                raise RuntimeError("Missing dependency 'pyyaml'.") from exc

            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                docs.append(loaded)

        return docs

    # No profile provided.
    if common_dir.exists() or databases_dir.exists():
        return load_yaml_documents(common_dir, file_glob)

    # Legacy mode when semantic/ does not use structured profile directories yet.
    return load_yaml_documents(root_dir, file_glob)


def build_baseline_semantic_model(database, table_names: list[str]) -> SemanticModel:
    models: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    inspector = _build_inspector(database)

    for table in table_names:
        schema_name, raw_table_name = _split_table_identifier(table)

        columns = []
        for col in inspector.get_columns(raw_table_name, schema=schema_name):
            columns.append(
                {
                    "name": col.get("name"),
                    "type": str(col.get("type", "")),
                    "nullable": bool(col.get("nullable", True)),
                    "primary_key": bool(col.get("primary_key", False)),
                    "description": "",
                }
            )

        models.append(
            {
                "name": table,
                "table": table,
                "schema": schema_name,
                "description": "",
                "aliases": [],
                "columns": columns,
            }
        )

        for fk in inspector.get_foreign_keys(raw_table_name, schema=schema_name):
            constrained_columns = fk.get("constrained_columns") or []
            referred_columns = fk.get("referred_columns") or []
            referred_table = fk.get("referred_table")
            referred_schema = fk.get("referred_schema")
            if not constrained_columns or not referred_columns or not referred_table:
                continue

            to_model = (
                f"{referred_schema}.{referred_table}"
                if referred_schema
                else str(referred_table)
            )

            relationships.append(
                {
                    "from_model": table,
                    "to_model": to_model,
                    "type": "many_to_one",
                    "join": {
                        "from_column": constrained_columns[0],
                        "to_column": referred_columns[0],
                    },
                    "description": "",
                }
            )

    return SemanticModel(models=models, relationships=relationships, instructions=[])


def merge_semantic_model(
    baseline: SemanticModel,
    docs: list[dict[str, Any]],
) -> SemanticModel:
    model_map: dict[str, dict[str, Any]] = {
        model["name"]: json.loads(json.dumps(model)) for model in baseline.models
    }
    instructions = list(baseline.instructions)

    for doc in docs:
        for model in doc.get("models", []):
            name = model.get("name")
            if not name:
                continue

            if name not in model_map:
                model_map[name] = {
                    "name": name,
                    "table": model.get("table") or name,
                    "description": model.get("description") or "",
                    "aliases": model.get("aliases") or [],
                    "columns": model.get("columns") or [],
                }
                continue

            target = model_map[name]
            for field in ["description", "aliases", "table"]:
                if field in model and model[field] is not None:
                    target[field] = model[field]

            if "columns" in model and isinstance(model["columns"], list):
                target_columns = {
                    c.get("name"): c
                    for c in target.get("columns", [])
                    if isinstance(c, dict) and c.get("name")
                }
                for col in model["columns"]:
                    col_name = col.get("name") if isinstance(col, dict) else None
                    if not col_name:
                        continue
                    if col_name not in target_columns:
                        target.get("columns", []).append(col)
                        target_columns[col_name] = col
                    else:
                        merged = target_columns[col_name]
                        for k, v in col.items():
                            if v is not None:
                                merged[k] = v

        instructions.extend(doc.get("instructions", []))

    relationships = _merge_relationships(
        baseline_relationships=baseline.relationships,
        docs=docs,
    )

    return SemanticModel(
        models=list(model_map.values()),
        relationships=relationships,
        instructions=instructions,
    )


def _merge_relationships(
    *,
    baseline_relationships: list[dict[str, Any]],
    docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    merged_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    priority_by_key: dict[tuple[str, str, str, str, str], int] = {}

    for relation in baseline_relationships:
        if not isinstance(relation, dict):
            continue
        normalized = _normalize_relationship(relation)
        key = _relationship_key(normalized)
        if key is None:
            continue
        merged_by_key[key] = normalized
        priority_by_key[key] = 0

    for doc in docs:
        for relation in doc.get("relationships", []):
            if not isinstance(relation, dict):
                continue

            normalized = _normalize_relationship(relation)
            key = _relationship_key(normalized)
            if key is None:
                continue

            if key not in merged_by_key:
                merged_by_key[key] = normalized
                priority_by_key[key] = 1
                continue

            existing = merged_by_key[key]
            existing_priority = priority_by_key[key]
            merged = _merge_relationship_values(
                existing=existing,
                incoming=normalized,
                existing_priority=existing_priority,
                incoming_priority=1,
            )
            merged_by_key[key] = merged
            priority_by_key[key] = max(existing_priority, 1)

    return list(merged_by_key.values())


def _normalize_relationship(relation: dict[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(relation))

    from_model = str(copied.get("from_model") or copied.get("fromModel") or "").strip()
    to_model = str(copied.get("to_model") or copied.get("toModel") or "").strip()
    rel_type = str(copied.get("type") or "").strip()

    join_data = copied.get("join") if isinstance(copied.get("join"), dict) else {}
    join_from = str(
        join_data.get("from_column") or join_data.get("fromColumn") or ""
    ).strip()
    join_to = str(join_data.get("to_column") or join_data.get("toColumn") or "").strip()

    description = str(copied.get("description") or "").strip()

    normalized: dict[str, Any] = {
        "from_model": from_model,
        "to_model": to_model,
        "type": rel_type,
        "join": {
            "from_column": join_from,
            "to_column": join_to,
        },
        "description": description,
    }

    for key, value in copied.items():
        if key in {
            "from_model",
            "fromModel",
            "to_model",
            "toModel",
            "type",
            "join",
            "description",
        }:
            continue
        normalized[key] = value

    return normalized


def _relationship_key(
    relation: dict[str, Any],
) -> tuple[str, str, str, str, str] | None:
    from_model = str(relation.get("from_model") or "").strip()
    to_model = str(relation.get("to_model") or "").strip()

    if not from_model or not to_model:
        return None

    rel_type = str(relation.get("type") or "").strip()
    join_data = relation.get("join") if isinstance(relation.get("join"), dict) else {}
    join_from = str(join_data.get("from_column") or "").strip()
    join_to = str(join_data.get("to_column") or "").strip()

    return (
        from_model.lower(),
        to_model.lower(),
        rel_type.lower(),
        join_from.lower(),
        join_to.lower(),
    )


def _merge_relationship_values(
    *,
    existing: dict[str, Any],
    incoming: dict[str, Any],
    existing_priority: int,
    incoming_priority: int,
) -> dict[str, Any]:
    merged = json.loads(json.dumps(existing))

    incoming_is_higher = incoming_priority > existing_priority
    same_priority = incoming_priority == existing_priority

    for field in ["from_model", "to_model", "type"]:
        existing_value = str(merged.get(field) or "").strip()
        incoming_value = str(incoming.get(field) or "").strip()

        if incoming_is_higher and incoming_value:
            merged[field] = incoming_value
            continue

        if not existing_value and incoming_value:
            merged[field] = incoming_value
            continue

        if same_priority and incoming_value and incoming_value != existing_value:
            merged[field] = incoming_value

    existing_join = merged.get("join") if isinstance(merged.get("join"), dict) else {}
    incoming_join = (
        incoming.get("join") if isinstance(incoming.get("join"), dict) else {}
    )

    for field in ["from_column", "to_column"]:
        existing_value = str(existing_join.get(field) or "").strip()
        incoming_value = str(incoming_join.get(field) or "").strip()

        if incoming_is_higher and incoming_value:
            existing_join[field] = incoming_value
            continue

        if not existing_value and incoming_value:
            existing_join[field] = incoming_value
            continue

        if same_priority and incoming_value and incoming_value != existing_value:
            existing_join[field] = incoming_value

    merged["join"] = existing_join

    existing_desc = str(merged.get("description") or "").strip()
    incoming_desc = str(incoming.get("description") or "").strip()

    if not existing_desc and incoming_desc:
        merged["description"] = incoming_desc
    elif incoming_is_higher and incoming_desc:
        merged["description"] = incoming_desc
    elif same_priority and incoming_desc and len(incoming_desc) > len(existing_desc):
        merged["description"] = incoming_desc

    return merged


def dump_baseline_yaml(baseline: SemanticModel, output_path: Path) -> None:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency 'pyyaml'.") from exc

    payload = {
        "models": baseline.models,
        "relationships": baseline.relationships,
        "instructions": baseline.instructions,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def load_or_build_semantic_model(
    database,
    table_names: list[str],
    *,
    semantic_profile: str | None = None,
) -> SemanticModel:
    config = AppConfig()
    baseline = build_baseline_semantic_model(database, table_names)

    if config.MDL_AUTO_GENERATE_BASELINE:
        baseline_file = config.MDL_BASELINE_FILE
        profile = (semantic_profile or "").strip()
        profile_dir = config.MDL_DIR / config.MDL_DATABASES_SUBDIR / profile
        profile_docs_exist = profile and profile_dir.exists()
        if profile_docs_exist:
            baseline_file = (
                config.MDL_DIR
                / config.MDL_DATABASES_SUBDIR
                / profile
                / "_baseline.generated.yaml"
            )
        dump_baseline_yaml(baseline, baseline_file)

    docs = load_yaml_documents_for_profile(
        root_dir=config.MDL_DIR,
        file_glob=config.MDL_FILE_GLOB,
        semantic_profile=semantic_profile,
    )
    if not docs:
        return baseline

    return merge_semantic_model(baseline, docs)


def _build_inspector(database):
    try:
        from sqlalchemy import inspect
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency 'sqlalchemy'.") from exc

    engine = getattr(database, "_engine", None) or getattr(database, "engine", None)
    if engine is None:
        raise RuntimeError(
            "Could not access SQLAlchemy engine from SQLDatabase for schema introspection."
        )
    return inspect(engine)


def _split_table_identifier(value: str) -> tuple[str | None, str]:
    text = (value or "").strip()
    if not text:
        return None, ""

    cleaned = text.strip('"`[]')
    parts = [part.strip('"`[]') for part in cleaned.split(".") if part.strip()]
    if len(parts) <= 1:
        return None, parts[0] if parts else cleaned

    schema = parts[-2]
    table = parts[-1]
    return schema, table
