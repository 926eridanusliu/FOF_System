from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class StyleSpec:
    font_ascii: str | None = None
    font_east_asia: str | None = None
    size_pt: float | None = None
    color: str | None = None
    bold: bool | None = None


@dataclass
class FillResult:
    success: bool
    filled: str
    location: str
    field: str
    category: str
    format_abnormal: bool = False
    message: str = ""
    expected_paragraph_delta: int = 0

    def as_tuple(self) -> tuple[bool, str, str]:
        """Required operation contract: (success/failure, what, location)."""
        return self.success, self.filled, self.location

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParagraphValidation:
    before: int
    after: int
    expected_delta: int
    actual_delta: int
    tolerance: int
    success: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReportSummary:
    total_fields: int
    filled_fields: int
    empty_fields: int
    failed_fields: int
    abnormal_fields: int
    unknown_input_fields: int
    paragraph_validation: ParagraphValidation
    results: list[FillResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["results"] = [r.to_dict() for r in self.results]
        return data
