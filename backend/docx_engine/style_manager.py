from __future__ import annotations

import re
from copy import deepcopy

from lxml import etree

from .models import StyleSpec
from .package import DocxPackage


class StyleManager:
    """Creates runs/paragraphs while preserving source styles by default."""

    def __init__(
        self,
        package: DocxPackage,
        styles: dict[str, StyleSpec] | None = None,
    ):
        self.package = package
        self.styles = styles or {}

    def make_run(
        self,
        value: str,
        *,
        source_paragraph=None,
        category: str = "default",
        include_break: bool = False,
    ):
        w = self.package.qn
        run = etree.Element(w("r"))
        source_rpr = None
        if source_paragraph is not None:
            runs = source_paragraph.xpath("./w:r", namespaces=self.package.NS)
            for candidate in reversed(runs):
                rpr = candidate.find(w("rPr"))
                if rpr is not None:
                    source_rpr = deepcopy(rpr)
                    break
        if source_rpr is not None:
            run.append(source_rpr)
        spec = self.styles.get(category) or self.styles.get("default")
        if spec is not None:
            self._apply_spec(run, spec)
        if include_break:
            etree.SubElement(run, w("br"))
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        parts = re.split(r"(\n|\t)", normalized)
        for part in parts:
            if part == "\n":
                etree.SubElement(run, w("br"))
            elif part == "\t":
                etree.SubElement(run, w("tab"))
            elif part or len(parts) == 1:
                text = etree.SubElement(run, w("t"))
                text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                text.text = part
        return run

    def clone_paragraph(self, source_paragraph, *, preserve_numbering: bool = False):
        w = self.package.qn
        paragraph = etree.Element(w("p"))
        ppr = source_paragraph.find(w("pPr"))
        if ppr is not None:
            cloned_ppr = deepcopy(ppr)
            if not preserve_numbering:
                self._remove_numbering_from_ppr(cloned_ppr)
            paragraph.append(cloned_ppr)
        return paragraph

    def remove_numbering(self, paragraph) -> None:
        """Keep paragraph formatting while removing automatic-list numbering."""
        ppr = paragraph.find(self.package.qn("pPr"))
        if ppr is not None:
            self._remove_numbering_from_ppr(ppr)

    def format_answer_paragraph(self, paragraph) -> None:
        """Apply a two-character first-line indent without indenting wrapped lines."""
        w = self.package.qn
        ppr = paragraph.find(w("pPr"))
        if ppr is None:
            ppr = etree.Element(w("pPr"))
            paragraph.insert(0, ppr)
        self._remove_numbering_from_ppr(ppr)
        indentation = ppr.find(w("ind"))
        if indentation is None:
            indentation = etree.SubElement(ppr, w("ind"))
        for attribute in (
            "left",
            "start",
            "hanging",
            "hangingChars",
            "firstLine",
            "firstLineChars",
        ):
            indentation.attrib.pop(w(attribute), None)
        indentation.set(w("leftChars"), "0")
        indentation.set(w("firstLineChars"), "200")

    def _remove_numbering_from_ppr(self, ppr) -> None:
        # Question paragraphs often use Word automatic numbering. Answers
        # inherit the visual settings, but must not become numbered list items.
        num_pr = ppr.find(self.package.qn("numPr"))
        if num_pr is not None:
            ppr.remove(num_pr)

    def validate_value(self, value: str, category: str) -> tuple[bool, str]:
        issues = []
        if "\x00" in value:
            issues.append("包含非法 NUL 字符")
        if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in value):
            issues.append("包含不可打印控制字符")
        if category == "cover_checkbox" and value not in {
            "□", "☑", "✓", "true", "false", "True", "False", "1", "0"
        }:
            issues.append("复选框值应为 □/☑/布尔值")
        spec = self.styles.get(category) or self.styles.get("default")
        if spec and spec.color and not re.fullmatch(r"[0-9A-Fa-f]{6}", spec.color):
            issues.append("颜色必须是 6 位十六进制 RGB")
        return bool(issues), "；".join(issues)

    def _apply_spec(self, run, spec: StyleSpec) -> None:
        w = self.package.qn
        rpr = run.find(w("rPr"))
        if rpr is None:
            rpr = etree.Element(w("rPr"))
            run.insert(0, rpr)
        fonts = rpr.find(w("rFonts"))
        if fonts is None and (spec.font_ascii or spec.font_east_asia):
            fonts = etree.SubElement(rpr, w("rFonts"))
        if fonts is not None:
            if spec.font_ascii:
                fonts.set(w("ascii"), spec.font_ascii)
                fonts.set(w("hAnsi"), spec.font_ascii)
            if spec.font_east_asia:
                fonts.set(w("eastAsia"), spec.font_east_asia)
        if spec.size_pt is not None:
            half_points = str(round(spec.size_pt * 2))
            for name in ("sz", "szCs"):
                el = rpr.find(w(name))
                if el is None:
                    el = etree.SubElement(rpr, w(name))
                el.set(w("val"), half_points)
        if spec.color is not None:
            color = rpr.find(w("color"))
            if color is None:
                color = etree.SubElement(rpr, w("color"))
            color.set(w("val"), spec.color.upper())
        if spec.bold is not None:
            bold = rpr.find(w("b"))
            if spec.bold and bold is None:
                etree.SubElement(rpr, w("b"))
            elif not spec.bold and bold is not None:
                rpr.remove(bold)
