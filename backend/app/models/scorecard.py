from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReportScorecard(Base):
    __tablename__ = "report_scorecards"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), unique=True, index=True
    )
    nav_original_filename: Mapped[str | None] = mapped_column(String(255))
    nav_stored_filename: Mapped[str | None] = mapped_column(String(255))
    nav_sheet_name: Mapped[str | None] = mapped_column(String(255))
    nav_columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    detected_columns: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    nav_preview: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    calculation_inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    quantitative_score: Mapped[float | None] = mapped_column(Float)
    qualitative_score: Mapped[float | None] = mapped_column(Float)
    compliance_deduction: Mapped[float | None] = mapped_column(Float)
    total_score: Mapped[float | None] = mapped_column(Float)
    admitted: Mapped[bool | None] = mapped_column(Boolean)
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
