"""tests/unit/test_graph.py — regenerated to match the Phase-1 analyst graph.

Baseline baseline tests (transform_text node, after_transform edge) were
removed when the capability slot was replaced. This file covers:
  - graph compiles with all Phase-1 nodes
  - no-key import doesn't crash (langgraph graphs compile at import time)
  - error edges route correctly (sql_gen→repair|fail, validate→repair|execute)
"""
from __future__ import annotations

from src.graph.agent import agentic_ai
from src.graph.edges import after_sql_gen, after_validate, after_repair


def test_graph_compiles() -> None:
    assert agentic_ai is not None
    node_names = set(agentic_ai.get_graph().nodes)
    for expected in {
        "plan", "sql_gen", "validate", "repair", "execute",
        "detect_anomalies", "explain", "audit", "fail_answer", "end_node",
    }:
        assert expected in node_names, f"missing node: {expected}"


# ---- edge routing ----

def test_sql_gen_error_routes_to_repair_first() -> None:
    assert after_sql_gen({"failed": False, "sql_error": "boom", "repair_attempts": 0}) == "repair"


def test_sql_gen_routes_to_validate_when_clean() -> None:
    assert after_sql_gen({"failed": False, "sql_error": None, "repair_attempts": 0}) == "validate"


def test_validate_error_routes_to_repair() -> None:
    assert after_validate({"sql_error": "boom"}) == "repair"


def test_validate_clean_routes_to_execute() -> None:
    assert after_validate({"sql_error": None}) == "execute"


def test_repair_exhausted_routes_to_fail() -> None:
    assert after_repair({"failed": False, "sql_error": "still-broken", "repair_attempts": 2}) == "fail_answer"
