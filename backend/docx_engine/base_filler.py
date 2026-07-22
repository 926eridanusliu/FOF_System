from __future__ import annotations

from .models import FillResult
from .package import DocxPackage
from .style_manager import StyleManager


class BaseFiller:
    category = "unknown"

    def __init__(
        self,
        package: DocxPackage,
        bookmarks: dict,
        style_manager: StyleManager,
    ):
        self.package = package
        self.bookmarks = bookmarks
        self.styles = style_manager

    def result(
        self,
        success: bool,
        field: str,
        value: object,
        location: str,
        *,
        abnormal: bool = False,
        message: str = "",
        delta: int = 0,
    ) -> FillResult:
        return FillResult(
            success=success,
            filled="" if value is None else str(value),
            location=location,
            field=field,
            category=self.category,
            format_abnormal=abnormal,
            message=message,
            expected_paragraph_delta=delta,
        )

    def bookmark(self, name: str):
        return self.bookmarks.get(name)

    def replace_bookmark_content(self, name: str, value: str, category: str):
        located = self.bookmark(name)
        if located is None:
            return None
        start, end, _ = located
        parent = start.getparent()
        if parent is not end.getparent():
            raise ValueError(f"跨容器书签暂不支持：{name}")
        while start.getnext() is not end:
            parent.remove(start.getnext())
        parent.insert(
            parent.index(end),
            self.styles.make_run(
                value,
                source_paragraph=parent,
                category=category,
            ),
        )
        return parent
