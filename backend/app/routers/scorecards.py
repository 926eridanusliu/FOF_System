from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import storage
from app.database import get_db
from app.models.report import DueDiligenceReport, ReportStatus
from app.models.scorecard import ReportScorecard
from app.schemas.scorecard import ScorecardCalculateRequest, ScorecardRead
from app.services.scorecard import (
    calculate_scorecard,
    load_nav_file,
    parse_nav_upload,
    preview_rows,
)


router = APIRouter(prefix="/api/reports", tags=["Scorecards"])
MAX_NAV_BYTES = 20 * 1024 * 1024
NAV_CONTENT_TYPES = {
    "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/csv",
}


def _get_report(report_id: int, db: Session) -> DueDiligenceReport:
    report = db.get(DueDiligenceReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="尽调报告不存在")
    return report


def _get_scorecard(report_id: int, db: Session) -> ReportScorecard | None:
    return db.scalar(
        select(ReportScorecard).where(ReportScorecard.report_id == report_id)
    )


def _scorecard_read(report_id: int, scorecard: ReportScorecard | None) -> ScorecardRead:
    if scorecard is None:
        return ScorecardRead(report_id=report_id)
    return ScorecardRead(
        report_id=report_id,
        nav_original_filename=scorecard.nav_original_filename,
        nav_sheet_name=scorecard.nav_sheet_name,
        nav_columns=list(scorecard.nav_columns or []),
        detected_columns=dict(scorecard.detected_columns or {}),
        nav_preview=list(scorecard.nav_preview or []),
        calculation_inputs=dict(scorecard.calculation_inputs or {}),
        metrics=dict(scorecard.metrics or {}),
        score_rows=list(scorecard.score_rows or []),
        quantitative_score=scorecard.quantitative_score,
        qualitative_score=scorecard.qualitative_score,
        compliance_deduction=scorecard.compliance_deduction,
        total_score=scorecard.total_score,
        admitted=scorecard.admitted,
        calculated_at=scorecard.calculated_at,
    )


def _stored_path(report_id: int, stored_filename: str | None) -> Path | None:
    if not stored_filename or Path(stored_filename).name != stored_filename:
        return None
    target = storage.NAV_UPLOAD_DIR / f"report-{report_id}" / stored_filename
    return target if target.is_file() else None


@router.get("/{report_id}/scorecard", response_model=ScorecardRead)
def get_scorecard(report_id: int, db: Session = Depends(get_db)) -> ScorecardRead:
    _get_report(report_id, db)
    return _scorecard_read(report_id, _get_scorecard(report_id, db))


@router.post(
    "/{report_id}/scorecard/nav",
    response_model=ScorecardRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and inspect a NAV workbook",
)
def upload_nav_file(
    report_id: int,
    payload: bytes = Body(media_type="application/octet-stream"),
    content_type: str | None = Header(default=None, alias="Content-Type"),
    original_filename: str | None = Header(default=None, alias="X-Filename"),
    db: Session = Depends(get_db),
) -> ScorecardRead:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以上传或替换净值文件")
    if not payload:
        raise HTTPException(status_code=422, detail="净值文件不能为空")
    if len(payload) > MAX_NAV_BYTES:
        raise HTTPException(status_code=413, detail="净值文件不能超过 20 MB")
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_content_type not in NAV_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="仅支持 .xlsx 或 .csv 净值文件")

    fallback_name = "nav.csv" if normalized_content_type in {"text/csv", "application/csv"} else "nav.xlsx"
    decoded_name = unquote(original_filename or fallback_name)
    safe_name = Path(decoded_name).name
    suffix = Path(safe_name).suffix.lower()
    try:
        table = parse_nav_upload(payload, suffix)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report_dir = storage.NAV_UPLOAD_DIR / f"report-{report_id}"
    report_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"nav-{uuid4().hex[:12]}{suffix}"
    target = report_dir / stored_filename
    target.write_bytes(payload)

    scorecard = _get_scorecard(report_id, db)
    old_path = _stored_path(report_id, scorecard.nav_stored_filename) if scorecard else None
    if scorecard is None:
        scorecard = ReportScorecard(report_id=report_id)
        db.add(scorecard)
    scorecard.nav_original_filename = safe_name
    scorecard.nav_stored_filename = stored_filename
    scorecard.nav_sheet_name = table.sheet_name
    scorecard.nav_columns = table.columns
    scorecard.detected_columns = table.detected_columns
    scorecard.nav_preview = preview_rows(table)
    scorecard.calculation_inputs = {}
    scorecard.metrics = {}
    scorecard.score_rows = []
    scorecard.quantitative_score = None
    scorecard.qualitative_score = None
    scorecard.compliance_deduction = None
    scorecard.total_score = None
    scorecard.admitted = None
    scorecard.calculated_at = None
    db.commit()
    db.refresh(scorecard)
    if old_path and old_path != target:
        old_path.unlink(missing_ok=True)
    return _scorecard_read(report_id, scorecard)


@router.post(
    "/{report_id}/scorecard/calculate",
    response_model=ScorecardRead,
    summary="Calculate quantitative and qualitative admission scores",
)
def calculate_report_scorecard(
    report_id: int,
    payload: ScorecardCalculateRequest,
    db: Session = Depends(get_db),
) -> ScorecardRead:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以重新计算评分卡")
    scorecard = _get_scorecard(report_id, db)
    if scorecard is None:
        raise HTTPException(status_code=422, detail="请先上传净值文件")
    nav_path = _stored_path(report_id, scorecard.nav_stored_filename)
    if nav_path is None:
        raise HTTPException(status_code=422, detail="已上传的净值文件不存在，请重新上传")
    try:
        result = calculate_scorecard(load_nav_file(nav_path), payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    scorecard.calculation_inputs = payload.model_dump()
    scorecard.metrics = result["metrics"]
    scorecard.score_rows = result["score_rows"]
    scorecard.quantitative_score = result["quantitative_score"]
    scorecard.qualitative_score = result["qualitative_score"]
    scorecard.compliance_deduction = result["compliance_deduction"]
    scorecard.total_score = result["total_score"]
    scorecard.admitted = result["admitted"]
    scorecard.calculated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(scorecard)
    return _scorecard_read(report_id, scorecard)


@router.delete(
    "/{report_id}/scorecard/nav",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a draft report NAV file and calculated scorecard",
)
def delete_nav_file(
    report_id: int,
    db: Session = Depends(get_db),
) -> Response:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以删除净值文件")
    scorecard = _get_scorecard(report_id, db)
    if scorecard is None:
        raise HTTPException(status_code=404, detail="尚未上传净值文件")
    target = _stored_path(report_id, scorecard.nav_stored_filename)
    db.delete(scorecard)
    db.commit()
    if target:
        target.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
