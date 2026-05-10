import os

os.environ["ENVIRONMENT"] = "test"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_RUNTIME_SWITCHING_ENABLED"] = "false"
os.environ["LLM_MOCK_ENABLED"] = "true"
os.environ["MOCK_LLM_FAILURE_MODE"] = "none"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ANTHROPIC_MODEL"] = ""
os.environ["ANTHROPIC_VALIDATE_MODEL_ON_STARTUP"] = "false"
os.environ["CORS_EXTRA_ORIGINS"] = "[]"
os.environ["REVIEWER_INVITE_CODE"] = "demo-reviewer-code"

import pytest

from app.auth.rate_limit import login_rate_limiter, signup_rate_limiter
from app.core.runtime_config import clear_runtime_llm_provider_override
from app.db.seed import seed_database
from app.llm.providers import reset_llm_provider_cache


@pytest.fixture()
def seeded_database() -> None:
    login_rate_limiter.clear()
    signup_rate_limiter.clear()
    clear_runtime_llm_provider_override()
    reset_llm_provider_cache()
    seed_database()
