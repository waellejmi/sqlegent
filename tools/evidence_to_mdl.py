#!/usr/bin/env python3
"""
Generate a semantic YAML file (instruction channel) for a single question's evidence.
Usage:
  tools/evidence_to_mdl.py --question-id 123 --db-id financial \
    --question "What is X?" --evidence-file path/to/evidence.txt --out-dir /tmp/eval_mdl

Outputs: {out_dir}/eval_q{question_id}_{db_id}.yaml
"""
import argparse
from pathlib import Path
import json


def load_evidence_text(args):
    if args.evidence_text:
        return args.evidence_text
    if args.evidence_file:
        p = Path(args.evidence_file)
        if not p.exists():
            raise SystemExit(f"Evidence file not found: {p}")
        return p.read_text(encoding="utf-8")
    return ""


def build_payload(question_id, db_id, question_text, evidence_text):
    instr = {
        "id": f"eval_q{question_id}",
        "scope": "instruction",
        "is_default": False,
        "question": question_text or "",
        "instruction": evidence_text or "",
    }
    payload = {
        "models": [],
        "relationships": [],
        "instructions": [instr],
    }
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--db-id", required=True)
    parser.add_argument("--question", dest="question_text", default="")
    parser.add_argument("--evidence-text", dest="evidence_text", default="")
    parser.add_argument("--evidence-file", dest="evidence_file", default=None)
    parser.add_argument("--out-dir", dest="out_dir", default="/tmp/eval_mdl")
    args = parser.parse_args()

    evidence_text = load_evidence_text(args)

    payload = build_payload(args.question_id, args.db_id, args.question_text, evidence_text)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"eval_q{args.question_id}_{args.db_id}.yaml"

    try:
        import yaml
    except Exception:
        # Fallback: write a simple YAML-like serialization if pyyaml unavailable
        content_lines = ["models: []", "relationships: []", "instructions:"]
        instr = payload["instructions"][0]
        content_lines.append("  - id: %s" % instr["id"])
        content_lines.append("    scope: %s" % instr["scope"])
        content_lines.append("    is_default: %s" % str(instr["is_default"]).lower())
        content_lines.append("    question: |\n      %s" % (instr["question"].replace("\n", "\n      ")))
        content_lines.append("    instruction: |\n      %s" % (instr["instruction"].replace("\n", "\n      ")))
        out_path.write_text("\n".join(content_lines), encoding="utf-8")
        print(out_path)
        return

    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)

    print(out_path)

if __name__ == "__main__":
    main()
