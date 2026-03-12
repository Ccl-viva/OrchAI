from __future__ import annotations

import os
from typing import Any

from ..config import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER
from .base import LLMPublicSettings, LLMRuntimeConfig
from .registry import get_provider
from .runtime import get_workflow_llm_config, set_workflow_llm_config


def _normalize_provider(value: Any) -> str:
    provider = str(value or DEFAULT_LLM_PROVIDER).strip().lower()
    if provider != "openai":
        return "openai"
    return provider


def _normalize_model(value: Any) -> str:
    model = str(value or DEFAULT_LLM_MODEL).strip()
    return model or DEFAULT_LLM_MODEL


def _runtime_from_environment(provider: str, model: str) -> LLMRuntimeConfig | None:
    if provider != "openai":
        return None
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    return LLMRuntimeConfig(provider=provider, model=model, api_key=api_key)


def resolve_requested_llm(payload: dict[str, Any] | None) -> tuple[dict[str, Any], LLMRuntimeConfig | None]:
    data = payload or {}
    provider = _normalize_provider(data.get("provider"))
    model = _normalize_model(data.get("model"))
    api_key = str(data.get("api_key") or "").strip()

    if api_key:
        public = LLMPublicSettings(provider=provider, model=model, enabled=True, source="session")
        runtime = LLMRuntimeConfig(provider=provider, model=model, api_key=api_key)
        return public.to_dict(), runtime

    runtime = _runtime_from_environment(provider, model)
    if runtime:
        public = LLMPublicSettings(provider=provider, model=model, enabled=True, source="environment")
        return public.to_dict(), runtime

    public = LLMPublicSettings(provider=provider, model=model, enabled=False, source="rules")
    return public.to_dict(), None


def cache_workflow_runtime(workflow_id: str, llm_settings: dict[str, Any], runtime: LLMRuntimeConfig | None) -> None:
    if runtime is None:
        return
    if str(llm_settings.get("source")) != "session":
        return
    set_workflow_llm_config(workflow_id, runtime)


def resolve_workflow_runtime(workflow_id: str, llm_settings: dict[str, Any] | None) -> LLMRuntimeConfig | None:
    runtime = get_workflow_llm_config(workflow_id)
    if runtime:
        return runtime

    settings = llm_settings or {}
    if not settings.get("enabled"):
        return None
    if str(settings.get("source")) != "environment":
        return None

    provider = _normalize_provider(settings.get("provider"))
    model = _normalize_model(settings.get("model"))
    return _runtime_from_environment(provider, model)


def parse_goal_with_llm(goal: str, runtime: LLMRuntimeConfig | None) -> dict[str, Any] | None:
    if runtime is None:
        return None
    try:
        provider = get_provider(runtime)
        return provider.parse_goal(goal)
    except Exception:
        return None


def generate_clarification_message(
    *,
    workflow_id: str,
    llm_settings: dict[str, Any] | None,
    goal: str,
    parsed_goal: dict[str, Any],
    state: dict[str, Any],
    node_parameters: dict[str, Any],
    options: list[str],
) -> str | None:
    runtime = resolve_workflow_runtime(workflow_id, llm_settings)
    if runtime is None:
        return None
    try:
        provider = get_provider(runtime)
        return provider.generate_clarification_message(
            goal=goal,
            parsed_goal=parsed_goal,
            state=state,
            node_parameters=node_parameters,
            options=options,
        )
    except Exception:
        return None
