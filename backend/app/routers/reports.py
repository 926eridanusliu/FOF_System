from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from docx.image.exceptions import UnrecognizedImageError
from docx.image.image import Image as DocxImage
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import storage
from app.database import get_db
from app.models.manager import Manager
from app.models.product import Product
from app.models.generation_job import GenerationJobStatus, ReportGenerationJob
from app.models.report import DueDiligenceReport, ReportStatus
from app.models.report_version import ReportVersion
from app.models.scorecard import ReportScorecard
from app.schemas.generation_job import GenerationJobRead
from app.schemas.report import (
    GenerateResponse,
    ImageUploadResponse,
    ReportCreate,
    ReportRead,
    ReportUpdate,
    ValidationResult,
)
from app.services.document_generator import generate_document
from app.services.generation_queue import enqueue_generation
from app.services.report_validator import manifest_image_fields, validate_report
from app.services.report_versions import (
    create_report_version,
    remove_uncommitted_version_files,
)
from app.services.scorecard import scorecard_snapshot
from app.services.feishu_notifications import create_notification, enqueue_notification


router = APIRouter(prefix="/api/reports", tags=["Reports"])
file_router = APIRouter(prefix="/api/files", tags=["Files"])
MAX_IMAGE_BYTES = 10 * 1024 * 1024
LEGACY_IMAGE_FIELDS = {
    "image_org_structure": "qa_section1_q002_answer",
    "image_performance_comparison": "qa_section2_q119_answer",
}


def _get_report(report_id: int, db: Session) -> DueDiligenceReport:
    report = db.get(DueDiligenceReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="尽调报告不存在")
    return report


def _ensure_relations(manager_id: int, product_id: int, db: Session) -> tuple[Manager, Product]:
    manager = db.get(Manager, manager_id)
    if manager is None:
        raise HTTPException(status_code=404, detail="管理人不存在")
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="产品不存在")
    if product.manager_id != manager_id:
        raise HTTPException(status_code=422, detail="产品不属于所选管理人")
    return manager, product


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)) -> DueDiligenceReport:
    _ensure_relations(payload.manager_id, payload.product_id, db)
    report = DueDiligenceReport(**payload.model_dump(), status=ReportStatus.DRAFT)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("", response_model=list[ReportRead])
def list_reports(
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    manager_id: int | None = Query(default=None, gt=0),
    product_id: int | None = Query(default=None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[DueDiligenceReport]:
    statement = select(DueDiligenceReport)
    if report_status is not None:
        statement = statement.where(DueDiligenceReport.status == report_status)
    if manager_id is not None:
        statement = statement.where(DueDiligenceReport.manager_id == manager_id)
    if product_id is not None:
        statement = statement.where(DueDiligenceReport.product_id == product_id)
    return list(db.scalars(statement.offset(skip).limit(limit)))


@router.get("/{report_id}", response_model=ReportRead)
def get_report(report_id: int, db: Session = Depends(get_db)) -> DueDiligenceReport:
    return _get_report(report_id, db)


@router.put("/{report_id}", response_model=ReportRead)
def update_report(
    report_id: int,
    payload: ReportUpdate,
    db: Session = Depends(get_db),
) -> DueDiligenceReport:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以编辑")
    changes = payload.model_dump(exclude_unset=True)
    for field in ("title", "manager_id", "product_id", "template_type", "content"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} 不能为 null")
    manager_id = changes.get("manager_id", report.manager_id)
    product_id = changes.get("product_id", report.product_id)
    _ensure_relations(manager_id, product_id, db)
    for field, value in changes.items():
        setattr(report, field, value)
    db.commit()
    db.refresh(report)
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: int, db: Session = Depends(get_db)) -> Response:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以删除")
    if db.scalar(
        select(ReportVersion.id).where(ReportVersion.report_id == report_id).limit(1)
    ):
        raise HTTPException(status_code=409, detail="已有历史版本的报告不能删除")
    db.delete(report)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{report_id}/validate", response_model=ValidationResult)
def validate_report_endpoint(
    report_id: int,
    db: Session = Depends(get_db),
) -> ValidationResult:
    report = _get_report(report_id, db)
    return validate_report(report, db.get(Manager, report.manager_id), db.get(Product, report.product_id))


@router.post("/{report_id}/submit", response_model=ReportRead)
def submit_report(report_id: int, db: Session = Depends(get_db)) -> DueDiligenceReport:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以提交")
    validation = validate_report(
        report, db.get(Manager, report.manager_id), db.get(Product, report.product_id)
    )
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.model_dump())
    manager = db.get(Manager, report.manager_id)
    product = db.get(Product, report.product_id)
    if manager is None or product is None:
        raise HTTPException(status_code=409, detail="报告关联的管理人或产品不存在")
    submitted_at = datetime.now(timezone.utc)
    report.status = ReportStatus.SUBMITTED
    report.submitted_at = submitted_at
    version_dir: Path | None = None
    try:
        version, version_dir = create_report_version(
            report,
            manager,
            product,
            db.scalar(
                select(ReportScorecard).where(ReportScorecard.report_id == report_id)
            ),
            submitted_at,
            db,
        )
        db.add(version)
        db.commit()
    except (OSError, ValueError, IntegrityError) as exc:
        db.rollback()
        if version_dir is not None:
            remove_uncommitted_version_files(version_dir)
        raise HTTPException(status_code=409, detail=f"创建历史版本失败：{exc}") from exc
    db.refresh(report)
    return report


