from __future__ import annotations

import re
from typing import Any


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else ""
    if isinstance(value, (list, tuple)):
        return "\n".join(stringify(item) for item in value if stringify(item))
    if isinstance(value, dict):
        return "\n".join(
            f"{key}：{stringify(item)}"
            for key, item in value.items()
            if key != "_applicable" and stringify(item)
        )
    return str(value)


def combine(*values: Any, separator: str = "\n") -> str:
    parts = [stringify(value) for value in values]
    return separator.join(part for part in parts if part)


def get(data: dict, path: str, default=None):
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part, default)
    return current


def chinese_date(value: Any) -> str:
    text = stringify(value).strip()
    match = re.fullmatch(r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})日?", text)
    if not match:
        return text
    year, month, day = match.groups()
    return f"{year}年{int(month)}月{int(day)}日"


def dotted_date(value: Any) -> str:
    text = stringify(value).strip()
    match = re.fullmatch(r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})日?", text)
    if not match:
        return text
    year, month, day = match.groups()
    return f"{year}.{int(month)}.{int(day)}"


def whitelist_names(value: Any, limit: int = 5) -> str:
    text = stringify(value).strip()
    text = re.sub(r"^(?:有|是)\s*[：:、，,]?\s*", "", text)
    names = [part.strip() for part in re.split(r"[、，,；;\\n]+", text) if part.strip()]
    return f"是，{'、'.join(names[:limit])}" if names else ""


