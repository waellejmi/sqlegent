import json
from pathlib import Path
from typing import Any, Dict


def slug_model(model_name: str) -> str:
    m = (model_name or "unknown").strip()
    return m.replace("/", "_").replace(":", "_").replace(" ", "_").replace("\\", "_")


def write_raw_result(rec: Dict[str, Any], out_path: Path):
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def pick_preview_rows(rows_list, n):
    if not rows_list:
        return []

    non_null = [
        row
        for row in rows_list
        if any((cell is not None and cell != "") for cell in row)
    ]
    source = non_null if non_null else rows_list
    length = len(source)

    if length <= n:
        return source

    indices = []
    for i in range(n):
        idx = (i * (length - 1)) // (n - 1) if n > 1 else length // 2
        indices.append(idx)

    seen = set()
    out = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            out.append(source[idx])

    return out


def get_analysis_status(analysis_result):
    if analysis_result is None:
        return None

    if isinstance(analysis_result, dict):
        return analysis_result.get("status")

    return getattr(analysis_result, "status", None)


def strip_sql_limit(sql: str):
    try:
        from sqlglot import parse_one
        from sqlglot.expressions import Select
    except Exception:
        return sql, None

    try:
        expr = parse_one(sql)
        for node in expr.walk():
            if isinstance(node, Select) and "limit" in (
                getattr(node, "args", {}) or {}
            ):
                node.args.pop("limit", None)
        return expr.sql(dialect="sqlite"), None
    except Exception as exc:
        return sql, f"sql_reexecution_failure: sqlglot_parse_error: {exc}"
