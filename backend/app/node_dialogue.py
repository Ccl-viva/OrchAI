from __future__ import annotations

import re
from typing import Any

from .llm.service import interpret_node_dialogue


NODE_PROFILES = {
    "upload_file": {
        "description": "Collect the source file from the user.",
        "purpose": "Provide source data for all downstream steps.",
    },
    "parse_excel": {
        "description": "Read and parse the uploaded Excel file into a table.",
        "purpose": "Expose columns and sample rows for later operations.",
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
        "purpose": "Compute summary metrics such as sum/mean/max/min/count.",
    },
    "export_excel": {
        "description": "Export computed results as an Excel file.",
        "purpose": "Produce a downloadable artifact for the workflow.",
    },
    "export_csv": {
        "description": "Export computed results as a CSV file.",
        "purpose": "Produce a downloadable artifact for the workflow.",
    },
}

METHOD_KEYWORDS = {
    "sum": ["sum", "total", "add up", "\u6c42\u548c", "\u6c47\u603b", "\u603b\u548c"],
    "mean": ["mean", "avg", "average", "\u5e73\u5747"],
    "max": ["max", "maximum", "\u6700\u5927"],
    "min": ["min", "minimum", "\u6700\u5c0f"],
    "count": ["count", "\u6570\u91cf", "\u8ba1\u6570"],
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


def _normalize_method(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"avg", "average"}:
        return "mean"
    if text in {"sum", "mean", "max", "min", "count"}:
        return text
    return None


def _resolve_column(value: Any, columns: list[str]) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text in columns:
        return text
    lowered_map = {column.lower(): column for column in columns}
    return lowered_map.get(text.lower(), text)


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
        resolved = _resolve_column(token, columns)
        if resolved:
            return resolved

    match = re.search(r"(?:field|column|\u5b57\u6bb5|\u5217)\s*[:=]?\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)", message, flags=re.IGNORECASE)
    if not match:
        return None
    return _resolve_column(match.group(1), columns)


def _detect_sheet(message: str) -> str | int | None:
    match = re.search(r"(?:sheet|sheet_name|\u5de5\u4f5c\u8868)\s*[:=]?\s*([a-zA-Z0-9_\-\u4e00-\u9fa5]+)", message, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    if value.isdigit():
        return int(value)
    return value


def _detect_delimiter(message: str) -> str | None:
    named_patterns = [
        (r"(?:delimiter|delim|\u5206\u9694\u7b26)\s*[:=]?\s*tab", "\t"),
        (r"(?:delimiter|delim|\u5206\u9694\u7b26)\s*[:=]?\s*comma", ","),
        (r"(?:delimiter|delim|\u5206\u9694\u7b26)\s*[:=]?\s*semicolon", ";"),
        (r"(?:delimiter|delim|\u5206\u9694\u7b26)\s*[:=]?\s*pipe", "|"),
    ]
    for pattern, value in named_patterns:
        if re.search(pattern, message, flags=re.IGNORECASE):
            return value

    symbol_match = re.search(r"(?:delimiter|delim|\u5206\u9694\u7b26)\s*[:=]?\s*(.)", message, flags=re.IGNORECASE)
    if symbol_match:
        return symbol_match.group(1)
    return None


def _detect_export_name(message: str) -> str | None:
    file_match = re.search(r"([a-zA-Z0-9_\-\u4e00-\u9fa5]+\.(?:xlsx|csv))", message, flags=re.IGNORECASE)
    if file_match:
        return file_match.group(1)

    match = re.search(
        r"(?:filename|file name|\u8f93\u51fa\u6587\u4ef6|\u6587\u4ef6\u540d)\s*[:=]?\s*([a-zA-Z0-9_\-\u4e00-\u9fa5]+)",
        message,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1)


def _detect_confirm_prompt(message: str) -> str | None:
    match = re.search(r"(?:prompt|\u63d0\u793a|message)\s*[:=]?\s*(.+)$", message, flags=re.IGNORECASE)
    if match:
        prompt = match.group(1).strip()
        if prompt:
            return prompt

    fallback = re.search(r"(?:change to|\u6539\u6210|\u6539\u4e3a)\s*(.+)$", message, flags=re.IGNORECASE)
    if not fallback:
        return None
    prompt = fallback.group(1).strip()
    return prompt or None


def _detect_options_override(message: str) -> list[str]:
    match = re.search(r"(?:options|\u9009\u9879|\u5019\u9009\u5b57\u6bb5)\s*[:=]?\s*(.+)$", message, flags=re.IGNORECASE)
    if not match:
        return []

    raw = match.group(1)
    values = [item.strip() for item in re.split(r"[,\uff0c\s]+", raw) if item.strip()]
    unique: list[str] = []
    for item in values:
        if item not in unique:
            unique.append(item)
    return unique


def _profile(node_type: str) -> dict[str, str]:
    return NODE_PROFILES.get(node_type, {"description": "Custom node", "purpose": "Execute configured action"})


def _collect_rule_intent_updates(message: str, columns: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
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

    delimiter = _detect_delimiter(message)
    if delimiter is not None:
        state_patch["parse_delimiter"] = delimiter
        applied_updates["parse_delimiter"] = delimiter

    export_name = _detect_export_name(message)
    if export_name:
        state_patch["export_name"] = export_name
        applied_updates["export_name"] = export_name

    return state_patch, applied_updates


def _normalize_export_name(raw_export_name: str, node_type: str) -> str:
    name = raw_export_name.strip()
    if not name:
        return name
    lowered = name.lower()
    if node_type == "export_excel" and not lowered.endswith(".xlsx"):
        return f"{name}.xlsx"
    if node_type == "export_csv" and not lowered.endswith(".csv"):
        return f"{name}.csv"
    return name


def _normalize_llm_state_patch(raw: Any, columns: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, Any] = {}

    if "selected_field" in raw:
        resolved = _resolve_column(raw.get("selected_field"), columns)
        if resolved:
            normalized["selected_field"] = resolved

    if "selected_method" in raw:
        method = _normalize_method(raw.get("selected_method"))
        if method:
            normalized["selected_method"] = method

    if "parse_sheet" in raw:
        sheet = raw.get("parse_sheet")
        if isinstance(sheet, int):
            normalized["parse_sheet"] = sheet
        else:
            text = str(sheet or "").strip()
            if text:
                normalized["parse_sheet"] = int(text) if text.isdigit() else text

    if "parse_delimiter" in raw:
        delimiter = str(raw.get("parse_delimiter") or "").strip()
        if delimiter.lower() == "tab":
            delimiter = "\t"
        if delimiter:
            normalized["parse_delimiter"] = delimiter[0] if delimiter != "\t" else delimiter

    if "export_name" in raw:
        export_name = str(raw.get("export_name") or "").strip()
        if export_name:
            normalized["export_name"] = export_name

    return normalized


def _normalize_llm_parameter_patch(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, Any] = {}

    if "message" in raw:
        message = str(raw.get("message") or "").strip()
        if message:
            normalized["message"] = message

    if "options_override" in raw and isinstance(raw.get("options_override"), list):
        unique: list[str] = []
        for item in raw["options_override"]:
            text = str(item or "").strip()
            if text and text not in unique:
                unique.append(text)
        if unique:
            normalized["options_override"] = unique

    return normalized


def _slim_llm_state(workflow_state: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    return {
        "has_uploaded_file": bool(workflow_state.get("uploaded_file")),
        "columns": columns,
        "selected_field": workflow_state.get("selected_field"),
        "selected_method": workflow_state.get("selected_method"),
        "parse_sheet": workflow_state.get("parse_sheet"),
        "parse_delimiter": workflow_state.get("parse_delimiter"),
        "export_name": workflow_state.get("export_name"),
    }


def _llm_dialogue_updates(
    *,
    node: dict[str, Any],
    workflow: dict[str, Any],
    message: str,
    columns: list[str],
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    payload = interpret_node_dialogue(
        workflow_id=str(workflow["id"]),
        llm_settings=workflow.get("llm_settings", {}),
        goal=str(workflow.get("goal", "")),
        parsed_goal=workflow.get("parsed_goal", {}),
        state=_slim_llm_state(workflow.get("state", {}), columns),
        node={
            "id": node.get("id"),
            "type": node.get("type"),
            "status": node.get("status"),
            "parameters": node.get("parameters", {}),
        },
        message=message,
        columns=columns,
    )
    if not isinstance(payload, dict):
        return {}, {}, None

    state_patch = _normalize_llm_state_patch(payload.get("state_patch"), columns)
    parameter_patch = _normalize_llm_parameter_patch(payload.get("parameter_patch"))
    reply = str(payload.get("reply") or "").strip() or None
    return state_patch, parameter_patch, reply


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

    state_patch, applied_updates = _collect_rule_intent_updates(message, columns)
    llm_state_patch, llm_parameter_patch, llm_reply = _llm_dialogue_updates(
        node=node,
        workflow=workflow,
        message=message,
        columns=columns,
    )

    state_patch.update(llm_state_patch)
    applied_updates.update(llm_state_patch)
    should_reset = False

    if node_type == "parse_excel":
        sheet_name = state_patch.get("parse_sheet")
        if isinstance(sheet_name, (str, int)):
            parameters["sheet_name"] = sheet_name
            should_reset = True

        if "parse_sheet" in applied_updates:
            reply = llm_reply or f"I'll use sheet {applied_updates['parse_sheet']} for this file."
        elif applied_updates:
            reply = llm_reply or "I captured that change and will use it in the next steps."
            should_reset = True
        else:
            reply = llm_reply or "Tell me which sheet to use, for example `Sheet1`."

    elif node_type == "parse_csv":
        delimiter = state_patch.get("parse_delimiter")
        if isinstance(delimiter, str) and delimiter:
            parameters["delimiter"] = delimiter
            should_reset = True

        if "parse_delimiter" in applied_updates:
            shown = "\\t" if applied_updates["parse_delimiter"] == "\t" else applied_updates["parse_delimiter"]
            reply = llm_reply or f"I'll read this file using `{shown}` as the delimiter."
        elif applied_updates:
            reply = llm_reply or "I captured that change and will use it in the next steps."
            should_reset = True
        else:
            reply = llm_reply or "You can tell me the delimiter, for example comma, semicolon, or tab."

    elif node_type == "aggregate":
        if "selected_field" in applied_updates:
            parameters["field"] = applied_updates["selected_field"]
            should_reset = True
        if "selected_method" in applied_updates:
            parameters["method"] = applied_updates["selected_method"]
            should_reset = True

        if "selected_field" in applied_updates or "selected_method" in applied_updates:
            reply = llm_reply or "I updated the result you want me to compute."
        elif applied_updates:
            reply = llm_reply or "I captured that change and will use it in the next steps."
            should_reset = True
        else:
            reply = llm_reply or "Tell me which column and calculation you want, such as average, sum, or count."

    elif node_type == "user_confirm":
        prompt = _detect_confirm_prompt(message)
        options = _detect_options_override(message)
        if "message" in llm_parameter_patch:
            prompt = llm_parameter_patch["message"]
        if "options_override" in llm_parameter_patch:
            options = llm_parameter_patch["options_override"]

        if prompt:
            parameters["message"] = prompt
            applied_updates["message"] = prompt
            should_reset = True
        if options:
            parameters["options_override"] = options
            applied_updates["options_override"] = options
            should_reset = True

        if prompt or options:
            reply = llm_reply or "I updated this clarification bubble."
        elif applied_updates:
            reply = llm_reply or "I captured your intent. The next step will use it."
            should_reset = True
        else:
            reply = llm_reply or "Tell me the choice directly, or ask me to rewrite this clarification."

    elif node_type in {"export_excel", "export_csv"}:
        export_name = state_patch.get("export_name")
        if isinstance(export_name, str) and export_name:
            normalized_name = _normalize_export_name(export_name, node_type)
            parameters["export_name"] = normalized_name
            state_patch["export_name"] = normalized_name
            applied_updates["export_name"] = normalized_name
            should_reset = True

        if "export_name" in applied_updates:
            reply = llm_reply or f"I'll name the output `{applied_updates['export_name']}`."
        elif applied_updates:
            reply = llm_reply or "I captured that change for the final output."
            should_reset = True
        else:
            suffix_hint = "result.xlsx" if node_type == "export_excel" else "result.csv"
            reply = llm_reply or f"Tell me the output file name, for example `{suffix_hint}`."

    elif node_type == "upload_file":
        if applied_updates:
            reply = llm_reply or "I captured those details and will use them after you upload the file."
            should_reset = True
        else:
            reply = llm_reply or "Upload the source file, or tell me more about what result you want."

    else:
        if applied_updates:
            reply = llm_reply or "I captured your changes for downstream planning."
            should_reset = True
        else:
            reply = llm_reply or "I did not find a direct change to apply yet."

    if applied_updates:
        should_reset = True

    conversation.append({"role": "assistant", "content": reply})
    parameters["conversation"] = conversation[-20:]

    return parameters, reply, applied_updates, state_patch, should_reset
