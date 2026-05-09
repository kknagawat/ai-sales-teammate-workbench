from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    BackgroundJobStatus,
    LLMProvider,
    LLMProviderMode,
    LLMRequestType,
    LLMRunStatus,
    WorkItemPriority,
    WorkItemStatus,
)


class AssignedReviewerResponse(BaseModel):
    id: UUID
    name: str
    email: str


class WorkItemSummary(BaseModel):
    id: UUID
    status: WorkItemStatus
    priority: WorkItemPriority
    version: int
    lead_name: str
    lead_email: str
    lead_title: str | None
    company_name: str
    company_domain: str | None
    lead_source: str
    source_event_type: str
    buying_stage: str
    intent_score: int
    fit_score: int
    assigned_reviewer: AssignedReviewerResponse | None
    created_at: datetime
    updated_at: datetime


class WorkItemListResponse(BaseModel):
    items: list[WorkItemSummary]


class GenerationRunSummary(BaseModel):
    id: UUID
    provider: LLMProvider
    provider_mode: LLMProviderMode
    model: str
    request_type: LLMRequestType
    status: LLMRunStatus
    structured_output: dict | None
    decision_trace: dict | None
    token_usage: dict | None
    latency_ms: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class BackgroundJobSummary(BaseModel):
    id: UUID
    task_name: str
    status: BackgroundJobStatus
    attempt_count: int
    max_attempts: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class WorkItemDetail(WorkItemSummary):
    reviewer_note: str | None
    ai_draft: str
    final_draft: str
    regeneration_count: int
    approved_draft_snapshot: str | None
    approved_at: datetime | None
    sent_at: datetime | None
    source_event_summary: str
    source_event_at: datetime
    lead_profile: dict
    latest_generation_run: GenerationRunSummary | None
    background_jobs: list[BackgroundJobSummary]


class AuditLogResponse(BaseModel):
    id: UUID
    actor_user_id: UUID | None
    actor_name: str | None
    action: str
    metadata: dict
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]


class GenerationRunListResponse(BaseModel):
    items: list[GenerationRunSummary]


class DraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_draft: str = Field(min_length=1, max_length=12000)
    last_seen_version: int = Field(ge=1, le=2_000_000_000)


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_seen_version: int = Field(ge=1, le=2_000_000_000)
    reviewer_note: str | None = Field(default=None, max_length=2000)


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_seen_version: int = Field(ge=1, le=2_000_000_000)
    reviewer_feedback: str | None = Field(default=None, max_length=2000)


class AdminUserResponse(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminUsersResponse(BaseModel):
    items: list[AdminUserResponse]
