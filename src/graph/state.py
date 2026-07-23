"""AgentState — the TypedDict flowing through the analyst graph."""
from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Core input
    question: str
    schema_summary: str

    # Plan step
    plan: str | None

    # SQL generation
    sql: str | None
    sql_error: str | None
    repair_attempts: int

    # Execution
    result_rows: list[dict] | None
    result_columns: list[str] | None
    row_count: int | None
    duration_ms: int | None

    # Analysis
    anomalies: list[dict] | None

    # Explanation
    answer: str | None
    followups: list[str] | None

    # Audit
    audit_id: int | None

    # Progress (serialised for the frontend step counter)
    steps: list[dict] | None

    # Error state set by the graph when it gives up
    failed: bool
    failure_reason: str | None

    # Provider / model (set at node entry from LLMClient)
    provider: str | None
    model: str | None