class InputDataMapper:
    STRATEGY_CHECKBOXES = {
        "指数增强": "cover_strategy_stock_index_enhanced",
        "股票量化选股": "cover_strategy_stock_quant",
        "股票主观多头": "cover_strategy_stock_discretionary",
        "宏观对冲": "cover_strategy_macro_hedge",
        "市场中性": "cover_strategy_market_neutral",
        "期货及期权套利": "cover_strategy_futures_options_arbitrage",
        "日内回转（T0）": "cover_strategy_t0",
        "纯债": "cover_strategy_bond_pure",
        "债券增强": "cover_strategy_bond_enhanced",
        "债券复合": "cover_strategy_bond_composite",
        "可转债": "cover_strategy_convertible_bond",
        "期货量化趋势": "cover_strategy_futures_quant_trend",
        "期货主观": "cover_strategy_futures_discretionary",
        "复合策略": "cover_strategy_composite",
    }

    def map(self, data: dict, profile: str) -> dict[str, str]:
        if any(
            key.startswith(("cover_", "table_", "qa_", "strat_", "attachment_", "image_"))
            for key in data
        ):
            mapped = {}
            for key, value in data.items():
                if key.startswith("__") or key in {"report_type", "attachment_type", "template_type"}:
                    continue
                if key.startswith("cover_strategy_") and key != "cover_strategy_other_text":
                    mapped[key] = "☑" if value in {True, 1, "1", "true", "True", "是", "☑"} else "□"
                elif key.startswith("image_") or "credit_screenshot" in key:
                    mapped[key] = stringify(value)
                else:
                    mapped[key] = stringify(value)
            for bookmark in self.STRATEGY_CHECKBOXES.values():
                mapped.setdefault(bookmark, "□")
            return mapped
        return (
            self._licensed(data)
            if profile == "licensed"
            else self._private(data, include_revision_fields=profile == "private_2026")
        )

    def _cover(self, data: dict) -> dict[str, str]:
        header = data.get("header", {})
        values = {
            "cover_manager_name": stringify(header.get("manager_name")),
            "cover_product_name": stringify(header.get("product_name")),
            "cover_investigator": stringify(header.get("investigator")),
            "cover_report_date": dotted_date(header.get("report_date")),
            "cover_strategy_other_text": stringify(header.get("other_strategy_desc")),
        }
        selected = set(header.get("strategy_type") or [])
        for label, bookmark in self.STRATEGY_CHECKBOXES.items():
            values[bookmark] = "☑" if label in selected else "□"
        return values

    def _licensed(self, data: dict) -> dict[str, str]:
        values = self._cover(data)
        report = data.get("licensed_report", {})
        basic = report.get("basic_info", {})
        basic_keys = [
            "company_name", "registered_location", "registered_capital",
            "registered_address", "established_date", "legal_representative",
            "business_scope", "company_website", "total_aum", "non_mmf_aum",
            "public_products_count", "fund_manager_count",
        ]
        for row, key in enumerate(basic_keys):
            values[f"table_1_row{row}_col1"] = stringify(basic.get(key))
        self._map_rows(values, 2, report.get("shareholders", []), ["name", "ratio"], 1, 5)
        breakdown = get(report, "product.strategy_breakdown", []) or []
        self._map_rows(values, 3, breakdown, ["type", "aum"], 1, 3)
        values.update({
            "qa_section1_research_team": stringify(get(report, "team.description")),
            "qa_section2_strategy_logic": stringify(get(report, "product.strategy_overview")),
            "qa_section2_nav_history": stringify(get(report, "product.nav_trend")),
            "qa_section2_max_drawdowns": stringify(get(report, "product.drawdown_analysis")),
            "qa_section2_industry_allocation": stringify(get(report, "product.industry_allocation")),
            "qa_section2_holder_structure": stringify(get(report, "product.holder_structure")),
            "qa_section3_manager_bio": stringify(get(report, "fund_manager.profile")),
            "qa_section4_credit_screenshot_1": "",
            "qa_section4_credit_screenshot_2": "",
            "qa_section4_credit_screenshot_3": "",
            "qa_section5_conclusion": stringify(report.get("conclusion")),
        })
        for index in range(1, 12):
            values[f"attachment_extra_{index}"] = ""
        return values

    def _private(
        self, data: dict, *, include_revision_fields: bool = False
    ) -> dict[str, str]:
        values = self._cover(data)
        basic = data.get("section_1_1_basic_info_table", {})
        table1 = [
            basic.get("company_name"),
            basic.get("former_name"),
            combine(chinese_date(basic.get("established_date")), basic.get("registered_capital"),
            basic.get("paid_in_capital"), separator="/"),
            combine(basic.get("registered_address"), basic.get("actual_office_address"),
                    separator="/\n"),
            basic.get("legal_representative"),
            basic.get("business_scope"),
            combine(
                basic.get("amac_registration_no"),
                chinese_date(basic.get("amac_registration_date")),
                separator="/",
            ),
            basic.get("amac_member"),
            combine(
                basic.get("latest_aum"),
                chinese_date(basic.get("aum_stat_date")),
                separator="（",
            ) + (
                "）" if basic.get("aum_stat_date") else ""
            ),
            basic.get("own_capital_in_aum"),
            basic.get("aum_last_3_years"),
            combine(basic.get("total_products_issued"), basic.get("active_products"), separator="/"),
            basic.get("liquidated_by_stop_loss"),
            basic.get("products_above_par_ratio"),
            basic.get("advisory_aum"),
            basic.get("total_employees"),
            basic.get("research_team_size"),
            basic.get("research_team_change_1y"),
            basic.get("has_compliance_officer"),
            basic.get("compliance_officer_years"),
            basic.get("compliance_team_size"),
            whitelist_names(basic.get("other_whitelist")),
            basic.get("can_provide_daily_nav"),
            basic.get("can_provide_quarterly_l4"),
            basic.get("dd_contact_name"),
            basic.get("dd_contact_title"),
            basic.get("dd_contact_phone"),
            basic.get("dd_contact_email"),
            basic.get("dd_contact_address"),
        ]
        for row, value in enumerate(table1):
            values[f"table_1_row{row}_col1"] = stringify(value)
        self._map_rows(values, 2, get(data, "section_1_2_org_structure.departments", []),
                       ["name", "headcount", "functions", "head"], 1, 5)
        self._map_rows(values, 3, get(data, "section_1_3_equity.shareholders", []),
                       ["name", "ratio"], 1, 5)
        self._map_rows(values, 4, get(data, "section_1_4_team.yearly_headcount", []),
                       ["year", "headcount", "changes"], 1, 6)
        self._map_rows(values, 5, get(data, "section_1_5_key_personnel.members", []),
                       ["name", "title", "join_date", "education", "career"], 1, 5)
        systems = data.get("section_1_6_systems", {})
        system_keys = [
            "corporate_management", "investment_trading", "compliance_risk",
            "information_disclosure", "other",
        ]
        for row, key in enumerate(system_keys, 1):
            values[f"table_6_row{row}_col1"] = stringify(systems.get(key))
        for col in range(2):
            values[f"table_6_row6_col{col}"] = ""
        if include_revision_fields:
            report_date = dotted_date(get(data, "header.report_date"))
            for table in range(1, 13):
                values[f"table_{table}_data_cutoff_date"] = report_date
        self._private_product_tables(values, data)
        self._private_qa(values, data)
        return values

    @staticmethod
    def _map_rows(values, table, rows, keys, start, count):
        rows = rows or []
        values.setdefault("__dynamic_tables", {})[str(table)] = [
            {str(col): stringify(item.get(key)) for col, key in enumerate(keys)}
            for item in rows if isinstance(item, dict)
        ]
        for row in range(start, start + count):
            item = rows[row - start] if row - start < len(rows) else {}
            for col, key in enumerate(keys):
                values[f"table_{table}_row{row}_col{col}"] = stringify(item.get(key))

    def _private_product_tables(self, values: dict, data: dict) -> None:
        branches = [
            (7, "stock_subjective"), (8, "quantitative"), (9, "managed_futures"),
            (10, "fixed_income"), (11, "options_arbitrage"),
        ]
        strategy = data.get("section_1_9_strategy", {})
        for table, branch in branches:
            products = get(strategy, f"{branch}.representative_products", []) or []
            max_rows = 2 if table == 7 else 3
            self._map_rows(values, table, products,
                           ["name", "established", "annual_return", "max_dd", "aum"],
                           1, max_rows)
        overview = data.get("section_1_13_product_management", {}).get("strategy_overview", []) or []
        dynamic_overview = []
        for row in range(2, 7):
            item = overview[row - 2] if row - 2 < len(overview) else {}
            product = (item.get("products") or [{}])[0]
            row_values = [
                item.get("strategy_type"), item.get("aum"), product.get("name"),
                product.get("pm"), product.get("established"), product.get("aum"),
                product.get("annual_return"),
            ]
            for col, value in enumerate(row_values):
                values[f"table_12_row{row}_col{col}"] = stringify(value)
        for item in overview:
            product = (item.get("products") or [{}])[0]
            row_values = [
                item.get("strategy_type"), item.get("aum"), product.get("name"),
                product.get("pm"), product.get("established"), product.get("aum"),
                product.get("annual_return"),
            ]
            dynamic_overview.append({str(col): stringify(value) for col, value in enumerate(row_values)})
        values.setdefault("__dynamic_tables", {})["12"] = dynamic_overview

    def _private_qa(self, values: dict, data: dict) -> None:
        overview = stringify(get(data, "section_1_1_text.company_overview"))
        qualifications = stringify(get(data, "section_1_1_text.qualifications_licenses"))
        awards = stringify(get(data, "section_1_1_text.major_awards"))
        values.update({
            "qa_section1_q001_answer": combine(
                overview,
                qualifications,
                f"奖项：\n{awards}" if awards else "",
            ),
            "image_org_structure": self._image_value(
                get(data, "section_1_2_org_structure.chart_path")
                or get(data, "images.org_structure")
            ),
            "qa_section1_q003_answer": "",
            "qa_section1_q004_answer": stringify(get(data, "section_1_2_org_structure.research_team_plan")),
            "qa_section1_q005_answer": "",
            "qa_section1_q006_answer": stringify(get(data, "section_1_3_equity.equity_change_history")),
            "image_equity_structure": self._image_value(
                get(data, "section_1_3_equity.changed_structure_chart_path")
                or get(data, "images.equity_structure")
            ),
            "qa_section1_q007_answer": stringify(get(data, "section_1_3_equity.core_team_shareholding")),
            "qa_section1_q008_answer": combine(
                get(data, "section_1_3_equity.controlling_shareholder_info"),
                get(data, "section_1_3_equity.subsidiaries"),
                get(data, "section_1_3_equity.related_parties"),
            ),
            "qa_section1_q009_answer": "",
            "qa_section1_q010_answer": stringify(get(data, "section_1_4_team.supplementary")),
            "qa_section1_q011_answer": "",
            "qa_section1_q012_answer": stringify(get(data, "section_1_5_key_personnel.supplementary")),
            "qa_section1_q013_answer": "",
            "qa_section1_q014_answer": stringify(get(data, "section_1_7_incentives.description")),
            "qa_section1_q015_answer": combine(
                get(data, "section_1_8_it.it_products"),
                get(data, "section_1_8_it.server_hosting"),
                get(data, "section_1_8_it.it_investment_2y"),
            ),
            "qa_section1_q016_answer": stringify(get(data, "section_1_8_it.data_sources")),
            "qa_section1_q017_answer": stringify(get(data, "section_1_8_it.backup_mechanism")),
            "qa_section1_q018_answer": stringify(get(data, "section_1_8_it.emergency_measures")),
            "qa_section2_q019_answer": combine(
                get(data, "section_1_9_strategy.strategy_summary"),
                get(data, "section_1_9_strategy.strategy_idea_method_market"),
                get(data, "section_1_9_strategy.sub_strategy_ratios"),
            ),
            "qa_section2_q020_answer": combine(
                get(data, "section_1_9_strategy.investment_decision_process"),
                get(data, "section_1_9_strategy.decision_committee"),
            ),
            "qa_section2_q021_answer": stringify(
                get(data, "section_1_9_strategy.post_investment_monitoring")
            ),
            "qa_section2_q022_answer": stringify(
                get(data, "section_1_9_strategy.composite_sub_strategies")
            ),
            "qa_section2_q023_answer": stringify(
                get(data, "section_1_9_strategy.third_party_disclosure")
            ),
            "image_performance_comparison": self._image_value(
                get(data, "section_1_10_performance_comparison.chart_path")
                or get(data, "images.performance_comparison")
            ),
            "qa_section3_q120_answer": combine(
                get(data, "section_1_11_risk_control.risk_methods"),
                get(data, "section_1_11_risk_control.risk_system_features"),
            ),
            "qa_section3_q121_answer": combine(
                get(data, "section_1_11_risk_control.has_nav_warning_threshold"),
                get(data, "section_1_11_risk_control.risk_management_plan"),
            ),
            "qa_section3_q122_answer": self._manager_risks(data),
            "qa_section4_q123_answer": "",
            "qa_section4_q124_answer": combine(
                get(data, "section_1_13_product_management.aum_target_3y"),
                get(data, "section_1_13_product_management.ideal_aum"),
            ),
        })
        for number in range(125, 128):
            values[f"qa_section5_q{number:03d}_answer"] = ""
        for number in range(1, 4):
            values[f"qa_section5_credit_screenshot_{number}"] = self._image_value(
                get(data, f"section_1_14_credit_status.screenshot_{number}_path")
                or get(data, f"images.credit_status_{number}")
            )
        self._strategy_qa(values, data)

    @staticmethod
    def _image_value(value: Any) -> str:
        return stringify(value)

    @staticmethod
    def _manager_risks(data: dict) -> str:
        risks = data.get("section_1_12_manager_risks", {})
        lines = []
        for key, item in risks.items():
            if isinstance(item, dict) and item.get("exists"):
                lines.append(f"{key}：{item.get('detail') or '存在'}")
        return "\n".join(lines) if lines else "无"

    def _strategy_qa(self, values: dict, data: dict) -> None:
        strategy = data.get("section_1_9_strategy", {})
        managed = strategy.get("managed_futures", {})
        cta_map = {
            "strategy_type_mechanism": ["strategy_type_detail", "profit_mechanism"],
            "position_management": ["position_management", "max_margin_ratio"],
            "intraday_leverage": ["intraday_leverage"],
            "overnight_leverage": ["overnight_leverage"],
            "futures_allocation": [
                "financial_vs_commodity_ratio", "avg_instruments_count",
                "instrument_selection_criteria",
            ],
            "margin_usage": ["avg_margin_ratio", "max_margin_ratio_ex"],
            "trading_frequency": ["trading_frequency", "freq_breakdown_contribution"],
            "trading_system": ["trading_system_dev", "development_language",
                               "speed_hosting_acceleration_counter"],
            "trend_signal": ["trend_signal_mechanism"],
            "position_sizing": ["position_sizing_method", "signal_position_sizing"],
            "research_platform_data": ["research_platform", "data_sources_used", "data_sources"],
            "factor_inventory": ["factor_count_classification"],
            "factor_entry": ["factor_entry_criteria"],
            "factor_universality": ["universality_requirement"],
            "take_profit": ["has_take_profit"],
            "arbitrage_portfolio": ["arbitrage_pair_selection"],
            "cross_section_portfolio": ["cross_sectional_construction"],
            "adverse_market_drawdown": ["unfavorable_market", "max_drawdown_analysis"],
            "risk_mitigation": ["key_risks_and_mitigation"],
            "capacity": ["estimated_capacity"],
            "competitive_advantage": ["competitive_advantage"],
            "future_research": ["future_research_direction"],
        }
        applicable = bool(managed.get("_applicable"))
        for suffix, keys in cta_map.items():
            values[f"strat_cta_{suffix}"] = (
                combine(*(managed.get(key) for key in keys)) if applicable else ""
            )
        branch_maps = {
            "quant": ("quantitative", {
                "methodology": ["quant_methodology"],
                "stock_pool": ["stock_universe"],
                "style_industry_exposure": ["exposure_constraints", "exposure_monitoring_freq"],
                "holding_constraints": ["holdings_count", "holding_period_turnover", "single_stock_cap", "has_stop_loss"],
                "benchmark_index": ["benchmark_index"],
                "team_structure": ["quant_team_groups"],
                "factor_sources": ["factor_source", "total_factors_in_pool"],
                "factor_mix": ["active_factors_classification_weight", "factor_correlation_requirement"],
                "factor_substrategy": ["factor_sub_strategy", "sub_strategy_count"],
                "factor_entry": ["factor_entry_criteria", "factor_stability_requirement"],
                "risk_profit_factor": ["risk_vs_alpha_factor"],
                "machine_learning": ["uses_ml_dl"],
                "ml_features_compute": ["ml_original_features", "ml_dim_reduction", "ml_base_learner", "ml_compute_resources"],
                "ml_explainability": ["ml_interpretability", "ml_correlation_reduction"],
                "capacity": ["strategy_capacity"],
                "max_drawdown": ["nav_and_excess_max_dd"],
                "research_trading_system": ["trading_systems"],
                "enhanced_neutral_consistency": ["enhanced_vs_neutral_overlap"],
                "neutral_hedging": ["neutral_hedging_instrument", "neutral_market_exposure", "neutral_exposure_monitoring_freq"],
                "neutral_dynamic_position": ["neutral_dynamic_position"],
                "basis_risk": ["basis_volatility_management"],
                "competitive_advantage": ["competitive_advantage"],
            }),
            "bond": ("fixed_income", {
                "investment_scope": ["investment_scope"],
                "allocation_rating_concentration": ["allocation_and_min_rating", "top5_concentration"],
                "leverage": ["avg_leverage", "max_leverage"],
                "issuer_region_rating": ["issuer_type_region", "issuer_rating_requirement"],
                "industry_price_duration_limits": ["industry_concentration_limit", "price_deviation_limit", "avg_duration"],
                "blacklist": ["blacklist_and_avoidance"],
                "credit_downshift": ["credit_downgrade_approach"],
                "turnover_trading_system": ["trading_frequency", "trading_system"],
                "repo_counterparties": ["repo_participation", "repo_top5_counterparties"],
                "equity_exposure": ["equity_exposure_ratio"],
                "local_government_bonds": ["urban_investment_bonds"],
                "property_bonds": ["property_bonds"],
                "performance_attribution": ["performance_attribution"],
                "max_drawdown": ["max_drawdown_analysis"],
                "market_outlook": ["market_outlook_short", "market_outlook_medium", "market_outlook_long"],
                "competitive_advantage": ["competitive_advantage"],
            }),
            "option": ("options_arbitrage", {
                "strategy_logic_weights": ["strategy_logic_and_sub_weights"],
                "underlying_capital_allocation": ["instrument_selection_allocation"],
                "short_option_ratio": ["short_option_ratio", "near_term_contracts"],
                "volatility_forecast": ["volatility_forecast_method"],
                "market_data_cycle": ["market_data_source", "intraday_data_period"],
                "frequency_holding_pricing": ["trading_freq_holding_period", "pricing_model_freq"],
                "hedging": ["hedging_method_freq"],
                "greeks_tail_risk": ["risk_monitoring_greeks", "tail_risk_management"],
                "position_holiday": ["position_management", "holiday_position_adjustment"],
                "risk_system": ["risk_system_build_or_vendor"],
                "stress_test": ["stress_test_scenarios"],
                "trading_system": ["trading_system_type"],
                "signal_pm_trader_roles": ["signal_decision", "pm_trader_division"],
                "capacity": ["capacity_limit_factors"],
                "market_suitability": ["favorable_vs_unfavorable_market"],
                "top_drawdowns": ["top3_daily_drawdowns"],
                "competitive_advantage": ["peer_comparison_advantage"],
            }),
        }
        for prefix, (branch_name, field_map) in branch_maps.items():
            branch = strategy.get(branch_name, {})
            applicable = bool(branch.get("_applicable"))
            for suffix, keys in field_map.items():
                values[f"strat_{prefix}_{suffix}"] = (
                    combine(*(branch.get(key) for key in keys)) if applicable else ""
                )