@router.post("/{report_id}/archive", response_model=ReportRead)
def archive_report(report_id: int, db: Session = Depends(get_db)) -> DueDiligenceReport:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.SUBMITTED:
        raise HTTPException(status_code=409, detail="只有已提交报告可以归档")
    report.status = ReportStatus.ARCHIVED
    report.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(report)
    return report


@router.post("/{report_id}/generate", response_model=GenerateResponse)
def generate_report(report_id: int, db: Session = Depends(get_db)) -> GenerateResponse:
    report = _get_report(report_id, db)
    manager = db.get(Manager, report.manager_id)
    product = db.get(Product, report.product_id)
    validation = validate_report(
        report, manager, product
    )
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.model_dump())
    scorecard = db.scalar(
        select(ReportScorecard).where(ReportScorecard.report_id == report_id)
    )
    try:
        generated = generate_document(report, scorecard_snapshot(scorecard))
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=500, detail=f"报告生成失败：{exc}") from exc
    report.generated_filename = generated.filename
    if manager is None or product is None:
        raise HTTPException(status_code=409, detail="报告关联的管理人或产品不存在")
    notification = create_notification(
        db,
        report,
        manager,
        product,
        generated.filename,
    )
    db.commit()
    enqueue_notification(notification.id, db.get_bind())
    return GenerateResponse(
        filename=generated.filename,
        download_url=f"/api/files/{generated.filename}",
        validation=generated.validation,
    )


