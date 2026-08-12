from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .extractor import BookmarkExtractor
from .mapper import InputDataMapper
from .models import FieldResult, Report
from .style_check import StyleChecker


def normalize(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


class Validator:
    """
    Validate all bookmark-addressable values in a generated DOCX.

    `template_path` is optional but recommended for exact style/table checks.
    The public validation contract remains:
        validate(generated_docx, input_data) -> Report
    """

    def __init__(
        self,
        template_path: str | Path | None = None,
        *,
        profile: str = "auto",
    ):
        self.template_path = Path(template_path) if template_path else None
        self.profile = profile
        self.mapper = InputDataMapper()
        self.style_checker = StyleChecker()

    def validate(
        self,
        generated_docx: str | Path,
        input_data: dict[str, Any] | str | Path,
    ) -> Report:
        generated = Path(generated_docx)
        data = self._load_input(input_data)
        extractor = BookmarkExtractor(generated)
        actual = extractor.extract_all()
        profile = self._detect_profile(extractor.bookmark_names)
        expected = self.mapper.map(self._flatten_dynamic_rows(data, profile), profile)
        results = []
        matched = missing = mismatched = extra = empty_expected = 0
        for field in extractor.bookmark_names:
            item = actual[field]
            expected_value = expected.get(field, "")
            # Dedicated image bookmarks always extract as ``[图片]``.  The
            # licensed-financial-institution template also permits its three
            # credit screenshot slots to contain a textual attachment
            # description, so only normalize those fields as images when the
            # generated document actually contains a drawing.
            if (
                field.startswith("image_")
                or (
                    "credit_screenshot" in field
                    and item.value == "[图片]"
                )
            ) and normalize(expected_value):
                expected_value = "[图片]"
            actual_value = item.value
            expected_normalized = normalize(expected_value)
            actual_normalized = normalize(actual_value)
            if expected_normalized and not actual_normalized:
                status = "遗漏"
                missing += 1
            elif not expected_normalized and actual_normalized:
                status = "多余填充"
                extra += 1
            elif expected_normalized != actual_normalized:
                status = "值不一致"
                mismatched += 1
            elif expected_normalized:
                status = "一致"
                matched += 1
            else:
                status = "应为空且为空"
                empty_expected += 1
            results.append(FieldResult(
                field=field,
                expected=str(expected_value or ""),
                actual=str(actual_value or ""),
                status=status,
                location=item.location,
            ))
        # Expected mapped fields absent from the document are also omissions.
        for field in sorted(set(expected) - set(actual)):
            if normalize(expected[field]):
                missing += 1
                results.append(FieldResult(
                    field, str(expected[field]), "", "遗漏", "书签不存在",
                    "输入数据有值，但生成文档中没有对应书签",
                ))
        dynamic = data.get("__dynamic_tables", {})
        definitions_path = self.template_path.with_name("table_definitions.json") if self.template_path else None
        if isinstance(dynamic, dict) and definitions_path and definitions_path.is_file():
            from docx import Document
            definitions = json.loads(definitions_path.read_text(encoding="utf-8"))
            definition_key = "licensed_institution" if profile == "licensed" else "private_fund"
            document = Document(generated)
            for table_number, rows in dynamic.items():
                definition = definitions.get(definition_key, {}).get(str(table_number))
                if not definition or not isinstance(rows, list):
                    continue
                capacity = int(definition["template_rows"])
                start_row = int(definition["start_row"])
                for offset, row in enumerate(rows[capacity:], capacity):
                    if not isinstance(row, dict):
                        continue
                    for column in definition["columns"]:
                        col = int(column["col"])
                        expected_value = row.get(str(col), row.get(col, ""))
                        if column.get("input") == "percent" and expected_value not in (None, "") and not str(expected_value).strip().endswith(("%", "％")):
                            expected_value = f"{str(expected_value).strip()}%"
                        suffix = str(column.get("output_suffix", ""))
                        if suffix and expected_value not in (None, "") and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", str(expected_value).strip()):
                            expected_value = f"{str(expected_value).strip()}{suffix}"
                        location = f"table:{table_number}; row:{start_row + offset}; col:{col}"
                        try:
                            actual_value = document.tables[int(table_number) - 1].rows[start_row + offset].cells[col].text
                        except (IndexError, ValueError):
                            actual_value = ""
                        if normalize(expected_value) and not normalize(actual_value):
                            status = "遗漏"; missing += 1
                        elif normalize(expected_value) != normalize(actual_value):
                            status = "值不一致"; mismatched += 1
                        else:
                            status = "一致"; matched += 1
                        results.append(FieldResult(
                            f"table_{table_number}_dynamic_row{start_row + offset}_col{col}",
                            str(expected_value or ""), str(actual_value or ""), status, location,
                        ))
        format_issues = self.style_checker.compare_fields(
            extractor, actual, self.template_path
        )
        table_issues = self.style_checker.compare_tables(
            generated,
            self.template_path,
            dynamic_rows={
                str(table): len(rows)
                for table, rows in dynamic.items()
                if isinstance(rows, list) and rows
            } if isinstance(dynamic, dict) else None,
        )
        notes = [
            "比较范围为文档中的全部书签字段；metadata、scorecard、eligibility_check 等非报告输出数据不参与遗漏统计。",
            "建议传入原始空白模板作为 template_path，以启用精确字体、字号、颜色和表格几何比较。",
        ]
        return Report(
            generated_docx=str(generated),
            profile=profile,
            matched=matched,
            missing=missing,
            mismatched=mismatched,
            extra=extra,
            empty_expected=empty_expected,
            format_issue_count=len(format_issues),
            table_issue_count=len(table_issues),
            field_results=results,
            format_issues=format_issues,
            table_issues=table_issues,
            notes=notes,
        )

    @staticmethod
    def _load_input(input_data):
        if isinstance(input_data, dict):
            return input_data
        return json.loads(Path(input_data).read_text(encoding="utf-8"))

    def _detect_profile(self, names):
        if self.profile != "auto":
            return self.profile
        names = set(names)
        if "qa_section5_conclusion" in names or len(names) < 100:
            return "licensed"
        if "table_1_data_cutoff_date" in names:
            return "private_2026"
        return "private"

    def _flatten_dynamic_rows(self, data: dict[str, Any], profile: str) -> dict[str, Any]:
        dynamic = data.get("__dynamic_tables", {})
        definitions_path = self.template_path.with_name("table_definitions.json") if self.template_path else None
        if not isinstance(dynamic, dict) or not definitions_path or not definitions_path.is_file():
            return data
        definitions = json.loads(definitions_path.read_text(encoding="utf-8"))
        definition_key = "licensed_institution" if profile == "licensed" else "private_fund"
        result = dict(data)
        for table, rows in dynamic.items():
            definition = definitions.get(definition_key, {}).get(str(table))
            if not definition or not isinstance(rows, list):
                continue
            for offset, row in enumerate(rows[:int(definition["template_rows"])]):
                if not isinstance(row, dict):
                    continue
                actual_row = int(definition["start_row"]) + offset
                for column in definition["columns"]:
                    col = int(column["col"])
                    value = row.get(str(col), row.get(col, ""))
                    input_type = definition.get("row_input_types", {}).get(str(actual_row), column.get("input", "text"))
                    if input_type == "percent" and value not in (None, "") and not str(value).strip().endswith(("%", "％")):
                        value = f"{str(value).strip()}%"
                    suffix = str(column.get("output_suffix", ""))
                    if suffix and value not in (None, "") and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", str(value).strip()):
                        value = f"{str(value).strip()}{suffix}"
                    result[f"table_{table}_row{actual_row}_col{col}"] = value
        return result
