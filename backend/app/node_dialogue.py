from __future__ import annotations

import re
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
        "purpose": "Compute summary metrics such as sum/mean/max/min/count.",
    },
    "export_excel": {
        "description": "Export computed results as an Excel file.",
        "purpose": "Produce a downloadable artifact for the workflow.",
    },
}

METHOD_KEYWORDS = {
    "sum": ["sum", "total", "求和", "总和", "汇总"],
    "mean": ["mean", "avg", "average", "平均"],
    "max": ["max", "maximum", "最大"],
    "min": ["min", "minimum", "最小"],
    "count": ["count", "计数", "数量"],
}


def _normalize_conversation(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if not role or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _detect_method(message: str) -> str | None:
    lowered = message.lower()
    for method, keywords in METHOD_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return method
    return None


def _detect_field(message: str, columns: list[str]) -> str | None:
    normalized_columns = [str(item).strip() for item in columns if str(item).strip()]
    lowered_map = {item.lower(): item for item in normalized_columns}
    lowered_message = message.lower()

    # Prefer explicit mention of an existing column name.
    for lowered, original in lowered_map.items():
        if lowered and lowered in lowered_message:
            return original

    # Parse quoted field names.
    quoted = re.findall(r"[\"“'`](.+?)[\"”'`]", message)
    for token in quoted:
        token = token.strip()
        if not token:
            continue
        if token.lower() in lowered_map:
            return lowered_map[token.lower()]
        return token

    # Parse generic "field: xxx" patterns.
    match = re.search(r"(?:field|column|字段|列)\s*[:：]?\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)", message, flags=re.IGNORECASE)
    if match:
        token = match.group(1).strip()
        if token.lower() in lowered_map:
            return lowered_map[token.lower()]
        return token

    return None


def _detect_sheet(message: str) -> str | int | None:
    match = re.search(r"(?:sheet|工作表)\s*[:：]?\s*([a-zA-Z0-9_\-\u4e00-\u9fa5]+)", message, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    if value.isdigit():
        return int(value)
    return value


def _detect_export_name(message: str) -> str | None:
    match = re.search(r"([a-zA-Z0-9_\-\u4e00-\u9fa5]+\.xlsx)", message, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(r"(?:filename|file name|文件名)\s*[:：]?\s*([a-zA-Z0-9_\-\u4e00-\u9fa5]+)", message, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)}.xlsx"
    return None


def _detect_confirm_prompt(message: str) -> str | None:
    match = re.search(r"(?:prompt|提示)\s*[:：]\s*(.+)$", message, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()

    match = re.search(r"(?:改成|改为|change to)\s*(.+)$", message, flags=re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        if candidate:
            return candidate
    return None


def _detect_options_override(message: str) -> list[str]:
    match = re.search(r"(?:options|候选|可选|字段)\s*[:：]\s*(.+)$", message, flags=re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1)
    options = [item.strip() for item in re.split(r"[,，/|;；\s]+", raw) if item.strip()]
    unique: list[str] = []
    for option in options:
        if option not in unique:
            unique.append(option)
    return unique


def _profile(node_type: str) -> dict[str, str]:
    return NODE_PROFILES.get(node_type, {"description": "Custom node", "purpose": "Execute configured action"})


def apply_node_dialogue(
    *,
    node: dict[str, Any],
    workflow: dict[str, Any],
    message: str,
) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any], bool]:
    """
    Returns:
        updated_parameters, assistant_reply, applied_updates, state_patch, should_reset_from_node
    """
    node_type = node["type"]
    parameters = dict(node.get("parameters", {}))
    conversation = _normalize_conversation(parameters.get("conversation"))
    conversation.append({"role": "user", "content": message})

    profile = _profile(node_type)
    parameters["description"] = profile["description"]
    parameters["purpose"] = profile["purpose"]

    applied_updates: dict[str, Any] = {}
    state_patch: dict[str, Any] = {}
    should_reset = False

    workflow_state = workflow.get("state", {})
    columns = [str(item) for item in workflow_state.get("columns", [])]

    if node_type == "aggregate":
        field = _detect_field(message, columns)
        method = _detect_method(message)
        if field:
            parameters["field"] = field
            state_patch["selected_field"] = field
            applied_updates["field"] = field
            should_reset = True
        if method:
            parameters["method"] = method
            applied_updates["method"] = method
            should_reset = True
        if applied_updates:
            reply = f"Updated aggregate node with {applied_updates}."
        else:
            reply = "I can update aggregate `field` and `method` (sum/mean/max/min/count)."

    elif node_type == "user_confirm":
        prompt = _detect_confirm_prompt(message)
        options = _detect_options_override(message)
        if prompt:
            parameters["message"] = prompt
            applied_updates["message"] = prompt
            should_reset = True
        if options:
            parameters["options_override"] = options
            applied_updates["options_override"] = options
            should_reset = True
        if applied_updates:
            reply = "Updated confirm node prompt/options."
        else:
            reply = "You can set `prompt: ...` or `options: col1,col2` to customize this confirm node."

    elif node_type == "parse_excel":
        sheet_name = _detect_sheet(message)
        if sheet_name is not None:
            parameters["sheet_name"] = sheet_name
            applied_updates["sheet_name"] = sheet_name
            should_reset = True
            reply = f"Parse node will use sheet: {sheet_name}."
        else:
            reply = "You can set target sheet via `sheet: Sheet1`."

    elif node_type == "export_excel":
        export_name = _detect_export_name(message)
        if export_name:
            parameters["export_name"] = export_name
            applied_updates["export_name"] = export_name
            should_reset = True
            reply = f"Export file name set to {export_name}."
        else:
            reply = "You can rename output via `filename: result.xlsx`."

    elif node_type == "upload_file":
        reply = "Upload node is ready. Please upload an Excel file to continue."
    else:
        reply = "No editable controls found for this node."

    conversation.append({"role": "assistant", "content": reply})
    parameters["conversation"] = conversation[-20:]

    return parameters, reply, applied_updates, state_patch, should_reset
