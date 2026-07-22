"""Bookmark-driven DOCX generation engine."""

from .compat import BookmarkTemplateEngine
from .generator import DocxGenerator, GenerationResult
from .image_filler import ImageFiller
from .models import FillResult, ParagraphValidation, ReportSummary, StyleSpec

__all__ = [
    "DocxGenerator",
    "BookmarkTemplateEngine",
    "GenerationResult",
    "FillResult",
    "ParagraphValidation",
    "ReportSummary",
    "StyleSpec",
    "ImageFiller",
]
