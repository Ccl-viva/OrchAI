from __future__ import annotations

import re
from typing import Any

from .llm.base import LLMRuntimeConfig
from .llm.service import parse_goal_with_llm

ZH_AVERAGE = ["\u5e73\u5747"]
ZH_MAX = ["\u6700\u5927"]
ZH_MIN = ["\u6700\u5c0f"]
ZH_COUNT = ["\u6570\u91cf", "\u8ba1\u6570"]
ZH_AGGREGATE = ["\u6c42\u548c", "\u6c47\u603b", "\u7edf\u8ba1", "\u603b\u548c"]
ZH_EXCEL = ["\u8868\u683c", "\u5de5\u4f5c\u8868", "\u7535\u5b50\u8868\u683c"]
ZH_CSV = ["\u9017\u53f7\u5206\u9694"]
ZH_EXPORT = ["\u5bfc\u51fa", "\u4e0b\u8f7d"]
ZH_FIELD = ["\u5b57\u6bb5", "\u5217"]
ZH_AMOUNT = ["\u91d1\u989d", "\u4ef7\u683c"]


def _normalize_source_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "xlsx": "excel",
        "xls": "excel",
        "sheet": "excel",
        "spreadsheet": "excel",
        "csv_file": "csv",
        "tsv": "csv",
    }
    return aliases.get(text, text)


def _normalize_method(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"avg", "average"}:
        return "mean"
    if text in {"sum", "mean", "max", "min", "count"}:
        return text
    return "sum"


def _contains_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _detect_method(goal_text: str) -> str:
    text = goal_text.lower()
    if _contains_any(text, ["average", "avg", "mean", *ZH_AVERAGE]):
        return "mean"
    if _contains_any(text, ["max", "maximum", *ZH_MAX]):
        return "max"
    if _contains_any(text, ["min", "minimum", *ZH_MIN]):
        return "min"
    if _contains_any(text, ["count", *ZH_COUNT]):
        return "count"
    return "sum"


def _detect_field(goal: str) -> str | None:
    patterns = [
        r"(?:sum|total|average|avg|mean|max|min|count)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        r"(?:field|column)\s*[:=]?\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)",
        r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:sum|total|average|avg|mean|max|min|count)",
    ]
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

    lowered = goal.lower()
    if "price" in lowered:
        return "price"
    if any(token in goal for token in ZH_AMOUNT):
        return "\u91d1\u989d" if "\u91d1\u989d" in goal else "\u4ef7\u683c"
    return None


def _fallback_parse(goal: str) -> dict[str, Any]:
    lowered = goal.lower()

    if _contains_any(lowered, ["csv", ".csv", "tsv", ".tsv", *ZH_CSV]):
        source_type = "csv"
    elif _contains_any(lowered, ["excel", ".xlsx", ".xls", "sheet", *ZH_EXCEL]):
        source_type = "excel"
    else:
        source_type = "excel"

    operation = (
        "aggregate"
        if _contains_any(lowered, ["sum", "total", "average", "avg", "mean", "max", "min", "count", *ZH_AGGREGATE])
        else "analyze"
    )
    method = _detect_method(goal) if operation == "aggregate" else "sum"

    if _contains_any(lowered, ["csv", ".csv", "export csv"]):
        output = "csv"
    elif _contains_any(lowered, ["excel", "xlsx", "download", *ZH_EXPORT]):
        output = "excel"
    else:
        output = "excel" if source_type == "excel" else "csv"

    return {
        "input_type": source_type,
        "source_type": source_type,
        "operation": operation,
        "field": _detect_field(goal),
        "method": method,
        "output": output,
    }


def _normalize_parsed_goal(parsed: dict[str, Any], goal: str) -> dict[str, Any]:
    fallback = _fallback_parse(goal)

    source_type = _normalize_source_type(parsed.get("source_type") or parsed.get("input_type") or fallback["source_type"])
    if source_type not in {"excel", "csv"}:
        source_type = fallback["source_type"]

    operation = str(parsed.get("operation") or fallback["operation"]).strip().lower() or fallback["operation"]

    field = parsed.get("field")
    if field is None:
        field = fallback["field"]
    elif isinstance(field, str):
        field = field.strip() or None
    else:
        field = str(field).strip() or None

    output = str(parsed.get("output") or fallback["output"]).strip().lower() or fallback["output"]
    if output not in {"excel", "csv", "json"}:
        output = fallback["output"]

    return {
        "input_type": source_type,
        "source_type": source_type,
        "operation": operation,
        "field": field,
        "method": _normalize_method(parsed.get("method") or fallback["method"]),
        "output": output,
    }


def parse_goal(goal: str, runtime: LLMRuntimeConfig | None = None) -> dict[str, Any]:
    parsed = parse_goal_with_llm(goal, runtime)
    if isinstance(parsed, dict):
        return _normalize_parsed_goal(parsed, goal)
    return _fallback_parse(goal)
