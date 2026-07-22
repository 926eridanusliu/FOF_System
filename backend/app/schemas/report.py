from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.report import ReportStatus, ReportTemplateType


class ReportBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    manager_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    template_type: ReportTemplateType = ReportTemplateType.PRIVATE_FUND
    content: dict[str, Any] = Field(default_factory=dict)
    conclusion: str | None = None
    risk_items: list[str] = Field(default_factory=list)


class ReportCreate(ReportBase):
    pass


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    manager_id: int | None = Field(default=None, gt=0)
    product_id: int | None = Field(default=None, gt=0)
    template_type: ReportTemplateType | None = None
    content: dict[str, Any] | None = None
    conclusion: str | None = None
    risk_items: list[str] | None = None


class ReportRead(ReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ReportStatus
    generated_filename: str | None
    submitted_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ValidationIssue(BaseModel):
    field: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class DocumentValidationSummary(BaseModel):
    success: bool
    matched: int
    missing: int
    mismatched: int
    extra: int
    format_issues: int
    table_issues: int


class GenerateResponse(BaseModel):
    filename: str
    download_url: str
    validation: DocumentValidationSummary


class ImageUploadResponse(BaseModel):
    field: str
    filename: str
    content_type: str
    size: int
    width_px: int
    height_px: int
    download_url: str
