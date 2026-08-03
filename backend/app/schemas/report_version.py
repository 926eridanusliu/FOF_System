from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.report import ReportTemplateType


class ReportVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    version_number: int
    title: str
    template_type: ReportTemplateType
    total_score: float | None = None
    submitted_at: datetime
    created_at: datetime
    snapshot_hash: str


class ReportVersionDetail(ReportVersionSummary):
    report_snapshot: dict[str, Any]
    scorecard_snapshot: dict[str, Any] | None = None
    file_manifest: dict[str, Any] = Field(default_factory=dict)


class VersionDiffItem(BaseModel):
    field_path: str
    label: str
    change_type: Literal["added", "removed", "changed"]
    before: Any = None
    after: Any = None


class ReportVersionComparison(BaseModel):
    report_id: int
    from_version: int
    to_version: int
    change_count: int
    changes: list[VersionDiffItem] = Field(default_factory=list)
