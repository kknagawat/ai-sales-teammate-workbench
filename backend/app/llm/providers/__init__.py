from app.core.config import Settings
from app.core.runtime_config import get_effective_settings
from app.llm.errors import LLMConfigurationError
from app.llm.providers.anthropic import AnthropicLLMProvider
from app.llm.providers.mock import MockLLMProvider
from app.llm.types import LLMProviderProtocol

_provider_cache: dict[tuple[object, ...], LLMProviderProtocol] = {}


def _cache_key(settings: Settings) -> tuple[object, ...]:
    anthropic_key = (
        settings.anthropic_api_key.get_secret_value()
        if settings.anthropic_api_key is not None
        else None
    )
    return (
        settings.llm_provider,
        settings.llm_mock_enabled,
        settings.mock_llm_failure_mode,
        settings.anthropic_model,
        anthropic_key,
        settings.anthropic_structured_output_mode,
        settings.llm_extended_thinking_enabled,
        settings.llm_expose_provider_thinking_summary,
    )


def reset_llm_provider_cache() -> None:
    _provider_cache.clear()


def _build_provider(settings: Settings) -> LLMProviderProtocol:
    if settings.llm_provider == "mock":
        if not settings.llm_mock_enabled:
            raise LLMConfigurationError("Mock provider is selected but disabled.")
        return MockLLMProvider(settings)
    if settings.llm_provider == "anthropic":
        return AnthropicLLMProvider(settings)
    raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}")


def get_llm_provider(
    settings: Settings | None = None,
    *,
    organization_id=None,
) -> LLMProviderProtocol:
    selected_settings = settings or get_effective_settings(organization_id=organization_id)
    key = _cache_key(selected_settings)
    if key not in _provider_cache:
        _provider_cache[key] = _build_provider(selected_settings)
    return _provider_cache[key]
