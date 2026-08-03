from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notification import ReportNotification
from app.models.report import DueDiligenceReport
from app.schemas.notification import NotificationConfigRead, NotificationRead
from app.services.feishu_notifications import config_summary, retry_notification
from app.services.deletions import is_deleted


router = APIRouter(tags=["Feishu notifications"])


def _ensure_report(report_id: int, db: Session) -> None:
    report = db.get(DueDiligenceReport, report_id)
    if report is None or is_deleted("report", report_id, db) or is_deleted("manager", report.manager_id, db):
        raise HTTPException(status_code=404, detail="尽调报告不存在")


@router.get(
    "/api/notifications/config",
    response_model=NotificationConfigRead,
    summary="Read non-secret Feishu integration status",
)
def read_notification_config() -> dict:
    return config_summary()


@router.get(
    "/api/reports/{report_id}/notifications",
    response_model=list[NotificationRead],
    summary="List report notification delivery records",
)
def list_report_notifications(
    report_id: int, db: Session = Depends(get_db)
) -> list[ReportNotification]:
    _ensure_report(report_id, db)
    return list(
        db.scalars(
            select(ReportNotification)
            .where(ReportNotification.report_id == report_id)
            .order_by(ReportNotification.id.desc())
        )
    )


@router.post(
    "/api/reports/{report_id}/notifications/{notification_id}/retry",
    response_model=NotificationRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed or disabled report notification",
)
def retry_report_notification(
    report_id: int,
    notification_id: int,
    db: Session = Depends(get_db),
) -> ReportNotification:
    _ensure_report(report_id, db)
    notification = db.get(ReportNotification, notification_id)
    if notification is None or notification.report_id != report_id:
        raise HTTPException(status_code=404, detail="通知记录不存在")
    try:
        return retry_notification(notification, db)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
