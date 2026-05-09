import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select

from app.audit import actions
from app.core.config import Settings
from app.core.runtime_config import clear_runtime_llm_provider_override
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.sync_session import sync_session_factory
from app.llm.providers import reset_llm_provider_cache
from app.main import app
from app.models.audit_log import AuditLog


def _client():
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.headers.update({"Origin": "http://localhost:3000"})
    return client


def test_anthropic_structured_output_mode_defaults_to_tool_use() -> None:
    settings = Settings()

    assert settings.anthropic_structured_output_mode == "tool_use"


def test_public_config_does_not_expose_anthropic_secret() -> None:
    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="secret-key",
        anthropic_model="claude-sonnet-demo",
    )

    public_config = settings.public_config().model_dump()

    assert "secret-key" not in str(public_config)
    assert public_config["llm"]["provider"] == "anthropic"
    assert public_config["llm"]["mode"] == "real"
    assert public_config["llm"]["anthropic_configured"] is True
    assert "anthropic" in public_config["llm"]["available_providers"]
    assert public_config["llm"]["runtime_switching_enabled"] is False


def _enable_runtime_switching(monkeypatch: pytest.MonkeyPatch, *, anthropic: bool = False) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_runtime_switching_enabled", True)
    if anthropic:
        monkeypatch.setattr(settings, "anthropic_api_key", SecretStr("server-side-secret"))
        monkeypatch.setattr(settings, "anthropic_model", "claude-test-model")


def test_runtime_provider_switch_defaults_to_disabled(seeded_database) -> None:
    clear_runtime_llm_provider_override()
    reset_llm_provider_cache()
    client = _client()
    login = client.post(
        "/auth/login",
        json={
            "email": "admin@acme.example",
            "password": "AdminPass123!",
            "organization_slug": "acme",
        },
    )
    assert login.status_code == 200

    current = client.get("/config/public")
    assert current.status_code == 200
    assert current.json()["llm"]["provider"] == "mock"
    assert current.json()["llm"]["runtime_switching_enabled"] is False
    assert current.json()["llm"]["active_provider_source"] == "environment"

    response = client.patch("/config/runtime/llm-provider", json={"provider": "mock"})

    assert response.status_code == 403


def test_admin_can_update_runtime_provider_and_audit_is_written(
    seeded_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_runtime_switching(monkeypatch, anthropic=True)
    clear_runtime_llm_provider_override()
    reset_llm_provider_cache()
    client = _client()
    login = client.post(
        "/auth/login",
        json={
            "email": "admin@acme.example",
            "password": "AdminPass123!",
            "organization_slug": "acme",
        },
    )
    assert login.status_code == 200

    response = client.patch("/config/runtime/llm-provider", json={"provider": "anthropic"})

    assert response.status_code == 200
    assert response.json()["llm"]["provider"] == "anthropic"
    assert response.json()["llm"]["active_provider_source"] == "runtime_override"
    with sync_session_factory() as session:
        audit = session.scalar(
            select(AuditLog)
            .where(AuditLog.action == actions.RUNTIME_PROVIDER_CHANGED)
            .order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert audit.metadata_json["from_provider"] == "mock"
        assert audit.metadata_json["to_provider"] == "anthropic"


def test_runtime_provider_override_is_org_scoped(
    seeded_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_runtime_switching(monkeypatch, anthropic=True)
    clear_runtime_llm_provider_override()
    reset_llm_provider_cache()
    acme_client = _client()
    acme_login = acme_client.post(
        "/auth/login",
        json={
            "email": "admin@acme.example",
            "password": "AdminPass123!",
            "organization_slug": "acme",
        },
    )
    assert acme_login.status_code == 200
    switch = acme_client.patch("/config/runtime/llm-provider", json={"provider": "anthropic"})
    assert switch.status_code == 200

    globex_client = _client()
    globex_login = globex_client.post(
        "/auth/login",
        json={
            "email": "admin@globex.example",
            "password": "AdminPass123!",
            "organization_slug": "globex",
        },
    )
    assert globex_login.status_code == 200

    acme_config = acme_client.get("/config/public")
    globex_config = globex_client.get("/config/public")

    assert acme_config.json()["llm"]["provider"] == "anthropic"
    assert acme_config.json()["llm"]["active_provider_source"] == "runtime_override"
    assert globex_config.json()["llm"]["provider"] == "mock"
    assert globex_config.json()["llm"]["active_provider_source"] == "environment"


def test_runtime_provider_switch_requires_admin(seeded_database) -> None:
    client = _client()
    login = client.post(
        "/auth/login",
        json={
            "email": "reviewer@acme.example",
            "password": "ReviewerPass123!",
            "organization_slug": "acme",
        },
    )
    assert login.status_code == 200

    response = client.patch("/config/runtime/llm-provider", json={"provider": "mock"})

    assert response.status_code == 403


def test_runtime_provider_switch_rejects_unconfigured_claude(
    seeded_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_runtime_switching(monkeypatch)
    client = _client()
    login = client.post(
        "/auth/login",
        json={
            "email": "admin@acme.example",
            "password": "AdminPass123!",
            "organization_slug": "acme",
        },
    )
    assert login.status_code == 200

    response = client.patch("/config/runtime/llm-provider", json={"provider": "anthropic"})

    assert response.status_code == 409
    assert "Claude provider is not configured" in response.json()["detail"]


def test_password_hash_roundtrip() -> None:
    password_hash = hash_password("CorrectHorse123!")

    assert verify_password("CorrectHorse123!", password_hash)
    assert not verify_password("wrong", password_hash)


def test_password_hash_does_not_truncate_after_72_bytes() -> None:
    base_password = "x" * 72
    longer_password = f"{base_password}-different-suffix"
    password_hash = hash_password(base_password)

    assert verify_password(base_password, password_hash)
    assert not verify_password(longer_password, password_hash)


def test_access_token_roundtrip() -> None:
    from uuid import uuid4

    user_id = uuid4()
    token = create_access_token(user_id)

    assert decode_access_token(token) == user_id


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", auth_cookie_secure=True)


def test_production_requires_secure_auth_cookie() -> None:
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            jwt_secret="a-production-secret-that-is-long-enough",
            auth_cookie_secure=False,
        )


def test_production_security_settings_can_be_valid() -> None:
    settings = Settings(
        environment="production",
        jwt_secret="a-production-secret-that-is-long-enough",
        auth_cookie_secure=True,
        reviewer_invite_code="production-reviewer-code",
    )

    assert settings.environment == "production"
