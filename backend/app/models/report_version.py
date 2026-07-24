from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (
        UniqueConstraint("report_id", "version_number", name="uq_report_version_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id", ondelete="RESTRICT"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    report_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    scorecard_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    file_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(ReportVersion, "before_update")
def reject_version_update(*_args: object) -> None:
    raise ValueError("历史版本快照不可修改")


@event.listens_for(ReportVersion, "before_delete")
def reject_version_delete(*_args: object) -> None:
    raise ValueError("历史版本快照不可删除")
