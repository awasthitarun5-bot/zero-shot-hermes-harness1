"""Conditional edges — routes the analyst graph.

Routing contract:
- If **failed** is True → go to fail_answer (terminal).
- After validate: error → repair; clean → execute.
- After repair (1st retry): still error → validate again; if repair_attempts >= 2 → fail.
- After execute: always → detect_anomalies → explain → audit → end.
"""
from __future__ import annotations

from src.graph.state import AgentState


def after_sql_gen(state: AgentState) -> str:
    if state.get("failed") or state.get("sql_error"):
        return "repair" if (state.get("repair_attempts") or 0) < 2 else "fail_answer"
    return "validate"


def after_validate(state: AgentState) -> str:
    if state.get("sql_error"):
        return "repair"
    return "execute"


def after_repair(state: AgentState) -> str:
    if state.get("failed") or state.get("sql_error"):
        if (state.get("repair_attempts") or 0) >= 2:
            return "fail_answer"
    return "validate"


def after_execute(state: AgentState) -> str:
    # Even if execute errored, we already routed to fail_answer inside the node
    return "detect_anomalies"


def after_explain(state: AgentState) -> str:
    return "audit"


def after_audit(state: AgentState) -> str:
    return "end_node"
