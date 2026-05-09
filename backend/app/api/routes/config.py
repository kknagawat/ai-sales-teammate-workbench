from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_optional_current_user
from app.audit import actions
from app.core.config import LLMProviderName, PublicConfig, get_settings
from app.core.runtime_config import (
    clear_runtime_llm_provider_override,
    get_effective_settings,
    get_runtime_llm_provider_override,
    set_runtime_llm_provider_override,
)
from app.db.session import get_async_session
from app.llm.providers import reset_llm_provider_cache
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter()


class RuntimeLLMProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: LLMProviderName


def _public_runtime_config(user: User | None = None) -> PublicConfig:
    organization_id = user.organization_id if user else None
    source = (
        "runtime_override"
        if get_runtime_llm_provider_override(organization_id) is not None
        else "environment"
    )
    return get_effective_settings(organization_id=organization_id).public_config(
        active_provider_source=source
    )


@router.get("/public", response_model=PublicConfig)
async def get_public_config(
    current_user: User | None = Depends(get_optional_current_user),
) -> PublicConfig:
    return _public_runtime_config(current_user)


@router.patch("/runtime/llm-provider", response_model=PublicConfig)
async def update_runtime_llm_provider(
    payload: RuntimeLLMProviderUpdate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> PublicConfig:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")

    settings = get_settings()
    if not settings.llm_runtime_switching_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Runtime provider switching is disabled.",
        )
    if payload.provider == "mock" and not settings.llm_mock_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mock provider is disabled.",
        )
    if payload.provider == "anthropic" and not settings.anthropic_configured:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Claude provider is not configured on the server.",
        )

    before_settings = get_effective_settings(organization_id=current_user.organization_id)
    before_provider = before_settings.llm_provider
    before_source = (
        "runtime_override"
        if get_runtime_llm_provider_override(current_user.organization_id) is not None
        else "environment"
    )

    if payload.provider == settings.llm_provider:
        clear_runtime_llm_provider_override(current_user.organization_id)
        after_source = "environment"
    else:
        set_runtime_llm_provider_override(current_user.organization_id, payload.provider)
        after_source = "runtime_override"
    reset_llm_provider_cache()

    session.add(
        AuditLog(
            organization_id=current_user.organization_id,
            actor_user_id=current_user.id,
            action=actions.RUNTIME_PROVIDER_CHANGED,
            metadata_json={
                "from_provider": before_provider,
                "to_provider": payload.provider,
                "from_source": before_source,
                "to_source": after_source,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    await session.commit()
    return _public_runtime_config(current_user)
