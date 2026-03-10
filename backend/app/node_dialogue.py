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
    "sum": ["sum", "total", "add up", "求和", "汇总", "总和"],
    "mean": ["mean", "avg", "average", "平均", "均值"],
    "max": ["max", "maximum", "最大"],
    "min": ["min", "minimum", "最小"],
    "count": ["count", "数量", "计数"],
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
        if role and content:
            normalized.append({"role": role, "content": content})
    return normalized


def _normalize_columns(columns: Any) -> list[str]:
    if not isinstance(columns, list):
        return []
    return [str(item).strip() for item in columns if str(item).strip()]


def _detect_method(message: str) -> str | None:
    lowered = message.lower()
    for method, keywords in METHOD_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return method
    return None


def _detect_field(message: str, columns: list[str]) -> str | None:
    lowered_message = message.lower()
    lowered_map = {item.lower(): item for item in columns}

    for lowered, original in lowered_map.items():
        if lowered and lowered in lowered_message:
            return original

    quoted_tokens = re.findall(r"[\"'`](.+?)[\"'`]", message)
    for token in quoted_tokens:
        value = token.strip()
        if not value:
            continue
        if value.lower() in lowered_map:
            return lowered_map[value.lower()]
        return value

    pattern = r"(?:field|column|字段|列)\s*[:：]?\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)"
    match = re.search(pattern, message, flags=re.IGNORECASE)
    if not match:
        return None

    value = match.group(1).strip()
    if value.lower() in lowered_map:
        return lowered_map[value.lower()]
    return value


def _detect_sheet(message: str) -> str | int | None:
    pattern = r"(?:sheet|sheet_name|工作表)\s*[:：]?\s*([a-zA-Z0-9_\-\u4e00-\u9fa5]+)"
    match = re.search(pattern, message, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    if value.isdigit():
        return int(value)
    return value


def _detect_export_name(message: str) -> str | None:
    xlsx_match = re.search(r"([a-zA-Z0-9_\-\u4e00-\u9fa5]+\.xlsx)", message, flags=re.IGNORECASE)
    if xlsx_match:
        return xlsx_match.group(1)

    pattern = r"(?:filename|file name|输出文件|文件名)\s*[:：]?\s*([a-zA-Z0-9_\-\u4e00-\u9fa5]+)"
    match = re.search(pattern, message, flags=re.IGNORECASE)
    if not match:
        return None
    return f"{match.group(1)}.xlsx"


def _detect_confirm_prompt(message: str) -> str | None:
    pattern = r"(?:prompt|提示|message)\s*[:：]\s*(.+)$"
    match = re.search(pattern, message, flags=re.IGNORECASE)
    if match:
        prompt = match.group(1).strip()
        if prompt:
            return prompt

    fallback = re.search(r"(?:改成|改为|change to)\s*(.+)$", message, flags=re.IGNORECASE)
    if not fallback:
        return None
    prompt = fallback.group(1).strip()
    return prompt or None


def _detect_options_override(message: str) -> list[str]:
    pattern = r"(?:options|选项|候选字段)\s*[:：]\s*(.+)$"
    match = re.search(pattern, message, flags=re.IGNORECASE)
    if not match:
        return []

    raw = match.group(1)
    values = [item.strip() for item in re.split(r"[,，;；\s]+", raw) if item.strip()]
    unique: list[str] = []
    for item in values:
        if item not in unique:
            unique.append(item)
    return unique


def _profile(node_type: str) -> dict[str, str]:
    return NODE_PROFILES.get(node_type, {"description": "Custom node", "purpose": "Execute configured action"})


def _collect_intent_updates(message: str, columns: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    state_patch: dict[str, Any] = {}
    applied_updates: dict[str, Any] = {}

    field = _detect_field(message, columns)
    if field:
        state_patch["selected_field"] = field
        applied_updates["selected_field"] = field

    method = _detect_method(message)
    if method:
        state_patch["selected_method"] = method
        applied_updates["selected_method"] = method

    sheet = _detect_sheet(message)
    if sheet is not None:
        state_patch["parse_sheet"] = sheet
        applied_updates["parse_sheet"] = sheet

    export_name = _detect_export_name(message)
    if export_name:
        state_patch["export_name"] = export_name
        applied_updates["export_name"] = export_name

    return state_patch, applied_updates


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
    node_type = str(node["type"])
    parameters = dict(node.get("parameters", {}))
    conversation = _normalize_conversation(parameters.get("conversation"))
    conversation.append({"role": "user", "content": message})

    profile = _profile(node_type)
    parameters["description"] = profile["description"]
    parameters["purpose"] = profile["purpose"]

    workflow_state = workflow.get("state", {})
    columns = _normalize_columns(workflow_state.get("columns"))

    state_patch, applied_updates = _collect_intent_updates(message, columns)
    should_reset = False

    if node_type == "parse_excel":
        sheet_name = state_patch.get("parse_sheet")
        if isinstance(sheet_name, (str, int)):
            parameters["sheet_name"] = sheet_name
            should_reset = True

        if "parse_sheet" in applied_updates:
            reply = f"Parse node will use sheet: {applied_updates['parse_sheet']}."
        elif applied_updates:
            reply = "Captured your intent updates. They will influence downstream nodes."
            should_reset = True
        else:
            reply = "You can set target sheet with `sheet: Sheet1`."

    elif node_type == "aggregate":
        if "selected_field" in applied_updates:
            parameters["field"] = applied_updates["selected_field"]
            should_reset = True
        if "selected_method" in applied_updates:
            parameters["method"] = applied_updates["selected_method"]
            should_reset = True

        if "selected_field" in applied_updates or "selected_method" in applied_updates:
            reply = "Aggregate node updated from your instruction."
        elif applied_updates:
            reply = "Captured your intent updates for downstream nodes."
            should_reset = True
        else:
            reply = "You can update aggregate `field` and `method` (sum/mean/max/min/count)."

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

        if prompt or options:
            reply = "Updated confirm node prompt/options."
        elif applied_updates:
            reply = "Captured your intent updates. Next generated node will use them."
            should_reset = True
        else:
            reply = "Use `prompt: ...` or `options: col1,col2` to customize this confirm node."

    elif node_type == "export_excel":
        export_name = state_patch.get("export_name")
        if isinstance(export_name, str) and export_name:
            parameters["export_name"] = export_name
            should_reset = True

        if "export_name" in applied_updates:
            reply = f"Export file name set to {applied_updates['export_name']}."
        elif applied_updates:
            reply = "Captured your intent updates for this workflow."
            should_reset = True
        else:
            reply = "You can rename output via `filename: result.xlsx`."

    elif node_type == "upload_file":
        if applied_updates:
            reply = "Captured your intent updates. They will be used when generating next nodes."
            should_reset = True
        else:
            reply = "Upload node is ready. Please upload an Excel file to continue."

    else:
        if applied_updates:
            reply = "Captured your intent updates for downstream planning."
            should_reset = True
        else:
            reply = "No editable controls found for this node."

    if applied_updates:
        should_reset = True

    conversation.append({"role": "assistant", "content": reply})
    parameters["conversation"] = conversation[-20:]

    return parameters, reply, applied_updates, state_patch, should_reset
