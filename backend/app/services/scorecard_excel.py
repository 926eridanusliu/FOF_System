from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

from app import storage


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "private_product_admission_scorecard.xlsx"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

SCORE_ITEMS: tuple[dict[str, Any], ...] = (
    {"key": "one_year_return", "category": "定量指标（收益能力）", "indicator": "近1年收益率", "maximum": 13, "cell": "D4"},
    {"key": "relative_return", "category": "定量指标（收益能力）", "indicator": "相对收益", "maximum": 13, "cell": "D5", "take_higher": True},
    {"key": "long_term_return", "category": "定量指标（收益能力）", "indicator": "近3/5年年化收益率", "maximum": 10, "cell": "D6"},
    {"key": "monthly_win_rate", "category": "定量指标（收益稳定性）", "indicator": "月度胜率", "maximum": 8, "cell": "D7"},
    {"key": "max_drawdown", "category": "定量指标（风险指标）", "indicator": "最大回撤", "maximum": 10, "cell": "D8"},
    {"key": "sharpe_ratio", "category": "定量指标（风险指标）", "indicator": "夏普比率", "maximum": 13, "cell": "D9"},
    {"key": "calmar_ratio", "category": "定量指标（风险指标）", "indicator": "卡玛比率", "maximum": 8, "cell": "D10"},
    {"key": "managed_products", "category": "定性指标", "indicator": "管理产品数量及规模", "maximum": 12, "cell": "D11"},
    {"key": "investment_manager", "category": "定性指标", "indicator": "投资经理", "maximum": 6, "cell": "D12"},
    {"key": "research_team", "category": "定性指标", "indicator": "投研团队", "maximum": 5, "cell": "D13"},
    {"key": "team_stability", "category": "定性指标", "indicator": "团队稳定性及激励机制", "maximum": 3, "cell": "D14"},
    {"key": "allocation_value", "category": "定性指标", "indicator": "资产配置价值", "maximum": 4, "cell": "D15"},
    {"key": "risk_control", "category": "定性指标", "indicator": "风控体系", "maximum": 4, "cell": "D16"},
    {"key": "coinvestment", "category": "定性指标", "indicator": "跟投比例", "maximum": 4, "cell": "D17"},
    {"key": "compliance_deduction", "category": "扣分项", "indicator": "合规事件（扣分项）", "maximum": None, "cell": "D18"},
)
SCORE_ITEM_BY_KEY = {item["key"]: item for item in SCORE_ITEMS}


def scorecard_template_definition() -> list[dict[str, Any]]:
    return [dict(item) for item in SCORE_ITEMS]


def validate_manual_scores(raw_scores: dict[str, Any]) -> dict[str, float]:
    missing = [item["key"] for item in SCORE_ITEMS if item["key"] not in raw_scores]
    if missing:
        labels = [SCORE_ITEM_BY_KEY[key]["indicator"] for key in missing]
        raise ValueError(f"请填写全部评分项：{'、'.join(labels)}")
    scores: dict[str, float] = {}
    for item in SCORE_ITEMS:
        value = raw_scores[item["key"]]
        if isinstance(value, bool):
            raise ValueError(f"{item['indicator']}必须填写数字")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{item['indicator']}必须填写数字") from exc
        if number < 0:
            raise ValueError(f"{item['indicator']}不能小于0")
        maximum = item["maximum"]
        if maximum is not None and number > maximum:
            raise ValueError(f"{item['indicator']}不能超过满分{maximum}分")
        scores[item["key"]] = round(number, 2)
    return scores


def summarize_manual_scores(raw_scores: dict[str, Any]) -> dict[str, Any]:
    scores = validate_manual_scores(raw_scores)
    quantitative = max(scores["one_year_return"], scores["relative_return"]) + sum(
        scores[key] for key in ("long_term_return", "monthly_win_rate", "max_drawdown", "sharpe_ratio", "calmar_ratio")
    )
    qualitative = sum(scores[key] for key in (
        "managed_products", "investment_manager", "research_team", "team_stability",
        "allocation_value", "risk_control", "coinvestment",
    ))
    deduction = scores["compliance_deduction"]
    total = quantitative + qualitative - deduction
    return {
        "manual_scores": scores,
        "score_rows": [{
            "category": item["category"], "indicator": item["indicator"], "value": "人工评分",
            "score": scores[item["key"]], "maximum": item["maximum"] if item["maximum"] is not None else "扣分",
            "basis": "与近1年收益率取高计入定量得分" if item.get("take_higher") else "员工依据尽调内容及模板打分说明录入",
        } for item in SCORE_ITEMS],
        "quantitative_score": round(quantitative, 2),
        "qualitative_score": round(qualitative, 2),
        "compliance_deduction": round(deduction, 2),
        "total_score": round(total, 2),
        "admitted": total >= 60,
    }


def _replace_numeric_cell(root: ElementTree.Element, reference: str, value: float) -> None:
    cell = root.find(f".//{{{SHEET_NS}}}c[@r='{reference}']")
    if cell is None:
        raise ValueError(f"评分卡模板缺少单元格 {reference}")
    cell.attrib.pop("t", None)
    for child in list(cell):
        if child.tag != f"{{{SHEET_NS}}}v":
            cell.remove(child)
    value_element = cell.find(f"{{{SHEET_NS}}}v")
    if value_element is None:
        value_element = ElementTree.SubElement(cell, f"{{{SHEET_NS}}}v")
    value_element.text = f"{value:g}"


def render_scorecard_workbook(raw_scores: dict[str, Any], output_path: Path) -> Path:
    summary = summarize_manual_scores(raw_scores)
    if not TEMPLATE_PATH.is_file():
        raise ValueError("准入打分卡模板不存在")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(TEMPLATE_PATH, "r") as source:
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in source.namelist():
            raise ValueError("准入打分卡模板缺少工作表")
        root = ElementTree.fromstring(source.read(sheet_name))
        for item in SCORE_ITEMS:
            _replace_numeric_cell(root, item["cell"], summary["manual_scores"][item["key"]])
        _replace_numeric_cell(root, "D19", summary["total_score"])
        sheet_bytes = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as target:
            for entry in source.infolist():
                target.writestr(entry, sheet_bytes if entry.filename == sheet_name else source.read(entry.filename))
    output_path.write_bytes(buffer.getvalue())
    return output_path


def generate_scorecard_workbook(report_id: int, raw_scores: dict[str, Any]) -> Path:
    filename = f"scorecard-report-{report_id}-{uuid4().hex[:8]}.xlsx"
    return render_scorecard_workbook(raw_scores, storage.SCORECARD_GENERATED_DIR / filename)
