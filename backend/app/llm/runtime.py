from __future__ import annotations

import threading

from .base import LLMRuntimeConfig

_RUNTIME_LOCK = threading.Lock()
_WORKFLOW_LLM_CONFIG: dict[str, LLMRuntimeConfig] = {}


def set_workflow_llm_config(workflow_id: str, config: LLMRuntimeConfig) -> None:
    with _RUNTIME_LOCK:
        _WORKFLOW_LLM_CONFIG[workflow_id] = config


def get_workflow_llm_config(workflow_id: str) -> LLMRuntimeConfig | None:
    with _RUNTIME_LOCK:
        return _WORKFLOW_LLM_CONFIG.get(workflow_id)
