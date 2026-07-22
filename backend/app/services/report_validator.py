import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app import storage
from app.models.manager import Manager
from app.models.product import Product
from app.models.report import DueDiligenceReport, ReportTemplateType
from app.schemas.report import ValidationIssue, ValidationResult


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
MANIFEST_FILES = {
    ReportTemplateType.PRIVATE_FUND: TEMPLATE_DIR / "private_fund_manifest.json",
    ReportTemplateType.LICENSED_INSTITUTION: TEMPLATE_DIR / "licensed_institution_manifest.json",
}

# These are the shared identity fields present in both existing minimum-data
# fixtures from phase three. No synthetic report values are introduced here.
REQUIRED_CONTENT_FIELDS = (
    "cover_manager_name",
    "cover_product_name",
    "cover_investigator",
    "cover_report_date",
    "table_1_row0_col1",
)


@lru_cache
def manifest_fields(template_type: ReportTemplateType) -> frozenset[str]:
    payload = json.loads(MANIFEST_FILES[template_type].read_text(encoding="utf-8"))
    return frozenset(item["bookmark"] for item in payload["bookmarks"])


@lru_cache
def manifest_image_fields(template_type: ReportTemplateType) -> frozenset[str]:
    payload = json.loads(MANIFEST_FILES[template_type].read_text(encoding="utf-8"))
    return frozenset(
        item["bookmark"] for item in payload["bookmarks"] if item.get("type") == "image"
    )


def _has_selected_strategy(content: dict[str, Any]) -> bool:
    return any(
        key.startswith("cover_strategy_")
        and key != "cover_strategy_other_text"
        and value not in (None, "", False, "□", "0", 0)
        for key, value in content.items()
    )


def validate_report(
    report: DueDiligenceReport,
    manager: Manager | None,
    product: Product | None,
) -> ValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    content = report.content or {}

    if manager is None:
        errors.append(ValidationIssue(field="manager_id", message="关联的管理人不存在"))
    if product is None:
        errors.append(ValidationIssue(field="product_id", message="关联的产品不存在"))
    elif product.manager_id != report.manager_id:
        errors.append(
            ValidationIssue(field="product_id", message="产品不属于报告所选管理人")
        )

    for field in REQUIRED_CONTENT_FIELDS:
        if content.get(field) in (None, ""):
            errors.append(ValidationIssue(field=f"content.{field}", message="必填字段不能为空"))

    if not _has_selected_strategy(content):
        errors.append(
            ValidationIssue(field="content.cover_strategy_*", message="至少选择一种投资策略")
        )

    if manager is not None:
        if content.get("cover_manager_name") not in (None, "", manager.name):
            errors.append(
                ValidationIssue(
                    field="content.cover_manager_name",
                    message="报告中的管理人名称与关联管理人不一致",
                )
            )
        if content.get("table_1_row0_col1") not in (None, "", manager.name):
            errors.append(
                ValidationIssue(
                    field="content.table_1_row0_col1",
                    message="表格中的管理人名称与关联管理人不一致",
                )
            )
    if product is not None and content.get("cover_product_name") not in (
        None,
        "",
        product.name,
    ):
        errors.append(
            ValidationIssue(
                field="content.cover_product_name",
                message="报告中的产品名称与关联产品不一致",
            )
        )

    known_fields = manifest_fields(report.template_type)
    metadata_fields = {"report_type", "attachment_type", "template_type"}
    unknown = sorted(set(content) - known_fields - metadata_fields)
    if unknown:
        errors.append(
            ValidationIssue(
                field="content",
                message=f"存在 {len(unknown)} 个模板书签清单之外的字段：{', '.join(unknown[:5])}",
            )
        )

    upload_root = storage.UPLOAD_DIR.resolve()
    for field in manifest_image_fields(report.template_type):
        value = content.get(field)
        if not value:
            continue
        raw_path = value.get("path") if isinstance(value, dict) else value
        image_path = Path(str(raw_path)).expanduser().resolve()
        if not image_path.is_relative_to(upload_root) or not image_path.is_file():
            errors.append(
                ValidationIssue(
                    field=f"content.{field}",
                    message="图片必须通过报告图片上传接口重新上传",
                )
            )

    missing_count = len(known_fields - set(content))
    if missing_count:
        warnings.append(
            ValidationIssue(
                field="content",
                message=f"有 {missing_count} 个可选模板字段未提供，将保留为空",
            )
        )
    if not report.conclusion:
        warnings.append(ValidationIssue(field="conclusion", message="尚未填写尽调结论"))
    if not report.risk_items:
        warnings.append(ValidationIssue(field="risk_items", message="尚未填写风险项"))

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
