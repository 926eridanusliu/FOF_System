from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum as SqlEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.report import ReportTemplateType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportGenerationJob(Base):
    __tablename__ = "report_generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[GenerationJobStatus] = mapped_column(
        SqlEnum(GenerationJobStatus, native_enum=False),
        default=GenerationJobStatus.QUEUED,
        index=True,
    )
    template_type: Mapped[ReportTemplateType] = mapped_column(
        SqlEnum(ReportTemplateType, native_enum=False)
    )
    content_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    filename: Mapped[str | None] = mapped_column(String(255))
    validation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def download_url(self) -> str | None:
        return f"/api/files/{self.filename}" if self.filename else None
