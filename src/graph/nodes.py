"""Graph nodes — UP Police Data Analyst capability slot.

Node contract: ``(state) -> partial state``.
Failures go into state fields (``error`` / ``sql_error`` / ``failed``) so the
conditional edges route cleanly — never raise through the graph.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

from src.graph.state import AgentState
from src.llm.client import LLMClient, load_prompt
from src.llm.providers.base import LLMError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RETRY_MSG = ". Retrying with the error message..."


def _now_ms() -> int:
    return int(time.perf_counter() * 1000)


def _normalize(question: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", question.lower()).strip()


def _cache_key(question: str) -> str:
    return hashlib.sha256(_normalize(question).encode()).hexdigest()[:16]


def _append_step(state: AgentState, name: str, status: str) -> None:
    steps = (state.get("steps") or []) + [{"name": name, "status": status}]
    state["steps"] = steps


def _format_table(columns: list[str], rows: list[dict], max_rows: int = 30) -> str:
    """Render a small slice of the result as a plain-text table for the LLM."""
    display = rows[:max_rows]
    header = "| " + " | ".join(columns) + " |\n|" + "|".join(["---"] * len(columns)) + "|"
    body = "\n".join(
        "| " + " | ".join(str(row.get(c, "")) for c in columns) + " |"
        for row in display
    )
    out = f"{header}\n{body}"
    if len(rows) > max_rows:
        out += f"\n... ({len(rows) - max_rows} more rows omitted)"
    return out


def _detect_anomalies(columns: list[str], rows: list[dict]) -> list[dict]:
    """Heuristic anomaly detection: top absolute value + >3x mean outlier.
    Pure Python — no external stats deps."""
    anomalies: list[dict] = []
    numeric_cols = [
        c
        for c in columns
        if any(isinstance(r.get(c), (int, float)) for r in rows[:200])
    ]
    for col in numeric_cols[:2]:
        vals = [r.get(col, 0) or 0 for r in rows]
        if not vals:
            continue
        mean = sum(vals) / len(vals) if vals else 0
        max_val = max(vals)
        # Find label from the first *non-numeric* column (usually a name/label)
        label_cols = [c for c in columns if c not in numeric_cols]
        label_col = label_cols[0] if label_cols else columns[0]
        matching_row = next((r for r in rows if r.get(col) == max_val), {})
        label = matching_row.get(label_col, "unknown")
        anomalies.append(
            {
                "field": col,
                "label": f"{label} — {col}",
                "value": max_val,
                "severity": "high" if max_val > 3 * mean else "medium",
            }
        )
    return anomalies[:3]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def plan_node(state: AgentState) -> AgentState:
    try:
        client = LLMClient()
        t0 = _now_ms()
        system_text = (
            "You are a data analyst for the Uttar Pradesh Police. "
            "You answer operational questions using a live SQL database.\n\n"
            "SCHEMA:\n{schema}\n\n"
            "OFFICER QUESTION:\n{question}\n\n"
            "Write a 3-5 bullet plan covering:\n"
            "1. Which tables to query and why.\n"
            "2. What columns to project.\n"
            "3. What filters and groupings are needed.\n"
            "4. How to detect the most important anomaly for this question.\n"
            "Keep it concrete and grounded in the schema above."
        ).format(
            schema=state.get("schema_summary", "(schema not yet loaded)"),
            question=state["question"],
        )
        plan_text = client.complete(
            system_text,
            f"OFFICER QUESTION:\n{state['question']}\n\nSCHEMA:\n{state.get('schema_summary','')}",
            max_tokens=512,
        ).strip()
        state["plan"] = plan_text
        state["provider"] = client.provider_name
        state["model"] = client.model
        _append_step(state, "plan", "done")
        state["duration_ms"] = (state.get("duration_ms") or 0) + (_now_ms() - t0)
    except LLMError as exc:
        state["error"] = f"plan_failed: {exc}"
        _append_step(state, "plan", "error")
        state["failed"] = True
        state["failure_reason"] = str(exc)
    return state


def sql_gen_node(state: AgentState) -> AgentState:
    if state.get("failed"):
        return state
    try:
        client = LLMClient()
        t0 = _now_ms()
        system_text = (
            "You write SQL for Microsoft SQL Server (T-SQL). IMPORTANT constraints:\n"
            "- SELECT only. No INSERT/UPDATE/DELETE/MERGE/DDL/DCL.\n"
            "- Only reference tables and columns from the SCHEMA block below.\n"
            "- Use TOP (not LIMIT). Use GETDATE() not CURRENT_DATE.\n"
            "- For date range questions, use DATEADD / DATEDIFF against GETDATE().\n"
            "- Add TOP 1000 or SET ROWCOUNT if returning many rows.\n"
            "- Prefer simple GROUP BY queries; window functions only if ranking is required.\n"
            "- Use table aliases (f for fir_registry, c for challan_log, etc.)\n\n"
            "SCHEMA:\n{schema}\n\n"
            "ANALYSIS PLAN:\n{plan}\n\n"
            "OFFICER QUESTION:\n{question}\n\n"
            "Return ONLY a clean SQL query. No markdown fences, no explanation."
        ).format(
            schema=state.get("schema_summary", "(no schema loaded)"),
            plan=state.get("plan", ""),
            question=state["question"],
        )
        sql_text = client.complete(
            system_text,
            f"OFFICER QUESTION:\n{state['question']}\n\nPLAN:\n{state.get('plan','')}",
            max_tokens=1024,
        ).strip()
        sql_text = re.sub(r"^```sql\n|^```\n|\n```$", "", sql_text, flags=re.MULTILINE).strip()
        state["sql"] = sql_text
        state["repair_attempts"] = state.get("repair_attempts", 0)
        _append_step(state, "sql_gen", "done")
        state["duration_ms"] = (state.get("duration_ms") or 0) + (_now_ms() - t0)
    except LLMError as exc:
        state["sql_error"] = str(exc)
        _append_step(state, "sql_gen", "error")
        state["failed"] = True
        state["failure_reason"] = str(exc)
    return state


def _dry_run_sql(sql: str) -> tuple[bool, str | None]:
    """Attempt a cheap dry-run using the sqlalchemy session factory."""
    try:
        from src.db.session import _SESSION_MAKER
        with _SESSION_MAKER() as session:
            session.execute("SET FMTONLY ON")
            session.execute(sql)
            session.execute("SET FMTONLY OFF")
            session.commit()
        return True, None
    except Exception as exc:
        return False, str(exc)


def validate_node(state: AgentState) -> AgentState:
    if state.get("failed"):
        return state
    sql = state.get("sql") or ""
    t0 = _now_ms()
    ok_flag, err = _dry_run_sql(sql)
    if ok_flag:
        _append_step(state, "validate", "done")
    else:
        state["sql_error"] = err
        _append_step(state, "validate", "error")
        state["repair_attempts"] = state.get("repair_attempts", 0) + 1
    state["duration_ms"] = (state.get("duration_ms") or 0) + (_now_ms() - t0)
    return state


def repair_node(state: AgentState) -> AgentState:
    if state.get("failed"):
        return state
    attempts = state.get("repair_attempts", 0)
    if attempts >= 2:
        state["failed"] = True
        state["failure_reason"] = (
            f"sql_repair_exhausted after 2 attempts: {state.get('sql_error')}"
        )
        _append_step(state, "repair", "error")
        return state
    try:
        client = LLMClient()
        t0 = _now_ms()
        system_text = (
            "You are repairing a SQL Server query that failed validation.\n\n"
            "SCHEMA:\n{schema}\n\n"
            "PREVIOUS FAILED QUERY:\n{sql}\n\n"
            "VALIDATION ERROR:\n{error}\n\n"
            "Fix ONLY the broken parts. Keep the original intent. "
            "Return only the corrected SQL — no explanation, no markdown fences."
        ).format(
            schema=state.get("schema_summary", ""),
            sql=state.get("sql", ""),
            error=state.get("sql_error", ""),
        )
        repaired = client.complete(
            system_text,
            f"ERROR:\n{state.get('sql_error', '')}\n\nBAD SQL:\n{state.get('sql', '')}",
            max_tokens=1024,
        ).strip()
        repaired = re.sub(r"^```sql\n|^```\n|\n```$", "", repaired, flags=re.MULTILINE).strip()
        state["sql"] = repaired
        state["sql_error"] = None
        state["repair_attempts"] = attempts + 1
        _append_step(state, "repair", "done")
        state["duration_ms"] = (state.get("duration_ms") or 0) + (_now_ms() - t0)
    except LLMError as exc:
        state["failed"] = True
        state["failure_reason"] = f"repair_failed: {exc}"
        _append_step(state, "repair", "error")
    return state


def execute_node(state: AgentState) -> AgentState:
    if state.get("failed"):
        return state
    sql = state.get("sql") or ""
    t0 = _now_ms()
    try:
        from src.db.session import _SESSION_MAKER
        with _SESSION_MAKER() as session:
            cursor = session.execute(sql)
            if cursor.returns_rows:
                rows = [dict(row._mapping) for row in cursor.fetchall()]
                columns = list(rows[0].keys()) if rows else []
            else:
                rows = []
                columns = []
        state["result_rows"] = rows
        state["result_columns"] = columns
        state["row_count"] = len(rows)
    except Exception as exc:
        state["sql_error"] = str(exc)
        state["failed"] = True
        state["failure_reason"] = f"execute_failed: {exc}"
        _append_step(state, "execute", "error")
        state["duration_ms"] = (state.get("duration_ms") or 0) + (_now_ms() - t0)
        return state
    _append_step(state, "execute", "done")
    state["duration_ms"] = (state.get("duration_ms") or 0) + (_now_ms() - t0)
    return state


def detect_anomalies_node(state: AgentState) -> AgentState:
    if state.get("failed"):
        return state
    rows_state = state.get("result_rows") or []
    cols_state = state.get("result_columns") or []
    state["anomalies"] = _detect_anomalies(cols_state, rows_state)
    return state


def explain_node(state: AgentState) -> AgentState:
    if state.get("failed"):
        return state
    try:
        client = LLMClient()
        t0 = _now_ms()
        anomalies_text = "\n".join(
            f"- {a['label']}: value={a['value']} severity={a['severity']}"
            for a in (state.get("anomalies") or [])
        )
        system_text = (
            "You are a police data analyst. Write a concise briefing.\n\n"
            "OFFICER QUESTION:\n{question}\n\n"
            "ANALYSIS PLAN:\n{plan}\n\n"
            "QUERY RESULTS ({row_count} rows):\n{result_table}\n\n"
            "TOP ANOMALIES:\n{anomalies}\n\n"
            "Write 1-3 sentences:\n"
            "- The headline number.\n"
            "- The top anomaly with its concrete value.\n"
            "- One sentence on what it means operationally.\n\n"
            "Then list 1-2 follow-up questions as 'Want ...' bullet points.\n"
            "No hedging. No markdown headings."
        ).format(
            question=state["question"],
            plan=state.get("plan", "(none)"),
            row_count=state.get("row_count", 0),
            result_table=_format_table(
                state.get("result_columns") or [],
                state.get("result_rows") or [],
            ),
            anomalies=anomalies_text or "(none detected)",
        )
        answer = client.complete(
            system_text,
            (
                f"Question: {state['question']}\n"
                f"Rows returned: {state.get('row_count', 0)}\n"
                f"Anomalies: {anomalies_text or 'none'}"
            ),
            max_tokens=1024,
        ).strip()
        # Split answer text from followup bullets (lines starting with -)
        parts = re.split(r"\n\s*- ", answer, maxsplit=1)
        answer_text = parts[0].strip()
        rest = (parts[1] if len(parts) > 1 else "").strip()
        followups = re.findall(r"^(.+)$", rest, re.MULTILINE) if rest else []
        state["answer"] = answer_text
        state["followups"] = followups[:2]
        _append_step(state, "explain", "done")
        state["duration_ms"] = (state.get("duration_ms") or 0) + (_now_ms() - t0)
    except LLMError as exc:
        state["answer"] = (
            f"I retrieved the data but the analysis failed: {exc}. "
            "The numbers and SQL are shown above — please review manually."
        )
        state["followups"] = [
            "Try a simpler date range.",
            "Try a single district at a time.",
        ]
        _append_step(state, "explain", "error")
    return state


def audit_node(state: AgentState) -> AgentState:
    """Fire-and-forget audit write. Never propagates an exception."""
    try:
        from src.db.session import _SESSION_MAKER
        with _SESSION_MAKER() as session:
            session.execute(
                """
                INSERT INTO audit_log
                  (session_id, officer_id, question, sql, row_count, duration_ms,
                   error, llm_provider, llm_model, token_usage, data_source)
                VALUES
                  (:session_id, :officer_id, :question, :sql, :row_count, :duration_ms,
                   :error, :llm_provider, :llm_model, :token_usage, :data_source)
                """,
                {
                    "session_id": state.get("run_id", "unknown"),
                    "officer_id": None,
                    "question": state.get("question", ""),
                    "sql": state.get("sql"),
                    "row_count": state.get("row_count"),
                    "duration_ms": state.get("duration_ms"),
                    "error": state.get("failure_reason")
                    or state.get("sql_error")
                    or state.get("error"),
                    "llm_provider": state.get("provider"),
                    "llm_model": state.get("model"),
                    "token_usage": None,
                    "data_source": _data_source(),
                },
            )
            session.commit()
    except Exception as exc:
        logging.getLogger("audit").warning("audit write failed: %s", exc)
    _append_step(state, "audit", "done")
    return state


def fail_answer(state: AgentState) -> AgentState:
    reason = state.get("failure_reason") or state.get("sql_error") or "unknown error"
    state["failed"] = True
    state["answer"] = (
        f"I couldn't complete that question: {reason}. "
        "Try rephrasing, narrowing the date range, or adding a location."
    )
    state["followups"] = [
        "Try a simpler question first.",
        "Narrow to a single district.",
    ]
    state["steps"] = (state.get("steps") or []) + [{"name": "fail", "status": "done"}]
    return state


# ---------------------------------------------------------------------------
# DB / config helpers
# ---------------------------------------------------------------------------

def _data_source() -> str:
    try:
        from src.config.settings import get_settings
        from src.db.session import data_source_from_url
        return data_source_from_url(get_settings().database_url)
    except Exception:
        return "unknown"
