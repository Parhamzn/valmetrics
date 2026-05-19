"""Weighted-Average Cost of Capital (WACC).

WACC = (E / V) * Ke + (D / V) * Kd * (1 - tax_rate)
where V = E + D.
"""

from __future__ import annotations

from apps.valuation.engine.types import WACCInputs, WACCOutputs


def wacc(inputs: WACCInputs) -> WACCOutputs:
    """Return the WACC and capital-structure weights.

    Raises:
        ValueError: if the total invested capital (MVE + MVD) is non-positive.
    """
    total = inputs.market_value_equity + inputs.market_value_debt
    if total <= 0:
        raise ValueError(
            "Total invested capital (market_value_equity + market_value_debt) "
            "must be positive."
        )

    equity_weight = inputs.market_value_equity / total
    debt_weight = inputs.market_value_debt / total
    after_tax_kd = inputs.cost_of_debt * (1.0 - inputs.tax_rate)
    wacc_value = equity_weight * inputs.cost_of_equity + debt_weight * after_tax_kd

    return WACCOutputs(
        wacc=wacc_value,
        equity_weight=equity_weight,
        debt_weight=debt_weight,
    )
