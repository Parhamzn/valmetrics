"""Simple Excess Return Model (constant growth).

Damodaran's preferred valuation approach for financial-services firms (banks,
insurance), where book equity is economically meaningful and reported cash
flows are noisy. Equity value is anchored at current book value and adjusted
upward (or downward) by the present value of perpetual returns above (below)
the cost of equity.

Reference: Damodaran, "Valuing Financial Service Firms" (NYU Stern),
https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/finfirm09.pdf
"""

from __future__ import annotations

from apps.valuation.engine.types_excess_return import (
    SimpleExcessReturnInputs,
    SimpleExcessReturnOutputs,
)


def simple_excess_return(
    inputs: SimpleExcessReturnInputs,
) -> SimpleExcessReturnOutputs:
    """Damodaran's constant-growth excess return model.

    Formula::

        V = BV + [BV × (ROE − Ke) × (1 + g) / (Ke − g)]

    Equivalently::

        excess_return_per_share = (ROE − Ke) × BV
        pv_perpetual_excess     = excess_return_per_share × (1 + g) / (Ke − g)
        fair_value_per_share    = BV + pv_perpetual_excess

    Source: Damodaran, "Valuing Financial Service Firms" (NYU).

    Notes:
        ``fair_value_per_share`` can fall below ``book_value_per_share`` when
        ROE < Ke — the firm is destroying value, and the market should be
        willing to pay less than book.

    Raises:
        ValueError: if ``growth_rate >= cost_of_equity`` (Gordon denominator
            non-positive).
        ValueError: if ``book_value_per_share <= 0`` (model meaningless for
            negative-equity firms).
    """
    if inputs.growth_rate >= inputs.cost_of_equity:
        raise ValueError(
            "Simple Excess Return requires growth_rate < cost_of_equity; "
            f"got growth_rate={inputs.growth_rate}, "
            f"cost_of_equity={inputs.cost_of_equity}."
        )
    if inputs.book_value_per_share <= 0:
        raise ValueError(
            "Simple Excess Return requires book_value_per_share > 0; "
            f"got {inputs.book_value_per_share}. The model is meaningless "
            "for negative-equity firms."
        )

    excess_return = (
        inputs.return_on_equity - inputs.cost_of_equity
    ) * inputs.book_value_per_share

    pv = excess_return * (1.0 + inputs.growth_rate) / (
        inputs.cost_of_equity - inputs.growth_rate
    )

    fair_value = inputs.book_value_per_share + pv

    return SimpleExcessReturnOutputs(
        excess_return_per_share=excess_return,
        pv_perpetual_excess=pv,
        fair_value_per_share=fair_value,
    )
