from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.actions import audit_action_check_sql
from app.models.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("lead_work_items.id", ondelete="CASCADE"),
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint(audit_action_check_sql(), name="ck_audit_logs_action"),
        Index("ix_audit_logs_org_created", "organization_id", text("created_at DESC")),
        Index("ix_audit_logs_work_item_created", "work_item_id", text("created_at DESC")),
    )
