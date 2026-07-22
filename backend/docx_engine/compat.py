from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .generator import DocxGenerator, GenerationResult
from .models import StyleSpec
from .package import DocxPackage


class BookmarkTemplateEngine:
    """兼容旧调用方式的通用书签模板引擎。"""

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
        self.generator = DocxGenerator(
            self.template_path,
            self.manifest_path,
            styles=styles,
            paragraph_tolerance=paragraph_tolerance,
        )

    def render(
        self,
        values: dict[str, Any],
        output_path: str | Path,
        **report_paths,
    ) -> GenerationResult:
        return self.generator.generate(values, output_path, **report_paths)

    def render_json(
        self,
        json_path: str | Path,
        output_path: str | Path,
        **report_paths,
    ) -> GenerationResult:
        values = json.loads(Path(json_path).read_text(encoding="utf-8"))
        return self.render(values, output_path, **report_paths)

    def list_bookmarks(self) -> list[str]:
        package = DocxPackage(self.template_path)
        try:
            return sorted(package.bookmark_index())
        finally:
            package.close()
