"""
Evaluation harness utilities: manifest generation, gold SQL execution, and execution-accuracy comparator.

Commands:
  python -m src.eval.harness manifest --dataset evaluation/MINIDEV/mini_dev_sqlite.json --out evaluation/results/manifest.json --sample-size 100 --seed 42
  python -m src.eval.harness exec_gold --db-root evaluation/MINIDEV/dev_databases --db-id financial --sql "SELECT ..."
  python -m src.eval.harness compare --reference-file ref_rows.json --agent-file agent_rows.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sqlite3
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


@dataclass
class Question:
    question_id: int
    db_id: str
    question: str
    evidence: Any
    SQL: str
    difficulty: str


def load_dataset(path: Path) -> List[Question]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions: List[Question] = []
    for item in data:
        questions.append(
            Question(
                question_id=int(item["question_id"]),
                db_id=str(item.get("db_id") or ""),
                question=str(item.get("question") or ""),
                evidence=item.get("evidence"),
                SQL=str(item.get("SQL") or ""),
                difficulty=str(item.get("difficulty") or ""),
            )
        )
    return questions


def stratified_sample(
    questions: List[Question], sample_size: int, seed: int
) -> List[int]:
    total = len(questions)
    if sample_size >= total:
        return [q.question_id for q in questions]

    groups: Dict[Tuple[str, str], List[Question]] = {}
    for q in questions:
        key = (q.db_id, q.difficulty)
        groups.setdefault(key, []).append(q)

    # proportional allocation with largest remainder method
    alloc: Dict[Tuple[str, str], int] = {}
    remainders: List[Tuple[Tuple[str, str], float]] = []
    for k, grp in groups.items():
        exact = len(grp) * sample_size / total
        base = int(math.floor(exact))
        alloc[k] = base
        remainders.append((k, exact - base))

    remaining = sample_size - sum(alloc.values())
    remainders.sort(key=lambda x: x[1], reverse=True)
    i = 0
    while remaining > 0 and i < len(remainders):
        k = remainders[i][0]
        if alloc[k] < len(groups[k]):
            alloc[k] += 1
            remaining -= 1
        i += 1

    # If any group allocations exceed group size (rare), cap and redistribute
    surplus = 0
    for k in list(alloc.keys()):
        if alloc[k] > len(groups[k]):
            surplus += alloc[k] - len(groups[k])
            alloc[k] = len(groups[k])
    if surplus > 0:
        # redistribute surplus to groups with spare capacity
        candidates = [k for k in groups.keys() if alloc[k] < len(groups[k])]
        idx = 0
        while surplus > 0 and candidates:
            k = candidates[idx % len(candidates)]
            alloc[k] += 1
            surplus -= 1
            if alloc[k] >= len(groups[k]):
                candidates.remove(k)
            idx += 1

    # perform sampling within each group
    rnd = random.Random(seed)
    selected_ids: List[int] = []
    for k, grp in groups.items():
        n = alloc.get(k, 0)
        if n <= 0:
            continue
        choices = rnd.sample([q.question_id for q in grp], min(n, len(grp)))
        selected_ids.extend(choices)

    # If rounding led to different total, adjust by random selection across remaining
    if len(selected_ids) < sample_size:
        remaining_needed = sample_size - len(selected_ids)
        remaining_pool = [
            q.question_id for q in questions if q.question_id not in selected_ids
        ]
        rnd.shuffle(remaining_pool)
        selected_ids.extend(remaining_pool[:remaining_needed])
    elif len(selected_ids) > sample_size:
        rnd.shuffle(selected_ids)
        selected_ids = selected_ids[:sample_size]

    return sorted(selected_ids)


def current_git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:
        return ""


def write_manifest(
    dataset_path: str,
    database_root: str,
    selected_question_ids: List[int],
    out_path: Path,
    sample_size: int,
    seed: int,
):
    """
    Write a minimal manifest for evaluation runs. Judge configuration removed: deterministic comparator used instead.
    """
    manifest = {
        "dataset_path": dataset_path,
        "database_root": database_root,
        "sample_size": sample_size,
        "seed": seed,
        "selected_question_ids": selected_question_ids,
        "agent_git_commit": current_git_commit(),
        "condition_a_config": {
            "ENABLE_CONTEXT_LAYER": 0,
        },
        "condition_b_config": {
            "ENABLE_CONTEXT_LAYER": 1,
            "ENABLE_INSTRUCTION_CONTEXT": 1,
            "ENABLE_SCHEMA_CONTEXT": 0,
            "CONTEXT_PROJECT_ID_template": "eval_q{question_id}",
            "CONTEXT_STORE_PATH_template": "evaluation/results/context_eval_q{question_id}.sqlite",
        },
        "run_order": "sequential_a_then_b",
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return out_path


# Gold SQL execution and serialization


def execute_sqlite_query(
    db_file: Path, sql: str
) -> Tuple[List[Tuple[Any, ...]], List[str]]:
    """
    Execute SQL against SQLite and return (rows, column_names).
    """
    if not db_file.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_file}")
    conn = sqlite3.connect(str(db_file))
    try:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in (cur.description or [])]
        return rows, cols
    finally:
        conn.close()


def normalize_value_for_compare(v: Any):
    """
    Normalize a value for robust comparison:
    - None stays None
    - floats rounded to 4 decimals
    - ints preserved
    - numeric strings converted to numbers
    - ISO-like dates/datetimes reduced to date part
    - strings are stripped and lowercased to avoid case/whitespace mismatches
    """
    if v is None:
        return None

    # Numbers
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, int):
        return v

    # Strings: attempt numeric parse, date normalize, then whitespace/case normalize
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return ""
        # Numeric-looking strings
        try:
            if "." in s:
                return round(float(s), 4)
            return int(s)
        except ValueError:
            pass

        # ISO date or datetime -> return date part YYYY-MM-DD
        # match YYYY-MM-DD or YYYY-MM-DD HH:MM:SS(.micro)? with optional timezone
        import re

        m = re.match(
            r"^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$",
            s,
        )
        if m:
            return m.group(1)

        # Normalize case and whitespace for general strings
        return s.lower()

    return v


def serialize_rows_for_judge(
    rows: List[Tuple[Any, ...]], columns: List[str] | None = None
) -> Tuple[List[Tuple[Any, ...]], str]:
    """
    Normalize rows and produce a deterministic, human-readable text for the judge.
    Includes an optional header row with column names. NULLs rendered as `<NULL>`; empty strings as "".
    """
    # Normalize values
    normalized = [tuple(normalize_value_for_compare(c) for c in row) for row in rows]

    def cell_key(c: Any) -> str:
        if c is None:
            return "<NULL>"
        if isinstance(c, float):
            return f"{c:.4f}"
        if c == "":
            return '""'
        return str(c)

    sorted_rows = sorted(normalized, key=lambda r: tuple(cell_key(c) for c in r))

    # Build text representation, cap at 50 rows
    max_rows = 50
    displayed = sorted_rows[:max_rows]
    lines = []
    # Header
    if columns:
        lines.append(" | ".join(columns))

    for r in displayed:
        line = " | ".join(cell_key(c) for c in r)
        lines.append(line)
    more = len(sorted_rows) - len(displayed)
    if more > 0:
        lines.append(f"... {more} more rows")

    text = "\n".join(lines)
    return sorted_rows, text


def compare_rows(
    agent_rows: List[Tuple[Any, ...]],
    agent_cols: List[str],
    reference_rows: List[Tuple[Any, ...]],
    reference_cols: List[str],
) -> bool:
    """
    Column-wise superset match: for every reference (gold) column, find some agent column
    whose full value-multiset (after normalize_value_for_compare) matches it exactly. Extra
    agent columns are ignored. Row order is irrelevant. Row COUNT must match.
    """
    # Quick length check on rows
    if len(agent_rows or []) != len(reference_rows or []):
        return False

    def col_vals(rows, idx):
        return [normalize_value_for_compare(r[idx]) for r in (rows or [])]

    matched_agent_cols = set()
    for gi in range(len(reference_cols or [])):
        g_counter = Counter(col_vals(reference_rows, gi))
        found = False
        for aj in range(len(agent_cols or [])):
            if aj in matched_agent_cols:
                continue
            a_counter = Counter(col_vals(agent_rows, aj))
            if a_counter == g_counter:
                matched_agent_cols.add(aj)
                found = True
                break
        if not found:
            return False
    return True


# NOTE: row order is intentionally NOT normalized before comparison — this matches official
# BIRD Mini-Dev behavior exactly (see evaluation_utils.py: execute_sql applies no sort). This
# means soft_f1 is order-sensitive: if agent SQL or gold SQL lacks an explicit ORDER BY, results
# can vary based on database scan order alone. This is a known characteristic of the official
# metric, not a bug — do not add sorting as a "fix."


def calculate_row_match(predicted_row, ground_truth_row):
    """
    Direct port of BIRD Mini-Dev's calculate_row_match. Per-row, normalized by the gold row's
    column count. No null handling — None is a normal value checked via `in`.
    """
    total_columns = len(ground_truth_row)
    if total_columns == 0:
        return 0.0, 0.0, 0.0

    matches = 0
    element_in_pred_only = 0
    for pred_val in predicted_row:
        if pred_val in ground_truth_row:
            matches += 1
        else:
            element_in_pred_only += 1
    element_in_truth_only = sum(
        1 for truth_val in ground_truth_row if truth_val not in predicted_row
    )

    return (
        matches / total_columns,
        element_in_pred_only / total_columns,
        element_in_truth_only / total_columns,
    )


def soft_f1(agent_rows, reference_rows):
    """
    Direct port of BIRD Mini-Dev's calculate_f1_score. Rows are aligned by POSITION
    (predicted[i] vs ground_truth[i]), matching official behavior exactly — this is
    intentionally order-sensitive, do not sort inputs before calling this function.
    """
    predicted = [tuple(r) for r in (agent_rows or [])]
    ground_truth = [tuple(r) for r in (reference_rows or [])]

    if not predicted and not ground_truth:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    match_scores, pred_only_scores, truth_only_scores = [], [], []

    for i, gt_row in enumerate(ground_truth):
        if i >= len(predicted):
            match_scores.append(0)
            pred_only_scores.append(0)
            truth_only_scores.append(1)
            continue
        m, p, t = calculate_row_match(predicted[i], gt_row)
        match_scores.append(m)
        pred_only_scores.append(p)
        truth_only_scores.append(t)

    for _ in range(max(0, len(predicted) - len(ground_truth))):
        match_scores.append(0)
        pred_only_scores.append(1)
        truth_only_scores.append(0)

    tp = sum(match_scores)
    fp = sum(pred_only_scores)
    fn = sum(truth_only_scores)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def execution_accuracy_official(agent_rows, reference_rows) -> int:
    """
    Direct port of BIRD Mini-Dev's calculate_ex. Full-row exact set equality — an agent result
    with any extra or missing column fails outright, regardless of whether the requested data
    is otherwise correct. This is stricter than our existing column-superset comparator.
    """
    predicted_set = set(tuple(r) for r in (agent_rows or []))
    ground_truth_set = set(tuple(r) for r in (reference_rows or []))
    return 1 if predicted_set == ground_truth_set else 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    p_manifest = sub.add_parser("manifest")
    p_manifest.add_argument("--dataset", required=True)
    p_manifest.add_argument("--database-root", required=True)
    p_manifest.add_argument("--out", required=True)
    p_manifest.add_argument("--sample-size", type=int, default=100)
    p_manifest.add_argument("--seed", type=int, default=42)

    p_exec = sub.add_parser("exec_gold")
    p_exec.add_argument("--db-root", required=True)
    p_exec.add_argument("--db-id", required=True)
    p_exec.add_argument("--sql", required=True)

    p_compare = sub.add_parser("compare")
    p_compare.add_argument("--reference-file", required=True)
    p_compare.add_argument("--agent-file", required=True)

    args = parser.parse_args()
    if args.cmd == "manifest":
        dataset = Path(args.dataset)
        questions = load_dataset(dataset)
        selected = stratified_sample(questions, args.sample_size, args.seed)
        out = write_manifest(
            dataset_path=str(dataset),
            database_root=args.database_root,
            selected_question_ids=selected,
            out_path=Path(args.out),
            sample_size=args.sample_size,
            seed=args.seed,
        )
        print(out)
        return

    if args.cmd == "exec_gold":
        db_file = Path(args.db_root) / args.db_id / f"{args.db_id}.sqlite"
        rows, cols = execute_sqlite_query(db_file, args.sql)
        sorted_rows, text = serialize_rows_for_judge(rows, columns=cols)
        out = {
            "reference_rows": sorted_rows,
            "reference_text": text,
            "reference_columns": cols,
        }
        print(json.dumps(out, indent=2, default=str))
        return

    if args.cmd == "compare":
        with open(args.reference_file, "r", encoding="utf-8") as f:
            ref = json.load(f)
        with open(args.agent_file, "r", encoding="utf-8") as f:
            agent = json.load(f)
        ref_rows = [tuple(r) for r in ref.get("reference_rows", [])]
        ref_cols = ref.get("reference_columns") or ref.get("columns") or []
        agent_rows = [tuple(r) for r in agent.get("agent_rows", [])]
        agent_cols = agent.get("agent_columns") or agent.get("columns") or []
        result = compare_rows(agent_rows, agent_cols, ref_rows, ref_cols)
        print("column_superset_match:", result)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
