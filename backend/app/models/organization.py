from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    users = relationship("User", back_populates="organization")
    work_items = relationship("LeadWorkItem", back_populates="organization")
