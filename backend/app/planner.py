from __future__ import annotations

from typing import Any


NODE_PROFILES = {
    "upload_file": {
        "description": "Collect the Excel file from the user.",
        "purpose": "Provide source data for all downstream steps.",
    },
    "parse_excel": {
        "description": "Read and parse the uploaded Excel file into a table.",
        "purpose": "Expose columns and sample rows for later operations.",
    },
    "user_confirm": {
        "description": "Ask the user to confirm ambiguous fields.",
        "purpose": "Resolve uncertainty before executing numeric operations.",
    },
    "aggregate": {
        "description": "Aggregate a selected numeric column.",
        "purpose": "Compute the required summary metric (sum/mean/max/min/count).",
    },
    "export_excel": {
        "description": "Export the final result into an Excel file.",
        "purpose": "Deliver a downloadable output artifact for the workflow.",
    },
}


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
    profile = NODE_PROFILES.get(node_type, {"description": "", "purpose": ""})
    base_parameters = {
        "description": profile["description"],
        "purpose": profile["purpose"],
        "conversation": [],
    }
    if node_type == "user_confirm":
        return {
            "type": node_type,
            "parameters": {
                **base_parameters,
                "message": "Please confirm which field should be aggregated.",
            },
        }
    if node_type == "aggregate":
        return {
            "type": node_type,
            "parameters": {
                **base_parameters,
                "field": goal.get("field"),
                "method": goal.get("method", "sum"),
            },
        }
    return {"type": node_type, "parameters": base_parameters}


def build_initial_nodes(goal: dict[str, Any]) -> list[dict[str, Any]]:
    ordered_gaps = ["need_input", "need_parse", "need_field", "need_sum", "need_output"]
    return [generate_node(gap, goal) for gap in ordered_gaps]
