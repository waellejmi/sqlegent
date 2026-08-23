import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_records(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Malformed JSON on line {line_num} of {path}: {e}")
    return records


def save_summary(scores_by_condition, jsonl_path, out_path):
    summary = {
        "source_file": str(jsonl_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conditions": scores_by_condition,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return out_path


AGENT_DECLINE_VALUES = {
    "irrelevant"
}  # agent_answer values treated as a genuine failure to
# answer, not a harness error — scored as incorrect,
# kept in the denominator. Extend this set if the agent
# uses other decline/give-up statuses.


def compute_scores(records, untagged_ids=None, declined_ids=None):
    """
    Returns a dict with:
      total: total record count
      tagged_errors: count of records with a non-null evaluation_error_type
      untagged_errors: count of records where evaluation_error_type is null, agent_answer is
                        NOT a known decline value, but every metric field is still null — i.e.
                        the comparator never ran and the harness failed to record why. Excluded
                        from evaluated, since this is a harness bug, not an agent failure.
      agent_declined: count of records where agent_answer is in AGENT_DECLINE_VALUES (e.g.
                       "irrelevant") — the agent chose not to answer a question that has a
                       real answer. This IS a genuine NL2SQL failure and stays IN the evaluated
                       denominator, scored as incorrect (0) across all three metrics.
      evaluated: total - tagged_errors - untagged_errors (agent_declined is included here)
      ex_official / soft_ex / soft_f1: as before, with declined records contributing 0.
    """
    total = len(records)
    tagged_errors = 0
    untagged_errors = 0
    agent_declined = 0

    ex_sum = 0
    soft_ex_sum = 0
    soft_f1_sum = 0.0
    evaluated = 0

    for r in records:
        if r.get("evaluation_error_type"):
            tagged_errors += 1
            continue

        answer = r.get("agent_answer")
        declined = (
            isinstance(answer, str) and answer.strip().lower() in AGENT_DECLINE_VALUES
        )

        ex = r.get("execution_accuracy_official")
        soft_ex = r.get("column_superset_match")
        f1 = r.get("soft_f1_score")

        if declined:
            agent_declined += 1
            if declined_ids is not None:
                declined_ids.append(r.get("question_id", "?"))
            evaluated += 1
            # scored as incorrect: contributes 0 to ex_sum, soft_ex_sum, soft_f1_sum
            continue

        if ex is None and soft_ex is None and f1 is None:
            untagged_errors += 1
            if untagged_ids is not None:
                untagged_ids.append(r.get("question_id", "?"))
            continue

        evaluated += 1
        if ex is not None:
            ex_sum += int(ex)
        if soft_ex is not None:
            soft_ex_sum += 1 if soft_ex else 0
        if f1 is not None:
            soft_f1_sum += float(f1)

    return {
        "total": total,
        "tagged_errors": tagged_errors,
        "untagged_errors": untagged_errors,
        "agent_declined": agent_declined,
        "evaluated": evaluated,
        "ex_official_accuracy": (ex_sum / evaluated) if evaluated else 0.0,
        "soft_ex_accuracy": (soft_ex_sum / evaluated) if evaluated else 0.0,
        "soft_f1_mean": (soft_f1_sum / evaluated) if evaluated else 0.0,
    }


def print_block(label, scores):
    print(f"\n{label}")
    print("-" * len(label))
    print(f"  Total entries:       {scores['total']}")
    print(
        f"  Tagged errors:       {scores['tagged_errors']}  (evaluation_error_type set, excluded)"
    )
    print(
        f"  Untagged errors:     {scores['untagged_errors']}  (all metrics null, no error type — harness bug, excluded)"
    )
    print(
        f"  Agent declined:      {scores['agent_declined']}  (agent_answer='irrelevant' etc — scored as incorrect, included)"
    )
    print(f"  Evaluated (denom):   {scores['evaluated']}")
    print(f"  EX accuracy (official):      {scores['ex_official_accuracy'] * 100:.2f}%")
    print(f"  Soft EX (column-superset):   {scores['soft_ex_accuracy'] * 100:.2f}%")
    print(f"  Soft F1 (mean):               {scores['soft_f1_mean']:.4f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl_path", help="Path to the results JSONL file")
    parser.add_argument(
        "--save-summary",
        help="Path to write a compact aggregate summary JSON, for CI regression gating",
    )
    parser.add_argument(
        "--by-condition",
        action="store_true",
        help="Also break down scores by 'condition' field",
    )
    parser.add_argument(
        "--by-difficulty",
        action="store_true",
        help="Also break down scores by 'difficulty' field",
    )
    args = parser.parse_args()

    records = load_records(args.jsonl_path)
    if not records:
        print(f"No records found in {args.jsonl_path}")
        return

    print(f"Source: {args.jsonl_path}")
    untagged_ids = []
    declined_ids = []
    print_block("Overall", compute_scores(records, untagged_ids, declined_ids))

    if declined_ids:
        print(
            f"\n  NOTE: {len(declined_ids)} record(s) had agent_answer='irrelevant' (or "
            f"another decline value). Counted as INCORRECT, included in the denominator. "
            f"question_ids: {declined_ids}"
        )

    if untagged_ids:
        print(
            f"\n  WARNING: {len(untagged_ids)} record(s) had no evaluation_error_type, "
            f"agent_answer was not a known decline value, and no computed metrics — "
            f"comparator likely never ran. Excluded from all denominators. "
            f"question_ids: {untagged_ids}"
        )
        print(
            "  These are harness bugs, not scored incorrect answers — fix the harness to "
            "tag them with an evaluation_error_type so this warning stops firing."
        )

    if args.save_summary:
        groups = defaultdict(list)
        for r in records:
            groups[r.get("condition", "unknown")].append(r)
        by_condition = {k: compute_scores(v) for k, v in groups.items()}
        out = save_summary(by_condition, args.jsonl_path, args.save_summary)
        print(f"\nSummary written to {out}")

    if args.by_condition:
        groups = defaultdict(list)
        for r in records:
            groups[r.get("condition", "unknown")].append(r)
        for key in sorted(groups.keys()):
            print_block(f"Condition: {key}", compute_scores(groups[key]))

    if args.by_difficulty:
        groups = defaultdict(list)
        for r in records:
            groups[r.get("difficulty", "unknown")].append(r)
        for key in sorted(groups.keys()):
            print_block(f"Difficulty: {key}", compute_scores(groups[key]))


if __name__ == "__main__":
    main()
