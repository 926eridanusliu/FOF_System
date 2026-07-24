from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationStatus(str, Enum):
    DISABLED = "disabled"
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class ReportNotification(Base):
    """Durable outbox record for a generated-report notification."""

    __tablename__ = "report_notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), index=True
    )
    generation_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_generation_jobs.id", ondelete="SET NULL"), index=True
    )
    event_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    status: Mapped[NotificationStatus] = mapped_column(
        SqlEnum(NotificationStatus, native_enum=False),
        default=NotificationStatus.PENDING,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    manager_name: Mapped[str] = mapped_column(String(255))
    product_name: Mapped[str] = mapped_column(String(255))
    report_date: Mapped[str] = mapped_column(String(100))
    download_url: Mapped[str | None] = mapped_column(String(2000))
    recipient_id: Mapped[str | None] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[str | None] = mapped_column(Text)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
