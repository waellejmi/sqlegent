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
    relationships = list(baseline.relationships)
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

        relationships.extend(doc.get("relationships", []))
        instructions.extend(doc.get("instructions", []))

    return SemanticModel(
        models=list(model_map.values()),
        relationships=relationships,
        instructions=instructions,
    )


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


def load_or_build_semantic_model(database, table_names: list[str]) -> SemanticModel:
    config = AppConfig()
    baseline = build_baseline_semantic_model(database, table_names)

    if config.MDL_AUTO_GENERATE_BASELINE:
        dump_baseline_yaml(baseline, config.MDL_BASELINE_FILE)

    docs = load_yaml_documents(config.MDL_DIR, config.MDL_FILE_GLOB)
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
