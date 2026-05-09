from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.health import DependencyHealth

Environment = Literal["local", "test", "staging", "production"]
LLMProviderName = Literal["anthropic", "mock"]
MockLLMFailureMode = Literal[
    "none",
    "provider_error",
    "timeout",
    "rate_limit",
    "malformed",
    "intermittent",
]
ApprovalWorkerFailureMode = Literal["none", "email", "crm"]


class PublicLLMConfig(BaseModel):
    provider: LLMProviderName
    provider_label: str
    mode: Literal["real", "mock"]
    model_label: str
    structured_outputs_enabled: bool
    decision_trace_enabled: bool
    provider_thinking_summary_enabled: bool
    runtime_switching_enabled: bool
    available_providers: list[LLMProviderName]
    active_provider_source: Literal["environment", "runtime_override"]
    anthropic_configured: bool


class PublicFeatureConfig(BaseModel):
    regeneration: bool
    approval_processing: bool
    audit_log: bool
    ai_decision_trace: bool


class PublicConfig(BaseModel):
    environment: Environment
    llm: PublicLLMConfig
    features: PublicFeatureConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI Sales Teammate API"
    app_version: str = "0.1.0"
    environment: Environment = "local"

    frontend_origin: str = "http://localhost:3000"
    cors_extra_origins: list[str] = Field(default_factory=list)

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_sales_teammate"
    redis_url: str = "redis://localhost:6379/0"
    approval_worker_failure_mode: ApprovalWorkerFailureMode = "none"
    approval_job_stale_after_seconds: int = Field(default=300, ge=1, le=86_400)

    jwt_secret: SecretStr = SecretStr("local-dev-secret-change-me")
    jwt_algorithm: Literal["HS256"] = "HS256"
    auth_cookie_name: str = "ai_sales_session"
    auth_cookie_max_age_seconds: int = 60 * 60 * 24
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    signup_rate_limit_attempts: int = 5
    signup_rate_limit_window_seconds: int = 60
    signup_demo_data_enabled: bool = True
    reviewer_invite_code: SecretStr = SecretStr("demo-reviewer-code")

    llm_provider: LLMProviderName = "mock"
    llm_runtime_switching_enabled: bool = False
    llm_mock_enabled: bool = True
    llm_allow_mock_fallback: bool = True
    mock_llm_failure_mode: MockLLMFailureMode = "none"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str | None = None
    anthropic_validate_model_on_startup: bool = False
    anthropic_structured_output_mode: Literal["tool_use"] = "tool_use"
    llm_structured_outputs_enabled: bool = True
    llm_decision_trace_enabled: bool = True
    llm_extended_thinking_enabled: bool = False
    llm_thinking_mode: Literal["off", "manual", "adaptive"] = "off"
    llm_thinking_budget_tokens: int = 1024
    llm_expose_provider_thinking_summary: bool = False

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be true when SameSite=None.")

        if self.environment == "production":
            jwt_secret = self.jwt_secret.get_secret_value()
            if jwt_secret == "local-dev-secret-change-me" or len(jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a strong production secret.")
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production.")
            reviewer_invite_code = self.reviewer_invite_code.get_secret_value()
            if reviewer_invite_code == "demo-reviewer-code" or len(reviewer_invite_code) < 12:
                raise ValueError("REVIEWER_INVITE_CODE must be changed in production.")

        return self

    @field_validator("cors_extra_origins", mode="before")
    @classmethod
    def parse_cors_extra_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_origin, *self.cors_extra_origins]
        if self.environment in {"local", "test"}:
            origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])
        return list(dict.fromkeys(origins))

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

    @property
    def anthropic_configured(self) -> bool:
        return self.anthropic_api_key is not None and bool(self.anthropic_model)

    @property
    def available_llm_providers(self) -> list[LLMProviderName]:
        providers: list[LLMProviderName] = []
        if self.llm_mock_enabled:
            providers.append("mock")
        if self.anthropic_configured:
            providers.append("anthropic")
        return providers

    def public_config(
        self,
        *,
        active_provider_source: Literal["environment", "runtime_override"] = "environment",
    ) -> PublicConfig:
        is_anthropic = self.llm_provider == "anthropic"
        provider_label = "Claude" if is_anthropic else "Mock AI"
        model_label = (
            self.anthropic_model
            if is_anthropic and self.anthropic_model
            else provider_label
        )

        return PublicConfig(
            environment=self.environment,
            llm=PublicLLMConfig(
                provider=self.llm_provider,
                provider_label=provider_label,
                mode="real" if is_anthropic else "mock",
                model_label=model_label,
                structured_outputs_enabled=self.llm_structured_outputs_enabled,
                decision_trace_enabled=self.llm_decision_trace_enabled,
                provider_thinking_summary_enabled=self.llm_expose_provider_thinking_summary,
                runtime_switching_enabled=self.llm_runtime_switching_enabled,
                available_providers=self.available_llm_providers,
                active_provider_source=active_provider_source,
                anthropic_configured=self.anthropic_configured,
            ),
            features=PublicFeatureConfig(
                regeneration=True,
                approval_processing=True,
                audit_log=True,
                ai_decision_trace=self.llm_decision_trace_enabled,
            ),
        )

    def llm_health(self) -> DependencyHealth:
        if self.llm_provider == "mock":
            if not self.llm_mock_enabled:
                return DependencyHealth(
                    status="misconfigured",
                    detail="Mock provider is selected but disabled.",
                )
            return DependencyHealth(status="ok", detail="Mock LLM provider selected.")

        if self.anthropic_api_key is None:
            return DependencyHealth(
                status="misconfigured",
                detail="ANTHROPIC_API_KEY is not configured.",
            )
        if not self.anthropic_model:
            return DependencyHealth(
                status="misconfigured",
                detail="ANTHROPIC_MODEL is not configured.",
            )
        return DependencyHealth(status="ok", detail="Anthropic provider is configured.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
