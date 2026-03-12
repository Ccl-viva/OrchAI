from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from .base import LLMRuntimeConfig


def _extract_json_object(text: str) -> dict[str, Any] | None:
    content = text.strip()
    if not content:
        return None

    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    code_block = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, flags=re.DOTALL)
    if code_block:
        try:
            parsed = json.loads(code_block.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    object_match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
    if not object_match:
        return None
    try:
        parsed = json.loads(object_match.group(1))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


class OpenAIProvider:
    name = "openai"

    def __init__(self, config: LLMRuntimeConfig) -> None:
        self._client = OpenAI(api_key=config.api_key)
        self._model = config.model

    def _json_completion(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.choices[0].message.content or ""
        return _extract_json_object(text)

    def parse_goal(self, goal: str) -> dict[str, Any] | None:
        return self._json_completion(
            system_prompt="You convert user goals into strict JSON for workflow planning. Return JSON only.",
            user_prompt=(
                "Return a JSON object with keys: input_type, source_type, operation, field, method, output. "
                "Use the user's language only when needed for field names. Leave unknown field as null.\n"
                f"User goal: {goal}"
            ),
        )

    def generate_clarification_message(
        self,
        *,
        goal: str,
        parsed_goal: dict[str, Any],
        state: dict[str, Any],
        node_parameters: dict[str, Any],
        options: list[str],
    ) -> str | None:
        payload = self._json_completion(
            system_prompt=(
                "You write one concise clarification question for an AI workflow product. "
                "Ask only the minimum question needed to continue. "
                "Do not mention internal nodes, parsing, execution engines, or technical workflow steps. "
                "Match the user's language. Return JSON only."
            ),
            user_prompt=(
                "Return JSON with one key: message.\n"
                f"User goal: {goal}\n"
                f"Parsed goal: {json.dumps(parsed_goal, ensure_ascii=False)}\n"
                f"Current state: {json.dumps(state, ensure_ascii=False)}\n"
                f"Current draft question: {json.dumps(node_parameters, ensure_ascii=False)}\n"
                f"Available options: {json.dumps(options, ensure_ascii=False)}"
            ),
        )
        if not payload:
            return None
        message = str(payload.get("message", "")).strip()
        return message or None
