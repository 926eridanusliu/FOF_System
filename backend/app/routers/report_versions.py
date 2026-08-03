from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.manager import Manager
from app.models.product import Product
from app.models.report import DueDiligenceReport
from app.models.report_version import ReportVersion
from app.models.scorecard import ReportScorecard
from app.schemas.report import ReportRead
from app.schemas.report_version import (
    ReportVersionComparison,
    ReportVersionDetail,
    ReportVersionSummary,
)
from app.services.report_versions import (
    compare_versions,
    restore_report_version,
    verify_version,
    version_summary,
)
from app.services.deletions import is_deleted


router = APIRouter(prefix="/api/reports/{report_id}/versions", tags=["Report Versions"])


def _get_report(report_id: int, db: Session) -> DueDiligenceReport:
    report = db.get(DueDiligenceReport, report_id)
    if report is None or is_deleted("report", report_id, db) or is_deleted("manager", report.manager_id, db):
        raise HTTPException(status_code=404, detail="尽调报告不存在")
    return report


def _get_version(
    report_id: int, version_number: int, db: Session
) -> ReportVersion:
    version = db.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report_id,
            ReportVersion.version_number == version_number,
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="历史版本不存在")
    try:
        verify_version(version)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return version


@router.get("", response_model=list[ReportVersionSummary])
def list_report_versions(
    report_id: int,
    db: Session = Depends(get_db),
) -> list[ReportVersionSummary]:
    _get_report(report_id, db)
    versions = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.report_id == report_id)
        .order_by(ReportVersion.version_number.desc())
    )
    return [version_summary(version) for version in versions]


@router.get("/compare", response_model=ReportVersionComparison)
def compare_report_versions(
    report_id: int,
    from_version: int = Query(gt=0),
    to_version: int = Query(gt=0),
    db: Session = Depends(get_db),
) -> ReportVersionComparison:
    _get_report(report_id, db)
    before = _get_version(report_id, from_version, db)
    after = _get_version(report_id, to_version, db)
    try:
        return compare_versions(report_id, before, after)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{version_number}", response_model=ReportVersionDetail)
def get_report_version(
    report_id: int,
    version_number: int,
    db: Session = Depends(get_db),
) -> ReportVersionDetail:
    version = _get_version(report_id, version_number, db)
    summary = version_summary(version)
    return ReportVersionDetail(
        **summary.model_dump(),
        report_snapshot=version.report_snapshot,
        scorecard_snapshot=version.scorecard_snapshot,
        file_manifest=version.file_manifest or {},
    )


@router.post("/{version_number}/restore", response_model=ReportRead)
def restore_version(
    report_id: int,
    version_number: int,
    db: Session = Depends(get_db),
) -> DueDiligenceReport:
    report = _get_report(report_id, db)
    version = _get_version(report_id, version_number, db)
    snapshot = version.report_snapshot or {}
    manager = db.get(Manager, snapshot.get("manager_id"))
    product = db.get(Product, snapshot.get("product_id"))
    if manager is None or product is None:
        raise HTTPException(status_code=409, detail="历史版本关联的管理人或产品已不存在")
    if product.manager_id != manager.id:
        raise HTTPException(status_code=409, detail="历史版本的管理人与产品关联已失效")

    scorecard = db.scalar(
        select(ReportScorecard).where(ReportScorecard.report_id == report_id)
    )
    created_files: list[Path] = []
    try:
        created_files = restore_report_version(report, version, scorecard, db)
        db.commit()
        db.refresh(report)
        return report
    except ValueError as exc:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        for path in created_files:
            path.unlink(missing_ok=True)
        raise
