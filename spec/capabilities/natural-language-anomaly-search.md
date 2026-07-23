# Natural-Language Anomaly Search

## What It Does
Accepts a free-text question from an officer, plans the analytic intent, generates a validated SQL query against the operational MsSQL database, executes it, detects anomalies in the result, and returns a plain-English answer with 1–2 suggested follow-up questions.

## Inputs
- `question` (str) — raw natural-language question from the officer
- `schema_summary` (str) — introspected DB schema cached at startup

## Outputs
- `answer` (str) — 1–3 sentence plain-English summary with key numbers and anomaly highlights
- `sql` (str) — the SELECT query that was actually executed
- `rows` (list[dict]) — result set (up to 1000 rows)
- `columns` (list[str]) — column names
- `anomalies` (list[dict]) — top 3 outliers/flags with `{field, label, value, severity}`
- `followups` (list[str]) — 1–2 suggested next questions
- `steps` (list[dict]) — per-step status for the frontend progress indicator
- `csv_url` (str | null) — relative URL to download the result as CSV
- `error` (str | null) — error message if the graph could not complete

## External Calls
- **Anthropic Claude API** — `plan_node`, `sql_gen_node`, `repair_node`, `explain_node` (4–6 calls in a happy path)
- **MsSQL (pyodbc)** — `validate_node` (dry-run) and `execute_node` (real SELECT)

## Error Cases
| Error | Handling |
|---|---|
| LLM returns a SQL that fails validation | `repair_node` retries once with the error message + schema; if still failing, returns `error: "sql_generation_failed"`, logs to audit, shows a rephrase prompt in the UI |
| DB connection lost mid-query | Catches `pyodbc.Error`, stores in `sql_error`, returns clean 500 with `"Database unreachable"` message; audit log records the timeout |
| LLM returns 429/500 | Caught at the API route level; returns 503 with `"Analyst service temporarily unavailable"`. No SQL is generated or run. |
| Query returns 0 rows | Valid — agent still produces an answer: "No FIRs matched... try widening the date range." |
| LLM disconnects mid-generation | FastAPI stream cut; client receives a partial response with `error: "generation_interrupted"`. |

## Success Criteria
- A question referencing a real table/column in the MsSQL schema returns a correct, parseable SQL and a coherent answer with anomalies
- The same question issued twice (cache miss both times) returns the same SQL shape (idempotent)
- A deliberately ambiguous question ("show me everything") produces a graceful re-prompt, not a raw error
- All queries (success and failure) appear in the `audit_log` table with timestamps
