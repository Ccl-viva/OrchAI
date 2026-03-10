from __future__ import annotations

from typing import Any

from .base import WorkflowAdapter
from .excel import ExcelWorkflowAdapter


DEFAULT_SOURCE_TYPE = "excel"

_ADAPTERS: dict[str, WorkflowAdapter] = {
    DEFAULT_SOURCE_TYPE: ExcelWorkflowAdapter(),
}


def get_adapter(source_type: str | None) -> WorkflowAdapter:
    normalized = (source_type or DEFAULT_SOURCE_TYPE).strip().lower()
    return _ADAPTERS.get(normalized, _ADAPTERS[DEFAULT_SOURCE_TYPE])


def resolve_source_type(parsed_goal: dict[str, Any]) -> str:
    raw = str(parsed_goal.get("source_type") or parsed_goal.get("input_type") or "").strip().lower()
    alias_map = {
        "xlsx": "excel",
        "xls": "excel",
        "sheet": "excel",
        "spreadsheet": "excel",
    }
    normalized = alias_map.get(raw, raw)
    if normalized in _ADAPTERS:
        return normalized
    return DEFAULT_SOURCE_TYPE
