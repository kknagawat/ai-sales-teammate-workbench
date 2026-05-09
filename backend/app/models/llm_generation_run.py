from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import LLMProvider, LLMProviderMode, LLMRequestType, LLMRunStatus
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class LLMGenerationRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "llm_generation_runs"

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_work_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[LLMProvider] = mapped_column(
        SAEnum(
            LLMProvider,
            name="llm_provider",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    provider_mode: Mapped[LLMProviderMode] = mapped_column(
        SAEnum(
            LLMProviderMode,
            name="llm_provider_mode",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(60), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(60), nullable=False)
    request_type: Mapped[LLMRequestType] = mapped_column(
        SAEnum(
            LLMRequestType,
            name="llm_request_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[LLMRunStatus] = mapped_column(
        SAEnum(
            LLMRunStatus,
            name="llm_run_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    structured_output: Mapped[dict | None] = mapped_column(JSONB)
    decision_trace: Mapped[dict | None] = mapped_column(JSONB)
    provider_thinking_summary: Mapped[str | None] = mapped_column(Text)
    provider_raw_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    work_item = relationship(
        "LeadWorkItem",
        back_populates="generation_runs",
        foreign_keys=[work_item_id],
    )

    __table_args__ = (
        Index("ix_llm_generation_runs_work_item_created", "work_item_id", text("created_at DESC")),
        Index(
            "ix_llm_generation_runs_org_provider_created",
            "organization_id",
            "provider",
            text("created_at DESC"),
        ),
        Index(
            "ix_llm_generation_runs_org_status_created",
            "organization_id",
            "status",
            text("created_at DESC"),
        ),
    )
