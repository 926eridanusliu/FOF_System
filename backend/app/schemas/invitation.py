from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.report import ReportTemplateType


class InvitationCreate(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=30)
    can_edit: bool = True


class InvitationPermissionUpdate(BaseModel):
    can_edit: bool


class InvitationRead(BaseModel):
    id: int
    report_id: int
    expires_at: datetime
    revoked_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime
    last_saved_at: datetime | None
    can_edit: bool
    fill_url: str | None = None


class InvitationCreated(InvitationRead):
    fill_url: str


class PublicReportRead(BaseModel):
    title: str
    manager_name: str
    product_names: list[str]
    template_type: ReportTemplateType
    content: dict[str, Any]
    conclusion: str | None
    risk_items: list[str]
    expires_at: datetime
    submitted_at: datetime | None
    auto_strategy_keys: list[str] = Field(default_factory=list)
    can_edit: bool


class PublicReportUpdate(BaseModel):
    content: dict[str, Any]
    conclusion: str | None = None
    risk_items: list[str] = Field(default_factory=list)
