from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMRuntimeConfig:
    provider: str
    model: str
    api_key: str


@dataclass(frozen=True)
class LLMPublicSettings:
    provider: str
    model: str
    enabled: bool
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "enabled": self.enabled,
            "source": self.source,
        }


class LLMProvider(Protocol):
    name: str

    def parse_goal(self, goal: str) -> dict[str, Any] | None:
        ...

    def generate_clarification_message(
        self,
        *,
        goal: str,
        parsed_goal: dict[str, Any],
        state: dict[str, Any],
        node_parameters: dict[str, Any],
        options: list[str],
    ) -> str | None:
        ...

    def interpret_node_dialogue(
        self,
        *,
        goal: str,
        parsed_goal: dict[str, Any],
        state: dict[str, Any],
        node: dict[str, Any],
        message: str,
        columns: list[str],
    ) -> dict[str, Any] | None:
        ...
