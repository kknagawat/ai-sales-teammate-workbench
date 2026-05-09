from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import LLMProvider, LLMProviderMode, LLMRequestType
from app.schemas.generation import GenerationResult

PROMPT_VERSION = "runtime-v1"
GENERATION_SCHEMA_VERSION = "generation-result-v1"


class GenerationContext(BaseModel):
    organization_id: UUID
    work_item_id: UUID
    lead_profile: dict
    request_type: LLMRequestType
    existing_draft: str | None = None
    reviewer_feedback: str | None = Field(default=None, max_length=2000)
    prompt_version: str = PROMPT_VERSION
    schema_version: str = GENERATION_SCHEMA_VERSION

    def input_snapshot(self) -> dict:
        return {
            "lead_profile": self.lead_profile,
            "existing_draft": self.existing_draft,
            "reviewer_feedback": self.reviewer_feedback,
            "request_type": self.request_type.value,
        }


class ProviderGenerationResult(BaseModel):
    output: GenerationResult
    provider: LLMProvider
    provider_mode: LLMProviderMode
    model: str
    provider_raw_metadata: dict = Field(default_factory=dict)
    token_usage: dict | None = None
    latency_ms: int | None = None
    provider_thinking_summary: str | None = None


class LLMProviderProtocol(Protocol):
    provider: LLMProvider
    provider_mode: LLMProviderMode
    model: str

    async def generate_followup(self, context: GenerationContext) -> ProviderGenerationResult:
        ...
