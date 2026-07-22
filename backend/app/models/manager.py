from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.report import DueDiligenceReport


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Manager(Base):
    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    unified_social_credit_code: Mapped[str | None] = mapped_column(
        String(18), unique=True, index=True
    )
    contact_name: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    products: Mapped[list[Product]] = relationship(
        back_populates="manager", passive_deletes=True
    )
    reports: Mapped[list[DueDiligenceReport]] = relationship(
        back_populates="manager", passive_deletes=True
    )
