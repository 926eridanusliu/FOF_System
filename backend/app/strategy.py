"""Shared product strategy keys and branch rules."""

STRATEGY_BRANCHES: dict[str, str | None] = {
    "cover_strategy_stock_index_enhanced": "quant",
    "cover_strategy_stock_quant": "quant",
    "cover_strategy_stock_discretionary": None,
    "cover_strategy_macro_hedge": None,
    # The private-fund template places its market-neutral questions in the
    # quantitative strategy section.
    "cover_strategy_market_neutral": "quant",
    "cover_strategy_futures_options_arbitrage": "option",
    "cover_strategy_t0": "quant",
    "cover_strategy_bond_pure": "bond",
    "cover_strategy_bond_enhanced": "bond",
    "cover_strategy_bond_composite": "bond",
    "cover_strategy_convertible_bond": "bond",
    "cover_strategy_futures_quant_trend": "cta",
    "cover_strategy_futures_discretionary": "cta",
    "cover_strategy_composite": None,
    # Stored on products so the selection can flow into the report cover's
    # free-text "其他投资策略" slot without introducing an unknown report field.
    "cover_strategy_other": None,
}

STRATEGY_KEYS = frozenset(STRATEGY_BRANCHES)


def validate_strategy_keys(values: list[str]) -> list[str]:
    """Deduplicate and validate strategy bookmark keys while preserving order."""
    unique = list(dict.fromkeys(values))
    invalid = [value for value in unique if value not in STRATEGY_KEYS]
    if invalid:
        raise ValueError(f"未知策略字段：{', '.join(invalid)}")
    return unique
