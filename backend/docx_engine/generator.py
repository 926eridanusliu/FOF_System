from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .checkbox_filler import CheckboxFiller
from .cover_filler import CoverFiller
from .image_filler import ImageFiller
from .models import FillResult, ParagraphValidation, ReportSummary, StyleSpec
from .package import DocxPackage
from .qa_filler import QASectionFiller
from .report import FillReportWriter
from .style_manager import StyleManager
from .table_filler import TableFiller


@dataclass
class GenerationResult:
    document: Path
    report_docx: Path
    report_json: Path
    summary: ReportSummary


class DocxGenerator:
    """Orchestrates all bookmark-driven fill modules."""

    def __init__(
        self,
        template_path: str | Path,
        manifest_path: str | Path,
        *,
        styles: dict[str, StyleSpec] | None = None,
        paragraph_tolerance: int = 0,
    ):
        self.template_path = Path(template_path)
        self.manifest_path = Path(manifest_path)
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.paragraph_tolerance = paragraph_tolerance
        self.styles = styles or {}

    def generate(
        self,
        data: dict[str, Any] | str | Path,
        output_path: str | Path,
        *,
        report_docx_path: str | Path | None = None,
        report_json_path: str | Path | None = None,
    ) -> GenerationResult:
        if isinstance(data, (str, Path)):
            data = json.loads(Path(data).read_text(encoding="utf-8"))
        values, merges, applicability = self._normalize_data(data)
        package = DocxPackage(self.template_path)
        try:
            before = package.paragraph_count()
            bookmarks = package.bookmark_index()
            styles = StyleManager(package, self.styles)
            cover = CoverFiller(package, bookmarks, styles)
            tables = TableFiller(package, bookmarks, styles)
            checkboxes = CheckboxFiller(package, bookmarks, styles)
            images = ImageFiller(package, bookmarks, styles)
            qa = QASectionFiller(package, bookmarks, styles)
            manifest_by_name = {x["bookmark"]: x for x in self.manifest["bookmarks"]}
            results: list[FillResult] = []

            # Every manifest field is reported, even when absent from input.
            for field, meta in manifest_by_name.items():
                value_present = field in values
                value = values.get(field, "")
                category = meta["type"]
                strategy = meta.get("strategy")
                if strategy and not applicability.get(strategy, False):
                    result = qa.clear_result(field)
                    result.category = category
                    results.append(result)
                    continue
                if not value_present:
                    results.append(
                        FillResult(
                            success=True,
                            filled="",
                            location=f"bookmark:{field}",
                            field=field,
                            category=category,
                            message="输入数据未提供",
                        )
                    )
                    continue
                if category == "cover":
                    result = cover.fill_result(field, value)
                elif category == "table_cutoff_date":
                    result = cover.fill_result(field, value)
                    result.category = category
                elif category == "cover_checkbox":
                    result = checkboxes.fill_result(field, value)
                elif category == "table_cell":
                    result = tables.fill_result(meta["table"], meta["row"], meta["col"], value)
                elif category in {"qa", "qa_attachment"}:
                    result = qa.fill_result(field, value, meta=meta)
                    result.category = category
                elif category == "image":
                    result = images.fill_result(field, value)
                else:
                    result = FillResult(False, str(value), field, field, category, message="未知字段类别")
                results.append(result)

            for merge in merges:
                results.append(
                    tables.merge_result(
                        int(merge["table"]),
                        tuple(merge["start"]),
                        tuple(merge["end"]),
                    )
                )

            unknown = sorted(set(values) - set(manifest_by_name))
            for field in unknown:
                results.append(
                    FillResult(
                        success=False,
                        filled=str(values[field]),
                        location="unknown",
                        field=field,
                        category="unknown",
                        message="输入字段不在书签清单中",
                    )
                )

            after = package.paragraph_count()
            expected = sum(r.expected_paragraph_delta for r in results if r.success)
            actual = after - before
            difference = abs(actual - expected)
            validation = ParagraphValidation(
                before=before,
                after=after,
                expected_delta=expected,
                actual_delta=actual,
                tolerance=self.paragraph_tolerance,
                success=difference <= self.paragraph_tolerance,
                message=(
                    "段落数偏差符合预期"
                    if difference <= self.paragraph_tolerance
                    else f"段落数偏差 {difference} 超过允许值"
                ),
            )
            if not validation.success:
                results.append(
                    FillResult(
                        success=False,
                        filled=str(actual),
                        location="document/body",
                        field="paragraph_count_validation",
                        category="validation",
                        message=validation.message,
                    )
                )
            output = package.save(output_path)
        finally:
            package.close()

        summary = ReportSummary(
            total_fields=len(manifest_by_name),
            filled_fields=sum(r.success and r.filled != "" for r in results if r.field in manifest_by_name),
            empty_fields=sum(r.success and r.filled == "" for r in results if r.field in manifest_by_name),
            failed_fields=sum(not r.success for r in results),
            abnormal_fields=sum(r.format_abnormal for r in results),
            unknown_input_fields=len(unknown),
            paragraph_validation=validation,
            results=results,
        )
        output = Path(output_path)
        report_docx = Path(report_docx_path) if report_docx_path else output.with_name(output.stem + "_填充报告.docx")
        report_json = Path(report_json_path) if report_json_path else output.with_name(output.stem + "_填充报告.json")
        FillReportWriter().write(summary, report_docx, report_json)
        return GenerationResult(output, report_docx, report_json, summary)

    @staticmethod
    def _normalize_data(
        data: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict], dict[str, bool]]:
        values = {}
        merges = list(data.get("merges", []))
        strategy_names = {"quant", "cta", "bond", "option"}
        applicability: dict[str, bool] = {}
        if "fields" in data:
            values.update(data["fields"])
        for key, value in data.items():
            if key in {"fields", "tables", "merges", "strategies"}:
                continue
            if key in strategy_names and isinstance(value, dict):
                continue
            if key.startswith("strat_") and key.endswith("_applicable"):
                strategy = key[len("strat_"):-len("_applicable")]
                if strategy in strategy_names:
                    applicability[strategy] = bool(value)
                    continue
            else:
                values[key] = value
        strategy_payloads = dict(data.get("strategies", {}))
        for strategy in strategy_names:
            if strategy in data and isinstance(data[strategy], dict):
                strategy_payloads.setdefault(strategy, data[strategy])
        for strategy, payload in strategy_payloads.items():
            if strategy not in strategy_names or not isinstance(payload, dict):
                continue
            if "_applicable" in payload:
                applicability[strategy] = bool(payload["_applicable"])
            for key, value in payload.items():
                if key == "_applicable":
                    continue
                field = key if key.startswith(f"strat_{strategy}_") else f"strat_{strategy}_{key}"
                values[field] = value
        for table, table_data in data.get("tables", {}).items():
            for row, row_data in table_data.get("rows", {}).items():
                for col, value in row_data.items():
                    values[f"table_{table}_row{row}_col{col}"] = value
            for merge in table_data.get("merges", []):
                merges.append({"table": int(table), **merge})
        # Supplying a strategy field implies applicability unless explicitly false.
        for strategy in strategy_names:
            has_value = any(key.startswith(f"strat_{strategy}_") for key in values)
            applicability.setdefault(strategy, has_value)
        return values, merges, applicability
