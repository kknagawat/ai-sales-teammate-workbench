from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class IdempotencyKey(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "idempotency_keys"

    organization_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "endpoint",
            "idempotency_key",
            name="uq_idempotency_keys_user_endpoint_key",
        ),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )
