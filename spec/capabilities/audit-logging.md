# Audit Logging

## What It Does
Records every query attempt (success or failure) to a local SQLite `audit_log` table for compliance and operational review.

## Inputs
- `question` (str)
- `sql` (str | null)
- `row_count` (int)
- `duration_ms` (int)
- `error` (str | null)
- `llm_provider` (str)
- `token_usage` (dict | null) — e.g. `{"prompt_tokens": 1024, "completion_tokens": 512, "total_tokens": 1536}`

## Outputs
- `audit_id` (int | None) — the inserted row's PK, or None if the audit write itself failed

## External Calls
- Local SQLite via `aiosqlite` — synchronous fallback if async pool is unavailable

## Error Cases
| Error | Handling |
|---|---|
| SQLite file locked / disk full | Caught, warning logged to stderr, `audit_id` returns `None`. **Query still succeeds** — audit must never block the operator. |
| Invalid `token_usage` shape | Stores `None` in the `token_usage` column rather than crashing |
| Column type mismatch on insert | Schema migration (Alembic) ensures the table is created correctly; mismatch is a startup error, not a runtime one |

## Success Criteria
- Every completed `POST /api/query` has a corresponding row in `audit_log` with `row_count` and `duration_ms` populated
- Failed queries (SQL generation failures, DB unreachable) also appear in `audit_log` with `error` populated
- `GET /api/schema` and `GET /api/download-csv` do NOT create audit rows (only actual query execution does)
