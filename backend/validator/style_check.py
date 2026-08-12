from __future__ import annotations

import zipfile
import json
from pathlib import Path

from lxml import etree

from .extractor import NS, W, BookmarkExtractor, ExtractedValue, qn
from .models import FormatIssue, TableIssue


class StyleChecker:
    def compare_fields(
        self,
        actual_extractor: BookmarkExtractor,
        actual: dict[str, ExtractedValue],
        template_path: str | Path | None,
    ) -> list[FormatIssue]:
        issues = []
        expected_extractor = BookmarkExtractor(template_path) if template_path else None
        expected = expected_extractor.extract_all() if expected_extractor else {}
        for field, item in actual.items():
            if not item.value or not item.runs:
                continue
            signatures = [
                self._signature(run, paragraph, actual_extractor.styles)
                for run, paragraph in item.runs
                if "".join(run.xpath(".//w:t/text()", namespaces=NS)).strip()
            ]
            signatures = [signature for signature in signatures if signature]
            if len(set(signatures)) > 1:
                issues.append(FormatIssue(
                    field, item.location, "样式不统一", "单一字体/字号/颜色",
                    "；".join(sorted(set(map(str, signatures)))),
                    "同一填充值包含多种有效样式",
                ))
            if expected_extractor:
                reference = expected.get(field)
                reference_signature = self._reference_signature(
                    reference, expected_extractor.styles
                )
                for signature in signatures:
                    if reference_signature and not self._compatible(signature, reference_signature):
                        issues.append(FormatIssue(
                            field, item.location, "字体字号颜色",
                            str(reference_signature), str(signature),
                            "填充值样式与模板上下文不一致",
                        ))
                        break
        return issues

    def compare_tables(
        self,
        generated_path: str | Path,
        template_path: str | Path | None,
        dynamic_rows: dict[str, int] | None = None,
    ) -> list[TableIssue]:
        if template_path is None:
            return self._internal_table_checks(generated_path)
        actual = self._table_signatures(generated_path)
        expected = self._table_signatures(template_path)
        issues = []
        if len(actual) != len(expected):
            issues.append(TableIssue(
                0, "表格数量", str(len(expected)), str(len(actual)), "表格数量发生变化"
            ))
        for index, (a, e) in enumerate(zip(actual, expected), 1):
            if a["grid"] != e["grid"]:
                issues.append(TableIssue(index, "grid", str(e["grid"]), str(a["grid"]), "表格列宽发生变化"))
            submitted_rows = (dynamic_rows or {}).get(str(index))
            expected_details = e["row_details"]
            if submitted_rows is not None:
                definitions_path = Path(template_path).with_name("table_definitions.json")
                if definitions_path.is_file():
                    definitions = json.loads(definitions_path.read_text(encoding="utf-8"))
                    profile = "private_fund" if len(expected) == 12 else "licensed_institution"
                    definition = definitions.get(profile, {}).get(str(index), {})
                    start = int(definition.get("start_row", 0))
                    capacity = int(definition.get("template_rows", 0))
                    if 0 < submitted_rows < capacity:
                        expected_details = expected_details[:start + submitted_rows]
            if len(a["row_details"]) < len(expected_details):
                issues.append(TableIssue(index, "rows", str(len(e["row_details"])), str(len(a["row_details"])), "表格行被删除"))
                continue
            if a["row_details"][:len(expected_details)] != expected_details:
                issues.append(TableIssue(index, "row_geometry", str(expected_details), str(a["row_details"][:len(expected_details)]), "模板原有行的几何或对齐方式发生变化"))
            if submitted_rows is not None and submitted_rows < len(e["row_details"]):
                if len(a["row_details"]) != len(expected_details):
                    issues.append(TableIssue(index, "dynamic_rows", str(len(expected_details)), str(len(a["row_details"])), "动态表格行数与填写数据不一致"))
            elif len(a["row_details"]) > len(e["row_details"]):
                reference = e["row_details"][-1]
                if any(row != reference for row in a["row_details"][len(e["row_details"]):]):
                    issues.append(TableIssue(index, "appended_row_geometry", str(reference), str(a["row_details"][len(e["row_details"]):]), "新增行未继承模板末行格式"))
        return issues

    def _reference_signature(self, item, styles):
        if item is None:
            return None
        for run, paragraph in item.runs:
            signature = self._signature(run, paragraph, styles)
            if signature:
                return signature
        # Empty bookmark: derive from its paragraph's style by locating bookmark.
        if item.context is not None:
            return self._signature(None, item.context, styles)
        return None

    def _signature(self, run, paragraph, styles):
        properties = {}
        default_rpr = (
            styles.find(".//w:docDefaults/w:rPrDefault/w:rPr", NS)
            if styles is not None else None
        )
        style_rpr = None
        if styles is not None:
            style_ids = paragraph.xpath("./w:pPr/w:pStyle/@w:val", namespaces=NS)
            if style_ids:
                candidates = styles.xpath(
                    f".//w:style[@w:styleId='{style_ids[0]}']/w:rPr",
                    namespaces=NS,
                )
                style_rpr = candidates[0] if candidates else None
        paragraph_rpr = paragraph.find("./w:pPr/w:rPr", NS)
        run_rpr = run.find("./w:rPr", NS) if run is not None else None
        for rpr in (default_rpr, style_rpr, paragraph_rpr, run_rpr):
            if rpr is None:
                continue
            fonts = rpr.find("./w:rFonts", NS)
            if fonts is not None:
                for key in ("eastAsia", "ascii", "hAnsi"):
                    value = fonts.get(qn(key))
                    if value:
                        properties[key] = value
            size = rpr.find("./w:sz", NS)
            if size is not None and size.get(qn("val")):
                properties["size_pt"] = int(size.get(qn("val"))) / 2
            color = rpr.find("./w:color", NS)
            if color is not None and color.get(qn("val")):
                properties["color"] = color.get(qn("val"))
        return (
            properties.get("eastAsia") or properties.get("ascii"),
            properties.get("size_pt"),
            properties.get("color", "auto"),
        )

    @staticmethod
    def _compatible(actual, expected):
        return all(
            expected_value is None or actual_value == expected_value
            for actual_value, expected_value in zip(actual, expected)
        )

    def _table_signatures(self, path):
        with zipfile.ZipFile(path) as archive:
            root = etree.fromstring(archive.read("word/document.xml"))
        tables = root.xpath("//w:body/w:tbl", namespaces=NS)
        result = []
        for table in tables:
            rows = table.xpath("./w:tr", namespaces=NS)
            result.append({
                "rows": [len(row.xpath("./w:tc", namespaces=NS)) for row in rows],
                "grid": table.xpath("./w:tblGrid/w:gridCol/@w:w", namespaces=NS),
                "cell_widths": [
                    cell.xpath("./w:tcPr/w:tcW/@w:w", namespaces=NS)
                    for row in rows for cell in row.xpath("./w:tc", namespaces=NS)
                ],
                "cell_properties": [
                    (
                        cell.xpath("./w:tcPr/w:gridSpan/@w:val", namespaces=NS),
                        cell.xpath("./w:tcPr/w:vMerge/@w:val", namespaces=NS),
                        bool(cell.xpath("./w:tcPr/w:vMerge[not(@w:val)]", namespaces=NS)),
                        cell.xpath("./w:tcPr/w:vAlign/@w:val", namespaces=NS),
                    )
                    for row in rows for cell in row.xpath("./w:tc", namespaces=NS)
                ],
                "paragraph_alignments": [
                    paragraph.xpath("./w:pPr/w:jc/@w:val", namespaces=NS)
                    for row in rows
                    for cell in row.xpath("./w:tc", namespaces=NS)
                    for paragraph in cell.xpath("./w:p", namespaces=NS)
                ],
                "row_details": [
                    {
                        "cells": len(row.xpath("./w:tc", namespaces=NS)),
                        "widths": [cell.xpath("./w:tcPr/w:tcW/@w:w", namespaces=NS) for cell in row.xpath("./w:tc", namespaces=NS)],
                        "properties": [(
                            cell.xpath("./w:tcPr/w:gridSpan/@w:val", namespaces=NS),
                            cell.xpath("./w:tcPr/w:vMerge/@w:val", namespaces=NS),
                            bool(cell.xpath("./w:tcPr/w:vMerge[not(@w:val)]", namespaces=NS)),
                            cell.xpath("./w:tcPr/w:vAlign/@w:val", namespaces=NS),
                        ) for cell in row.xpath("./w:tc", namespaces=NS)],
                        "alignments": [paragraph.xpath("./w:pPr/w:jc/@w:val", namespaces=NS) for cell in row.xpath("./w:tc", namespaces=NS) for paragraph in cell.xpath("./w:p", namespaces=NS)],
                    }
                    for row in rows
                ],
            })
        return result

    def _internal_table_checks(self, path):
        issues = []
        for index, table in enumerate(self._table_signatures(path), 1):
            if not table["grid"]:
                issues.append(TableIssue(
                    index, "tblGrid", "存在", "缺失", "无法验证列宽对齐"
                ))
        return issues
