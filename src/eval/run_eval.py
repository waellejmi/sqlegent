from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.eval.eval_helpers import (
    get_analysis_status,
    pick_preview_rows,
    slug_model,
    strip_sql_limit,
    write_raw_result,
)
from src.eval.harness import (
    compare_rows,
    execute_sqlite_query,
    execution_accuracy_official,
    load_dataset,
    normalize_value_for_compare,
    serialize_rows_for_judge,
    soft_f1,
    stratified_sample,
    write_manifest,
)
from utils.logger_setup import LoggerSetup

logger = LoggerSetup.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


RESULTS_DIR = ROOT / "evaluation" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_N = 3


def save_runtime_settings_patch(patch: dict[str, Any]):
    try:
        from config.app_config import AppConfig

        AppConfig().save_eval_runtime_settings(patch)
        return
    except Exception:
        pass

    eval_path = ROOT / ".app_config" / "eval_settings.json"
    data = {}

    if eval_path.exists():
        try:
            data = json.loads(eval_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    if not isinstance(data, dict):
        data = {}

    data.update(patch)
    eval_path.parent.mkdir(parents=True, exist_ok=True)
    eval_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def reset_database_tools():
    try:
        import tools.database as database_tools
    except Exception:
        return

    if hasattr(database_tools, "_active_database_uri"):
        database_tools._active_database_uri = ""

    for attr in ("_db", "_get_schema_tool", "_run_query_tool"):
        if hasattr(database_tools, attr):
            setattr(database_tools, attr, None)


def set_sqlite_database(db_file: Path, warn_on_failure: bool = False) -> str | None:
    try:
        from config.db_config import DBConfig

        db_config = DBConfig()
        previous_uri = None

        try:
            previous_uri = db_config.get_database_uri()
        except Exception:
            previous_uri = None

        db_config.set_database_uri(db_config.sqlite_path_to_uri(db_file))
        reset_database_tools()
        return previous_uri
    except Exception as exc:
        if warn_on_failure:
            logger.warning("Could not set DBConfig to sqlite uri: %s", exc)
        return None


def restore_database(previous_uri: str | None):
    if not previous_uri:
        return

    try:
        from config.db_config import DBConfig

        DBConfig().set_database_uri(previous_uri)
        reset_database_tools()
    except Exception:
        pass


def reset_context_service():
    try:
        import context_layer.service as context_service

        if hasattr(context_service, "_context_service"):
            context_service._context_service = None
    except Exception:
        pass


def remove_path(path: Path):
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def cleanup_with_evidence(question_id: int, db_id: str):
    try:
        from config.app_config import AppConfig

        cfg = AppConfig()
        remove_path(cfg.MDL_DIR / f"eval_q{question_id}_{db_id}.yaml")
        remove_path(Path(cfg.CONTEXT_STORE_PATH))
    except Exception:
        pass

    shutil.rmtree(RESULTS_DIR / "staged_mdl", ignore_errors=True)


async def invoke_agent(question: str, timeout: int = 120) -> dict[str, Any]:
    from app.agent_runtime import run_agent_with_interrupt
    from app.state_factory import build_initial_state, make_runnable_config
    from config.app_config import AppConfig

    checkpoint_path = AppConfig().ROOT_DIR / ".app_cache" / "checkpoints.sqlite"
    remove_path(checkpoint_path)

    initial_state = build_initial_state(question)
    config = make_runnable_config()

    async def interrupt_handler(_info: Any) -> dict:
        return {}

    start = time.time()
    final_state = None
    error = None

    try:
        _, final_state = await asyncio.wait_for(
            run_agent_with_interrupt(
                input_state=initial_state,
                config=config,
                interrupt_handler=interrupt_handler,
                on_message=None,
                on_transition=None,
            ),
            timeout=timeout,
        )
    except Exception as exc:
        error = str(exc)

    latency_ms = int((time.time() - start) * 1000)

    if error is not None or final_state is None:
        return {
            "last_query": None,
            "db_output": None,
            "analysis_result": None,
            "skip_decision": None,
            "skip_pipeline_fired": None,
            "agent_answer": None,
            "retries": 0,
            "latency_ms": latency_ms,
            "error": error or "agent produced no final state",
        }

    values = getattr(final_state, "values", {}) or {}

    last_query = values.get("last_query")
    db_output = values.get("db_output")
    skip_decision = values.get("skip_decision")
    retry_count = values.get("retry_count") or 0
    final_answer = values.get("final_answer")

    agent_answer = None
    if isinstance(final_answer, str) and final_answer.strip():
        agent_answer = final_answer.strip()

    skip_pipeline_fired = None
    if skip_decision is not None:
        if isinstance(skip_decision, dict):
            skip_pipeline_fired = bool(skip_decision.get("skip", False))
        else:
            skip_pipeline_fired = bool(getattr(skip_decision, "skip", False))

    analysis_result = values.get("analysis_result")
    if analysis_result is not None and not isinstance(analysis_result, dict):
        analysis_result = {
            "status": getattr(analysis_result, "status", None),
            "explanation": getattr(analysis_result, "explanation", None),
        }

    return {
        "last_query": last_query,
        "db_output": db_output,
        "analysis_result": analysis_result,
        "skip_decision": skip_decision,
        "skip_pipeline_fired": skip_pipeline_fired,
        "agent_answer": agent_answer,
        "retries": retry_count,
        "latency_ms": latency_ms,
        "error": None,
    }


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

    for logger_name in (
        "httpx",
        "transformers",
        "huggingface_hub",
        "urllib3",
        "hf_hub",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    dataset_path = Path(args.dataset)
    db_root = Path(args.database_root)
    questions = load_dataset(dataset_path)

    run_sample_size = args.sample_size
    run_seed = args.seed

    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        selected_ids = manifest.get("selected_question_ids", [])
        run_manifest_data = manifest
        run_sample_size = int(manifest.get("sample_size", run_sample_size))
        run_seed = int(manifest.get("seed", run_seed))
    else:
        selected_ids = stratified_sample(questions, args.sample_size, args.seed)
        run_manifest_data = {
            "dataset_path": str(dataset_path),
            "database_root": str(db_root),
            "sample_size": args.sample_size,
            "seed": args.seed,
            "selected_question_ids": selected_ids,
            "run_order": "sequential_a_then_b",
        }

    from config.app_config import AppConfig

    timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    requested_model = AppConfig().LLM_ACTIVE_MODEL

    run_base = (
        f"{run_sample_size}Q_{run_seed}S_{slug_model(requested_model)}_{timestamp}"
    )
    runs_dir = RESULTS_DIR / "runs"
    manifests_dir = RESULTS_DIR / "manifests"
    runs_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    raw_results_path = runs_dir / f"{run_base}.jsonl"
    manifest_path = manifests_dir / f"{run_base}_manifest.json"
    raw_results_path.unlink(missing_ok=True)

    if args.manifest:
        manifest_path.write_text(
            json.dumps(run_manifest_data or {}, indent=2),
            encoding="utf-8",
        )
    else:
        write_manifest(
            str(dataset_path),
            str(db_root),
            selected_ids,
            manifest_path,
            args.sample_size,
            args.seed,
        )

    logger.info("Run results file: %s", raw_results_path)
    logger.info("Run manifest file: %s", manifest_path)

    qmap = {q.question_id: q for q in questions}

    async def _run():
        for qid in selected_ids:
            q = qmap.get(qid)
            if not q:
                logger.warning("Missing question %s", qid)
                continue

            db_file = db_root / q.db_id / f"{q.db_id}.sqlite"

            try:
                rows, cols = execute_sqlite_query(db_file, q.SQL)
                raw_ref_rows = [tuple(r) for r in rows]
                ref_rows, _ = serialize_rows_for_judge(rows, columns=cols)
            except Exception as exc:
                logger.error("Gold SQL execution failed for q%s: %s", qid, exc)
                continue

            for condition in ("without_evidence", "with_evidence"):
                logger.info("Running q%s condition=%s", qid, condition)

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

                    tmp_out = RESULTS_DIR / "staged_mdl"
                    tmp_out.mkdir(parents=True, exist_ok=True)

                    script = ROOT / "tools" / "evidence_to_mdl.py"
                    evidence_text = json.dumps(q.evidence) if q.evidence else ""

                    cmd = [
                        str(script),
                        "--question-id",
                        str(qid),
                        "--db-id",
                        q.db_id,
                        "--question",
                        q.question,
                        "--evidence-text",
                        evidence_text,
                        "--out-dir",
                        str(tmp_out),
                    ]

                    try:
                        subprocess.check_output(cmd)
                    except Exception as exc:
                        logger.error(
                            "Failed to create evidence YAML for q%s: %s", qid, exc
                        )
                        continue

                    staged = list(tmp_out.glob(f"eval_q{qid}_*.yaml"))
                    if not staged:
                        logger.warning("No staged YAML produced for q%s", qid)
                    else:
                        cfg = AppConfig()
                        dest = cfg.MDL_DIR / staged[0].name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(staged[0], dest)

                        previous_evidence_uri = set_sqlite_database(
                            db_file, warn_on_failure=True
                        )
                        reset_context_service()

                        try:
                            from app.context_ops import run_context_reindex

                            run_context_reindex(None)
                        except Exception as exc:
                            logger.warning(
                                "Context reindex failed, continuing without reindex: %s",
                                exc,
                            )

                        restore_database(previous_evidence_uri)

                previous_agent_uri = set_sqlite_database(db_file)
                start = time.time()

                try:
                    agent_result = await invoke_agent(
                        q.question, timeout=args.agent_timeout
                    )
                    duration = int((time.time() - start) * 1000)
                except Exception as exc:
                    duration = int((time.time() - start) * 1000)
                    agent_result = {"error": str(exc), "latency_ms": duration}
                finally:
                    restore_database(previous_agent_uri)

                if condition == "with_evidence":
                    cleanup_with_evidence(qid, q.db_id)

                analysis_status = get_analysis_status(
                    agent_result.get("analysis_result")
                    if isinstance(agent_result, dict)
                    else None
                )

                agent_rows_full = None
                agent_cols = None
                execution_correct = None
                official_execution_correct = None
                soft_f1_result = None
                evaluation_error_type = None

                try:
                    if analysis_status == "success":
                        last_query = (
                            agent_result.get("last_query")
                            if isinstance(agent_result, dict)
                            else None
                        )

                        if last_query and AppConfig().EXECUTE_SQL_QUERIES:
                            unlimited_sql, limit_error = strip_sql_limit(last_query)
                            if limit_error:
                                evaluation_error_type = limit_error

                            try:
                                a_rows, a_cols = execute_sqlite_query(
                                    db_file, unlimited_sql
                                )
                                agent_rows_full = [tuple(r) for r in a_rows]
                                agent_cols = a_cols or []
                            except Exception as exc:
                                evaluation_error_type = (
                                    f"sql_reexecution_failure: {exc}"
                                )
                                agent_rows_full = None
                        elif agent_result.get("db_output"):
                            try:
                                db_output = agent_result.get("db_output")
                                parsed = (
                                    json.loads(db_output)
                                    if isinstance(db_output, str)
                                    else db_output
                                )

                                if isinstance(parsed, list):
                                    agent_rows_full = [tuple(r) for r in parsed]
                                    agent_cols = None
                            except Exception as exc:
                                evaluation_error_type = (
                                    f"agent_db_output_parse_error: {exc}"
                                )
                                agent_rows_full = None

                    if agent_rows_full is not None:
                        try:
                            execution_correct = compare_rows(
                                agent_rows_full,
                                agent_cols or [],
                                raw_ref_rows,
                                cols or [],
                            )
                        except Exception as exc:
                            evaluation_error_type = f"comparator_error: {exc}"
                            execution_correct = None

                        try:
                            official_execution_correct = execution_accuracy_official(
                                agent_rows_full,
                                raw_ref_rows,
                            )
                        except Exception as exc:
                            logger.warning(
                                "execution_accuracy_official computation failed for q%s: %s",
                                qid,
                                exc,
                            )
                            official_execution_correct = None

                        try:
                            soft_f1_result = soft_f1(agent_rows_full, raw_ref_rows)
                        except Exception as exc:
                            logger.warning(
                                "soft_f1 computation failed for q%s: %s", qid, exc
                            )
                            soft_f1_result = None
                except Exception as exc:
                    evaluation_error_type = f"comparator_error: {exc}"
                    agent_rows_full = None
                    agent_cols = None
                    execution_correct = None
                    official_execution_correct = None
                    soft_f1_result = None

                gold_total_rows = len(ref_rows or [])
                gold_value_counts_preview = None

                if (cols and len(cols) == 1) or (
                    not cols and ref_rows and len(ref_rows[0]) == 1
                ):
                    gold_counts = Counter(
                        normalize_value_for_compare(row[0]) for row in ref_rows or []
                    )
                    gold_value_counts_preview = [
                        {"value": value, "count": count}
                        for value, count in gold_counts.most_common(PREVIEW_N)
                    ]

                gold_db_preview = [
                    list(row) for row in pick_preview_rows(ref_rows or [], PREVIEW_N)
                ]

                agent_db_preview = None
                agent_db_total_rows = None
                agent_value_counts_preview = None

                if agent_rows_full is not None:
                    try:
                        sorted_agent_rows, _ = serialize_rows_for_judge(
                            agent_rows_full,
                            columns=agent_cols,
                        )
                    except Exception:
                        sorted_agent_rows = agent_rows_full

                    agent_db_total_rows = len(agent_rows_full)

                    if cols and len(cols) == 1 and agent_cols:
                        gold_counts = Counter(
                            normalize_value_for_compare(row[0])
                            for row in ref_rows or []
                        )

                        best_col = None
                        best_score = -1

                        for col_index in range(len(agent_cols)):
                            agent_counts = Counter(
                                normalize_value_for_compare(row[col_index])
                                for row in agent_rows_full
                            )
                            score = sum(
                                min(agent_counts[value], gold_counts.get(value, 0))
                                for value in agent_counts
                            )

                            if score > best_score:
                                best_score = score
                                best_col = col_index

                        if best_col is not None:
                            agent_counts = Counter(
                                normalize_value_for_compare(row[best_col])
                                for row in agent_rows_full
                            )
                            agent_value_counts_preview = [
                                {"value": value, "count": count}
                                for value, count in agent_counts.most_common(PREVIEW_N)
                            ]

                    agent_db_preview = [
                        list(row)
                        for row in pick_preview_rows(sorted_agent_rows, PREVIEW_N)
                    ]

                final_rec = {
                    "question_id": qid,
                    "db_id": q.db_id,
                    "difficulty": q.difficulty,
                    "condition": condition,
                    "question": q.question,
                    "run_sample_size": run_sample_size,
                    "run_seed": run_seed,
                    "run_model_requested": requested_model,
                    "run_file": raw_results_path.name,
                    "gold_sql": q.SQL,
                    "gold_db_preview": gold_db_preview,
                    "gold_db_total_rows": gold_total_rows,
                    "gold_value_counts_preview": gold_value_counts_preview,
                    "agent_answer": analysis_status,
                    "agent_last_query": (
                        agent_result.get("last_query")
                        if isinstance(agent_result, dict)
                        else None
                    ),
                    "agent_db_preview": agent_db_preview,
                    "agent_db_total_rows": agent_db_total_rows,
                    "agent_value_counts_preview": agent_value_counts_preview,
                    "execution_accuracy_official": official_execution_correct,
                    "column_superset_match": execution_correct,
                    "soft_f1_precision": (
                        soft_f1_result.get("precision") if soft_f1_result else None
                    ),
                    "soft_f1_recall": (
                        soft_f1_result.get("recall") if soft_f1_result else None
                    ),
                    "soft_f1_score": (
                        soft_f1_result.get("f1") if soft_f1_result else None
                    ),
                    "skip_pipeline_fired": (
                        agent_result.get("skip_pipeline_fired")
                        if isinstance(agent_result, dict)
                        else None
                    ),
                    "retries": (
                        agent_result.get("retries")
                        if isinstance(agent_result, dict)
                        else None
                    ),
                    "latency_ms": (
                        agent_result.get("latency_ms")
                        if isinstance(agent_result, dict)
                        else duration
                    ),
                    "error": (
                        agent_result.get("error")
                        if isinstance(agent_result, dict)
                        else None
                    ),
                    "evaluation_error_type": evaluation_error_type,
                }

                write_raw_result(final_rec, raw_results_path)
                logger.info("Wrote result for q%s condition=%s", qid, condition)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
