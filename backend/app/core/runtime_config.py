from uuid import UUID

from app.core.config import LLMProviderName, Settings, get_settings

_llm_provider_overrides: dict[UUID, LLMProviderName] = {}


def get_runtime_llm_provider_override(organization_id: UUID | None) -> LLMProviderName | None:
    if organization_id is None:
        return None
    return _llm_provider_overrides.get(organization_id)


def set_runtime_llm_provider_override(organization_id: UUID, provider: LLMProviderName) -> None:
    _llm_provider_overrides[organization_id] = provider


def clear_runtime_llm_provider_override(organization_id: UUID | None = None) -> None:
    if organization_id is None:
        _llm_provider_overrides.clear()
        return
    _llm_provider_overrides.pop(organization_id, None)


def get_effective_settings(
    settings: Settings | None = None,
    *,
    organization_id: UUID | None = None,
) -> Settings:
    base_settings = settings or get_settings()
    override = get_runtime_llm_provider_override(organization_id)
    if override is None:
        return base_settings
    # Only the provider is overridden; all secret/config validation still comes from env settings.
    return base_settings.model_copy(update={"llm_provider": override})
