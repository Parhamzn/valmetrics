"""Discounted Future Market Cap — equity-side multiples valuation.

Projects net income forward N years at a fixed growth rate, applies a terminal
P/E multiple to year-N earnings to estimate the future market cap, and
discounts that future market cap back to today (equity-side discount rate).
Fair value per share = PV(future market cap) / current diluted shares.

This is the equity analogue of an EV/EBITDA exit-multiple DCF: instead of an
enterprise value built from FCFF + multiple-based TV, we go straight to
equity value via P/E.

Important caveat for loss-making companies: if ``base_net_income <= 0`` the
projection's NI stays non-positive (or even diverges in sign if growth is
applied to a negative base), and the terminal market cap is meaningless under
a P/E framework. The engine still runs and returns the (negative or zero) per-
share value; the view / template should flag this case so users know the
model doesn't apply.

Source: Corporate Finance Institute, "Terminal Value"
(https://corporatefinanceinstitute.com/resources/valuation/terminal-value/).
"""

from __future__ import annotations

from apps.valuation.engine.types_discounted_future_mcap import (
    DFMCInputs,
    DFMCOutputs,
)


# Source: CFI "Terminal Value" — equity-side P/E variant of an exit multiple.
def discounted_future_mcap(inputs: DFMCInputs) -> DFMCOutputs:
    """Run the Discounted Future Market Cap model.

    Algorithm:
        1. For t in 1..N: ni_t = base_ni * (1 + g) ** t.
        2. terminal_ni = ni_N (use last projected year directly).
        3. future_market_cap = terminal_ni * terminal_pe.
        4. pv_future_market_cap = future_market_cap / (1 + discount_rate) ** N.
        5. fair_value_per_share = pv_future_market_cap / shares_outstanding.

    Raises:
        ValueError: if terminal_pe <= 0 (multiple undefined).
        ValueError: if shares_outstanding <= 0.
    """
    if inputs.terminal_pe <= 0:
        raise ValueError(
            "Discounted Future Market Cap requires terminal_pe > 0; "
            f"got terminal_pe={inputs.terminal_pe}."
        )
    if inputs.shares_outstanding <= 0:
        raise ValueError(
            f"shares_outstanding must be > 0; got {inputs.shares_outstanding}."
        )

    n = inputs.projection_years
    g = inputs.net_income_growth_rate
    base_ni = inputs.base_net_income

    projected: list[tuple[int, float]] = []
    last_ni = base_ni
    for t in range(1, n + 1):
        ni_t = base_ni * ((1.0 + g) ** t)
        projected.append((t, ni_t))
        last_ni = ni_t

    terminal_ni = last_ni
    future_market_cap = terminal_ni * inputs.terminal_pe
    pv_future_market_cap = (
        future_market_cap / ((1.0 + inputs.discount_rate) ** n) if n > 0
        else future_market_cap
    )

    fair_value_per_share = pv_future_market_cap / inputs.shares_outstanding

    return DFMCOutputs(
        projected_net_incomes=projected,
        terminal_net_income=terminal_ni,
        future_market_cap=future_market_cap,
        pv_future_market_cap=pv_future_market_cap,
        fair_value_per_share=fair_value_per_share,
    )
