# Roadmap — UP Police Data Analyst Agent

## What This Agent Does

An on-prem AI data analyst for UP Police that lets individual officers ask natural-language questions against a large centralised MsSQL database. The agent generates validated SQL, executes it, and surfaces the result as text answers with data tables, charts, and downloadable CSVs — plus automated anomaly flags (spikes, hotspots, trend breaks). No data rows leave the intranet.

## Who Uses It

Individual officers doing ad-hoc investigations at their desk. Each session is 10–15 minutes of related Q&A. No login required in Phase 1 (one shared client); audit log captures who asked what.

## Core Problem Being Solved

Officers currently need SQL expertise or analyst support to get answers from operational databases. Ad-hoc questions that should take seconds become hours of back-and-forth. This agent removes the SQL barrier while keeping governance (generated SQL is always visible and auditable).

## Success Criteria

- [ ] Officer types "Show me FIR count by district last month" and gets a ranked table + chart in under 15 seconds
- [ ] Generated SQL is visible beneath every answer; officer can verify or download it
- [ ] CSV of every result is one-click downloadable
- [ ] Query + answer is logged to audit table with timestamp, row count, duration
- [ ] App runs on-prem behind a single URL with no external data egress

## What This Agent Does NOT Do (Out of Scope)

- Write or modify data in the production database (read-only in Phase 1)
- Replace BI dashboards or scheduled reports (Phase 2+)
- Handle identity management or per-officer login (assumed per Phase 1 brief)
- Self-host any LLM model (cloud API only in Phase 1)

## Key Constraints

- **On-prem only:** data rows never leave the intranet; only the natural-language question text goes to Anthropic
- **DB load protection:** multi-step planning + SQL validation + result caching keeps live-DB load low
- **Read-only DB access:** service account used has SELECT-only permissions on operational tables
- **Production reliability:** error handling must be solid; operator never sees a raw traceback

## Phases of Development

### Phase 1 — Core query agent (NL → SQL → anomaly answer)

- **Goal:** Smallest user-testable win — officer asks one question, gets one structured answer with table + chart + CSV. Works end-to-end against the live MsSQL DB (or SQLite dev fallback).
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — LangGraph agent graph, SQL generation/validation/execution/explanation nodes, MsSQL + SQLite dual DB layer, audit logger, FastAPI routes — deps: none
  - `slice-b` (frontend) — Question input page, step-counter progress indicator, answer panel (text + SQL reveal + data table + chart + CSV download), health endpoint integration — deps: none
- **Key surfaces / files:**
  - Backend: `src/graph/nodes.py`, `src/graph/graph.py`, `src/prompts/query_analyst.md`, `src/db/`, `src/api/routes.py`, `tests/`
  - Frontend: `frontend/public/index.html`, `frontend/public/app.js`, `frontend/public/style.css`
- **Gate command:** `uv run pytest tests/test_phase1.py -q` (real Anthropic key from `.env`, real DB driver)
- **How the user tests it (handoff seed):**
  1. Set `AGENT_ANTHROPIC_API_KEY` in `.env` and `AGENT_DATABASE_URL` (MsSQL or SQLite)
  2. Run `uv run alembic upgrade head` to create the audit table
  3. Start the app: `uv run .venv/bin/python -m src` (or `uv run python -m src`)
  4. Open the served URL, type "How many FIRs were registered in each district last month?"
  5. Expected: step counter walks through 4 steps, a table of district counts appears, a bar chart renders, a "Download CSV" link works, the generated SQL is visible beneath the answer
  6. Parts clearly labelled as stubs: CSV local-upload path (UI stub only, no backend in Phase 1), PDF export button (visible but non-functional, labelled "Coming in Phase 2")

### Phase 2 — CSV upload path + query cache + PDF export

- **Goal:** Officers can upload their own CSVs alongside the live DB; repeated queries are served from cache; answers can be exported as PDF.
- **Independent slices (parallel build units):**
  - `slice-a` (backend) — CSV ingestion + schema inference + merge-into-SQLite, simple query-result cache keyed on question hash, PDF generation (Markdown → PDF) — deps: Phase 1 backend
  - `slice-b` (frontend) — Multi-file CSV upload zone, cache-hit indicator, PDF export button wired real — deps: Phase 1 frontend
- **Gate command:** `uv run pytest tests/test_phase2.py -q`
- **How the user tests it:** Upload a CSV, ask a question that uses it, see the answer include CSV data; ask the same question twice, second time is faster (cache hit noted); click "Export PDF" and get a formatted report.

### Phase 3 — Production hardening + self-hosted LLM option

- **Goal:** Per-officer login (JWT), per-officer usage quota, full prompt+token audit trail, optional self-hosted LLM endpoint for top-secret deployments, materialised-views advisory for DB-admin.
- **Gate command:** `uv run pytest tests/test_phase3.py -q`
- **How the user tests it:** Two officer accounts with separate audit logs; switching to self-hosted LLM base URL in `.env` swaps the provider without code changes.
