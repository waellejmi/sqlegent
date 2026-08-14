# CLAUDE.md — BIRD Mini-Dev Evaluation Harness for sql-agent

You are building a reproducible evaluation harness for the `sql-agent` NL2SQL pipeline. This
file is the complete spec. Read `semantic/README.md` and `src/config/app_config.py` before
writing any code — this file does not repeat what's already documented there.

## Objective

Measure answer accuracy of the NL2SQL agent on BIRD Mini-Dev under two conditions, using the
same 100 sampled questions for both:

- **Condition A (`without_evidence`)**: normal agent, semantic/context layer off, BIRD
  `evidence` field never provided.
- **Condition B (`with_evidence`)**: BIRD `evidence` converted into semantic-layer YAML, context
  layer on, same questions.

Also compute execution accuracy (deterministic comparison of raw query results against gold SQL
output) for both conditions, independent of the LLM judge. Report both metrics.

## Dataset

```
evaluation/MINIDEV/
├── dev_databases/<db_id>/<db_id>.sqlite
├── dev_tables.json
├── mini_dev_sqlite_gold.sql
└── mini_dev_sqlite.json
```

Load questions from `mini_dev_sqlite.json`. Fields per question: `question_id`, `db_id`,
`question`, `evidence`, `SQL`, `difficulty`. Never modify any file under `evaluation/MINIDEV/`.
Never send `evidence` (Condition A) or `SQL` (either condition) to the agent.

## Sampling

Stratified random sample by `db_id` and `difficulty`, seed `42`, sample size configurable
(default 100). Persist selected `question_id`s to `evaluation/results/manifest.json`. A rerun
using the saved manifest must not perform new random selection — load the IDs directly.

## Config

Edit `src/config/app_config.py` defaults / `settings.json` directly (no production concerns,
in-place edits are fine). Confirm the following state before running — some of these are already
set:

```
ASK_RESULT_CONFIRMATION     = 0     # must be 0, otherwise blocks on stdin per question
HUMAN_SQL_REVIEW             = 0
METADATA_CACHE_ENABLED       = 0     # same value both conditions, no exceptions
EXECUTE_SQL_QUERIES          = 1
ENABLE_ORCHESTRATOR          = false
ENABLE_INSTRUCTION_CONTEXT   = 0     # both conditions — not the variable under test
ENABLE_QUERY_MEMORY          = 0     # both conditions — recalls prior verified queries,
                                       # a separate confound from semantic evidence
ENABLE_FAILED_QUERY_LOG      = 0
LOG_JSON                     = 1
LOG_REQUESTS                 = 1
LOG_MAX_CHARS                = 20000  # raise from default, truncation hides eval failures
LOG_RESPONSE_MAX_CHARS       = 20000
```

Docker auto-discovery: disabled, already handled, no action needed.

Per condition:

```
Condition A: ENABLE_CONTEXT_LAYER = 0   (full disable)
Condition B: ENABLE_CONTEXT_LAYER = 1
             ENABLE_SCHEMA_CONTEXT = 1
             CONTEXT_PROJECT_ID = unique per question_id, e.g. f"eval_q{question_id}"
             CONTEXT_STORE_PATH = fresh temp sqlite file, one per question, deleted after
```

Before wiring Condition B: read `src/context_layer/`'s chunking/RAG implementation and confirm
(a) `CONTEXT_PROJECT_ID` actually scopes retrieval at the vector-search level, not just as a
label, and (b) what happens when `CONTEXT_REQUIRE_SEMANTIC_PROFILE=1` and no profile matches the
current `db_id` — does it hard-fail or fall back to `CONTEXT_DEFAULT_SEMANTIC_PROFILE`? If it
falls back silently, patch it to hard-fail for the eval run, or every non-matching `db_id` will
produce a result under the wrong (or no-op) semantic profile with no error raised.

Per `semantic/README.md`'s documented structure: write each question's generated YAML to a
scratch path outside `MDL_DIR`, stage only that one file in before invoking the agent, trigger
whatever indexing step normally runs on startup (auto-index is off, so this must be called
explicitly), then remove the staged file before the next question. `MDL_FILE_GLOB` is recursive
— anything left in `MDL_DIR` from a previous question on the same `db_id` will be picked up by
baseline regeneration for the next question. This is the leakage channel to prevent.

## Agent invocation

