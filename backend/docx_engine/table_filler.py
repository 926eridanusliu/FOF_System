from __future__ import annotations

from copy import deepcopy
import re

from lxml import etree

from .base_filler import BaseFiller


class TableFiller(BaseFiller):
    category = "table_cell"

    def fill(self, table: int, row: int, col: int, value: object):
        return self.fill_result(table, row, col, value).as_tuple()

    def fill_result(self, table: int, row: int, col: int, value: object):
        field = f"table_{table}_row{row}_col{col}"
        string = "" if value is None else str(value)
        abnormal, message = self.styles.validate_value(string, self.category)
        if self.bookmark(field) is None:
            return self.result(False, field, value, field, message="未找到表格坐标书签")
        try:
            self.replace_bookmark_content(field, string, self.category)
            return self.result(
                True,
                field,
                value,
                f"table:{table}; row:{row}; col:{col}",
                abnormal=abnormal,
                message=message,
            )
        except Exception as exc:
            return self.result(False, field, value, field, message=str(exc))

    def resize_dynamic_rows(
        self,
        table: int,
        rows: list[dict],
        *,
        start_row: int,
        template_rows: int,
        columns: list[dict],
    ):
        """Fit a dynamic table to submitted rows while preserving template styling."""
        results = []
        if not rows:
            return results
        try:
            tbl = self.package.body.xpath("./w:tbl", namespaces=self.package.NS)[table - 1]
            table_rows = tbl.xpath("./w:tr", namespaces=self.package.NS)
            keep = min(len(rows), template_rows)
            if keep < template_rows:
                removed = table_rows[start_row + keep:start_row + template_rows]
                paragraph_count = sum(
                    len(row.xpath(".//w:p", namespaces=self.package.NS)) for row in removed
                )
                for row in removed:
                    tbl.remove(row)
                result = self.result(
                    True,
                    f"table_{table}_trimmed_rows",
                    template_rows - keep,
                    f"table:{table}",
                )
                result.expected_paragraph_delta = -paragraph_count
                results.append(result)

            overflow = rows[template_rows:]
            if not overflow:
                return results
            table_rows = tbl.xpath("./w:tr", namespaces=self.package.NS)
            template = table_rows[start_row + template_rows - 1]
            for offset, values in enumerate(overflow, template_rows):
                clone = deepcopy(template)
                for bookmark in clone.xpath(".//w:bookmarkStart | .//w:bookmarkEnd", namespaces=self.package.NS):
                    bookmark.getparent().remove(bookmark)
                cells = clone.xpath("./w:tc", namespaces=self.package.NS)
                for column in columns:
                    col = int(column["col"])
                    if col >= len(cells):
                        continue
                    cell = cells[col]
                    text_nodes = cell.xpath(".//w:t", namespaces=self.package.NS)
                    value = values.get(str(col), values.get(col, ""))
                    string = "" if value is None else str(value)
                    if column.get("input") == "percent" and string and not string.endswith(("%", "％")):
                        string = f"{string}%"
                    suffix = str(column.get("output_suffix", ""))
                    if suffix and string and re.fullmatch(r"[+-]?\d+(?:\.\d+)?", string):
                        string = f"{string}{suffix}"
                    if text_nodes:
                        text_nodes[0].text = string
                        if string.startswith(" ") or string.endswith(" "):
                            text_nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                        for node in text_nodes[1:]:
                            node.text = ""
                    else:
                        paragraphs = cell.xpath("./w:p", namespaces=self.package.NS)
                        paragraph = paragraphs[0] if paragraphs else etree.SubElement(cell, self.package.qn("p"))
                        run = etree.SubElement(paragraph, self.package.qn("r"))
                        text = etree.SubElement(run, self.package.qn("t"))
                        text.text = string
                tbl.append(clone)
                result = self.result(True, f"table_{table}_dynamic_row_{offset}", values, f"table:{table}; row:{start_row + offset}")
                result.expected_paragraph_delta = len(clone.xpath(".//w:p", namespaces=self.package.NS))
                results.append(result)
        except Exception as exc:
            results.append(self.result(False, f"table_{table}_dynamic_rows", rows, f"table:{table}", message=str(exc)))
        return results

    def merge(
        self,
        table: int,
        start: tuple[int, int],
        end: tuple[int, int],
    ):
        return self.merge_result(table, start, end).as_tuple()

    def merge_result(
        self,
        table: int,
        start: tuple[int, int],
        end: tuple[int, int],
    ):
        r1, c1 = start
        r2, c2 = end
        location = f"table:{table}; merge:({r1},{c1})-({r2},{c2})"
        try:
            tbl = self.package.body.xpath("./w:tbl", namespaces=self.package.NS)[table - 1]
            rows = tbl.xpath("./w:tr", namespaces=self.package.NS)
            if r1 > r2 or c1 > c2:
                raise ValueError("合并范围起点必须小于终点")
            if r2 >= len(rows):
                raise IndexError("合并行超出表格范围")
            merged_first_cells = []
            for row_index in range(r1, r2 + 1):
                cells = rows[row_index].xpath("./w:tc", namespaces=self.package.NS)
                if c2 >= len(cells):
                    raise IndexError("合并列超出表格范围")
                first = cells[c1]
                tcpr = first.find(self.package.qn("tcPr"))
                if tcpr is None:
                    tcpr = etree.Element(self.package.qn("tcPr"))
                    first.insert(0, tcpr)
                if c2 > c1:
                    span = tcpr.find(self.package.qn("gridSpan"))
                    if span is None:
                        span = etree.SubElement(tcpr, self.package.qn("gridSpan"))
                    span.set(self.package.qn("val"), str(c2 - c1 + 1))
                    for cell in cells[c1 + 1:c2 + 1]:
                        rows[row_index].remove(cell)
                merged_first_cells.append(first)
            if r2 > r1:
                for offset, cell in enumerate(merged_first_cells):
                    tcpr = cell.find(self.package.qn("tcPr"))
                    merge = tcpr.find(self.package.qn("vMerge"))
                    if merge is None:
                        merge = etree.SubElement(tcpr, self.package.qn("vMerge"))
                    if offset == 0:
                        merge.set(self.package.qn("val"), "restart")
                    else:
                        merge.attrib.pop(self.package.qn("val"), None)
                        for child in list(cell):
                            if child.tag != self.package.qn("tcPr"):
                                cell.remove(child)
                        cell.append(etree.Element(self.package.qn("p")))
            return self.result(True, "table_merge", f"{start}->{end}", location)
        except Exception as exc:
            return self.result(False, "table_merge", f"{start}->{end}", location, message=str(exc))
