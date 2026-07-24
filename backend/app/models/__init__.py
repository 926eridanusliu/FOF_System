"""SQLAlchemy models exported for metadata discovery."""

from app.models.manager import Manager
from app.models.product import Product
from app.models.report import DueDiligenceReport, ReportStatus, ReportTemplateType
from app.models.generation_job import GenerationJobStatus, ReportGenerationJob
from app.models.scorecard import ReportScorecard

__all__ = [
    "Manager",
    "Product",
    "DueDiligenceReport",
    "ReportStatus",
    "ReportTemplateType",
    "GenerationJobStatus",
    "ReportGenerationJob",
    "ReportScorecard",
]
