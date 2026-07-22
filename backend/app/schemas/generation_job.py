from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.generation_job import GenerationJobStatus
from app.models.report import ReportTemplateType
from app.schemas.report import DocumentValidationSummary


class GenerationJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    status: GenerationJobStatus
    template_type: ReportTemplateType
    filename: str | None
    download_url: str | None
    validation: DocumentValidationSummary | None
    error: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
