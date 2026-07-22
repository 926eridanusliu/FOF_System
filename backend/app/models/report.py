from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.manager import Manager
    from app.models.product import Product


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReportStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ARCHIVED = "archived"


class ReportTemplateType(str, Enum):
    PRIVATE_FUND = "private_fund"
    LICENSED_INSTITUTION = "licensed_institution"


class DueDiligenceReport(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("managers.id", ondelete="RESTRICT"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    template_type: Mapped[ReportTemplateType] = mapped_column(
        SqlEnum(ReportTemplateType, native_enum=False),
        default=ReportTemplateType.PRIVATE_FUND,
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    conclusion: Mapped[str | None] = mapped_column(Text)
    risk_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[ReportStatus] = mapped_column(
        SqlEnum(ReportStatus, native_enum=False), default=ReportStatus.DRAFT, index=True
    )
    generated_filename: Mapped[str | None] = mapped_column(String(255))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    manager: Mapped[Manager] = relationship(back_populates="reports")
    product: Mapped[Product] = relationship(back_populates="reports")
