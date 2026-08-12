from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from docx.image.exceptions import UnrecognizedImageError
from docx.image.image import Image as DocxImage
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import storage
from app.database import get_db
from app.models.manager import Manager
from app.models.product import Product
from app.models.generation_job import GenerationJobStatus, ReportGenerationJob
from app.models.report import DueDiligenceReport, ReportProduct, ReportStatus
from app.models.report_version import ReportVersion
from app.models.scorecard import ReportScorecard
from app.schemas.generation_job import GenerationJobRead
from app.schemas.deletion import DeletionRequest
from app.schemas.report import (
    GenerateResponse,
    ImageUploadResponse,
    JsonImportConflict,
    JsonImportResult,
    ReportCreate,
    ReportRead,
    ReportUpdate,
    ValidationResult,
)
from app.services.document_generator import generate_document
from app.services.document_generator import CONFIGS, FIELD_PREFIXES
from app.services.generation_queue import enqueue_generation
from app.services.report_validator import manifest_image_fields, validate_report
from app.services.report_versions import (
    create_report_version,
    remove_uncommitted_version_files,
)
from app.services.feishu_notifications import create_notification, enqueue_notification
from app.services.report_validator import manifest_fields, normalize_dynamic_tables
from validator.mapper import InputDataMapper
from app.services.deletions import add_deletion, is_deleted, visible_entity


router = APIRouter(prefix="/api/reports", tags=["Reports"])
file_router = APIRouter(prefix="/api/files", tags=["Files"])
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 5 * 1024 * 1024
LEGACY_IMAGE_FIELDS = {
    "image_org_structure": "qa_section1_q002_answer",
    "image_performance_comparison": "qa_section2_q119_answer",
}


def _get_report(report_id: int, db: Session) -> DueDiligenceReport:
    report = db.get(DueDiligenceReport, report_id)
    if (
        report is None
        or is_deleted("report", report_id, db)
        or is_deleted("manager", report.manager_id, db)
    ):
        raise HTTPException(status_code=404, detail="尽调报告不存在")
    return report


def _ensure_relations(manager_id: int, product_ids: list[int], db: Session) -> tuple[Manager, list[Product]]:
    manager = db.get(Manager, manager_id)
    if manager is None or is_deleted("manager", manager_id, db):
        raise HTTPException(status_code=404, detail="管理人不存在")
    if not product_ids:
        raise HTTPException(status_code=422, detail="至少选择一只产品")
    products: list[Product] = []
    for product_id in dict.fromkeys(product_ids):
        product = db.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"产品 #{product_id} 不存在")
        if product.manager_id != manager_id:
            raise HTTPException(status_code=422, detail="产品不属于所选管理人")
        products.append(product)
    return manager, products


def _set_report_products(
    report: DueDiligenceReport, products: list[Product]
) -> None:
    report.report_products.clear()
    report.report_products.extend(
        ReportProduct(product=product, ordinal=index)
        for index, product in enumerate(products)
    )
    report.product_id = products[0].id


def _report_products(report: DueDiligenceReport, db: Session) -> list[Product]:
    products = [link.product for link in report.report_products]
    if not products:
        primary = db.get(Product, report.product_id)
        return [primary] if primary else []
    return products


def _sync_identity_and_strategies(
    report: DueDiligenceReport,
    manager: Manager,
    products: list[Product],
    *,
    preserve_product_name: bool = False,
) -> None:
    content = dict(report.content or {})
    content["cover_manager_name"] = manager.name
    content["table_1_row0_col1"] = manager.name
    if not preserve_product_name or not content.get("cover_product_name"):
        content["cover_product_name"] = "、".join(product.name for product in products)
    for product in products:
        for strategy_key in product.strategy_keys:
            if strategy_key == "cover_strategy_other":
                content["cover_strategy_other_text"] = (
                    content.get("cover_strategy_other_text") or "其他"
                )
            else:
                content[strategy_key] = True
    report.content = content


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: Session = Depends(get_db)) -> DueDiligenceReport:
    product_ids = payload.product_ids or [payload.product_id]
    manager, products = _ensure_relations(payload.manager_id, product_ids, db)
    values = payload.model_dump(exclude={"product_ids"})
    values["product_id"] = products[0].id
    report = DueDiligenceReport(**values, status=ReportStatus.DRAFT)
    _set_report_products(report, products)
    _sync_identity_and_strategies(report, manager, products)
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
    statement = select(DueDiligenceReport).where(
        visible_entity("report", DueDiligenceReport.id),
        visible_entity("manager", DueDiligenceReport.manager_id),
    )
    if report_status is not None:
        statement = statement.where(DueDiligenceReport.status == report_status)
    if manager_id is not None:
        statement = statement.where(DueDiligenceReport.manager_id == manager_id)
    if product_id is not None:
        statement = statement.where(
            DueDiligenceReport.report_products.any(ReportProduct.product_id == product_id)
            | (DueDiligenceReport.product_id == product_id)
        )
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
    for field in ("title", "manager_id", "product_id", "product_ids", "template_type", "content"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} 不能为 null")
    manager_id = changes.get("manager_id", report.manager_id)
    product_ids = changes.pop("product_ids", None)
    if product_ids is None:
        product_ids = report.product_ids
        if "product_id" in changes and changes["product_id"] not in product_ids:
            product_ids = [changes["product_id"], *product_ids]
    manager, products = _ensure_relations(manager_id, product_ids, db)
    for field, value in changes.items():
        setattr(report, field, value)
    _set_report_products(report, products)
    _sync_identity_and_strategies(report, manager, products)
    db.commit()
    db.refresh(report)
    return report


