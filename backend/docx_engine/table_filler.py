from __future__ import annotations

from copy import deepcopy

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
