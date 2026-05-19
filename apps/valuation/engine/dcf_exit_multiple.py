"""DCF with an EV/EBITDA exit-multiple terminal value.

Same FCFF projection mechanics as the perpetual-growth DCF, but the terminal
value is ``Year N EBITDA × Exit EV/EBITDA multiple`` instead of a Gordon-growth
perpetuity. This is the practitioner-favored approach (especially in private
equity / banking) because it anchors the terminal value to observable market
multiples; the academic critique is that multiples drift over time.

We also expose an *implied terminal growth* diagnostic: given the exit-multiple
TV, what perpetual growth rate ``g`` would Gordon-growth need to produce the
same number? Damodaran's standard caveat is to always sanity-check this — if
the implied ``g`` is above the risk-free rate (or below zero) the multiple is
likely inconsistent with the explicit projection.

Sources:
- Corporate Finance Institute, "Terminal Value"
  (https://corporatefinanceinstitute.com/resources/valuation/terminal-value/)
- Damodaran, DCF lecture notes
  (https://pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/dcfallOld.pdf)
"""

from __future__ import annotations

from apps.valuation.engine.types_dcf_exit_multiple import (
    DCFExitMultipleInputs,
    DCFExitMultipleOutputs,
    ExitMultipleProjectionYear,
)


# Source: CFI "Terminal Value"; Damodaran DCF notes — exit-multiple TV.
def dcf_exit_multiple(inputs: DCFExitMultipleInputs) -> DCFExitMultipleOutputs:
    """Run an exit-multiple DCF and return projections + valuation summary.

    Algorithm:
      1. For t in 1..N project revenue, EBIT, EBITDA, NOPAT, FCFF and discount.
         EBITDA each year = revenue_t × ebitda_margin.
      2. terminal_ebitda = ebitda at year N.
      3. terminal_value = terminal_ebitda × exit_ev_ebitda.
      4. pv_terminal_value = terminal_value / (1 + wacc) ** N.
      5. implied_terminal_growth: solve Gordon TV = FCFF_{N+1} / (wacc - g)
         for g, treating FCFF_{N+1} as FCFF_N (no further growth assumed in the
         diagnostic). g = wacc - (FCFF_N / terminal_value). Diagnostic only.
      6. enterprise_value = sum(pv_fcff) + pv_terminal_value.
      7. equity_value = EV - net_debt.
      8. fair_value_per_share = equity_value / shares_outstanding.

    Raises:
        ValueError: if exit_ev_ebitda <= 0 (terminal value undefined).
        ValueError: if shares_outstanding <= 0.
    """
    if inputs.exit_ev_ebitda <= 0:
        raise ValueError(
            "DCF exit-multiple requires exit_ev_ebitda > 0; "
            f"got exit_ev_ebitda={inputs.exit_ev_ebitda}."
        )
    if inputs.shares_outstanding <= 0:
        raise ValueError(
            f"shares_outstanding must be > 0; got {inputs.shares_outstanding}."
        )

    n = inputs.projection_years
    g = inputs.revenue_growth_rate
    ebit_m = inputs.ebit_margin
    ebitda_m = inputs.ebitda_margin
    tax = inputs.tax_rate
    reinvest = inputs.reinvestment_rate
    wacc_rate = inputs.wacc

    projections: list[ExitMultipleProjectionYear] = []
    prev_revenue = inputs.base_revenue
    last_fcff = 0.0
    last_ebitda = inputs.base_ebitda
    sum_pv_fcff = 0.0

    for t in range(1, n + 1):
        revenue_t = prev_revenue * (1.0 + g)
        ebit_t = revenue_t * ebit_m
        ebitda_t = revenue_t * ebitda_m
        tax_t = max(0.0, ebit_t) * tax
        nopat_t = ebit_t - tax_t
        reinvestment_t = nopat_t * reinvest
        fcff_t = nopat_t - reinvestment_t

        discount_factor_t = (1.0 + wacc_rate) ** t
        pv_fcff_t = fcff_t / discount_factor_t

        projections.append(
            ExitMultipleProjectionYear(
                year=t,
                revenue=revenue_t,
                ebit=ebit_t,
                ebitda=ebitda_t,
                tax_paid=tax_t,
                nopat=nopat_t,
                fcff=fcff_t,
                discount_factor=discount_factor_t,
                pv_fcff=pv_fcff_t,
            )
        )

        sum_pv_fcff += pv_fcff_t
        prev_revenue = revenue_t
        last_fcff = fcff_t
        last_ebitda = ebitda_t

    # Terminal value from the exit multiple applied to Year N EBITDA.
    terminal_ebitda = last_ebitda
    terminal_value = terminal_ebitda * inputs.exit_ev_ebitda
    pv_terminal_value = (
        terminal_value / ((1.0 + wacc_rate) ** n) if n > 0 else terminal_value
    )

    # Implied perpetual growth diagnostic: solve TV = FCFF_N / (wacc - g)
    # => g = wacc - FCFF_N / TV. (Per Damodaran's sanity-check guidance.)
    if terminal_value != 0:
        implied_terminal_growth = wacc_rate - (last_fcff / terminal_value)
    else:
        implied_terminal_growth = 0.0

    enterprise_value = sum_pv_fcff + pv_terminal_value
    equity_value = enterprise_value - inputs.net_debt
    fair_value_per_share = equity_value / inputs.shares_outstanding

    return DCFExitMultipleOutputs(
        projections=projections,
        terminal_ebitda=terminal_ebitda,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal_value,
        implied_terminal_growth=implied_terminal_growth,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
    )
