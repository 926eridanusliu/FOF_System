from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
import math
import posixpath
import re
from pathlib import Path
from statistics import median, stdev
from typing import Any, Iterable
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from app.schemas.scorecard import QualitativeScoreInputs, ScorecardCalculateRequest


DATE_ALIASES = ("日期", "净值日期", "估值日期", "date", "nav date")
NAV_ALIASES = (
    "累计净值",
    "复权净值",
    "产品净值",
    "单位净值",
    "净值",
    "nav",
    "cumulative nav",
)
BENCHMARK_ALIASES = (
    "基准净值",
    "业绩基准",
    "比较基准",
    "基准指数",
    "benchmark",
    "benchmark nav",
)
SOURCE_RULES = {
    "name": "开源证券私募产品准入打分卡（波动率区分版）",
    "source_file": "副本开源证券私募产品准入打分卡-评分调整版.xlsx",
    "source_sha256": "40695c6e18db092ca18fab988cd03e12930a5677a684f4bab1b6da0d8aab7a36",
    "admission_score": 60,
}


@dataclass(frozen=True)
class NavTable:
    sheet_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    detected_columns: dict[str, str | None]


@dataclass(frozen=True)
class NavPoint:
    date: date
    nav: float
    benchmark: float | None


def _normalize_header(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _detect_column(columns: Iterable[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {column: _normalize_header(column) for column in columns}
    for alias in aliases:
        exact = [column for column, value in normalized.items() if value == alias]
        if exact:
            return exact[0]
    for alias in aliases:
        partial = [column for column, value in normalized.items() if alias in value]
        if partial:
            return partial[0]
    return None


def _unique_headers(values: Iterable[Any]) -> list[str]:
    headers: list[str] = []
    counts: dict[str, int] = {}
    for index, value in enumerate(values, 1):
        base = str(value).strip() if value is not None and str(value).strip() else f"未命名列{index}"
        counts[base] = counts.get(base, 0) + 1
        headers.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return headers


def _locate_header(matrix: list[list[Any]]) -> tuple[int, list[str]]:
    for index, row in enumerate(matrix[:20]):
        headers = _unique_headers(row)
        if _detect_column(headers, DATE_ALIASES) and _detect_column(headers, NAV_ALIASES):
            return index, headers
    first_nonempty = next(
        ((index, row) for index, row in enumerate(matrix[:20]) if any(value is not None for value in row)),
        None,
    )
    if first_nonempty is None:
        raise ValueError("净值文件没有可读取的数据")
    index, row = first_nonempty
    return index, _unique_headers(row)


def _rows_from_matrix(matrix: list[list[Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    header_index, columns = _locate_header(matrix)
    rows: list[dict[str, Any]] = []
    for raw in matrix[header_index + 1 :]:
        padded = list(raw) + [None] * max(0, len(columns) - len(raw))
        record = {column: padded[index] for index, column in enumerate(columns)}
        if any(value not in (None, "") for value in record.values()):
            rows.append(record)
    if not rows:
        raise ValueError("净值文件只有表头，没有数据行")
    return columns, rows


def _decode_csv(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 编码无法识别，请保存为 UTF-8 或 GB18030")


def _xlsx_text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def _xlsx_column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    index = 0
    for character in letters.upper():
        index = index * 26 + ord(character) - ord("A") + 1
    return max(0, index - 1)


def _xlsx_date_styles(archive: ZipFile) -> set[int]:
    if "xl/styles.xml" not in archive.namelist():
        return set()
    root = ElementTree.fromstring(archive.read("xl/styles.xml"))
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    custom_formats = {
        int(item.attrib["numFmtId"]): item.attrib.get("formatCode", "")
        for item in root.findall("x:numFmts/x:numFmt", namespace)
    }
    builtin_dates = set(range(14, 23)) | {45, 46, 47}
    date_styles: set[int] = set()
    for index, cell_format in enumerate(root.findall("x:cellXfs/x:xf", namespace)):
        format_id = int(cell_format.attrib.get("numFmtId", "0"))
        format_code = custom_formats.get(format_id, "").lower()
        date_code = re.sub(r'\\.|"[^"]*"|\[[^\]]*\]', "", format_code)
        if format_id in builtin_dates or (
            ("y" in date_code or "d" in date_code)
            and any(token in date_code for token in ("/", "-", "."))
        ):
            date_styles.add(index)
    return date_styles


def _read_xlsx_matrix(payload: bytes) -> tuple[str, list[list[Any]]]:
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise ValueError("文件不是有效的 .xlsx 工作簿") from exc
    with archive:
        names = set(archive.namelist())
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(names):
            raise ValueError("文件缺少 Excel 工作簿结构")
        main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{{{package_rel_ns}}}Relationship")
        }
        sheet = next(
            (
                item
                for item in workbook.findall(f".//{{{main_ns}}}sheet")
                if item.attrib.get("state", "visible") == "visible"
            ),
            None,
        )
        if sheet is None:
            raise ValueError("工作簿没有可见工作表")
        relationship_id = sheet.attrib.get(f"{{{rel_ns}}}id")
        target = relationship_targets.get(relationship_id or "")
        if not target:
            raise ValueError("工作表关系无效")
        sheet_path = posixpath.normpath(
            target.lstrip("/") if target.startswith("/xl/") else posixpath.join("xl", target)
        )
        if sheet_path not in names:
            raise ValueError("工作表内容不存在")

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [
                _xlsx_text(item)
                for item in shared_root.findall(f"{{{main_ns}}}si")
            ]
        date_styles = _xlsx_date_styles(archive)
        workbook_properties = workbook.find(f"{{{main_ns}}}workbookPr")
        date_1904 = (
            workbook_properties is not None
            and workbook_properties.attrib.get("date1904") in {"1", "true", "True"}
        )
        epoch = datetime(1904, 1, 1) if date_1904 else datetime(1899, 12, 30)

        sheet_root = ElementTree.fromstring(archive.read(sheet_path))
        matrix: list[list[Any]] = []
        for row in sheet_root.findall(f".//{{{main_ns}}}sheetData/{{{main_ns}}}row"):
            values: list[Any] = []
            for cell in row.findall(f"{{{main_ns}}}c"):
                column_index = _xlsx_column_index(cell.attrib.get("r", "A1"))
                if len(values) <= column_index:
                    values.extend([None] * (column_index + 1 - len(values)))
                cell_type = cell.attrib.get("t", "n")
                raw = cell.find(f"{{{main_ns}}}v")
                raw_text = raw.text if raw is not None else ""
                if cell_type == "s":
                    value: Any = shared_strings[int(raw_text)] if raw_text else ""
                elif cell_type == "inlineStr":
                    value = _xlsx_text(cell.find(f"{{{main_ns}}}is"))
                elif cell_type in {"str", "e"}:
                    value = raw_text
                elif cell_type == "b":
                    value = raw_text == "1"
                elif raw_text == "":
                    value = None
                else:
                    number = float(raw_text)
                    style_index = int(cell.attrib.get("s", "0"))
                    if style_index in date_styles:
                        value = (epoch + timedelta(days=number)).date()
                    else:
                        value = int(number) if number.is_integer() else number
                values[column_index] = value
            matrix.append(values)
        return sheet.attrib.get("name", "Sheet1"), matrix


def parse_nav_upload(payload: bytes, suffix: str) -> NavTable:
    suffix = suffix.lower()
    if suffix == ".csv":
        matrix = [list(row) for row in csv.reader(StringIO(_decode_csv(payload)))]
        sheet_name = "CSV"
    elif suffix == ".xlsx":
        sheet_name, matrix = _read_xlsx_matrix(payload)
    else:
        raise ValueError("仅支持 .xlsx 或 .csv 净值文件；旧版 .xls 请先另存为 .xlsx")

    columns, rows = _rows_from_matrix(matrix)
    detected = {
        "date": _detect_column(columns, DATE_ALIASES),
        "nav": _detect_column(columns, NAV_ALIASES),
        "benchmark": _detect_column(columns, BENCHMARK_ALIASES),
    }
    return NavTable(sheet_name, columns, rows, detected)


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"无法识别日期：{text or '<空>'}")


def _parse_number(value: Any, column: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{column} 包含布尔值，不能作为净值")
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value or "").strip().replace(",", "")
        if text.endswith("%"):
            number = float(text[:-1]) / 100
        else:
            number = float(text)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{column} 必须是大于 0 的有限数值")
    return number


def nav_points(
    table: NavTable,
    date_column: str,
    nav_column: str,
    benchmark_column: str | None,
) -> list[NavPoint]:
    required = [date_column, nav_column] + ([benchmark_column] if benchmark_column else [])
    missing = [column for column in required if column not in table.columns]
    if missing:
        raise ValueError(f"净值文件不存在列：{'、'.join(missing)}")
    points_by_date: dict[date, NavPoint] = {}
    errors: list[str] = []
    for row_number, row in enumerate(table.rows, 2):
        if row.get(date_column) in (None, "") or row.get(nav_column) in (None, ""):
            continue
        try:
            point_date = _parse_date(row[date_column])
            benchmark = (
                _parse_number(row[benchmark_column], benchmark_column)
                if benchmark_column and row.get(benchmark_column) not in (None, "")
                else None
            )
            points_by_date[point_date] = NavPoint(
                point_date,
                _parse_number(row[nav_column], nav_column),
                benchmark,
            )
        except (TypeError, ValueError) as exc:
            errors.append(f"第 {row_number} 行：{exc}")
            if len(errors) >= 5:
                break
    if errors:
        raise ValueError("；".join(errors))
    points = sorted(points_by_date.values(), key=lambda point: point.date)
    if len(points) < 2:
        raise ValueError("至少需要两个不同日期的有效净值")
    return points


def _window(points: list[NavPoint], days: int | None) -> list[NavPoint]:
    if days is None:
        return points
    cutoff = points[-1].date - timedelta(days=days)
    anchor = max((index for index, point in enumerate(points) if point.date <= cutoff), default=0)
    return points[anchor:]


def _annualized_return(points: list[NavPoint], use_benchmark: bool = False) -> float:
    first = points[0].benchmark if use_benchmark else points[0].nav
    last = points[-1].benchmark if use_benchmark else points[-1].nav
    if first is None or last is None:
        raise ValueError("所选期间的基准净值存在空值")
    elapsed_days = (points[-1].date - points[0].date).days
    if elapsed_days <= 0:
        raise ValueError("净值日期区间必须大于 0 天")
    return (last / first) ** (365.25 / elapsed_days) - 1


def _periodic_returns(points: list[NavPoint]) -> list[float]:
    return [current.nav / previous.nav - 1 for previous, current in zip(points, points[1:])]


def _annualized_volatility(points: list[NavPoint]) -> float:
    returns = _periodic_returns(points)
    if len(returns) < 2:
        return 0.0
    day_gaps = [
        max(1, (current.date - previous.date).days)
        for previous, current in zip(points, points[1:])
    ]
    return stdev(returns) * math.sqrt(365.25 / median(day_gaps))


def _max_drawdown(points: list[NavPoint]) -> float:
    peak = points[0].nav
    maximum = 0.0
    for point in points:
        peak = max(peak, point.nav)
        maximum = max(maximum, (peak - point.nav) / peak)
    return maximum


def _monthly_win_rate(points: list[NavPoint]) -> tuple[float, int]:
    month_ends: dict[tuple[int, int], NavPoint] = {}
    for point in points:
        month_ends[(point.date.year, point.date.month)] = point
    closes = [month_ends[key] for key in sorted(month_ends)]
    returns = [current.nav / previous.nav - 1 for previous, current in zip(closes, closes[1:])][-12:]
    if not returns:
        raise ValueError("净值跨度不足以计算月度胜率")
    return sum(value > 0 for value in returns) / len(returns), len(returns)


def _volatility_band(volatility: float) -> str:
    if volatility < 0.03:
        return "low"
    if volatility < 0.10:
        return "medium"
    return "high"


def _score_floor(value: float, thresholds: list[tuple[float, float]]) -> float:
    for threshold, score in thresholds:
        if value >= threshold:
            return score
    return 0.0


def _score_ceiling(value: float, thresholds: list[tuple[float, float]]) -> float:
    for threshold, score in thresholds:
        if value <= threshold:
            return score
    return 0.0


ONE_YEAR_RULES = {
    "low": [(0.05, 13), (0.03, 9), (0.01, 5)],
    "medium": [(0.10, 13), (0.05, 9), (0.03, 5)],
    "high": [(0.15, 13), (0.10, 9), (0.05, 5)],
}
LONG_TERM_RULES = {
    "low": [(0.03, 10), (0.02, 7), (0.01, 4)],
    "medium": [(0.06, 10), (0.04, 7), (0.02, 4)],
    "high": [(0.08, 10), (0.06, 7), (0.04, 4)],
}
WIN_RATE_RULES = {
    "low": [(0.91, 8), (0.83, 6), (0.75, 4)],
    "medium": [(0.75, 8), (0.67, 6), (0.58, 4)],
    "high": [(0.67, 8), (0.58, 6), (0.50, 4)],
}
DRAWDOWN_RULES = {
    "low": [(0.01, 10), (0.02, 8), (0.04, 5)],
    "medium": [(0.05, 10), (0.08, 8), (0.12, 5)],
    "high": [(0.10, 10), (0.15, 8), (0.20, 5)],
}
SHARPE_RULES = {
    "low": [(1.5, 13), (1.0, 9), (0.5, 5)],
    "medium": [(1.2, 13), (0.8, 9), (0.4, 5)],
    "high": [(1.0, 13), (0.6, 9), (0.2, 5)],
}
CALMAR_RULES = {
    "low": [(2.0, 8), (1.5, 6), (1.0, 3)],
    "medium": [(1.5, 8), (1.0, 6), (0.5, 3)],
    "high": [(1.0, 8), (0.5, 6), (0.0, 3)],
}


def _row(category: str, indicator: str, value: str, score: float, maximum: float | str, basis: str) -> dict[str, Any]:
    return {
        "category": category,
        "indicator": indicator,
        "value": value,
        "score": round(score, 2),
        "maximum": maximum,
        "basis": basis,
    }


def _qualitative_rows(inputs: QualitativeScoreInputs) -> tuple[list[dict[str, Any]], float, float]:
    scale_high = {"bond": 50, "cta_t0": 2, "other": 5}[inputs.strategy_scale_group]
    scale_mid = {"bond": 30, "cta_t0": 1, "other": 3}[inputs.strategy_scale_group]
    if inputs.active_product_count <= 1:
        scale_score = 0
    elif inputs.managed_scale_100m >= scale_high:
        scale_score = 10
    elif inputs.managed_scale_100m >= scale_mid:
        scale_score = 5
    else:
        scale_score = 0
    headcount_score = 2 if inputs.company_headcount >= 10 else 1 if inputs.company_headcount >= 5 else 0
    size_score = scale_score + headcount_score

    if (
        inputs.manager_same_strategy_years >= 5
        and inputs.manager_industry_years >= 10
        and inputs.manager_philosophy_level == "complete"
        and inputs.manager_profile_stable
    ):
        manager_score = 6
    elif (
        inputs.manager_same_strategy_years >= 3
        and inputs.manager_industry_years >= 8
        and inputs.manager_philosophy_level in {"complete", "mature"}
        and inputs.manager_profile_stable
    ):
        manager_score = 4
    elif (
        inputs.manager_same_strategy_years >= 1
        and inputs.manager_industry_years >= 5
        and inputs.manager_philosophy_level in {"complete", "mature", "clear"}
        and inputs.manager_profile_stable
    ):
        manager_score = 3
    else:
        manager_score = 0

    if (
        inputs.research_headcount >= 8
        and inputs.research_background_match
        and inputs.core_research_experience_years >= 5
    ):
        research_score = 5
    elif (
        inputs.research_headcount >= 3
        and inputs.research_background_match
        and inputs.core_research_experience_years >= 3
    ):
        research_score = 4
    elif (
        inputs.research_headcount >= 3
        and inputs.core_research_experience_years > 3
        and inputs.research_live_track_record
    ):
        research_score = 3
    else:
        research_score = 0

    if inputs.core_departures_3y == 0 and inputs.incentive_level == "long_term":
        stability_score = 3
    elif inputs.core_departures_1y == 0 and inputs.incentive_level in {"long_term", "clear"}:
        stability_score = 2
    elif inputs.core_departures_1y <= 1 and inputs.incentive_level in {"long_term", "clear", "basic"}:
        stability_score = 1
    else:
        stability_score = 0

    capacity_ratio = inputs.current_strategy_scale_100m / inputs.theoretical_capacity_100m
    capacity_score = 2 if capacity_ratio <= 0.5 else 1 if capacity_ratio <= 0.9 else 0
    differentiation_score = {"significant": 2, "partial": 1, "none": 0}[inputs.differentiation_level]
    allocation_score = capacity_score + differentiation_score

    system_score = {"complete": 3, "substantial": 2, "basic": 1, "none": 0}[inputs.risk_system_level]
    risk_team_score = (
        1
        if inputs.risk_team_headcount >= 2 and inputs.risk_team_experience_years >= 3
        else 0
    )
    risk_score = system_score + risk_team_score

    if inputs.manager_coinvest_percent >= 5 and inputs.manager_coinvest_lock_years >= 1:
        coinvest_score = 4
    elif inputs.manager_coinvest_percent >= 2:
        coinvest_score = 3
    elif inputs.manager_coinvest_percent >= 1:
        coinvest_score = 2
    elif inputs.core_personal_coinvest:
        coinvest_score = 1
    else:
        coinvest_score = 0

    deduction = (
        inputs.regulatory_events_3y * 5
        + inputs.negative_or_litigation_events_3y * 3
    )
    rows = [
        _row("定性指标", "管理产品数量及规模", f"{inputs.managed_scale_100m:g}亿元；{inputs.company_headcount}人", size_score, 12, "规模10分与人数2分合计"),
        _row("定性指标", "投资经理", f"同策略{inputs.manager_same_strategy_years:g}年；从业{inputs.manager_industry_years:g}年", manager_score, 6, "按业绩年限、从业年限、理念及履历稳定性分档"),
        _row("定性指标", "投研团队", f"{inputs.research_headcount}人；核心经验{inputs.core_research_experience_years:g}年", research_score, 5, "按人数、专业匹配、核心经验及实盘验证分档"),
        _row("定性指标", "团队稳定性及激励机制", f"近1年离职{inputs.core_departures_1y}人；近3年{inputs.core_departures_3y}人", stability_score, 3, "按核心离职人数与激励机制分档"),
        _row("定性指标", "资产配置价值", f"容量使用率{capacity_ratio:.1%}", allocation_score, 4, "策略容量2分与差异化2分合计"),
        _row("定性指标", "风控体系", f"风控团队{inputs.risk_team_headcount}人", risk_score, 4, "制度建设3分与团队配备1分合计"),
        _row("定性指标", "跟投比例", f"管理人{inputs.manager_coinvest_percent:g}%；锁定{inputs.manager_coinvest_lock_years:g}年", coinvest_score, 4, "按管理人或核心投研跟投分档"),
        _row("扣分项", "合规事件", f"处罚/处分{inputs.regulatory_events_3y}次；负面/涉诉{inputs.negative_or_litigation_events_3y}次", -deduction, "扣分", "近3年处罚每次扣5分，重大负面或涉诉每次扣3分"),
    ]
    qualitative = sum(row["score"] for row in rows if row["category"] == "定性指标")
    return rows, float(qualitative), float(deduction)


def calculate_scorecard(table: NavTable, request: ScorecardCalculateRequest) -> dict[str, Any]:
    points = nav_points(
        table,
        request.date_column,
        request.nav_column,
        request.benchmark_column if request.benchmark_mode == "benchmark" else None,
    )
    history_days = (points[-1].date - points[0].date).days
    if history_days < 182:
        raise ValueError("评分卡要求产品至少存续满 6 个月")

    one_year_points = _window(points, 365)
    one_year_return = _annualized_return(one_year_points)
    volatility = _annualized_volatility(one_year_points)
    band = _volatility_band(volatility)
    max_drawdown = _max_drawdown(one_year_points)
    risk_free_rate = request.risk_free_rate_percent / 100
    sharpe = (
        (one_year_return - risk_free_rate) / volatility
        if volatility > 0
        else None
    )
    calmar = one_year_return / max_drawdown if max_drawdown > 0 else None
    win_rate, month_count = _monthly_win_rate(one_year_points)

    one_year_score = _score_floor(one_year_return, ONE_YEAR_RULES[band])
    if history_days < 365:
        one_year_score *= 0.5
    if request.benchmark_mode == "benchmark":
        if not request.benchmark_column:
            raise ValueError("选择相对收益模式时必须指定基准净值列")
        benchmark_return = _annualized_return(one_year_points, use_benchmark=True)
        relative_return = one_year_return - benchmark_return
        relative_score = _score_floor(relative_return, [(0.03, 13), (0.01, 9), (0.0, 5)])
    else:
        benchmark_return = None
        relative_return = None
        relative_score = 13.0 if one_year_return > 0 else 0.0
    return_score = max(one_year_score, relative_score)

    if history_days >= round(365.25 * 5):
        longterm_label = "近5年年化收益率"
        longterm_points = _window(points, round(365.25 * 5))
        longterm_multiplier = 1.0
    elif history_days >= round(365.25 * 3):
        longterm_label = "近3年年化收益率"
        longterm_points = _window(points, round(365.25 * 3))
        longterm_multiplier = 1.0
    else:
        longterm_label = "成立以来年化收益率"
        longterm_points = points
        longterm_multiplier = 0.8
    longterm_return = _annualized_return(longterm_points)
    longterm_score = _score_floor(longterm_return, LONG_TERM_RULES[band]) * longterm_multiplier
    win_score = _score_floor(win_rate, WIN_RATE_RULES[band]) * (0.8 if history_days < 365 else 1.0)
    drawdown_score = _score_ceiling(max_drawdown, DRAWDOWN_RULES[band])
    sharpe_score = _score_floor(sharpe, SHARPE_RULES[band]) if sharpe is not None else 0.0
    if calmar is None:
        calmar_score = 8.0 if one_year_return > 0 else 0.0
    else:
        calmar_score = _score_floor(calmar, CALMAR_RULES[band])

    band_label = {"low": "低波动", "medium": "中波动", "high": "高波动"}[band]
    quantitative_rows = [
        _row(
            "定量指标",
            "近1年收益率/相对收益（取高）",
            f"{one_year_return:.2%}" + (f"；超额{relative_return:.2%}" if relative_return is not None else "；无明确基准"),
            return_score,
            13,
            f"{band_label}档；绝对收益{one_year_score:g}分，相对收益{relative_score:g}分，取高",
        ),
        _row("定量指标", longterm_label, f"{longterm_return:.2%}", longterm_score, 10, f"{band_label}档" + ("；不足3年×0.8" if longterm_multiplier < 1 else "")),
        _row("定量指标", "月度胜率", f"{win_rate:.2%}（{month_count}个月）", win_score, 8, f"{band_label}档" + ("；不足1年×0.8" if history_days < 365 else "")),
        _row("定量指标", "最大回撤", f"{max_drawdown:.2%}", drawdown_score, 10, f"近1年/成立以来；{band_label}档"),
        _row("定量指标", "夏普比率", "—" if sharpe is None else f"{sharpe:.2f}", sharpe_score, 13, f"无风险利率{risk_free_rate:.2%}；{band_label}档"),
        _row("定量指标", "卡玛比率", "∞" if calmar is None and one_year_return > 0 else "—" if calmar is None else f"{calmar:.2f}", calmar_score, 8, f"年化收益/最大回撤；{band_label}档"),
    ]
    qualitative_rows, qualitative_score, deduction = _qualitative_rows(request.qualitative)
    quantitative_score = sum(row["score"] for row in quantitative_rows)
    total_score = quantitative_score + qualitative_score - deduction
    metrics = {
        "source_rules": SOURCE_RULES,
        "start_date": points[0].date.isoformat(),
        "end_date": points[-1].date.isoformat(),
        "observations": len(points),
        "history_days": history_days,
        "volatility_band": band,
        "volatility_band_label": band_label,
        "one_year_annualized_return": round(one_year_return, 10),
        "benchmark_annualized_return": None if benchmark_return is None else round(benchmark_return, 10),
        "relative_annualized_return": None if relative_return is None else round(relative_return, 10),
        "longterm_label": longterm_label,
        "longterm_annualized_return": round(longterm_return, 10),
        "annualized_volatility": round(volatility, 10),
        "monthly_win_rate": round(win_rate, 10),
        "monthly_observations": month_count,
        "max_drawdown": round(max_drawdown, 10),
        "sharpe_ratio": None if sharpe is None else round(sharpe, 10),
        "calmar_ratio": None if calmar is None else round(calmar, 10),
        "risk_free_rate": risk_free_rate,
    }
    return {
        "suggested_manual_scores": {
            "one_year_return": round(one_year_score, 2), "relative_return": round(relative_score, 2),
            "long_term_return": round(longterm_score, 2), "monthly_win_rate": round(win_score, 2),
            "max_drawdown": round(drawdown_score, 2), "sharpe_ratio": round(sharpe_score, 2),
            "calmar_ratio": round(calmar_score, 2), "managed_products": qualitative_rows[0]["score"],
            "investment_manager": qualitative_rows[1]["score"], "research_team": qualitative_rows[2]["score"],
            "team_stability": qualitative_rows[3]["score"], "allocation_value": qualitative_rows[4]["score"],
            "risk_control": qualitative_rows[5]["score"], "coinvestment": qualitative_rows[6]["score"],
            "compliance_deduction": deduction,
        },
        "metrics": metrics,
        "score_rows": quantitative_rows + qualitative_rows,
        "quantitative_score": round(quantitative_score, 2),
        "qualitative_score": round(qualitative_score, 2),
        "compliance_deduction": round(deduction, 2),
        "total_score": round(total_score, 2),
        "admitted": total_score >= SOURCE_RULES["admission_score"],
    }


def preview_rows(table: NavTable, limit: int = 5) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for row in table.rows[:limit]:
        preview.append(
            {
                key: value.isoformat() if isinstance(value, (date, datetime)) else value
                for key, value in row.items()
            }
        )
    return preview


def load_nav_file(path: Path) -> NavTable:
    return parse_nav_upload(path.read_bytes(), path.suffix)


def scorecard_snapshot(scorecard: Any | None) -> dict[str, Any] | None:
    if scorecard is None or scorecard.calculated_at is None or not scorecard.score_rows:
        return None
    return {
        "metrics": dict(scorecard.metrics or {}),
        "score_rows": list(scorecard.score_rows or []),
        "quantitative_score": scorecard.quantitative_score,
        "qualitative_score": scorecard.qualitative_score,
        "compliance_deduction": scorecard.compliance_deduction,
        "total_score": scorecard.total_score,
        "admitted": scorecard.admitted,
        "calculated_at": scorecard.calculated_at.isoformat(),
    }
