from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class AdapterInputError(ValueError):
    """Raised when user-provided runtime input is invalid but workflow should remain editable."""


@dataclass
class AdapterExecutionResult:
    state: dict[str, Any]
    workflow_status: str
    node_status: str | None = None
    advance: bool = False
    event: dict[str, Any] | None = None
    pending_confirmation: dict[str, Any] | None = None
    log_status: str | None = None
    log_result: dict[str, Any] = field(default_factory=dict)


class WorkflowAdapter(Protocol):
    source_type: str
    accepted_file_suffixes: set[str]

    def default_adapter_state(self, parsed_goal: dict[str, Any]) -> dict[str, Any]:
        ...

    def build_initial_nodes(self, parsed_goal: dict[str, Any]) -> list[dict[str, Any]]:
        ...

    def plan_next_node(
        self,
        parsed_goal: dict[str, Any],
        state: dict[str, Any],
        adapter_state: dict[str, Any],
    ) -> dict[str, Any] | None:
        ...

    def execute_node(
        self,
        *,
        workflow_id: str,
        node: dict[str, Any],
        state: dict[str, Any],
        confirm_value: str | None,
    ) -> AdapterExecutionResult:
        ...

    def apply_node_dialogue(
        self,
        *,
        node: dict[str, Any],
        workflow: dict[str, Any],
        message: str,
    ) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], bool]:
        ...
