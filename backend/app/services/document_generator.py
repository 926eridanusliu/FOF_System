from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from docx_engine import DocxGenerator
from validator import Validator
from validator.mapper import InputDataMapper

from app import storage
from app.models.report import DueDiligenceReport, ReportTemplateType
from app.services.report_validator import manifest_image_fields
from app.services.scorecard_document import append_scorecard


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = BACKEND_DIR / "app" / "templates"

CONFIGS = {
    ReportTemplateType.PRIVATE_FUND: {
        "profile": "private_2026",
        "template": TEMPLATE_DIR / "private_fund_template.docx",
        "manifest": TEMPLATE_DIR / "private_fund_manifest.json",
    },
    ReportTemplateType.LICENSED_INSTITUTION: {
        "profile": "licensed",
        "template": TEMPLATE_DIR / "licensed_institution_template.docx",
        "manifest": TEMPLATE_DIR / "licensed_institution_manifest.json",
    },
}
FIELD_PREFIXES = ("cover_", "table_", "qa_", "strat_", "attachment_", "image_")


@dataclass
class GeneratedDocument:
    filename: str
    path: Path
    validation: dict[str, Any]


def _prepare_content(report: DueDiligenceReport, profile: str) -> dict[str, Any]:
    raw = dict(report.content or {})
    if not any(key.startswith(FIELD_PREFIXES) for key in raw):
        raw = InputDataMapper().map(raw, profile)
    prepared = {
        key: value
        for key, value in raw.items()
        if key not in {"report_type", "attachment_type", "template_type"}
    }
    for field in manifest_image_fields(report.template_type):
        value = prepared.get(field)
        if not value:
            continue
        raw_path = value.get("path") if isinstance(value, dict) else value
        try:
            image_path = storage.resolve_uploaded_image(raw_path)
        except ValueError:
            image_path = None
        if image_path is None or not image_path.is_file():
            raise ValueError(f"图片字段 {field} 必须使用图片上传接口提供的文件")
        if isinstance(value, dict):
            prepared[field] = {**value, "path": str(image_path)}
        else:
            prepared[field] = str(image_path)
    return prepared


def generate_document(
    report: DueDiligenceReport,
    scorecard_snapshot: dict[str, Any] | None = None,
) -> GeneratedDocument:
    config = CONFIGS[report.template_type]
    storage.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"report-{report.id}-{uuid4().hex[:8]}.docx"
    output_path = storage.GENERATED_DIR / filename
    content = _prepare_content(report, config["profile"])

    generation = DocxGenerator(config["template"], config["manifest"]).generate(
        content,
        output_path,
    )
    if generation.summary.failed_fields or not generation.summary.paragraph_validation.success:
        raise ValueError("Word 生成器报告字段填充失败或段落结构异常")

    validation = Validator(
        config["template"], profile=config["profile"]
    ).validate(output_path, content)
    validation.to_json(output_path.with_name(f"{output_path.stem}_校验报告.json"))
    validation.to_docx(output_path.with_name(f"{output_path.stem}_校验报告.docx"))
    if scorecard_snapshot:
        append_scorecard(output_path, scorecard_snapshot)

    return GeneratedDocument(
        filename=filename,
        path=output_path,
        validation={
            "success": validation.success,
            "matched": validation.matched,
            "missing": validation.missing,
            "mismatched": validation.mismatched,
            "extra": validation.extra,
            "format_issues": validation.format_issue_count,
            "table_issues": validation.table_issue_count,
        },
    )