@router.post(
    "/{report_id}/generation-jobs",
    response_model=GenerationJobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a report generation job",
)
def create_generation_job(
    report_id: int,
    db: Session = Depends(get_db),
) -> ReportGenerationJob:
    report = _get_report(report_id, db)
    validation = validate_report(
        report, db.get(Manager, report.manager_id), db.get(Product, report.product_id)
    )
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.model_dump())

    active = db.scalar(
        select(ReportGenerationJob)
        .where(
            ReportGenerationJob.report_id == report_id,
            ReportGenerationJob.status.in_(
                [GenerationJobStatus.QUEUED, GenerationJobStatus.RUNNING]
            ),
        )
        .order_by(ReportGenerationJob.id.desc())
    )
    if active is not None:
        return active

    content_snapshot = dict(report.content or {})
    frozen_scorecard = scorecard_snapshot(
        db.scalar(select(ReportScorecard).where(ReportScorecard.report_id == report_id))
    )
    if frozen_scorecard:
        content_snapshot["__scorecard__"] = frozen_scorecard
    job = ReportGenerationJob(
        report_id=report.id,
        template_type=report.template_type,
        content_snapshot=content_snapshot,
        status=GenerationJobStatus.QUEUED,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueue_generation(job.id, db.get_bind())
    return job


@router.get(
    "/{report_id}/generation-jobs/{job_id}",
    response_model=GenerationJobRead,
    summary="Read report generation progress",
)
def get_generation_job(
    report_id: int,
    job_id: int,
    db: Session = Depends(get_db),
) -> ReportGenerationJob:
    _get_report(report_id, db)
    job = db.get(ReportGenerationJob, job_id)
    if job is None or job.report_id != report_id:
        raise HTTPException(status_code=404, detail="报告生成任务不存在")
    return job


@router.post(
    "/{report_id}/images/{field_name}",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image into a report bookmark",
)
def upload_report_image(
    report_id: int,
    field_name: str,
    payload: bytes = Body(media_type="application/octet-stream"),
    content_type: str | None = Header(default=None, alias="Content-Type"),
    original_filename: str | None = Header(default=None, alias="X-Filename"),
    db: Session = Depends(get_db),
) -> ImageUploadResponse:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以上传或替换图片")
    if field_name not in manifest_image_fields(report.template_type):
        allowed = sorted(manifest_image_fields(report.template_type))
        raise HTTPException(
            status_code=422,
            detail={"message": "该字段不是当前模板的图片书签", "allowed_fields": allowed},
        )
    if not payload:
        raise HTTPException(status_code=422, detail="上传图片不能为空")
    if len(payload) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 10 MB")
    try:
        image = DocxImage.from_blob(payload)
    except (UnrecognizedImageError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=415, detail="文件内容不是受支持的 PNG 或 JPEG 图片") from exc
    if image.ext.lower() not in {"png", "jpg", "jpeg"}:
        raise HTTPException(status_code=415, detail="仅支持 PNG 和 JPEG 图片")
    if content_type not in {"image/png", "image/jpeg", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Content-Type 必须是 image/png 或 image/jpeg")

    report_dir = storage.UPLOAD_DIR / f"report-{report.id}"
    report_dir.mkdir(parents=True, exist_ok=True)
    extension = "jpg" if image.ext.lower() in {"jpg", "jpeg"} else "png"
    stored_filename = f"{field_name}-{uuid4().hex[:12]}.{extension}"
    target = report_dir / stored_filename
    target.write_bytes(payload)

    content = dict(report.content or {})
    legacy_field = LEGACY_IMAGE_FIELDS.get(field_name)
    if legacy_field:
        content.pop(legacy_field, None)
    content[field_name] = {
        "path": storage.upload_relative_path(target),
        "original_filename": original_filename or stored_filename,
    }
    report.content = content
    db.commit()

    return ImageUploadResponse(
        field=field_name,
        filename=stored_filename,
        content_type=image.content_type,
        size=len(payload),
        width_px=image.px_width,
        height_px=image.px_height,
        download_url=f"/api/files/images/{report.id}/{stored_filename}",
    )


@router.delete(
    "/{report_id}/images/{field_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an uploaded image from a draft report",
)
def remove_report_image(
    report_id: int,
    field_name: str,
    db: Session = Depends(get_db),
) -> Response:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以删除图片")
    if field_name not in manifest_image_fields(report.template_type):
        raise HTTPException(status_code=422, detail="该字段不是当前模板的图片书签")
    content = dict(report.content or {})
    image_value = content.pop(field_name, None)
    if image_value is None:
        raise HTTPException(status_code=404, detail="该图片字段尚未上传文件")
    report.content = content
    db.commit()

    raw_path = image_value.get("path") if isinstance(image_value, dict) else image_value
    if raw_path:
        try:
            stored_path = storage.resolve_uploaded_image(raw_path)
        except ValueError:
            stored_path = None
        if stored_path is not None and stored_path.is_file():
            stored_path.unlink()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@file_router.get("/{filename}", response_class=FileResponse)
def download_file(filename: str) -> FileResponse:
    if Path(filename).name != filename or not filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="文件名无效")
    target = storage.GENERATED_DIR / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        target,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


@file_router.get("/images/{report_id}/{filename}", response_class=FileResponse)
def download_uploaded_image(report_id: int, filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="文件名无效")
    target = storage.UPLOAD_DIR / f"report-{report_id}" / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    media_type = "image/png" if target.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(target, media_type=media_type, filename=filename)
