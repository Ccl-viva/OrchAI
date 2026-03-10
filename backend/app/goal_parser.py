from __future__ import annotations

import json
import os
import re
from typing import Any


def _fallback_parse(goal: str) -> dict[str, Any]:
    text = goal.lower()
    input_type = "excel" if any(word in text for word in ["excel", "xlsx", "sheet", "表"]) else "table"
    operation = "aggregate" if any(word in text for word in ["sum", "total", "汇总", "总和", "求和"]) else "analyze"
    method = "sum" if operation == "aggregate" else "none"
    output = "excel" if any(word in text for word in ["excel", "导出", "download"]) else "json"

    field = None
    candidates = [
        r"sum\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        r"汇总([^\s，。,\.]+)",
        r"([a-zA-Z_][a-zA-Z0-9_]*)\s*总和",
    ]
    for pattern in candidates:
        match = re.search(pattern, goal, flags=re.IGNORECASE)
        if match:
            field = match.group(1).strip()
            break

    if not field:
        if "price" in text:
            field = "price"
        elif "价格" in goal:
            field = "价格"

    return {
        "input_type": input_type,
        "operation": operation,
        "field": field,
        "method": method,
        "output": output,
    }


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
        "将用户任务解析为JSON，字段必须包含："
        "input_type, operation, field, method, output。"
        "只输出JSON对象，不要解释。"
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GOAL_PARSER_MODEL", "gpt-4.1-mini"),
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a strict JSON parser for workflow planning."},
                {"role": "user", "content": f"{prompt}\n用户任务：{goal}"},
            ],
        )
        text = response.choices[0].message.content or "{}"
        parsed = json.loads(text)
        required = {"input_type", "operation", "field", "method", "output"}
        if not required.issubset(set(parsed.keys())):
            return _fallback_parse(goal)
        return parsed
    except Exception:
        return _fallback_parse(goal)
