from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import WorkItemPriority, WorkItemStatus
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class LeadWorkItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "lead_work_items"

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_reviewer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    status: Mapped[WorkItemStatus] = mapped_column(
        SAEnum(
            WorkItemStatus,
            name="work_item_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=WorkItemStatus.PENDING_REVIEW,
        server_default=WorkItemStatus.PENDING_REVIEW.value,
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    ai_draft: Mapped[str] = mapped_column(Text, nullable=False)
    final_draft: Mapped[str] = mapped_column(Text, nullable=False)
    regeneration_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    approved_draft_snapshot: Mapped[str | None] = mapped_column(Text)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    lead_first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    lead_last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    lead_email: Mapped[str] = mapped_column(String(320), nullable=False)
    lead_phone: Mapped[str | None] = mapped_column(String(60))
    lead_title: Mapped[str | None] = mapped_column(String(255))
    lead_linkedin_url: Mapped[str | None] = mapped_column(String(500))
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_domain: Mapped[str | None] = mapped_column(String(255))
    company_industry: Mapped[str] = mapped_column(String(255), nullable=False)
    company_size: Mapped[str] = mapped_column(String(50), nullable=False)
    company_region: Mapped[str] = mapped_column(String(120), nullable=False)
    lead_source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_event_summary: Mapped[str] = mapped_column(Text, nullable=False)
    buying_stage: Mapped[str] = mapped_column(String(80), nullable=False)
    intent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[WorkItemPriority] = mapped_column(
        SAEnum(
            WorkItemPriority,
            name="work_item_priority",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=WorkItemPriority.MEDIUM,
        server_default=WorkItemPriority.MEDIUM.value,
    )

    lead_profile: Mapped[dict] = mapped_column(JSONB, nullable=False)
    latest_generation_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "llm_generation_runs.id",
            name="fk_lead_work_items_latest_generation_run_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization = relationship("Organization", back_populates="work_items")
    assigned_reviewer = relationship(
        "User",
        back_populates="assigned_work_items",
        foreign_keys=[assigned_reviewer_id],
    )
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    generation_runs = relationship(
        "LLMGenerationRun",
        back_populates="work_item",
        foreign_keys="LLMGenerationRun.work_item_id",
    )
    latest_generation_run = relationship(
        "LLMGenerationRun",
        foreign_keys=[latest_generation_run_id],
        post_update=True,
    )

    __table_args__ = (
        Index(
            "ix_lead_work_items_org_status_created",
            "organization_id",
            "status",
            text("created_at DESC"),
        ),
        Index(
            "ix_lead_work_items_org_assigned_status",
            "organization_id",
            "assigned_reviewer_id",
            "status",
        ),
        Index("ix_lead_work_items_org_priority_status", "organization_id", "priority", "status"),
        Index(
            "ix_lead_work_items_org_source_event",
            "organization_id",
            "lead_source",
            "source_event_type",
        ),
        Index("ix_lead_work_items_org_company_domain", "organization_id", "company_domain"),
        Index("ix_lead_work_items_org_updated", "organization_id", text("updated_at DESC")),
    )
