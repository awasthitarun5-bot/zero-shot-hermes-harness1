# Agent Graph — UP Police Data Analyst

## Graph Overview

```
START
  │
  ▼
[plan_node]          — produces a short analysis plan (what to aggregate / filter / group)
  │
  ▼
[sql_gen_node]       — generates a single SQL query from the plan + schema context
  │
  ▼
[validate_node]      — dry-runs SQL (SET FMTONLY ON / sp_describe_first_result_set) to catch errors
  │   │
  │   └─[error]──▶ [repair_node] ──▶ [validate_node]  (one repair retry; max 2 attempts)
  │
  ▼ (valid)
[execute_node]       — runs SQL against MsSQL (select-only); captures row_count + timing
  │
  ▼
[detect_anomalies]   — scans result for top outliers (abs/mean-ratio, period-over-period % change)
  │
  ▼
[explain_node]       — writes plain-English answer; surfaces top 3 anomalies; appends 1–2 follow-up angles
  │
  ▼
[audit_node]         — writes entry to local SQLite audit table
  │
  ▼
END → JSON response to API
```

## State Schema (LangGraph state)

```python
class AgentState(TypedDict):
    question: str                    # raw user question
    schema_summary: str              # introspected DB schema (cached at startup)
    plan: str                        # analysis plan from plan_node
    sql: str                         # generated SQL
    sql_error: str | None            # validation error, if any
    repair_attempts: int             # how many times we retried SQL generation
    result_rows: list[dict] | None   # executed rows
    result_columns: list[str] | None # column names
    row_count: int                   # len(result_rows)
    duration_ms: int                 # wall-clock query time
    anomalies: list[dict]            # [{field, value, label, severity}]
    answer: str                      # final plain-English text
    followups: list[str]             # suggested next questions
    audit_id: int | None             # audit log row id
```

## Nodes

### plan_node
**Input:** `question`, `schema_summary`  
**Output:** `plan`  
Behaviour: One short paragraph (3–5 bullets) describing which tables/columns to use, what to aggregate, and what filters to apply. Concrete enough for sql_gen_node to act on without guessing.

### sql_gen_node
**Input:** `question`, `schema_summary`, `plan`  
**Output:** `sql`, `repair_attempts=0`  
Behaviour: Generates a single SELECT statement. Constraints enforced in the prompt:
- SELECT only, no DML/DDL
- Use only tables/columns present in `schema_summary`
- Add `TOP 1000` or equivalent limit (prevent runaway result sets)
- Prefer simple aggregates (COUNT/SUM/AVG/MAX/MIN + GROUP BY) first; window functions only if needed
- Include a brief comment explaining what the query does

### validate_node
**Input:** `sql`  
**Output:** `sql_error` (None if clean)  
Behaviour: Dry-runs the query using `SET FMTONLY ON` (SQL Server) or `sp_describe_first_result_set`. If this fails (e.g. syntax error, column not found), sets `sql_error` and returns to `repair_node`. Does NOT return rows.

### repair_node
**Input:** `question`, `schema_summary`, `plan`, `sql`, `sql_error`, `repair_attempts`  
**Output:** updated `sql`, `repair_attempts+1`  
Behaviour: One constrained retry — the LLM receives the previous SQL plus the error message plus the schema summary, asked to fix only the broken parts. Max 2 repair attempts total; after that, the graph routes to `fail_answer` (returns a clean "Couldn't generate a valid query — try rephrasing" message, logged to audit).

### execute_node
**Input:** `sql`, `schema_summary`  
**Output:** `result_rows`, `result_columns`, `row_count`, `duration_ms`  
Behaviour: Runs SQL against the MsSQL connection (or SQLite fallback). Hard limit of 1000 rows returned. Any DB-level error is caught, stored in `sql_error`, and routed back to `repair_node` once.

### detect_anomalies
**Input:** `result_rows`, `result_columns`  
**Output:** `anomalies`  
Behaviour: For numeric columns, flag:
1. Row with highest absolute value (top spike)
2. Largest period-over-period change if there's a date/timestamp column (first vs last period)
3. Any value > 3× the column mean (outlier)
Limit: top 3 anomalies. Each anomaly has `{field, label, value, severity: "high"|"medium"}`.

### explain_node
**Input:** `question`, `plan`, `anomalies`, `result_rows`, `result_columns`, `row_count`  
**Output:** `answer`, `followups`  
Behaviour: Writes 1–3 sentences of plain-English answer directly supported by the numbers. Lists the top anomalies with concrete values. Appends 1–2 follow-up questions (e.g. "Want to see this broken down by district?", "Want to filter to the last 30 days?"). Tone: concise, operational, no hedging fluff.

### audit_node
**Input:** all fields  
**Output:** `audit_id`  
Behaviour: Fire-and-forget insert into the `audit_log` table. Does not block the response if the audit DB is temporarily unavailable (logs a warning instead).

## Routing

```
START → plan_node → sql_gen_node → validate_node
    ├─[valid]───────────────────────────────────▶ execute_node → detect_anomalies → explain_node → audit_node → END
    └─[error & repair_attempts < 2]──────────────▶ repair_node → validate_node (loop)
    └─[error & repair_attempts >= 2]─────────────▶ fail_answer → audit_node → END
```

## Phase 1 Scope

Nodes included: `plan`, `sql_gen`, `validate`, `repair`, `execute`, `detect_anomalies`, `explain`, `audit`. CSV upload, cache, PDF export — absent from the graph in Phase 1 (available as future conditional edges).
