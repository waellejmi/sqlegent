"""
Run full evaluation harness per CLAUDE.md: uses manifest of selected questions, executes gold SQL, stages evidence as semantic YAML for 'with_evidence', reindexes, runs the agent fresh per question and condition, performs deterministic comparison against gold SQL, and writes raw_results.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.eval.harness import (
    compare_rows,
    execute_sqlite_query,
    load_dataset,
    normalize_value_for_compare,
    serialize_rows_for_judge,
)
from utils.logger_setup import LoggerSetup

logger = LoggerSetup.get_logger(__name__)


@dataclass
class RunResult:
    question_id: int
    db_id: str
    difficulty: str
    condition: str
    question: str
    agent_answer: Optional[str]
    reference_result: str
    execution_correct: Optional[bool]
    skip_pipeline_fired: Optional[bool]
    retries: Optional[int]
    latency_ms: Optional[int]
    error: Optional[str]
    evaluation_error_type: Optional[str]


ROOT = Path(__file__).resolve().parent.parent.parent
# Ensure repo root and src/ are on sys.path for local imports
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

RESULTS_DIR = ROOT / "evaluation" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RAW_RESULTS_PATH = RESULTS_DIR / "raw_results.jsonl"


def save_runtime_settings_patch(patch: Dict[str, Any]):
    # Write eval-specific runtime overrides so main settings.json is not modified
    try:
        from config.app_config import AppConfig

        cfg = AppConfig()
        cfg.save_eval_runtime_settings(patch)
    except Exception:
        # Fallback: write to .app_config/eval_settings.json directly
        eval_path = ROOT / ".app_config" / "eval_settings.json"
        data = {}
        if eval_path.exists():
            try:
                with open(eval_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data.update(patch)
        eval_path.parent.mkdir(parents=True, exist_ok=True)
        with open(eval_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


async def invoke_agent(question: str, timeout: int = 120) -> Dict[str, Any]:
    """
    Minimal agent invocation with evaluation-only model fallback:
    Try models from AppConfig.LLM_MODEL_LIST in order if a run times out or fails due to model-level errors.
    Restores original LLM_ACTIVE_MODEL after attempts.
    """
    from app.agent_runtime import run_agent_with_interrupt
    from app.state_factory import build_initial_state, make_runnable_config
    from config.app_config import AppConfig

    cfg = AppConfig()
    model_list = list(cfg.LLM_MODEL_LIST or [])
    # Ensure active model is in the rotation first
    if cfg.LLM_ACTIVE_MODEL and cfg.LLM_ACTIVE_MODEL not in model_list:
        model_list.insert(0, cfg.LLM_ACTIVE_MODEL)

    original_active = cfg.LLM_ACTIVE_MODEL

    # Ensure fresh LangGraph checkpointer by removing checkpoints DB
    cp_path = AppConfig().ROOT_DIR / ".app_cache" / "checkpoints.sqlite"
    try:
        if cp_path.exists():
            cp_path.unlink()
    except Exception:
        pass

    initial_state = build_initial_state(question)

    async def _dummy_interrupt_handler(_info: Any) -> dict:
        return {}

    last_error = None
    for model in model_list:
        try:
            # Set active model for this attempt (in-memory)
            cfg.LLM_ACTIVE_MODEL = model
            config = make_runnable_config()

            t0 = time.time()
            try:
                agent, final_state = await asyncio.wait_for(
                    run_agent_with_interrupt(
                        input_state=initial_state,
                        config=config,
                        interrupt_handler=_dummy_interrupt_handler,
                        on_message=None,
                        on_transition=None,
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                last_error = {
                    "error": f"agent_timeout_after_{timeout}s",
                    "model": model,
                }
                # try next model
                continue
            except Exception as e:
                last_error = {"error": str(e), "model": model}
                # try next model
                continue

            latency_ms = int((time.time() - t0) * 1000)

            # final_state.values is expected to be a dict-like mapping per agent/state.py
            values = getattr(final_state, "values", {}) or {}

            # Extract core fields straightforwardly
            last_query = values.get("last_query")
            db_output = values.get("db_output")
            analysis_result = values.get("analysis_result")
            skip_decision = values.get("skip_decision")
            retry_count = values.get("retry_count") or 0

            # Try to extract a human-readable final answer if present
            final_answer = values.get("final_answer")
            agent_answer = None
            if isinstance(final_answer, str) and final_answer.strip():
                agent_answer = final_answer.strip()

            # Derive skip_pipeline_fired boolean from skip_decision if available
            skip_pipeline_fired = None
            try:
                if skip_decision is None:
                    skip_pipeline_fired = None
                elif isinstance(skip_decision, dict):
                    skip_pipeline_fired = bool(skip_decision.get("skip", False))
                else:
                    skip_pipeline_fired = bool(getattr(skip_decision, "skip", False))
            except Exception:
                skip_pipeline_fired = None

            # Attempt to normalize analysis_result to a dict with 'status' and 'explanation'
            ar = None
            try:
                if analysis_result is None:
                    ar = None
                elif isinstance(analysis_result, dict):
                    ar = analysis_result
                else:
                    # pydantic model or object
                    ar = {
                        "status": getattr(analysis_result, "status", None),
                        "explanation": getattr(analysis_result, "explanation", None),
                    }
            except Exception:
                ar = None

            result = {
                "last_query": last_query,
                "db_output": db_output,
                "analysis_result": ar,
                "skip_decision": skip_decision,
                "skip_pipeline_fired": skip_pipeline_fired,
                "agent_answer": agent_answer,
                "retries": retry_count,
                "latency_ms": latency_ms,
                "error": None,
                "model_used": model,
            }

            # Restore original active model before returning
            try:
                cfg.LLM_ACTIVE_MODEL = original_active
            except Exception:
                pass

            return result

        except Exception as e:
            last_error = {"error": str(e), "model": model}
            continue

    # All models failed; restore original active model
    try:
        cfg.LLM_ACTIVE_MODEL = original_active
    except Exception:
        pass

    if last_error is None:
        return {"error": "agent_invocation_failed"}
    return last_error


def write_raw_result(rec: Dict[str, Any]):
    with open(RAW_RESULTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=False)
    parser.add_argument(
        "--dataset",
        default=str(ROOT / "evaluation" / "MINIDEV" / "mini_dev_sqlite.json"),
    )
    parser.add_argument(
        "--database-root",
        default=str(ROOT / "evaluation" / "MINIDEV" / "dev_databases"),
    )
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--agent-timeout",
        type=int,
        default=70,
        help="Per-agent timeout in seconds to prevent hangs (default 120)",
    )
    args = parser.parse_args()

    # Reduce noisy logging from HF/httpx during eval runs
    import logging as _logging

    for _n in (
        "httpx",
        "transformers",
        "huggingface_hub",
        "urllib3",
        "hf_hub",
    ):  # hf_hub alias
        try:
            _logging.getLogger(_n).setLevel(_logging.WARNING)
        except Exception:
            pass

    dataset_path = Path(args.dataset)
    db_root = Path(args.database_root)

    # Load dataset
    questions = load_dataset(dataset_path)

    # Manifest
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            selected_ids = manifest.get("selected_question_ids", [])
            run_order = manifest.get("run_order", "sequential_a_then_b")
    else:
        # simple stratified sampling via harness
        from src.eval.harness import stratified_sample, write_manifest

        selected_ids = stratified_sample(questions, args.sample_size, args.seed)
        manifest_path = RESULTS_DIR / "manifest.json"
        write_manifest(
            str(dataset_path),
            str(db_root),
            selected_ids,
            manifest_path,
            args.sample_size,
            args.seed,
        )
        run_order = "sequential_a_then_b"

    # Build lookup
    qmap = {q.question_id: q for q in questions}

    async def _run():
        for qid in selected_ids:
            q = qmap.get(qid)
            if not q:
                logger.warning("Missing question %s", qid)
                continue

            # Execute gold SQL
            db_file = Path(db_root) / q.db_id / f"{q.db_id}.sqlite"
            try:
                rows, cols = execute_sqlite_query(db_file, q.SQL)
                # Keep raw reference rows (unsorted, un-normalized) for official EX and soft_f1
                raw_ref_rows = [tuple(r) for r in rows]
                ref_rows, _ = serialize_rows_for_judge(rows, columns=cols)
            except Exception as e:
                logger.error("Gold SQL execution failed for q%s: %s", qid, e)
                continue

            for condition in ["without_evidence", "with_evidence"]:
                logger.info("Running q%s condition=%s", qid, condition)
                # Prepare runtime settings per condition
                if condition == "without_evidence":
                    patch = {
                        "ENABLE_CONTEXT_LAYER": False,
                        "ENABLE_INSTRUCTION_CONTEXT": False,
                        "ENABLE_SCHEMA_CONTEXT": False,
                        "CONTEXT_PROJECT_ID": f"eval_q{qid}",
                        "CONTEXT_STORE_PATH": str(
                            RESULTS_DIR / f"context_eval_q{qid}.sqlite"
                        ),
                    }
                    save_runtime_settings_patch(patch)
                    # ensure no staged YAML
                else:
                    patch = {
                        "ENABLE_CONTEXT_LAYER": True,
                        "ENABLE_INSTRUCTION_CONTEXT": True,
                        "ENABLE_SCHEMA_CONTEXT": False,
                        "CONTEXT_PROJECT_ID": f"eval_q{qid}",
                        "CONTEXT_STORE_PATH": str(
                            RESULTS_DIR / f"context_eval_q{qid}.sqlite"
                        ),
                    }
                    save_runtime_settings_patch(patch)
                    # Build YAML from evidence and stage
                    tmp_out = RESULTS_DIR / "staged_mdl"
                    tmp_out.mkdir(parents=True, exist_ok=True)
                    script = ROOT / "tools" / "evidence_to_mdl.py"
                    ev_text = ""
                    if q.evidence:
                        ev_text = json.dumps(q.evidence)
                    cmd = [
                        str(script),
                        "--question-id",
                        str(qid),
                        "--db-id",
                        q.db_id,
                        "--question",
                        q.question,
                        "--evidence-text",
                        ev_text,
                        "--out-dir",
                        str(tmp_out),
                    ]
                    try:
                        subprocess.check_output(cmd)
                    except Exception as e:
                        logger.error(
                            "Failed to create evidence YAML for q%s: %s", qid, e
                        )
                        continue
                    staged = list(tmp_out.glob(f"eval_q{qid}_*.yaml"))
                    if not staged:
                        logger.warning("No staged YAML produced for q%s", qid)
                    else:
                        # Copy to MDL_DIR
                        from config.app_config import AppConfig
                        from config.db_config import DBConfig

                        cfg = AppConfig()
                        dest = cfg.MDL_DIR / staged[0].name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(staged[0], dest)

                        # Temporarily set DBConfig to point to the question's sqlite file so
                        # reindex introspects the correct database instead of the default
                        # configured DB (which may be MySQL). Save/restore previous URI.
                        try:
                            db_config = DBConfig()
                            previous_uri = None
                            try:
                                previous_uri = db_config.get_database_uri()
                            except Exception:
                                previous_uri = None
                            sqlite_uri = db_config.sqlite_path_to_uri(db_file)
                            db_config.set_database_uri(sqlite_uri)
                        except Exception as e:
                            logger.warning(
                                "Could not set DBConfig to sqlite uri: %s", e
                            )

                        # Reindex. Ensure context_layer singleton is reset so it picks up the
                        # updated CONTEXT_STORE_PATH from AppConfig.
                        try:
                            # Reset module-level singleton
                            import importlib

                            import context_layer.service as _clsrv

                            if hasattr(_clsrv, "_context_service"):
                                _clsrv._context_service = None
                        except Exception:
                            pass

                        try:
                            from app.context_ops import run_context_reindex

                            run_context_reindex(None)
                        except Exception as e:
                            logger.warning(
                                "Context reindex failed, continuing without reindex: %s",
                                e,
                            )

                        # Restore previous DB URI if we changed it
                        try:
                            if previous_uri:
                                db_config.set_database_uri(previous_uri)
                        except Exception:
                            pass

                # Ensure DBConfig points to the question's sqlite file for agent runtime
                previous_db_uri = None
                try:
                    from config.db_config import DBConfig

                    db_config = DBConfig()
                    try:
                        previous_db_uri = db_config.get_database_uri()
                    except Exception:
                        previous_db_uri = None
                    sqlite_uri = db_config.sqlite_path_to_uri(db_file)
                    db_config.set_database_uri(sqlite_uri)

                    # Reset tools.database module-level caches so it reloads the sqlite DB
                    try:
                        import importlib

                        import tools.database as _td

                        if hasattr(_td, "_active_database_uri"):
                            _td._active_database_uri = ""
                        if hasattr(_td, "_db"):
                            _td._db = None
                        if hasattr(_td, "_get_schema_tool"):
                            _td._get_schema_tool = None
                        if hasattr(_td, "_run_query_tool"):
                            _td._run_query_tool = None
                    except Exception:
                        pass
                except Exception:
                    previous_db_uri = None

                # Run agent
                try:
                    start = time.time()
                    agent_result = await invoke_agent(
                        q.question, timeout=args.agent_timeout
                    )
                    duration = int((time.time() - start) * 1000)
                except Exception as e:
                    agent_result = {"error": str(e)}
                    duration = None

                # Restore previous DB URI if we changed it
                try:
                    if previous_db_uri:
                        db_config.set_database_uri(previous_db_uri)
                        try:
                            import importlib

                            import tools.database as _td

                            if hasattr(_td, "_active_database_uri"):
                                _td._active_database_uri = ""
                            if hasattr(_td, "_db"):
                                _td._db = None
                            if hasattr(_td, "_get_schema_tool"):
                                _td._get_schema_tool = None
                            if hasattr(_td, "_run_query_tool"):
                                _td._run_query_tool = None
                        except Exception:
                            pass
                except Exception:
                    pass

                # If we staged a YAML, unstage and delete context store
                if condition == "with_evidence":
                    try:
                        from config.app_config import AppConfig

                        cfg = AppConfig()
                        staged_file = cfg.MDL_DIR / f"eval_q{qid}_{q.db_id}.yaml"
                        if staged_file.exists():
                            staged_file.unlink()
                    except Exception:
                        pass
                    # delete context store file
                    try:
                        cfg = AppConfig()
                        p = Path(cfg.CONTEXT_STORE_PATH)
                        if p.exists():
                            p.unlink()
                    except Exception:
                        pass

                    # remove temporary staged MDL directory
                    try:
                        tmp_out_dir = RESULTS_DIR / "staged_mdl"
                        if tmp_out_dir.exists():
                            shutil.rmtree(tmp_out_dir)
                    except Exception:
                        pass

                PREVIEW_N = 3

                # Derive analysis_result status to record as agent_answer
                ar_field = None
                try:
                    ar_field = (
                        agent_result.get("analysis_result")
                        if isinstance(agent_result, dict)
                        else None
                    )
                    if ar_field is None:
                        ar_status = None
                    elif isinstance(ar_field, dict):
                        ar_status = ar_field.get("status")
                    else:
                        ar_status = getattr(ar_field, "status", None)
                except Exception:
                    ar_status = None

                # Build result record with explicit agent/gold preview fields
                rec = {
                    "question_id": qid,
                    "db_id": q.db_id,
                    "difficulty": q.difficulty,
                    "condition": condition,
                    "question": q.question,
                    # Agent-provided outputs: record analysis_result.status here per request
                    "agent_answer": ar_status,
                    "agent_last_query": agent_result.get("last_query")
                    if isinstance(agent_result, dict)
                    else None,
                    # Gold (reference) preview and metadata
                    "gold_db_preview": [list(r) for r in (ref_rows or [])[:PREVIEW_N]],
                    "gold_db_total_rows": len(ref_rows or []),
                    "execution_correct": None,
                    "skip_pipeline_fired": agent_result.get("skip_pipeline_fired")
                    if isinstance(agent_result, dict)
                    else None,
                    "retries": agent_result.get("retries")
                    if isinstance(agent_result, dict)
                    else None,
                    "latency_ms": agent_result.get("latency_ms")
                    if isinstance(agent_result, dict)
                    else duration,
                    "error": agent_result.get("error")
                    if isinstance(agent_result, dict)
                    else None,
                    "evaluation_error_type": None,
                }

                # Deterministic execution-accuracy comparator (superset-match)
                execution_correct = None
                agent_rows_full = None
                agent_cols = None
                soft_f1_result = None
                try:
                    from config.app_config import AppConfig
                    from src.eval import harness as harness_mod

                    try:
                        from sqlglot import parse_one
                        from sqlglot.expressions import Select
                    except Exception:
                        parse_one = None
                        Select = None

                    cfg = AppConfig()

                    ar = (
                        agent_result.get("analysis_result")
                        if isinstance(agent_result, dict)
                        else None
                    )
                    ar_status = None
                    if isinstance(ar, dict):
                        ar_status = ar.get("status")
                    else:
                        try:
                            ar_status = getattr(ar, "status", None)
                        except Exception:
                            ar_status = None

                    # Only compare when analysis_result.status == 'success'
                    if ar_status == "success":
                        last_query = (
                            agent_result.get("last_query")
                            if isinstance(agent_result, dict)
                            else None
                        )
                        if last_query and cfg.EXECUTE_SQL_QUERIES:
                            # Strip LIMIT using sqlglot if available
                            unlimited_sql = last_query
                            if parse_one is not None and Select is not None:
                                try:
                                    expr = parse_one(last_query)
                                    for node in expr.walk():
                                        if isinstance(node, Select) and "limit" in (
                                            getattr(node, "args", {}) or {}
                                        ):
                                            node.args.pop("limit", None)
                                    unlimited_sql = expr.sql(dialect="sqlite")
                                except Exception as e:
                                    rec["evaluation_error_type"] = (
                                        f"sql_reexecution_failure: sqlglot_parse_error: {e}"
                                    )
                                    unlimited_sql = last_query

                            # Execute the unlimited SQL separately against the sqlite DB
                            try:
                                a_rows, a_cols = execute_sqlite_query(
                                    db_file, unlimited_sql
                                )
                                agent_rows_full = [tuple(r) for r in a_rows]
                                agent_cols = a_cols or []
                            except Exception as e:
                                rec["evaluation_error_type"] = (
                                    f"sql_reexecution_failure: {e}"
                                )
                                agent_rows_full = None

                        else:
                            # Fallback to db_output field from final_state (not preferred)
                            if agent_result.get("db_output"):
                                try:
                                    db_out = agent_result.get("db_output")
                                    parsed = (
                                        json.loads(db_out)
                                        if isinstance(db_out, str)
                                        else db_out
                                    )
                                    if isinstance(parsed, list):
                                        agent_rows_full = [tuple(r) for r in parsed]
                                        agent_cols = None
                                except Exception as e:
                                    rec["evaluation_error_type"] = (
                                        f"agent_db_output_parse_error: {e}"
                                    )
                                    agent_rows_full = None

                    # If we don't have agent_rows_full, this is an evaluation error (or not run)
                    if agent_rows_full is None:
                        execution_correct = None
                        execution_accuracy_official = None
                    else:
                        # Use the consolidated comparator from harness (column-superset match)
                        try:
                            execution_correct = harness_mod.compare_rows(
                                agent_rows_full,
                                agent_cols or [],
                                raw_ref_rows,
                                cols or [],
                            )
                        except Exception as e:
                            rec["evaluation_error_type"] = f"comparator_error: {e}"
                            execution_correct = None

                        # Compute official EX (exact full-row set equality) on raw, limit-stripped results
                        try:
                            execution_accuracy_official = (
                                harness_mod.execution_accuracy_official(
                                    agent_rows_full, raw_ref_rows
                                )
                            )
                        except Exception as e:
                            logger.warning(
                                "execution_accuracy_official computation failed for q%s: %s",
                                qid,
                                e,
                            )
                            execution_accuracy_official = None

                        # Compute soft F1 (official algorithm). Only when agent_rows_full is present.
                        try:
                            sf = harness_mod.soft_f1(agent_rows_full, raw_ref_rows)
                            soft_f1_result = sf
                        except Exception as e:
                            logger.warning(
                                "soft_f1 computation failed for q%s: %s", qid, e
                            )
                            # Do not override evaluation_error_type for soft-f1 failures

                except Exception as e:
                    rec["evaluation_error_type"] = f"comparator_error: {e}"
                    execution_correct = None
                    soft_f1_result = None

                # Store previews instead of full outputs to avoid huge raw_results
                def _pick_preview_rows(rows_list, n):
                    """Deterministic, representative sampling from sorted rows.
                    Prefer non-null rows; when many exist, pick evenly spaced quantile samples
                    to show diverse values instead of the top lexicographic ones.
                    """
                    if not rows_list:
                        return []
                    non_null = [
                        r
                        for r in rows_list
                        if any((c is not None and c != "") for c in r)
                    ]
                    source = non_null if non_null else rows_list
                    L = len(source)
                    if L <= n:
                        return source
                    # pick indices at quantiles: include first, last, and evenly spaced in between
                    indices = []
                    for i in range(n):
                        idx = (i * (L - 1)) // (n - 1) if n > 1 else L // 2
                        indices.append(idx)
                    # deduplicate while preserving order
                    seen = set()
                    out = []
                    for idx in indices:
                        if idx not in seen:
                            seen.add(idx)
                            out.append(source[idx])
                    return out

                rec["gold_db_total_rows"] = len(ref_rows or [])
                # If gold selected a single column, provide a value-count preview (more informative)
                if (cols and len(cols) == 1) or (
                    not cols and ref_rows and len(ref_rows[0]) == 1
                ):
                    from collections import Counter

                    # normalize values for counting
                    gvals = [
                        normalize_value_for_compare(r[0]) for r in (ref_rows or [])
                    ]
                    gcount = Counter(gvals)
                    top = gcount.most_common(PREVIEW_N)
                    rec["gold_value_counts_preview"] = [
                        {"value": k, "count": v} for k, v in top
                    ]
                    # also keep a small sample of non-null values (quantile based)
                    rec["gold_db_preview"] = [
                        list(r) for r in _pick_preview_rows(ref_rows or [], PREVIEW_N)
                    ]
                else:
                    rec["gold_db_preview"] = [
                        list(r) for r in _pick_preview_rows(ref_rows or [], PREVIEW_N)
                    ]

                if agent_rows_full is not None:
                    # Sort agent rows deterministically using same serializer to mirror comparator sorting
                    try:
                        sorted_agent_rows, _ = serialize_rows_for_judge(
                            agent_rows_full, columns=agent_cols
                        )
                    except Exception:
                        sorted_agent_rows = agent_rows_full
                    rec["agent_db_total_rows"] = len(agent_rows_full)

                    # If gold has single column, try to show counts for agent column that best matches
                    if (cols and len(cols) == 1) and agent_cols:
                        from collections import Counter

                        # pick agent column with highest overlap by Counter similarity
                        best_col = None
                        best_score = -1
                        gcount = Counter(
                            [
                                normalize_value_for_compare(r[0])
                                for r in (ref_rows or [])
                            ]
                        )
                        for aj in range(len(agent_cols)):
                            acount = Counter(
                                [
                                    normalize_value_for_compare(r[aj])
                                    for r in agent_rows_full
                                ]
                            )
                            # score as number of equal counts across values
                            score = sum(
                                min(acount[k], gcount.get(k, 0)) for k in acount.keys()
                            )
                            if score > best_score:
                                best_score = score
                                best_col = aj
                        if best_col is not None:
                            acount = Counter(
                                [
                                    normalize_value_for_compare(r[best_col])
                                    for r in agent_rows_full
                                ]
                            )
                            top = acount.most_common(PREVIEW_N)
                            rec["agent_value_counts_preview"] = [
                                {"value": k, "count": v} for k, v in top
                            ]
                        else:
                            rec["agent_value_counts_preview"] = None
                        rec["agent_db_preview"] = [
                            list(r)
                            for r in _pick_preview_rows(sorted_agent_rows, PREVIEW_N)
                        ]
                    else:
                        rec["agent_db_preview"] = [
                            list(r)
                            for r in _pick_preview_rows(sorted_agent_rows, PREVIEW_N)
                        ]
                        rec["agent_value_counts_preview"] = None
                else:
                    rec["agent_db_preview"] = None
                    rec["agent_db_total_rows"] = None
                    rec["agent_value_counts_preview"] = None

                rec["column_superset_match"] = execution_correct
                # include official EX result if computed
                rec["execution_accuracy_official"] = (
                    execution_accuracy_official
                    if "execution_accuracy_official" in locals()
                    else None
                )

                # Build flat final record with ordered keys: meta -> gold -> agent -> evaluation
                final_rec = {
                    "question_id": rec.get("question_id"),
                    "db_id": rec.get("db_id"),
                    "difficulty": rec.get("difficulty"),
                    "condition": rec.get("condition"),
                    "question": rec.get("question"),
                    # Gold block (grouped by order, not nested)
                    "gold_sql": q.SQL,
                    "gold_db_preview": rec.get("gold_db_preview"),
                    "gold_db_total_rows": rec.get("gold_db_total_rows"),
                    "gold_value_counts_preview": rec.get("gold_value_counts_preview"),
                    # Agent block
                    "agent_answer": rec.get("agent_answer"),
                    "agent_llm_model": (agent_result.get("model_used")),
                    "agent_last_query": rec.get("agent_last_query"),
                    "agent_db_preview": rec.get("agent_db_preview"),
                    "agent_db_total_rows": rec.get("agent_db_total_rows"),
                    "agent_value_counts_preview": rec.get("agent_value_counts_preview"),
                    # Evaluation results
                    "execution_accuracy_official": rec.get(
                        "execution_accuracy_official"
                    ),
                    "column_superset_match": rec.get("column_superset_match"),
                    "soft_f1_precision": (
                        soft_f1_result.get("precision") if soft_f1_result else None
                    ),
                    "soft_f1_recall": (
                        soft_f1_result.get("recall") if soft_f1_result else None
                    ),
                    "soft_f1_score": (
                        soft_f1_result.get("f1") if soft_f1_result else None
                    ),
                    "skip_pipeline_fired": rec.get("skip_pipeline_fired"),
                    "retries": rec.get("retries"),
                    "latency_ms": rec.get("latency_ms"),
                    "error": rec.get("error"),
                    "evaluation_error_type": rec.get("evaluation_error_type"),
                }

                write_raw_result(final_rec)
                logger.info("Wrote result for q%s condition=%s", qid, condition)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
