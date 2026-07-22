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
        expected = self.mapper.map(data, profile)
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
        format_issues = self.style_checker.compare_fields(
            extractor, actual, self.template_path
        )
        table_issues = self.style_checker.compare_tables(
            generated, self.template_path
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
