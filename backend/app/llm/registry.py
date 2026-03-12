from __future__ import annotations

from .base import LLMProvider, LLMRuntimeConfig
from .openai_provider import OpenAIProvider


def get_provider(config: LLMRuntimeConfig) -> LLMProvider:
    if config.provider == "openai":
        return OpenAIProvider(config)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
