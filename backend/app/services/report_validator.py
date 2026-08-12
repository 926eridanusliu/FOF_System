import json
import re
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
TABLE_DEFINITIONS_FILE = TEMPLATE_DIR / "table_definitions.json"
CONTENT_METADATA_FIELDS = {"report_type", "attachment_type", "template_type", "__dynamic_tables"}

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


@lru_cache
def manifest_entries(template_type: ReportTemplateType) -> tuple[dict[str, Any], ...]:
    payload = json.loads(MANIFEST_FILES[template_type].read_text(encoding="utf-8"))
    return tuple(payload["bookmarks"])


@lru_cache
def table_definitions(template_type: ReportTemplateType) -> dict[str, dict[str, Any]]:
    payload = json.loads(TABLE_DEFINITIONS_FILE.read_text(encoding="utf-8"))
    key = template_type.value if hasattr(template_type, "value") else str(template_type)
    return payload[key]


def _filled(value: Any) -> bool:
    return value not in (None, "", False, "□", "0", 0, [])


def _field_optional(prompt: str) -> bool:
    return bool(re.search(r"[（(]如有[）)]", prompt or ""))


def _format_error(value: Any, input_type: str) -> str | None:
    if not _filled(value):
        return None
    text = str(value).strip()
    if input_type == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", text):
        return "邮箱格式不正确"
    if input_type == "phone" and not re.fullmatch(r"[+()\d\s-]{6,30}", text):
        return "电话号码格式不正确"
    if input_type == "url" and not re.fullmatch(r"https?://\S+", text):
        return "网址需以 http:// 或 https:// 开头"
    if input_type == "year" and not re.fullmatch(r"(?:19|20)\d{2}", text):
        return "年份应为四位数字"
    if input_type in {"integer", "number", "percent"}:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "应填写数字"
        if input_type == "integer" and not number.is_integer():
            return "应填写整数"
    return None


def _normalize_table_input(value: Any, input_type: str) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip().replace(",", "")
    if input_type == "percent":
        return re.sub(r"[％%]\s*$", "", text).strip()
    if input_type in {"integer", "number"}:
        match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(?:人|年|次|只|家|亿元|亿)?", text)
        return match.group(1) if match else text
    return value


