from __future__ import annotations

import json
import os
import re
from typing import Any


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


def _detect_method(goal_text: str) -> str:
    text = goal_text.lower()
    if any(word in text for word in ["average", "avg", "mean", "平均", "均值"]):
        return "mean"
    if any(word in text for word in ["max", "maximum", "最大"]):
        return "max"
    if any(word in text for word in ["min", "minimum", "最小"]):
        return "min"
    if any(word in text for word in ["count", "数量", "计数"]):
        return "count"
    return "sum"


def _detect_field(goal: str) -> str | None:
    patterns = [
        r"(?:sum|total|average|avg|mean|max|min|count)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        r"(?:field|column|字段|列)\s*[:：]?\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)",
        r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:总和|汇总|求和|平均值|均值)",
    ]
    for pattern in patterns:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    text = goal.lower()
    if "price" in text:
        return "price"
    if "金额" in goal:
        return "金额"
    return None


def _fallback_parse(goal: str) -> dict[str, Any]:
    text = goal.lower()

    if any(word in text for word in ["csv", ".csv", "逗号分隔", "tsv", ".tsv"]):
        source_type = "csv"
    elif any(word in text for word in ["excel", ".xlsx", ".xls", "sheet", "表格"]):
        source_type = "excel"
    else:
        source_type = "excel"

    operation = "aggregate" if any(
        word in text for word in ["sum", "total", "average", "avg", "mean", "max", "min", "count", "汇总", "求和", "统计"]
    ) else "analyze"
    method = _detect_method(goal) if operation == "aggregate" else "sum"

    if any(word in text for word in ["csv", ".csv", "导出csv"]):
        output = "csv"
    elif any(word in text for word in ["excel", "xlsx", "导出", "download"]):
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

    normalized = {
        "input_type": source_type,
        "source_type": source_type,
        "operation": operation,
        "field": field,
        "method": _normalize_method(parsed.get("method") or fallback["method"]),
        "output": output,
    }
    return normalized


def parse_goal(goal: str) -> dict[str, Any]:
    """
    Parse user intent to normalized planning JSON.
    Falls back to rule-based extraction when no OpenAI key is configured.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_parse(goal)

    try:
        from openai import OpenAI
    except Exception:
        return _fallback_parse(goal)

    prompt = (
        "Parse the user goal into JSON with keys: "
        "input_type, source_type, operation, field, method, output. "
        "Return JSON only."
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GOAL_PARSER_MODEL", "gpt-4.1-mini"),
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a strict JSON parser for workflow planning."},
                {"role": "user", "content": f"{prompt}\nUser goal: {goal}"},
            ],
        )
        text = response.choices[0].message.content or "{}"
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return _fallback_parse(goal)
        return _normalize_parsed_goal(parsed, goal)
    except Exception:
        return _fallback_parse(goal)
