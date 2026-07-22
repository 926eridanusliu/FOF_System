from __future__ import annotations

from .base_filler import BaseFiller


class CheckboxFiller(BaseFiller):
    category = "cover_checkbox"

    POSITIONS = {
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

    def fill(self, field: str, value: object):
        result = self.fill_result(field, value)
        return result.as_tuple()

    def fill_result(self, field: str, value: object):
        located = self.bookmark(field)
        if located is None:
            return self.result(False, field, value, field, message="未找到复选框书签")
        normalized = self._normalize(value)
        abnormal, message = self.styles.validate_value(str(value), self.category)
        start, _, _ = located
        paragraph = start.getparent()
        wanted = self.POSITIONS.get(field)
        if wanted is None:
            return self.result(False, field, value, f"bookmark:{field}", message="未配置复选框坐标")
        count = 0
        for text in paragraph.xpath("./w:r/w:t", namespaces=self.package.NS):
            chars = list(text.text or "")
            for index, char in enumerate(chars):
                if char == "□" or char == "☑":
                    count += 1
                    if count == wanted:
                        chars[index] = normalized
                        text.text = "".join(chars)
                        return self.result(
                            True,
                            field,
                            normalized,
                            f"bookmark:{field}; checkbox:{wanted}",
                            abnormal=abnormal,
                            message=message,
                        )
        return self.result(False, field, value, f"bookmark:{field}", message="目标复选框不存在")

    @staticmethod
    def _normalize(value: object) -> str:
        if value in {True, 1, "1", "true", "True", "✓", "☑"}:
            return "☑"
        return "□"
