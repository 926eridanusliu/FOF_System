from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import secrets

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import storage
from app.models.invitation import ReportInvitation
from app.models.manager import Manager
from app.models.report import DueDiligenceReport, ReportStatus
from app.routers.reports import (
    _get_report,
    _report_products,
    _sync_identity_and_strategies,
    remove_report_image,
    upload_report_image,
)
from app.schemas.invitation import (
    InvitationCreate,
    InvitationCreated,
    InvitationRead,
    PublicReportRead,
    PublicReportUpdate,
)
from app.schemas.report import ImageUploadResponse
from app.services.report_validator import manifest_fields, manifest_image_fields


router = APIRouter(tags=["Report invitations"])
MAX_PUBLIC_CONTENT_FIELDS = 1000


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _get_invitation(token: str, db: Session, *, editable: bool = False) -> ReportInvitation:
    invitation = db.scalar(
        select(ReportInvitation).where(ReportInvitation.token_hash == _token_hash(token))
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="填写链接不存在")
    now = datetime.now(timezone.utc)
    if invitation.revoked_at is not None:
        raise HTTPException(status_code=410, detail="填写链接已被撤销")
    if _aware(invitation.expires_at) <= now:
        raise HTTPException(status_code=410, detail="填写链接已过期")
    if editable and invitation.submitted_at is not None:
        raise HTTPException(status_code=409, detail="资料已经提交，不能继续修改")
    if editable and invitation.report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="内部报告已提交，不能继续修改")
    return invitation


def _public_report(invitation: ReportInvitation, db: Session) -> PublicReportRead:
    report = invitation.report
    manager = db.get(Manager, report.manager_id)
    products = _report_products(report, db)
    if manager is None or not products:
        raise HTTPException(status_code=409, detail="报告关联资料不完整")
    return PublicReportRead(
        title=report.title,
        manager_name=manager.name,
        product_names=[product.name for product in products],
        template_type=report.template_type,
        content=dict(report.content or {}),
        conclusion=report.conclusion,
        risk_items=list(report.risk_items or []),
        expires_at=invitation.expires_at,
        submitted_at=invitation.submitted_at,
        auto_strategy_keys=report.auto_strategy_keys,
    )


@router.post(
    "/api/reports/{report_id}/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    report_id: int,
    payload: InvitationCreate,
    db: Session = Depends(get_db),
) -> InvitationCreated:
    report = _get_report(report_id, db)
    if report.status != ReportStatus.DRAFT:
        raise HTTPException(status_code=409, detail="只有草稿报告可以创建填写链接")
    raw_token = secrets.token_urlsafe(32)
    invitation = ReportInvitation(
        report_id=report.id,
        token_hash=_token_hash(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    frontend_url = os.getenv("PUBLIC_FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
    return InvitationCreated(
        id=invitation.id,
        report_id=report.id,
        expires_at=invitation.expires_at,
        revoked_at=None,
        submitted_at=None,
        created_at=invitation.created_at,
        last_saved_at=None,
        fill_url=f"{frontend_url}/fill/{raw_token}",
    )


@router.get(
    "/api/reports/{report_id}/invitations",
    response_model=list[InvitationRead],
)
def list_invitations(
    report_id: int, db: Session = Depends(get_db)
) -> list[ReportInvitation]:
    _get_report(report_id, db)
    return list(
        db.scalars(
            select(ReportInvitation)
            .where(ReportInvitation.report_id == report_id)
            .order_by(ReportInvitation.id.desc())
        )
    )


@router.delete(
    "/api/reports/{report_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invitation(
    report_id: int, invitation_id: int, db: Session = Depends(get_db)
) -> Response:
    invitation = db.get(ReportInvitation, invitation_id)
    if invitation is None or invitation.report_id != report_id:
        raise HTTPException(status_code=404, detail="填写链接不存在")
    if invitation.revoked_at is None:
        invitation.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/public/fill/{token}", response_model=PublicReportRead)
def read_public_report(token: str, db: Session = Depends(get_db)) -> PublicReportRead:
    return _public_report(_get_invitation(token, db), db)


@router.put("/api/public/fill/{token}", response_model=PublicReportRead)
def update_public_report(
    token: str,
    payload: PublicReportUpdate,
    db: Session = Depends(get_db),
) -> PublicReportRead:
    invitation = _get_invitation(token, db, editable=True)
    report = invitation.report
    if len(payload.content) > MAX_PUBLIC_CONTENT_FIELDS:
        raise HTTPException(status_code=422, detail="填写字段数量超过限制")
    allowed = manifest_fields(report.template_type)
    unknown = sorted(set(payload.content) - allowed)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"存在模板之外的字段：{', '.join(unknown[:5])}",
        )
    incoming = dict(payload.content)
    for field in manifest_image_fields(report.template_type):
        if field not in incoming and field in (report.content or {}):
            incoming[field] = report.content[field]
    report.content = incoming
    report.conclusion = payload.conclusion
    report.risk_items = payload.risk_items
    manager = db.get(Manager, report.manager_id)
    products = _report_products(report, db)
    if manager is None or not products:
        raise HTTPException(status_code=409, detail="报告关联资料不完整")
    _sync_identity_and_strategies(report, manager, products)
    invitation.last_saved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invitation)
    return _public_report(invitation, db)


@router.post("/api/public/fill/{token}/submit", response_model=PublicReportRead)
def submit_public_report(token: str, db: Session = Depends(get_db)) -> PublicReportRead:
    invitation = _get_invitation(token, db, editable=True)
    invitation.submitted_at = datetime.now(timezone.utc)
    invitation.last_saved_at = invitation.submitted_at
    db.commit()
    db.refresh(invitation)
    return _public_report(invitation, db)


@router.post(
    "/api/public/fill/{token}/images/{field_name}",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_public_image(
    token: str,
    field_name: str,
    payload: bytes = Body(media_type="application/octet-stream"),
    content_type: str | None = Header(default=None, alias="Content-Type"),
    original_filename: str | None = Header(default=None, alias="X-Filename"),
    db: Session = Depends(get_db),
) -> ImageUploadResponse:
    invitation = _get_invitation(token, db, editable=True)
    result = upload_report_image(
        invitation.report_id,
        field_name,
        payload,
        content_type,
        original_filename,
        db,
    )
    invitation.last_saved_at = datetime.now(timezone.utc)
    db.commit()
    return result


@router.get("/api/public/fill/{token}/images/{field_name}")
def read_public_image(
    token: str,
    field_name: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    invitation = _get_invitation(token, db)
    if field_name not in manifest_image_fields(invitation.report.template_type):
        raise HTTPException(status_code=404, detail="图片字段不存在")
    value = (invitation.report.content or {}).get(field_name)
    raw_path = value.get("path") if isinstance(value, dict) else value
    try:
        image_path = storage.resolve_uploaded_image(raw_path)
    except ValueError:
        image_path = None
    if image_path is None or not image_path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(image_path)


@router.delete(
    "/api/public/fill/{token}/images/{field_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_public_image(
    token: str,
    field_name: str,
    db: Session = Depends(get_db),
) -> Response:
    invitation = _get_invitation(token, db, editable=True)
    result = remove_report_image(invitation.report_id, field_name, db)
    invitation.last_saved_at = datetime.now(timezone.utc)
    db.commit()
    return result
