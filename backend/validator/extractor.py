from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
qn = lambda name: f"{{{W}}}{name}"


@dataclass
class ExtractedValue:
    field: str
    value: str
    location: str
    runs: list[tuple[etree._Element, etree._Element]] = field(default_factory=list)
    context: etree._Element | None = None


class BookmarkExtractor:
    CHECKBOX_POSITIONS = {
        "cover_strategy_stock_index_enhanced": 1,
        "cover_strategy_stock_quant": 2,
        "cover_strategy_stock_discretionary": 3,
        "cover_strategy_macro_hedge": 4,
        "cover_strategy_market_neutral": 1,
        "cover_strategy_futures_options_arbitrage": 2,
        "cover_strategy_t0": 3,
        "cover_strategy_bond_pure": 1,
        "cover_strategy_bond_enhanced": 2,
        "cover_strategy_bond_composite": 3,
        "cover_strategy_convertible_bond": 4,
        "cover_strategy_futures_quant_trend": 1,
        "cover_strategy_futures_discretionary": 2,
        "cover_strategy_composite": 1,
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as archive:
            self.document = etree.fromstring(archive.read("word/document.xml"))
            self.styles = (
                etree.fromstring(archive.read("word/styles.xml"))
                if "word/styles.xml" in archive.namelist()
                else None
            )
        self.starts = self.document.xpath("//w:bookmarkStart", namespaces=NS)
        self.ends = {
            end.get(qn("id")): end
            for end in self.document.xpath("//w:bookmarkEnd", namespaces=NS)
        }

    @property
    def bookmark_names(self) -> list[str]:
        return [start.get(qn("name")) for start in self.starts if start.get(qn("name"))]

    def extract_all(self) -> dict[str, ExtractedValue]:
        return {
            start.get(qn("name")): self._extract(start)
            for start in self.starts
            if start.get(qn("name"))
        }

    def _extract(self, start) -> ExtractedValue:
        name = start.get(qn("name"))
        end = self.ends.get(start.get(qn("id")))
        parent = start.getparent()
        location = self._location(name)
        if name in self.CHECKBOX_POSITIONS:
            value, runs = self._checkbox(parent, self.CHECKBOX_POSITIONS[name])
            return ExtractedValue(name, value, location, runs, parent)
        if name in {"cover_investigator", "cover_report_date"}:
            full = self._paragraph_text(parent)
            label = "调查人员：" if name.endswith("investigator") else "报告日期："
            value = full.split(label, 1)[-1].replace("_", "").strip()
            return ExtractedValue(name, value, location, self._all_runs(parent), parent)
        if name == "cover_strategy_other_text":
            full = self._paragraph_text(parent)
            match = re.search(r"其他投资策略（(.*?)）", full)
            value = match.group(1).strip() if match else ""
            return ExtractedValue(name, value, location, self._all_runs(parent), parent)
        direct_nodes = []
        node = start.getnext()
        while node is not None and node is not end:
            direct_nodes.append(node)
            node = node.getnext()
        direct_text = "".join(self._node_text(direct) for direct in direct_nodes)
        direct_runs = [
            (run, parent)
            for direct in direct_nodes
            for run in (
                [direct] if direct.tag == qn("r")
                else direct.xpath(".//w:r", namespaces=NS)
            )
        ]
        if any(
            direct.xpath(".//w:drawing", namespaces=NS)
            or direct.tag == qn("drawing")
            for direct in direct_nodes
        ):
            return ExtractedValue(name, "[图片]", location, direct_runs, parent)
        if direct_text and name.startswith(("qa_", "strat_", "attachment_")):
            values = [direct_text.strip()]
            runs = list(direct_runs)
            sibling = parent.getnext()
            while sibling is not None and sibling.tag == qn("p"):
                if not self._is_generated_paragraph(sibling):
                    break
                paragraph_text = self._paragraph_text(sibling).strip()
                if paragraph_text:
                    values.append(paragraph_text)
                    runs.extend(self._all_runs(sibling))
                sibling = sibling.getnext()
            return ExtractedValue(
                name,
                "\n".join(values),
                location,
                runs,
                parent,
            )
        if direct_text or not name.startswith(("qa_", "strat_", "attachment_")):
            return ExtractedValue(name, direct_text.strip(), location, direct_runs, parent)
        if name == "qa_section3_q122_answer" and parent.tag == qn("p"):
            values = []
            runs = []
            sibling = parent.getnext()
            collecting = False
            while sibling is not None and sibling.tag == qn("p"):
                is_generated = self._is_generated_paragraph(sibling)
                paragraph_text = self._paragraph_text(sibling).strip()
                if is_generated:
                    collecting = True
                    if paragraph_text:
                        values.append(paragraph_text)
                        runs.extend(self._all_runs(sibling))
                elif collecting:
                    break
                sibling = sibling.getnext()
            return ExtractedValue(
                name, "\n".join(values), location, runs, parent
            )
        if parent.tag == qn("p") and self._paragraph_text(parent).strip():
            values = []
            runs = []
            sibling = parent.getnext()
            while sibling is not None and sibling.tag == qn("p"):
                if not self._is_generated_paragraph(sibling):
                    break
                paragraph_text = self._paragraph_text(sibling).strip()
                if paragraph_text:
                    values.append(paragraph_text)
                    runs.extend(self._all_runs(sibling))
                sibling = sibling.getnext()
            return ExtractedValue(name, "\n".join(values), location, runs, parent)
        return ExtractedValue(name, "", location, direct_runs, parent)

    @staticmethod
    def _is_generated_paragraph(paragraph) -> bool:
        return paragraph.get(qn("rsidR")) == "C0D3C0D3"

    def _checkbox(self, paragraph, wanted):
        count = 0
        for run in paragraph.xpath("./w:r", namespaces=NS):
            for text in run.xpath("./w:t", namespaces=NS):
                for char in text.text or "":
                    if char in {"□", "☑"}:
                        count += 1
                        if count == wanted:
                            return char, [(run, paragraph)]
        return "", []

    @staticmethod
    def _paragraph_text(paragraph):
        return BookmarkExtractor._node_text(paragraph)

    @staticmethod
    def _node_text(node):
        parts = []
        for element in node.iter():
            if element.tag == qn("t"):
                parts.append(element.text or "")
            elif element.tag == qn("br"):
                parts.append("\n")
            elif element.tag == qn("tab"):
                parts.append("\t")
        return "".join(parts)

    @staticmethod
    def _all_runs(paragraph):
        return [(run, paragraph) for run in paragraph.xpath("./w:r", namespaces=NS)]

    @staticmethod
    def _location(name):
        match = re.match(r"table_(\d+)_row(\d+)_col(\d+)", name)
        if match:
            return f"表{match.group(1)} 行{match.group(2)} 列{match.group(3)}"
        return f"书签:{name}"
