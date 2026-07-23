"""Query API — POST /api/query, GET /api/schema, GET /api/download-csv."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.config.settings import get_settings
from src.db.session import data_source_from_url, _get_engine
from src.graph.runner import run_agent

router = APIRouter()


# ---------- Schemas ----------

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=10_000)


# ---------- Endpoints ----------

@router.post("/query")
def post_query(req: QueryRequest) -> dict[str, Any]:
    if not req.question.strip():
        return _error_response("Please enter a question.", "")
    try:
        result = run_agent(req.question.strip())
    except Exception as exc:
        return _error_response(f"Service error: {exc}", "agent_crash")
    if result.get("error"):
        return result  # envelope already carries the error
    return result


def _error_response(message: str, code: str) -> dict[str, Any]:
    return {
        "answer": message,
        "sql": None,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "duration_ms": 0,
        "anomalies": [],
        "followups": [],
        "steps": [],
        "csv_url": None,
        "error": code or message,
        "provider": None,
        "model": None,
        "data_source": data_source_from_url(get_settings().database_url),
    }


@router.get("/schema")
def get_schema() -> dict[str, Any]:
    try:
        from sqlalchemy import inspect as sa_inspect
        insp = sa_inspect(_get_engine())
        tables = []
        for tbl in insp.get_table_names()[:60]:
            cols = [
                {"name": c["name"], "type": str(c["type"]), "nullable": c.get("nullable", True)}
                for c in insp.get_columns(tbl)[:30]
            ]
            tables.append({"name": tbl, "columns": cols})
        return {
            "tables": tables,
            "source": data_source_from_url(get_settings().database_url),
        }
    except Exception as exc:
        return {"tables": [], "source": "error", "error": str(exc)}


@router.get("/download-csv")
def download_csv(
    session_id: str = Query(..., alias="session_id"),
) -> Response:
    from sqlalchemy import text
    from src.db.session import _SESSION_MAKER
    rows: list[dict] = []
    columns: list[str] = []
    try:
        with _SESSION_MAKER() as session:  # type: ignore[call-arg]
            log_row = session.execute(
                text("SELECT sql FROM audit_log WHERE session_id = :sid LIMIT 1"),
                {"sid": session_id},
            ).fetchone()
            # We store the result rows on the agent RunRow; for simplicity here
            # we re-derive the CSV from the audit row's sql result if available.
            # For Phase 1 we regenerate via the same query — short-lived and cheap.
            if log_row and log_row.sql:
                cursor = session.execute(log_row.sql)
                if cursor.returns_rows:
                    rows = [dict(r._mapping) for r in cursor.fetchall()]
                    columns = list(rows[0].keys()) if rows else []
    except Exception:
        pass

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns or ["(no columns)"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    csv_bytes = buf.getvalue().encode("utf-8")

    filename = f"query-{session_id[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
