from __future__ import annotations

from typing import Any

from .base import AdapterExecutionResult, AdapterInputError
from ..csv_planner import build_initial_nodes, plan_next_node
from ..execution import execute_aggregate, execute_export_csv, execute_parse_csv
from ..node_dialogue import apply_node_dialogue


def _confirm_field_value(options: list[str], value: str) -> str:
    if value in options:
        return value
    lowered = {item.lower(): item for item in options}
    lowered_value = value.lower()
    if lowered_value in lowered:
        return lowered[lowered_value]
    raise AdapterInputError(f"Invalid field '{value}', options: {options}")


class CsvWorkflowAdapter:
    source_type = "csv"
    accepted_file_suffixes = {".csv", ".tsv"}

    def default_adapter_state(self, parsed_goal: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "version": "csv_v1",
            "delimiter": ",",
        }

    def build_initial_nodes(self, parsed_goal: dict[str, Any]) -> list[dict[str, Any]]:
        return build_initial_nodes(parsed_goal)

    def plan_next_node(
        self,
        parsed_goal: dict[str, Any],
        state: dict[str, Any],
        adapter_state: dict[str, Any],
    ) -> dict[str, Any] | None:
        _ = adapter_state
        return plan_next_node(parsed_goal, state)

    def execute_node(
        self,
        *,
        workflow_id: str,
        node: dict[str, Any],
        state: dict[str, Any],
        confirm_value: str | None,
    ) -> AdapterExecutionResult:
        node_type = str(node["type"])
        parameters = node.get("parameters", {})

        if node_type == "upload_file":
            if not state.get("uploaded_file"):
                return AdapterExecutionResult(
                    state=state,
                    workflow_status="waiting_input",
                    event={
                        "node_id": node["id"],
                        "node_type": node_type,
                        "status": "waiting",
                        "message": "Please upload a CSV/TSV file before execution.",
                    },
                )
            return AdapterExecutionResult(
                state=state,
                workflow_status="ready",
                node_status="success",
                advance=True,
                event={
                    "node_id": node["id"],
                    "node_type": node_type,
                    "status": "success",
                    "message": "Upload node completed.",
                },
                log_status="success",
                log_result={"message": "Upload node auto-completed."},
            )

        if node_type == "parse_csv":
            next_state, result = execute_parse_csv(state, parameters)
            return AdapterExecutionResult(
                state=next_state,
                workflow_status="ready",
                node_status="success",
                advance=True,
                event={
                    "node_id": node["id"],
                    "node_type": node_type,
                    "status": "success",
                    "message": result["message"],
                    "preview": result.get("preview"),
                },
                log_status="success",
                log_result=result,
            )

        if node_type == "user_confirm":
            options_override = parameters.get("options_override")
            if isinstance(options_override, list) and options_override:
                options = [str(item) for item in options_override]
            else:
                options = [str(item) for item in state.get("columns", [])]
            prompt_message = str(parameters.get("message", "Please select a field to continue."))
            current_selected = state.get("selected_field")

            if confirm_value:
                selected = _confirm_field_value(options, confirm_value) if options else confirm_value.strip()
                next_state = dict(state)
                next_state["selected_field"] = selected
                result = {
                    "message": f"User confirmed field: {selected}.",
                    "payload": {"selected_field": selected},
                }
                return AdapterExecutionResult(
                    state=next_state,
                    workflow_status="ready",
                    node_status="success",
                    advance=True,
                    event={
                        "node_id": node["id"],
                        "node_type": node_type,
                        "status": "success",
                        "message": result["message"],
                        "payload": result["payload"],
                    },
                    log_status="success",
                    log_result=result,
                )

            resolved_current = None
            if current_selected:
                if options:
                    try:
                        resolved_current = _confirm_field_value(options, str(current_selected))
                    except ValueError:
                        resolved_current = None
                else:
                    resolved_current = str(current_selected)

            if resolved_current:
                next_state = dict(state)
                next_state["selected_field"] = resolved_current
                result = {"message": f"Field already selected: {resolved_current}."}
                return AdapterExecutionResult(
                    state=next_state,
                    workflow_status="ready",
                    node_status="success",
                    advance=True,
                    event={
                        "node_id": node["id"],
                        "node_type": node_type,
                        "status": "success",
                        "message": result["message"],
                        "payload": {"selected_field": resolved_current},
                    },
                    log_status="success",
                    log_result=result,
                )

            return AdapterExecutionResult(
                state=state,
                workflow_status="waiting_confirmation",
                pending_confirmation={"message": prompt_message, "options": options},
                log_status="waiting",
                log_result={"message": prompt_message, "options": options},
            )

        if node_type == "aggregate":
            next_state, result = execute_aggregate(state, parameters)
            return AdapterExecutionResult(
                state=next_state,
                workflow_status="ready",
                node_status="success",
                advance=True,
                event={
                    "node_id": node["id"],
                    "node_type": node_type,
                    "status": "success",
                    "message": result["message"],
                    "preview": result.get("preview"),
                    "payload": result.get("result", {}),
                },
                log_status="success",
                log_result=result,
            )

        if node_type == "export_csv":
            next_state, result = execute_export_csv(workflow_id, state, parameters)
            return AdapterExecutionResult(
                state=next_state,
                workflow_status="ready",
                node_status="success",
                advance=True,
                event={
                    "node_id": node["id"],
                    "node_type": node_type,
                    "status": "success",
                    "message": result["message"],
                    "payload": result.get("payload", {}),
                },
                log_status="success",
                log_result=result,
            )

        raise ValueError(f"Unsupported node type: {node_type}")

    def apply_node_dialogue(
        self,
        *,
        node: dict[str, Any],
        workflow: dict[str, Any],
        message: str,
    ) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], bool]:
        return apply_node_dialogue(node=node, workflow=workflow, message=message)
