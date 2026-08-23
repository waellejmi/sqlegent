#!/usr/bin/env python3
"""
CI regression gate. Compares a current summary against a baseline and fails
(non-zero exit) if any metric regressed beyond the allowed threshold.

Usage:
    python compare_summaries.py --baseline baseline_summary.json --current current_summary.json --max-drop 3.0
"""

import argparse
import json
import sys

METRICS = ["ex_official_accuracy", "soft_ex_accuracy", "soft_f1_mean"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True)
    p.add_argument("--current", required=True)
    p.add_argument(
        "--max-drop",
        type=float,
        default=3.0,
        help="Max allowed drop in percentage points before failing",
    )
    args = p.parse_args()

    baseline = json.load(open(args.baseline))["conditions"]
    current = json.load(open(args.current))["conditions"]

    failed = False
    for condition in current:
        if condition not in baseline:
            print(f"SKIP: {condition} not present in baseline")
            continue
        for metric in METRICS:
            base_val = baseline[condition].get(metric, 0.0) * 100
            cur_val = current[condition].get(metric, 0.0) * 100
            delta = cur_val - base_val
            status = "REGRESSION" if delta < -args.max_drop else "ok"
            print(
                f"{condition:20} {metric:25} baseline={base_val:.2f}%  current={cur_val:.2f}%  delta={delta:+.2f}pp  [{status}]"
            )
            if status == "REGRESSION":
                failed = True

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
