from __future__ import annotations

from typing import Any

from .core_planner import (
    build_initial_nodes_generic,
    normalize_method,
    plan_next_node_generic,
)


NODE_PROFILES = {
    "upload_file": {
        "description": "Collect the CSV file from the user.",
        "purpose": "Provide source data for all downstream steps.",
    },
    "parse_csv": {
        "description": "Read and parse the uploaded CSV file into a table.",
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
    "export_csv": {
        "description": "Export the final result into a CSV file.",
        "purpose": "Deliver a downloadable output artifact for the workflow.",
    },
}


GAP_TO_NODE_TYPE = {
    "need_input": "upload_file",
    "need_parse": "parse_csv",
    "need_field": "user_confirm",
    "need_sum": "aggregate",
    "need_output": "export_csv",
}


def _csv_node_builder(
    _gap: str,
    node_type: str,
    base_parameters: dict[str, Any],
    _goal: dict[str, Any],
    state: dict[str, Any],
    _context: dict[str, Any],
) -> dict[str, Any] | None:
    if node_type == "parse_csv":
        parameters = dict(base_parameters)
        delimiter = state.get("parse_delimiter")
        if isinstance(delimiter, str) and delimiter:
            parameters["delimiter"] = delimiter
        return {"type": node_type, "parameters": parameters}

    if node_type == "export_csv":
        parameters = dict(base_parameters)
        export_name = state.get("export_name")
        if isinstance(export_name, str) and export_name.strip():
            parameters["export_name"] = export_name.strip()
        return {"type": node_type, "parameters": parameters}

    return None


def plan_next_node(goal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    return plan_next_node_generic(
        goal=goal,
        state=state,
        gap_to_node_type=GAP_TO_NODE_TYPE,
        node_profiles=NODE_PROFILES,
        node_builder=_csv_node_builder,
    )


def build_initial_nodes(goal: dict[str, Any]) -> list[dict[str, Any]]:
    selected_method = normalize_method(goal.get("method"))
    initial_state = {
        "uploaded_file": None,
        "columns": [],
        "preview": None,
        "selected_field": goal.get("field"),
        "selected_method": selected_method,
        "parse_delimiter": ",",
        "export_name": None,
        "aggregate_result": None,
        "exported_file": None,
    }
    return build_initial_nodes_generic(
        goal=goal,
        initial_state=initial_state,
        gap_to_node_type=GAP_TO_NODE_TYPE,
        node_profiles=NODE_PROFILES,
        node_builder=_csv_node_builder,
    )