Invoke programmatically via whatever entrypoint `src/app/` exposes for a single fresh
question-in / answer-out call (not `src/webui/main.py`, not chat mode). Every call must use a
new LangGraph thread/session with no reused checkpointer state. Capture per call:

- final answer (`explain_result` output)
- raw `run_query` result rows
- node history (specifically whether `skip_pipeline` fired)
- retry count, latency, token usage, any error

## Gold SQL / reference result

Execute gold SQL directly against the SQLite file for the question. This produces:
1. `reference_rows` — used for the execution-accuracy comparator.
2. `reference_text` — a deterministic serialization of the same rows, used as judge input.

Serialization rule (apply identically everywhere, both conditions): sort rows by all columns
ascending, round floats to 4 decimal places, cap at 50 rows in the judge-facing text with an
explicit `"... N more rows"` note if truncated. Gold SQL is never sent to the agent.

## Execution accuracy (deterministic, no LLM)

Compare `agent_raw_rows` to `reference_rows`: round floats to 4 decimal places, normalize each
row to a tuple, compare as multisets (row order not significant — verify this assumption against
BIRD's official eval script if available; if it treats order as significant for any query type,
flag it, don't silently assume). Output `execution_correct: true/false`. If the agent produced no
SQL or execution failed, record `evaluation_error`, not `false`.

## LLM judge

The judge server is already running and owned outside this harness. The harness only needs to
call it. Do not add code to start, stop, or manage the server process.

Endpoint the harness calls, once per (question, condition):

```
POST http://127.0.0.1:8080/v1/chat/completions
Content-Type: application/json

{
  "model": "local",
  "temperature": 0,
  "top_p": 0,
  "messages": [
    {
      "role": "system",
      "content": "You are evaluating the output of a natural-language-to-SQL (NL2SQL) agent. The agent was given a question about a database, generated and executed SQL against it, and produced a natural-language answer. You are given: the original question, a reference result (computed by executing the correct, ground-truth SQL query directly against the same database), and the agent's natural-language answer. Judge whether the agent's answer correctly and completely conveys the same factual content as the reference result. Differences in phrasing, formatting, units notation, row/column ordering, or added context do not make an answer incorrect, as long as the core facts match. Missing a required value, stating a wrong value, or contradicting the reference result makes the answer incorrect. Respond with exactly one word: YES if the agent's answer correctly conveys the reference result, or NO if it does not. Do not explain your reasoning. Do not output anything other than YES or NO."
    },
    {
      "role": "user",
      "content": "Question: {question}\nReference result: {reference_text}\nAgent answer: {agent_answer}"
    }
  ]
}
```

Response: read `choices[0].message.content`, strip whitespace, uppercase. Accept only exact
`"YES"` or `"NO"`. Anything else — extra text, empty, HTTP error, timeout — is
`evaluation_error`, type `malformed_judge_output` or `judge_api_failure`. Never map malformed
output to `NO`.

Optional robustness: `llama-server` supports GBNF grammar-constrained decoding via a `grammar`
field in the request body. If available for the judge model in use, add a grammar restricting
output to the literal tokens `YES` or `NO`. This removes most malformed-output cases at the
decoding level rather than relying only on a post-hoc string check. Keep the string check
regardless, as the fallback for cases where grammar constraint isn't in effect.

**Implementation:** a single stateless function, `call_judge(question, reference_text,
agent_answer) -> "YES" | "NO" | EvaluationError`, built with a plain HTTP client
(`requests`/`httpx`). Do not implement this as a LangGraph node or graph — there is no state to
manage, no branching, no multi-step control flow, it is one request and one constrained token
back. Do not use LangChain's `with_structured_output` for this either — it depends on the target
model/server supporting OpenAI-style tool calling, which is inconsistent across `llama-server`
builds and judge models, and if unsupported it silently falls back to prompt-based coercion
anyway, which is what the plain prompt above already does, just hidden behind a harder-to-debug
abstraction. The plain HTTP call is simpler, easier to unit-test in isolation, and easier to
defend when explaining the eval design.

Each call is independent: no session ID, no conversation carryover between questions. The full
system + user message is sent fresh every time, exactly as shown above.

Use a judge model different from whatever powers the agent. Log every request/response pair to
`evaluation/results/judge_calls.jsonl`.

## Per-question flow

```
for question in manifest.selected_questions:
    reference_rows = execute_gold_sql(question.SQL, db_path(question.db_id))
    reference_text = serialize(reference_rows)

    for condition in ["without_evidence", "with_evidence"]:
        if condition == "with_evidence":
            yaml = evidence_to_semantic_yaml(question.evidence, question.db_id)  # scripted
                                                                                   # conversion,
                                                                                   # not manual
            stage(yaml, question.db_id)
            reindex_context_layer()

        result = invoke_agent_fresh(question.question, db_path(question.db_id), condition_config)

        if condition == "with_evidence":
            unstage(question.db_id)
            delete_context_store_file()

        exec_correct = compare_rows(result.raw_rows, reference_rows)
        judge = call_judge(question.question, reference_text, result.final_answer)

        write_record(question, condition, result, reference_text, exec_correct, judge)
```

## Results record

`evaluation/results/raw_results.jsonl`, one line per (question, condition):

```json
{
  "question_id": 120,
  "db_id": "financial",
  "difficulty": "moderate",
  "condition": "with_evidence",
  "question": "...",
  "agent_answer": "...",
  "reference_result": "...",
  "judge": "YES",
  "execution_correct": true,
  "skip_pipeline_fired": false,
  "retries": 0,
  "latency_ms": 1234,
  "token_usage": {"prompt": 0, "completion": 0},
  "error": null,
  "evaluation_error_type": null
}
```

`evaluation_error_type` enum: `missing_database`, `missing_question`, `agent_execution_failure`,
`semantic_config_failure`, `judge_api_failure`, `malformed_judge_output`, `sql_execution_failure`.

## Summary

`evaluation/results/summary.json`. Per condition: sample size, seed, correct/incorrect/error
counts, answer accuracy (`YES / judged`), execution accuracy (`execution_correct / evaluated`).
Absolute improvement (`accuracy_with − accuracy_without`) for both metrics.

Paired outcomes, computed separately for answer accuracy and execution accuracy:

```
improved:            without=NO,  with=YES
unchanged_correct:   without=YES, with=YES
unchanged_incorrect: without=NO,  with=NO
regressed:           without=YES, with=NO
```

McNemar's test on the answer-accuracy paired outcomes: `b = regressed`, `c = improved`. If
`b + c >= 25`, use `(|b − c| − 1)^2 / (b + c)` as chi-square with 1 degree of freedom. If
`b + c < 25`, use the exact binomial test on `b` vs `c` with p=0.5. Report the p-value alongside
the raw percentage-point delta.

Also report: `skip_pipeline` fire rate per condition (surface separately if it differs
meaningfully between A and B — that's a confound, not noise to average out).

## Manifest (`evaluation/results/manifest.json`)

```json
{
  "dataset_path": "evaluation/MINIDEV/mini_dev_sqlite.json",
  "database_root": "evaluation/MINIDEV/dev_databases",
  "sample_size": 100,
  "seed": 42,
  "selected_question_ids": [...],
  "agent_git_commit": "...",
  "judge_model": "...",
  "judge_endpoint": "http://127.0.0.1:8080/v1/chat/completions",
  "condition_a_config": { ... resolved config ... },
  "condition_b_config": { ... resolved config ... },
  "run_order": "sequential_a_then_b | interleaved_per_question",
  "timestamp": "..."
}
```

## CLI

```
--sample-size INT      (default 100)
--seed INT              (default 42)
--condition             {without_evidence, with_evidence, both}
--judge-model STR
--judge-base-url STR    (default http://127.0.0.1:8080)
```

`both` runs the exact same manifest under both conditions. Fail loudly on: missing database,
missing question, invalid SQLite file, agent execution failure, semantic config failure, judge
API failure, malformed judge output. `evaluation_error` is never silently converted to
`incorrect`.

## Implementation order

1. Manifest generation. Confirm exact reproducibility (same seed → same IDs) before anything
   else.
2. Gold SQL execution + serialization + execution-accuracy comparator. No agent, no judge
   dependency — get this exactly right first.
3. Judge client against the running `llama-server`, tested standalone on a handful of known
   YES/NO pairs before wiring into the harness.
4. Condition A agent path (context layer fully off — simplest case).
5. Condition B agent path — only after confirming `CONTEXT_PROJECT_ID` scoping and semantic
   profile fallback behavior in `src/context_layer/` directly.
6. Full harness, CLI, summary generation, McNemar's test.