@router.post(
    "/{report_id}/import-json",
    response_model=JsonImportResult,
    summary="Preview or apply JSON data to a draft report",
)
async def import_report_json(
    report_id: int,
    request: Request,
    apply: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> JsonImportResult:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以导入 JSON")
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=422, detail="JSON 文件不能为空")
    if len(payload) > MAX_JSON_BYTES:
        raise HTTPException(status_code=413, detail="JSON 文件不能超过 5 MB")
    try:
        parsed = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"JSON 格式错误：{exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="JSON 顶层必须是对象")

    source_format = "report-content"
    candidate: dict = parsed
    if isinstance(parsed.get("content"), dict):
        candidate = parsed["content"]
        source_format = "report-export"
    elif not any(str(key).startswith(FIELD_PREFIXES) for key in parsed):
        source_format = "legacy-questionnaire"
        profile = str(CONFIGS[report.template_type]["profile"])
        candidate = InputDataMapper().map(parsed, profile)

    dynamic_tables = candidate.get("__dynamic_tables") if isinstance(candidate, dict) else None
    if not isinstance(dynamic_tables, dict):
        dynamic_tables = None

    allowed = manifest_fields(report.template_type)
    imported: dict = {}
    ignored: list[str] = []
    for raw_key, value in candidate.items():
        key = str(raw_key)
        if key == "__dynamic_tables":
            continue
        if key not in allowed:
            ignored.append(key)
            continue
        if key in manifest_image_fields(report.template_type):
            ignored.append(key)
            continue
        if key.startswith("cover_strategy_") and key != "cover_strategy_other_text":
            value = value in (True, 1, "1", "true", "True", "是", "☑")
        imported[key] = value

    current = dict(report.content or {})
    conflicts = [
        JsonImportConflict(field=key, current=current[key], incoming=value)
        for key, value in imported.items()
        if key in current
        and current[key] not in (None, "", False, [], {})
        and current[key] != value
    ]
    if apply:
        merged = {**current, **imported}
        if source_format == "legacy-questionnaire":
            merged.pop("__dynamic_tables", None)
        if dynamic_tables is not None:
            merged["__dynamic_tables"] = normalize_dynamic_tables(report.template_type, dynamic_tables)
        report.content = merged
        manager = db.get(Manager, report.manager_id)
        products = _report_products(report, db)
        if manager is None or not products:
            raise HTTPException(status_code=409, detail="报告关联的管理人或产品不存在")
        _sync_identity_and_strategies(
            report,
            manager,
            products,
            preserve_product_name=True,
        )
        db.commit()
        db.refresh(report)

    return JsonImportResult(
        source_format=source_format,
        recognized_count=len(imported),
        ignored_fields=sorted(ignored),
        conflicts=conflicts,
        imported_content=imported,
        applied=apply,
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int,
    payload: DeletionRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Response:
    report = _get_report(report_id, db)
    has_versions = bool(db.scalar(
        select(ReportVersion.id).where(ReportVersion.report_id == report_id).limit(1)
    ))
    if (report.status != ReportStatus.DRAFT or has_versions) and payload is None:
        raise HTTPException(status_code=409, detail="正式报告或已有历史版本的报告，删除时必须填写原因")
    add_deletion(
        entity_type="report",
        entity_id=report.id,
        display_name=report.title,
        reason=payload.reason if payload else "删除草稿报告",
        snapshot={
            "title": report.title,
            "manager_id": report.manager_id,
            "product_ids": report.product_ids,
            "template_type": report.template_type.value,
            "status": report.status.value,
            "has_versions": has_versions,
            "generated_filename": report.generated_filename,
        },
        db=db,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{report_id}/validate", response_model=ValidationResult)
def validate_report_endpoint(
    report_id: int,
    db: Session = Depends(get_db),
) -> ValidationResult:
    report = _get_report(report_id, db)
    return validate_report(report, db.get(Manager, report.manager_id), _report_products(report, db))


@router.post("/{report_id}/submit", response_model=ReportRead)
def submit_report(report_id: int, db: Session = Depends(get_db)) -> DueDiligenceReport:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以提交")
    products = _report_products(report, db)
    validation = validate_report(report, db.get(Manager, report.manager_id), products)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.model_dump())
    manager = db.get(Manager, report.manager_id)
    product = products[0] if products else None
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
    products = _report_products(report, db)
    validation = validate_report(report, manager, products)
    product = products[0] if products else None
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.model_dump())
    try:
        generated = generate_document(report)
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
        report, db.get(Manager, report.manager_id), _report_products(report, db)
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
