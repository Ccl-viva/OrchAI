from __future__ import annotations

from typing import Any


GAP_TO_NODE_TYPE = {
    "need_input": "upload_file",
    "need_parse": "parse_excel",
    "need_field": "user_confirm",
    "need_sum": "aggregate",
    "need_output": "export_excel",
}


def compute_gap(goal: dict[str, Any], state: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not state.get("uploaded_file"):
        gaps.append("need_input")
    if not state.get("columns"):
        gaps.append("need_parse")
    if not state.get("selected_field"):
        gaps.append("need_field")
    if not state.get("aggregate_result"):
        gaps.append("need_sum")
    if not state.get("exported_file"):
        gaps.append("need_output")
    return gaps


def generate_node(gap: str, goal: dict[str, Any]) -> dict[str, Any]:
    node_type = GAP_TO_NODE_TYPE[gap]
    if node_type == "user_confirm":
        return {
            "type": node_type,
            "parameters": {
                "message": "Please confirm which field should be aggregated.",
            },
        }
    if node_type == "aggregate":
        return {
            "type": node_type,
            "parameters": {
                "field": goal.get("field"),
                "method": goal.get("method", "sum"),
            },
        }
    return {"type": node_type, "parameters": {}}


def build_initial_nodes(goal: dict[str, Any]) -> list[dict[str, Any]]:
    ordered_gaps = ["need_input", "need_parse", "need_field", "need_sum", "need_output"]
    return [generate_node(gap, goal) for gap in ordered_gaps]
