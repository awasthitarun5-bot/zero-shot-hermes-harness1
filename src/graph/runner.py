"""run_agent() — entry point called by the API.

Generates a UUID run_id, writes a RunRow, invokes the graph, persists the
outcome, and returns a JSON-safe result dict.
"""
from __future__ import annotations

import uuid
from typing import Any

from src.db.models import RunRow
from src.db.session import _SESSION_MAKER
from src.graph.agent import agentic_ai
from src.graph.state import AgentState
from src.observability.events import get_logger, log_span


_SCHEMA_SUMMARY_CACHE: str | None = None


def _introspect_schema() -> str:
    global _SCHEMA_SUMMARY_CACHE
    if _SCHEMA_SUMMARY_CACHE is not None:
        return _SCHEMA_SUMMARY_CACHE
    try:
        from sqlalchemy import inspect as sa_inspect
        from src.db.session import _get_engine
        insp = sa_inspect(_get_engine())
        tables = insp.get_table_names()
        lines: list[str] = []
        for tbl in tables[:40]:
            cols = insp.get_columns(tbl)
            col_desc = ", ".join(
                f"{c['name']} ({c['type']})" for c in cols[:25]
            )
            lines.append(f"- {tbl}: {col_desc}")
        _SCHEMA_SUMMARY_CACHE = (
            "\n".join(lines) or "(no tables visible to this account)"
        )
        return _SCHEMA_SUMMARY_CACHE
    except Exception as exc:
        get_logger("schema").warning("Schema introspection failed: %s", exc)
        return f"(schema introspection failed: {exc})"


def run_agent(question: str) -> dict[str, Any]:
    log = get_logger("runner")
    run_id = str(uuid.uuid4())

    # Write a placeholder RunRow
    try:
        with _SESSION_MAKER() as session:
            run = RunRow(
                id=run_id,
                input_text=question,
                status="running",
            )
            session.add(run)
            session.commit()
    except Exception:
        pass

    initial: AgentState = {
        "run_id": run_id,
        "question": question,
        "schema_summary": _introspect_schema(),
        "plan": None,
        "sql": None,
        "sql_error": None,
        "repair_attempts": 0,
        "result_rows": None,
        "result_columns": None,
        "row_count": None,
        "duration_ms": None,
        "anomalies": None,
        "answer": None,
        "followups": None,
        "audit_id": None,
        "steps": [],
        "failed": False,
        "failure_reason": None,
        "provider": None,
        "model": None,
    }

    with log_span(log, "agent_run", run_id=run_id, question=question[:120]) as span:
        try:
            final: AgentState = agentic_ai.invoke(initial)
            span["failed"] = final.get("failed", False)
        except Exception as exc:
            log.exception("graph invocation crashed for %s: %s", run_id, exc)
            final = {
                **initial,
                "failed": True,
                "failure_reason": f"graph_crash: {exc}",
                "steps": [{"name": "graph", "status": "error"}],
            }

    # Persist RunRow outcome
    try:
        with _SESSION_MAKER() as session:
            run = session.get(RunRow, run_id)
            if run is not None:
                run.status = "failed" if final.get("failed") else "completed"
                run.output_text = final.get("answer")
                run.provider = final.get("provider")
                run.model = final.get("model")
                run.error_message = (
                    final.get("failure_reason")
                    or final.get("sql_error")
                    or final.get("error")
                )
    except Exception:
        pass

    return _serialize(final, run_id)


def _serialize(state: AgentState, run_id: str) -> dict[str, Any]:
    data_src = "unknown"
    try:
        from src.config.settings import get_settings
        from src.db.session import data_source_from_url
        data_src = data_source_from_url(get_settings().database_url)
    except Exception:
        pass

    csv_url = None
    if not state.get("failed") and state.get("result_rows") and state.get("result_columns"):
        csv_url = f"/api/download-csv?session_id={run_id}"

    return {
        "answer": state.get("answer"),
        "sql": state.get("sql"),
        "columns": state.get("result_columns"),
        "rows": state.get("result_rows"),
        "row_count": state.get("row_count"),
        "duration_ms": state.get("duration_ms"),
        "anomalies": state.get("anomalies"),
        "followups": state.get("followups"),
        "steps": state.get("steps"),
        "csv_url": csv_url,
        "error": (
            state.get("failure_reason") or state.get("sql_error") or state.get("error")
        ),
        "provider": state.get("provider"),
        "model": state.get("model"),
        "data_source": data_src,
    }
