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


def _normalize_method(method: Any) -> str | None:
    if not isinstance(method, str):
        return None
    value = method.strip().lower()
    if not value or value == "none":
        return None
    if value in {"avg", "average"}:
        return "mean"
    return value


def _normalize_columns(columns: Any) -> list[str]:
    if not isinstance(columns, list):
        return []
    return [str(item).strip() for item in columns if str(item).strip()]


def _resolve_field(field: Any, columns: list[str]) -> str | None:
    if not isinstance(field, str):
        return None
    value = field.strip()
    if not value:
        return None
    if value in columns:
        return value
    lowered_map = {column.lower(): column for column in columns}
    return lowered_map.get(value.lower())


def compute_gap(goal: dict[str, Any], state: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    columns = _normalize_columns(state.get("columns"))
    selected_field_raw = state.get("selected_field") or goal.get("field")
    selected_field = _resolve_field(selected_field_raw, columns) if columns else (str(selected_field_raw).strip() if selected_field_raw else None)

    if not state.get("uploaded_file"):
        gaps.append("need_input")
    if not columns:
        gaps.append("need_parse")

    if not selected_field:
        gaps.append("need_field")
    elif columns and not _resolve_field(selected_field, columns):
        gaps.append("need_field")

    if not state.get("aggregate_result"):
        gaps.append("need_sum")
    if not state.get("exported_file"):
        gaps.append("need_output")
    return gaps


def generate_node(gap: str, goal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    node_type = GAP_TO_NODE_TYPE[gap]
    profile = NODE_PROFILES.get(node_type, {"description": "", "purpose": ""})
    columns = _normalize_columns(state.get("columns"))
    selected_field_raw = state.get("selected_field") or goal.get("field")
    selected_field = _resolve_field(selected_field_raw, columns) if columns else (str(selected_field_raw).strip() if selected_field_raw else None)
    selected_method = _normalize_method(state.get("selected_method")) or _normalize_method(goal.get("method")) or "sum"

    base_parameters = {
        "description": profile["description"],
        "purpose": profile["purpose"],
        "conversation": [],
    }

    if node_type == "user_confirm":
        message = "Please confirm which field should be aggregated."
        if selected_field and columns and selected_field not in columns:
            message = f"Field '{selected_field}' was not found. Please choose a valid column."
        elif selected_field:
            message = f"Please confirm field '{selected_field}' for aggregation."

        return {
            "type": node_type,
            "parameters": {
                **base_parameters,
                "message": message,
                "options_override": columns,
            },
        }

    if node_type == "parse_excel":
        parameters = dict(base_parameters)
        sheet_name = state.get("parse_sheet")
        if isinstance(sheet_name, (str, int)):
            parameters["sheet_name"] = sheet_name
        return {"type": node_type, "parameters": parameters}

    if node_type == "aggregate":
        return {
            "type": node_type,
            "parameters": {
                **base_parameters,
                "field": selected_field,
                "method": selected_method,
            },
        }

    if node_type == "export_excel":
        parameters = dict(base_parameters)
        export_name = state.get("export_name")
        if isinstance(export_name, str) and export_name.strip():
            parameters["export_name"] = export_name.strip()
        return {"type": node_type, "parameters": parameters}

    return {"type": node_type, "parameters": base_parameters}


def plan_next_node(goal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    gaps = compute_gap(goal, state)
    if not gaps:
        return None
    return generate_node(gaps[0], goal, state)


def build_initial_nodes(goal: dict[str, Any]) -> list[dict[str, Any]]:
    selected_method = _normalize_method(goal.get("method"))
    initial_state = {
        "uploaded_file": None,
        "columns": [],
        "preview": None,
        "selected_field": goal.get("field"),
        "selected_method": selected_method,
        "parse_sheet": None,
        "export_name": None,
        "aggregate_result": None,
        "exported_file": None,
    }
    first = plan_next_node(goal, initial_state)
    if not first:
        return []
    return [first]
