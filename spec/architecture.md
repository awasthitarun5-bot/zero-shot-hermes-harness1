# Architecture — UP Police Data Analyst Agent

## System Overview

A FastAPI service running on-prem inside the UP Police intranet. Officers open a browser to a single URL and type natural-language questions. A LangGraph agent (powered by Anthropic Claude) plans the question into SQL, validates it, executes it against a live MsSQL database (or a local SQLite fallback), and returns an anomaly-flagged answer with a data table, chart, and CSV download link. All rows stay on-prem; only the question text goes to Anthropic.

## Component Map

```text
Officer (browser)
    │
    ▼
FastAPI server (port 8001)
    │
    ├─▶ LangGraph agent graph
    │       plan_node ──▶ sql_gen_node ──▶ validate_node ──▶ execute_node ──▶ explain_node
    │
    ├─▶ DB layer (pyodbc → MsSQL, or SQLite local fallback)
    │
    ├─▶ Cache layer (in-process dict keyed on question hash — Phase 1)
    │
    ├─▶ Audit logger (sync writes to SQLite audit table on every completed query)
    │
    └─▶ Static file server ── frontend (single-page app)
```

## Layers

| Layer | Responsibility |
|---|---|
| **API** | HTTP endpoints: `/health`, `/api/query`, `/api/download-csv`. Validates input, manages streaming SSE response. |
| **Agent Loop (LangGraph)** | Orchestrates the multi-step reasoning chain for each user question. |
| **Tools** | `generate_sql`, `validate_sql` (dry-run on DB), `run_query`, `build_answer`, `suggest_followups`. |
| **Storage** | Operational DB (MsSQL read-only, SELECT-only service account) + local SQLite (session state + audit log + dev fallback). |
| **Frontend** | Vanilla JS/HTML single-page app; no build step — copied straight to `frontend/public/`. |

## Data Flow

1. **Trigger:** Officer submits a question in the web UI
2. **Plan:** Agent generates a short analysis plan (what to aggregate/filter/group)
3. **SQL:** Agent generates a SQL query from the plan against the DB schema
4. **Validate:** SQL is dry-run (SET FMTONLY ON / sp_describe_first_result_set equivalent) against the live DB; errors are caught and fed back to the LLM for repair (one retry)
5. **Execute:** Validated SQL runs against MsSQL (SELECT only). Result rows materialised in memory.
6. **Explain:** Agent detects anomalies (top outliers vs mean, period-over-period changes) and writes a plain-English answer with error-bounded numeric claims
7. **Output:** JSON response → frontend renders text + SQL reveal + data table + bar/time-series chart + CSV download link
8. **Audit:** Query, SQL, row count, duration, timestamp, and any errors are persisted to the audit SQLite table

## External Dependencies

| Dependency | Purpose | Failure Mode |
|---|---|---|
| **Anthropic API** | NL→SQL reasoning | Agent returns a clear error: "Analyst service temporarily unavailable — your question was not run." No DB action taken. |
| **MsSQL server** | Operational data | If unreachable, app returns "Database unreachable — contact IT." Auto-falls back to local SQLite if `AGENT_DATABASE_URL` points there. |
| **Local SQLite** | Audit log + dev fallback | Non-critical; if it fails, query still executes but no audit is recorded — operator is warned. |

## Stack

- **Language:** Python 3.11+
- **Agent framework:** LangGraph (built-in in the baseline harness)
- **LLM provider + model:** Anthropic / `claude-3-5-sonnet-20240620`
- **Backend:** FastAPI (baseline) + Uvicorn
- **Database + drivers:** MsSQL via `pyodbc` (production) + SQLite via `aiosqlite` (local dev / audit)
- **Frontend:** Vanilla HTML/JS/CSS — zero build step, served as static files
- **Dependency management:** `uv` + `pyproject.tomol`
- **Migrations:** Alembic

| Key library | Version | Purpose |
|---|---|---|
| `langgraph` | latest | Agent graph orchestration |
| `anthropic` | >=0.39 | Claude API client |
| `pyodbc` | >=5.0 | MsSQL driver |
| `aiosqlite` | >=0.20 | Async SQLite (audit log) |
| `sqlalchemy` | 2.0 | ORM / schema reflection |
| `alembic` | latest | DB migrations |
| `uvicorn[standard]` | latest | ASGI server |
| `httpx` | latest | LLM client fallback/pings |

**Avoid:** pandas-heavy preprocessing (Phase 1 rows returned directly; pandas is a Phase 2 option if needed). Avoid async MsSQL drivers — pyodbc is synchronous and suffices inside FastAPI's threadpool.

## Deployment Model

- Long-running service on a single on-prem Windows/Linux server behind the police intranet reverse proxy
- Single `uv run python -m src` startup; no Docker requirement in Phase 1
- Config via `.env` file (gitignored); serves on `PORT` (default 8001)
- MsSQL connection string in `AGENT_DATABASE_URL`; switch between MsSQL and SQLite with one env change
