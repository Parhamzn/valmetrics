"""Discounted Cash Flow (DCF) with perpetual terminal growth.

Models firm value as the present value of explicit-period FCFF plus a Gordon
terminal value, then bridges to equity via net debt.
"""

from __future__ import annotations

from apps.valuation.engine.types import DCFInputs, DCFOutputs, ProjectionYear


def dcf_perpetual_growth(inputs: DCFInputs) -> DCFOutputs:
    """Run a perpetual-growth DCF and return projections + valuation summary.

    The model intentionally keeps capex / D&A / change_in_wc as 0.0 placeholders
    on each ProjectionYear; net reinvestment is folded into a single fraction
    of NOPAT (``reinvestment_rate``). The schema leaves room to break those out
    later without changing call sites.

    Raises:
        ValueError: if wacc <= terminal_growth (terminal value undefined).
        ValueError: if shares_outstanding <= 0.
    """
    if inputs.wacc <= inputs.terminal_growth:
        raise ValueError(
            "DCF requires wacc > terminal_growth; "
            f"got wacc={inputs.wacc}, terminal_growth={inputs.terminal_growth}."
        )
    if inputs.shares_outstanding <= 0:
        raise ValueError(
            f"shares_outstanding must be > 0; got {inputs.shares_outstanding}."
        )

    n = inputs.projection_years
    g = inputs.revenue_growth_rate
    margin = inputs.ebit_margin
    tax = inputs.tax_rate
    reinvest = inputs.reinvestment_rate
    wacc_rate = inputs.wacc

    projections: list[ProjectionYear] = []
    prev_revenue = inputs.base_revenue
    last_fcff = inputs.base_fcff  # fallback if N == 0
    sum_pv_fcff = 0.0

    for t in range(1, n + 1):
        revenue_t = prev_revenue * (1.0 + g)
        ebit_t = revenue_t * margin
        tax_t = max(0.0, ebit_t) * tax
        nopat_t = ebit_t - tax_t
        reinvestment_t = nopat_t * reinvest
        fcff_t = nopat_t - reinvestment_t

        discount_factor_t = (1.0 + wacc_rate) ** t
        pv_fcff_t = fcff_t / discount_factor_t

        projections.append(
            ProjectionYear(
                year=t,
                revenue=revenue_t,
                ebit=ebit_t,
                tax_paid=tax_t,
                nopat=nopat_t,
                dep_amort=0.0,
                capex=0.0,
                change_in_wc=0.0,
                fcff=fcff_t,
                discount_factor=discount_factor_t,
                pv_fcff=pv_fcff_t,
            )
        )

        sum_pv_fcff += pv_fcff_t
        prev_revenue = revenue_t
        last_fcff = fcff_t

    # Terminal value at end of year N using FCFF_{N+1}.
    fcff_n_plus_1 = last_fcff * (1.0 + inputs.terminal_growth)
    terminal_value = fcff_n_plus_1 / (wacc_rate - inputs.terminal_growth)
    pv_terminal_value = terminal_value / ((1.0 + wacc_rate) ** n) if n > 0 else terminal_value

    enterprise_value = sum_pv_fcff + pv_terminal_value
    equity_value = enterprise_value - inputs.net_debt
    fair_value_per_share = equity_value / inputs.shares_outstanding

    return DCFOutputs(
        projections=projections,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal_value,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
    )
