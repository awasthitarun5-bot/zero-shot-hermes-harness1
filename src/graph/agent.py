"""Graph assembly — StateGraph compiled once at import."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.graph.edges import (
    after_audit,
    after_execute,
    after_explain,
    after_repair,
    after_sql_gen,
    after_validate,
)
from src.graph.nodes import (
    audit_node,
    detect_anomalies_node,
    explain_node,
    execute_node,
    fail_answer,
    plan_node,
    repair_node,
    sql_gen_node,
    validate_node,
)
from src.graph.state import AgentState


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan_node)
    g.add_node("sql_gen", sql_gen_node)
    g.add_node("validate", validate_node)
    g.add_node("repair", repair_node)
    g.add_node("execute", execute_node)
    g.add_node("detect_anomalies", detect_anomalies_node)
    g.add_node("explain", explain_node)
    g.add_node("audit", audit_node)
    g.add_node("fail_answer", fail_answer)
    g.add_node("end_node", lambda s: s)

    g.set_entry_point("plan")
    g.add_edge("plan", "sql_gen")

    # sql_gen → validate (or repair / fail)
    g.add_conditional_edges(
        "sql_gen",
        after_sql_gen,
        {
            "validate": "validate",
            "repair": "repair",
            "fail_answer": "fail_answer",
        },
    )

    # validate → execute (or repair)
    g.add_conditional_edges(
        "validate",
        after_validate,
        {
            "execute": "execute",
            "repair": "repair",
        },
    )

    # repair → validate (or fail)
    g.add_conditional_edges(
        "repair",
        after_repair,
        {
            "validate": "validate",
            "fail_answer": "fail_answer",
        },
    )

    # execute → detect_anomalies (fail already branched out)
    g.add_edge("execute", "detect_anomalies")
    g.add_edge("detect_anomalies", "explain")
    g.add_edge("explain", "audit")
    g.add_edge("audit", END)
    g.add_edge("fail_answer", "end_node")
    g.add_edge("end_node", END)

    return g.compile()


agentic_ai = _build_graph()
