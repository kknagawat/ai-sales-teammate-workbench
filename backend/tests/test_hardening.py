from fastapi.testclient import TestClient

from app.core.config import Settings
from app.llm.providers.anthropic import AnthropicLLMProvider
from app.main import app, create_app


def test_security_headers_are_applied() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_unhandled_exception_returns_safe_error() -> None:
    test_app = create_app()

    def boom():
        raise RuntimeError("database password leaked")

    test_app.add_api_route("/__test_unhandled_exception", boom, methods=["GET"])

    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.get("/__test_unhandled_exception")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"
    assert response.json()["detail"]["message"] == "Something went wrong."
    assert "database password leaked" not in response.text


def test_lifespan_validates_anthropic_model_when_enabled(monkeypatch) -> None:
    settings = Settings(
        llm_provider="anthropic",
        anthropic_api_key="server-side-secret",
        anthropic_model="claude-test-model",
        anthropic_validate_model_on_startup=True,
    )
    provider = AnthropicLLMProvider(settings, client=object())
    calls: list[str] = []

    async def fake_validate_model(self):
        calls.append(self.model)

    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_llm_provider", lambda selected_settings: provider)
    monkeypatch.setattr(AnthropicLLMProvider, "validate_model", fake_validate_model)

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert calls == ["claude-test-model"]
