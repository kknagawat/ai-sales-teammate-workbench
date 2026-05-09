from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import BackgroundJobStatus
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class BackgroundJob(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "background_jobs"

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
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    task_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[BackgroundJobStatus] = mapped_column(
        SAEnum(
            BackgroundJobStatus,
            name="background_job_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=BackgroundJobStatus.QUEUED,
        server_default=BackgroundJobStatus.QUEUED.value,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default=text("3"),
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_background_jobs_work_item_task_status", "work_item_id", "task_name", "status"),
        Index(
            "uq_background_jobs_active",
            "work_item_id",
            "task_name",
            unique=True,
            postgresql_where=text("status IN ('QUEUED','RUNNING')"),
        ),
        Index(
            "ix_background_jobs_org_status_created",
            "organization_id",
            "status",
            text("created_at DESC"),
        ),
    )
