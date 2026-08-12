from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class QualitativeScoreInputs(BaseModel):
    strategy_scale_group: Literal["bond", "cta_t0", "other"]
    managed_scale_100m: float = Field(ge=0, description="管理规模，单位：亿元")
    active_product_count: int = Field(ge=0)
    company_headcount: int = Field(ge=0)

    manager_same_strategy_years: float = Field(ge=0)
    manager_industry_years: float = Field(ge=0)
    manager_philosophy_level: Literal["complete", "mature", "clear", "weak"]
    manager_profile_stable: bool

    research_headcount: int = Field(ge=0)
    research_background_match: bool
    core_research_experience_years: float = Field(ge=0)
    research_live_track_record: bool

    core_departures_1y: int = Field(ge=0)
    core_departures_3y: int = Field(ge=0)
    incentive_level: Literal["long_term", "clear", "basic", "none"]

    current_strategy_scale_100m: float = Field(ge=0)
    theoretical_capacity_100m: float = Field(gt=0)
    differentiation_level: Literal["significant", "partial", "none"]

    risk_system_level: Literal["complete", "substantial", "basic", "none"]
    risk_team_headcount: int = Field(ge=0)
    risk_team_experience_years: float = Field(ge=0)

    manager_coinvest_percent: float = Field(ge=0)
    manager_coinvest_lock_years: float = Field(ge=0)
    core_personal_coinvest: bool

    regulatory_events_3y: int = Field(ge=0)
    negative_or_litigation_events_3y: int = Field(ge=0)


class ScorecardCalculateRequest(BaseModel):
    date_column: str = Field(min_length=1)
    nav_column: str = Field(min_length=1)
    benchmark_column: str | None = None
    benchmark_mode: Literal["benchmark", "absolute"] = "absolute"
    risk_free_rate_percent: float = Field(default=0.0, ge=-100, le=100)
    qualitative: QualitativeScoreInputs


class ScorecardManualSaveRequest(BaseModel):
    scores: dict[str, float]


class ScorecardGenerateResponse(BaseModel):
    filename: str
    download_url: str


class ScorecardRead(BaseModel):
    report_id: int
    nav_original_filename: str | None = None
    nav_sheet_name: str | None = None
    nav_columns: list[str] = Field(default_factory=list)
    detected_columns: dict[str, Any] = Field(default_factory=dict)
    nav_preview: list[dict[str, Any]] = Field(default_factory=list)
    calculation_inputs: dict[str, Any] = Field(default_factory=dict)
    manual_scores: dict[str, float] = Field(default_factory=dict)
    template_items: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    score_rows: list[dict[str, Any]] = Field(default_factory=list)
    quantitative_score: float | None = None
    qualitative_score: float | None = None
    compliance_deduction: float | None = None
    total_score: float | None = None
    admitted: bool | None = None
    calculated_at: datetime | None = None