def normalize_dynamic_tables(
    template_type: ReportTemplateType, dynamic_tables: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    normalized: dict[str, list[dict[str, Any]]] = {}
    definitions = table_definitions(template_type)
    for table, rows in dynamic_tables.items():
        definition = definitions.get(str(table))
        if not definition or not isinstance(rows, list):
            continue
        normalized_rows = []
        for offset, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            actual_row = int(definition["start_row"]) + offset
            converted = {}
            for column in definition["columns"]:
                col = str(column["col"])
                value = row.get(col, row.get(column["col"], ""))
                input_type = definition.get("row_input_types", {}).get(str(actual_row), column.get("input", "text"))
                converted[col] = _normalize_table_input(value, input_type)
            normalized_rows.append(converted)
        normalized[str(table)] = normalized_rows
    return normalized


def _table_rows(content: dict[str, Any], table: str, definition: dict[str, Any]) -> list[dict[str, Any]]:
    dynamic = content.get("__dynamic_tables")
    if isinstance(dynamic, dict) and isinstance(dynamic.get(table), list):
        return [row for row in dynamic[table] if isinstance(row, dict)]
    rows = []
    for offset in range(int(definition["template_rows"])):
        actual = int(definition["start_row"]) + offset
        rows.append({
            str(column["col"]): content.get(f"table_{table}_row{actual}_col{column['col']}", "")
            for column in definition["columns"]
        })
    if definition["mode"] == "dynamic":
        while len(rows) > 1 and not any(_filled(value) for value in rows[-1].values()):
            rows.pop()
    return rows


def validate_online_content(template_type: ReportTemplateType, content: dict[str, Any]) -> ValidationResult:
    """Strict validation used before a manager submits the online questionnaire."""
    errors: list[ValidationIssue] = []
    selected = {
        key for key, value in content.items()
        if key.startswith("cover_strategy_") and key != "cover_strategy_other_text" and _filled(value)
    }
    has_other_strategy = _filled(content.get("cover_strategy_other_text"))
    branches = {
        "quant": {"cover_strategy_stock_index_enhanced", "cover_strategy_stock_quant", "cover_strategy_market_neutral", "cover_strategy_t0"},
        "cta": {"cover_strategy_futures_quant_trend", "cover_strategy_futures_discretionary"},
        "bond": {"cover_strategy_bond_pure", "cover_strategy_bond_enhanced", "cover_strategy_bond_composite", "cover_strategy_convertible_bond"},
        "option": {"cover_strategy_futures_options_arbitrage"},
    }
    active_branches = {name for name, keys in branches.items() if selected & keys}
    if not selected and not has_other_strategy:
        errors.append(ValidationIssue(field="content.cover_strategy_*", message="至少选择一种投资策略"))

    for field in manifest_entries(template_type):
        name = field["bookmark"]
        category = field.get("type", "")
        if category in {"cover_checkbox", "table_cell"} or name == "cover_strategy_other_text":
            continue
        if category == "table_cutoff_date":
            definition = table_definitions(template_type).get(str(field.get("table")), {})
            strategy_keys = set(definition.get("strategy_keys", []))
            if strategy_keys and not (strategy_keys & selected):
                continue
        if field.get("strategy") and field["strategy"] not in active_branches:
            continue
        if not _field_optional(field.get("prompt", "")) and not _filled(content.get(name)):
            errors.append(ValidationIssue(field=f"content.{name}", message=f"{field.get('prompt') or name}为必填项"))

    for table, definition in table_definitions(template_type).items():
        strategy_keys = set(definition.get("strategy_keys", []))
        if strategy_keys and not (strategy_keys & selected):
            continue
        rows = _table_rows(content, table, definition)
        if definition["mode"] == "dynamic" and not rows:
            errors.append(ValidationIssue(field=f"content.__dynamic_tables.{table}", message=f"{definition['title']}至少填写一行"))
            continue
        optional_rows = set(definition.get("optional_rows", []))
        row_types = definition.get("row_input_types", {})
        for offset, row in enumerate(rows):
            actual_row = int(definition["start_row"]) + offset
            for column in definition["columns"]:
                value = row.get(str(column["col"]), row.get(column["col"], ""))
                label = column["label"]
                row_label = definition.get("row_labels", {}).get(str(actual_row), f"第{offset + 1}行")
                if actual_row not in optional_rows and not _filled(value):
                    errors.append(ValidationIssue(field=f"content.__dynamic_tables.{table}.{offset}.{column['col']}", message=f"{definition['title']}：{row_label}的{label}不能为空"))
                    continue
                error = _format_error(value, row_types.get(str(actual_row), column.get("input", "text")))
                if error:
                    errors.append(ValidationIssue(field=f"content.__dynamic_tables.{table}.{offset}.{column['col']}", message=f"{definition['title']}：{row_label}的{label}{error}"))
    return ValidationResult(valid=not errors, errors=errors, warnings=[])


def _has_selected_strategy(content: dict[str, Any]) -> bool:
    return _filled(content.get("cover_strategy_other_text")) or any(
        key.startswith("cover_strategy_")
        and key != "cover_strategy_other_text"
        and value not in (None, "", False, "□", "0", 0)
        for key, value in content.items()
    )


def validate_report(
    report: DueDiligenceReport,
    manager: Manager | None,
    product: Product | list[Product] | None,
) -> ValidationResult:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    content = report.content or {}

    if manager is None:
        errors.append(ValidationIssue(field="manager_id", message="关联的管理人不存在"))
    products = product if isinstance(product, list) else ([product] if product else [])
    if not products:
        errors.append(ValidationIssue(field="product_id", message="关联的产品不存在"))
    elif any(item.manager_id != report.manager_id for item in products):
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
    expected_product_name = "、".join(item.name for item in products)
    if products and content.get("cover_product_name") not in (None, "", expected_product_name):
        warnings.append(
            ValidationIssue(
                field="content.cover_product_name",
                message="报告显示的产品名称与关联产品不同；将按报告中导入或填写的名称生成",
            )
        )

    known_fields = manifest_fields(report.template_type)
    unknown = sorted(set(content) - known_fields - CONTENT_METADATA_FIELDS)
    if unknown:
        errors.append(
            ValidationIssue(
                field="content",
                message=f"存在 {len(unknown)} 个模板书签清单之外的字段：{', '.join(unknown[:5])}",
            )
        )

    for field in manifest_image_fields(report.template_type):
        value = content.get(field)
        if not value:
            continue
        raw_path = value.get("path") if isinstance(value, dict) else value
        try:
            image_path = storage.resolve_uploaded_image(raw_path)
        except ValueError:
            image_path = None
        if image_path is None or not image_path.is_file():
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
