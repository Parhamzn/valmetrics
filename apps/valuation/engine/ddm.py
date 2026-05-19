"""Dividend Discount Models.

- simple_ddm:    Gordon growth (single stage).
- two_stage_ddm: Explicit high-growth phase followed by stable perpetual growth.
"""

from __future__ import annotations

from apps.valuation.engine.types import (
    SimpleDDMInputs,
    SimpleDDMOutputs,
    TwoStageDDMInputs,
    TwoStageDDMOutputs,
)


def simple_ddm(inputs: SimpleDDMInputs) -> SimpleDDMOutputs:
    """Gordon growth DDM: FV = D1 / (r - g), with D1 = D0 * (1 + g).

    Raises:
        ValueError: if growth_rate >= required_return (model undefined / non-positive).
    """
    if inputs.growth_rate >= inputs.required_return:
        raise ValueError(
            "Simple DDM requires growth_rate < required_return; "
            f"got g={inputs.growth_rate}, r={inputs.required_return}."
        )

    d1 = inputs.current_dividend * (1.0 + inputs.growth_rate)
    fair_value = d1 / (inputs.required_return - inputs.growth_rate)
    return SimpleDDMOutputs(fair_value=fair_value)


def two_stage_ddm(inputs: TwoStageDDMInputs) -> TwoStageDDMOutputs:
    """Two-stage DDM.

    Phase 1: explicit dividends for t=1..N, each growing at high_growth_rate
             from current_dividend (D0). PV at required_return.
    Phase 2: terminal value at end of year N using Gordon on D_{N+1}, where
             D_{N+1} = D_N * (1 + terminal_growth_rate). PV that TV back to t=0.
    Fair value = sum(PV dividends) + PV(TV).

    Raises:
        ValueError: if terminal_growth_rate >= required_return.
    """
    if inputs.terminal_growth_rate >= inputs.required_return:
        raise ValueError(
            "Two-stage DDM requires terminal_growth_rate < required_return; "
            f"got g={inputs.terminal_growth_rate}, r={inputs.required_return}."
        )

    r = inputs.required_return
    g1 = inputs.high_growth_rate
    g_term = inputs.terminal_growth_rate
    n = inputs.high_growth_years

    projections: list[tuple[int, float, float]] = []
    sum_pv_dividends = 0.0
    last_dividend = inputs.current_dividend

    for t in range(1, n + 1):
        dividend_t = inputs.current_dividend * ((1.0 + g1) ** t)
        pv_t = dividend_t / ((1.0 + r) ** t)
        projections.append((t, dividend_t, pv_t))
        sum_pv_dividends += pv_t
        last_dividend = dividend_t

    # Terminal value at end of year N, using D_{N+1}.
    d_n_plus_1 = last_dividend * (1.0 + g_term)
    terminal_value = d_n_plus_1 / (r - g_term)
    pv_terminal_value = terminal_value / ((1.0 + r) ** n)

    fair_value = sum_pv_dividends + pv_terminal_value

    return TwoStageDDMOutputs(
        projections=projections,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal_value,
        fair_value=fair_value,
    )
