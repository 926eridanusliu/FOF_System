from __future__ import annotations

from .base_filler import BaseFiller


class CoverFiller(BaseFiller):
    category = "cover"

    def fill(self, field: str, value: object):
        return self.fill_result(field, value).as_tuple()

    def fill_result(self, field: str, value: object):
        string = "" if value is None else str(value)
        abnormal, message = self.styles.validate_value(string, self.category)
        located = self.bookmark(field)
        if located is None:
            return self.result(False, field, value, field, message="未找到封面书签")
        try:
            start, _, _ = located
            paragraph = start.getparent()
            if field in {"cover_investigator", "cover_report_date"}:
                replaced = self._replace_text(paragraph, "____________________", string)
                if not replaced:
                    raise ValueError("未找到封面下划线占位符")
            elif field == "cover_strategy_other_text":
                replaced = self._replace_text(paragraph, "             ", string)
                if not replaced:
                    raise ValueError("未找到其他策略文本占位符")
                for text in paragraph.xpath("./w:r/w:t", namespaces=self.package.NS):
                    if "□其他投资策略" in (text.text or ""):
                        text.text = text.text.replace(
                            "□其他投资策略",
                            f"{'☑' if string.strip() else '□'}其他投资策略",
                            1,
                        )
                        break
            else:
                self.replace_bookmark_content(field, string, self.category)
            return self.result(
                True,
                field,
                value,
                f"bookmark:{field}",
                abnormal=abnormal,
                message=message,
            )
        except Exception as exc:
            return self.result(
                False,
                field,
                value,
                f"bookmark:{field}",
                abnormal=abnormal,
                message=str(exc),
            )

    def _replace_text(self, paragraph, needle: str, replacement: str) -> bool:
        for text in paragraph.xpath("./w:r/w:t", namespaces=self.package.NS):
            if needle in (text.text or ""):
                text.text = text.text.replace(needle, replacement, 1)
                return True
        return False
