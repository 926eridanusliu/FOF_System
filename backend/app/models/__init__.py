"""SQLAlchemy models exported for metadata discovery."""

from app.models.manager import Manager
from app.models.product import Product, ProductStrategy
from app.models.report import DueDiligenceReport, ReportProduct, ReportStatus, ReportTemplateType
from app.models.invitation import ReportInvitation
from app.models.generation_job import GenerationJobStatus, ReportGenerationJob
from app.models.scorecard import ReportScorecard
from app.models.report_version import ReportVersion
from app.models.notification import NotificationStatus, ReportNotification

__all__ = [
    "Manager",
    "Product",
    "ProductStrategy",
    "DueDiligenceReport",
    "ReportProduct",
    "ReportInvitation",
    "ReportStatus",
    "ReportTemplateType",
    "GenerationJobStatus",
    "ReportGenerationJob",
    "ReportScorecard",
    "ReportVersion",
    "NotificationStatus",
    "ReportNotification",
]
