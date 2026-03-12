from __future__ import annotations

from typing import Any, Callable


PlannerContext = dict[str, Any]
NodeBuilder = Callable[
    [str, str, dict[str, Any], dict[str, Any], dict[str, Any], PlannerContext],
    dict[str, Any] | None,
]


def normalize_method(method: Any) -> str | None:
    if not isinstance(method, str):
        return None
    value = method.strip().lower()
    if not value or value in {"none", "null"}:
        return None
    if value in {"avg", "average"}:
        return "mean"
    return value


def normalize_columns(columns: Any) -> list[str]:
    if not isinstance(columns, list):
        return []
    return [str(item).strip() for item in columns if str(item).strip()]


def resolve_field(field: Any, columns: list[str]) -> str | None:
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
    columns = normalize_columns(state.get("columns"))
    selected_field_raw = state.get("selected_field") or goal.get("field")
    selected_field = resolve_field(selected_field_raw, columns) if columns else (str(selected_field_raw).strip() if selected_field_raw else None)

    if not state.get("uploaded_file"):
        gaps.append("need_input")
    if not columns:
        gaps.append("need_parse")

    if not selected_field:
        gaps.append("need_field")
    elif columns and not resolve_field(selected_field, columns):
        gaps.append("need_field")

    if not state.get("aggregate_result"):
        gaps.append("need_sum")
    if not state.get("exported_file"):
        gaps.append("need_output")
    return gaps


def plan_next_node_generic(
    *,
    goal: dict[str, Any],
    state: dict[str, Any],
    gap_to_node_type: dict[str, str],
    node_profiles: dict[str, dict[str, str]],
    node_builder: NodeBuilder | None = None,
) -> dict[str, Any] | None:
    gaps = compute_gap(goal, state)
    if not gaps:
        return None

    gap = gaps[0]
    node_type = gap_to_node_type[gap]
    profile = node_profiles.get(node_type, {"description": "", "purpose": ""})
    columns = normalize_columns(state.get("columns"))
    selected_field_raw = state.get("selected_field") or goal.get("field")
    selected_field = resolve_field(selected_field_raw, columns) if columns else (str(selected_field_raw).strip() if selected_field_raw else None)
    selected_method = normalize_method(state.get("selected_method")) or normalize_method(goal.get("method")) or "sum"

    parameters = {
        "description": profile["description"],
        "purpose": profile["purpose"],
        "conversation": [],
    }
    context: PlannerContext = {
        "columns": columns,
        "selected_field": selected_field,
        "selected_method": selected_method,
    }

    if node_builder:
        custom = node_builder(gap, node_type, parameters, goal, state, context)
        if custom:
            return custom

    if node_type == "user_confirm":
        message = "Please confirm which field should be aggregated."
        if selected_field and columns and selected_field not in columns:
            message = f"Field '{selected_field}' was not found. Please choose a valid column."
        elif selected_field:
            message = f"Please confirm field '{selected_field}' for aggregation."

        return {
            "type": node_type,
            "parameters": {
                **parameters,
                "message": message,
                "options_override": columns,
            },
        }

    if node_type == "aggregate":
        return {
            "type": node_type,
            "parameters": {
                **parameters,
                "field": selected_field,
                "method": selected_method,
            },
        }

    return {"type": node_type, "parameters": parameters}


def build_initial_nodes_generic(
    *,
    goal: dict[str, Any],
    initial_state: dict[str, Any],
    gap_to_node_type: dict[str, str],
    node_profiles: dict[str, dict[str, str]],
    node_builder: NodeBuilder | None = None,
) -> list[dict[str, Any]]:
    first = plan_next_node_generic(
        goal=goal,
        state=initial_state,
        gap_to_node_type=gap_to_node_type,
        node_profiles=node_profiles,
        node_builder=node_builder,
    )
    if not first:
        return []
    return [first]
