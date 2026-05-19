"""Input/output dataclasses for the DCF — Exit Multiple model.

Kept separate from ``types.py`` so this file can be authored without colliding
with concurrent edits to the main engine types module. The mechanics of the
explicit-period FCFF projection match the perpetual-growth DCF; the only
difference is the terminal value, which is computed as
``Year N EBITDA × Exit EV/EBITDA multiple`` instead of a Gordon-growth
perpetuity.

Source: Corporate Finance Institute, "Terminal Value" explainer
(https://corporatefinanceinstitute.com/resources/valuation/terminal-value/);
Damodaran, *Investment Valuation* / DCF notes — recommends always
back-solving the implied perpetual growth rate as a sanity check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ExitMultipleProjectionYear:
    """One year of projected line items for the exit-multiple DCF.

    Same shape as :class:`apps.valuation.engine.types.ProjectionYear` but adds
    an explicit ``ebitda`` field so the terminal multiple can be applied to a
    Year N EBITDA we already track on the projection table.
    """

    year: int
    revenue: float
    ebit: float
    ebitda: float
    tax_paid: float
    nopat: float
    fcff: float
    discount_factor: float
    pv_fcff: float


@dataclass(frozen=True)
class DCFExitMultipleInputs:
    """Inputs for the DCF — Exit Multiple model.

    Attributes:
        ticker: Display identifier.
        base_revenue: Revenue in the trailing/base year.
        base_ebitda: EBITDA in the trailing/base year (for display).
        projection_years: Number of explicit forecast years (default 5).
        revenue_growth_rate: Annual revenue growth in the explicit period.
        ebit_margin: EBIT / revenue applied each year.
        ebitda_margin: EBITDA / revenue applied each year (used to project the
            Year N EBITDA that we multiply by the exit multiple).
        tax_rate: Effective tax rate applied to positive EBIT.
        reinvestment_rate: Net reinvestment as a fraction of NOPAT.
        wacc: Discount rate.
        exit_ev_ebitda: The terminal EV/EBITDA multiple. Must be > 0.
        net_debt: Total debt minus cash & equivalents.
        shares_outstanding: Diluted share count for per-share fair value.
    """

    ticker: str
    base_revenue: float
    base_ebitda: float
    projection_years: int = 5
    revenue_growth_rate: float = 0.0
    ebit_margin: float = 0.0
    ebitda_margin: float = 0.0
    tax_rate: float = 0.0
    reinvestment_rate: float = 0.0
    wacc: float = 0.0
    exit_ev_ebitda: float = 0.0
    net_debt: float = 0.0
    shares_outstanding: float = 0.0


@dataclass(frozen=True)
class DCFExitMultipleOutputs:
    """Computed exit-multiple DCF breakdown."""

    projections: List[ExitMultipleProjectionYear] = field(default_factory=list)
    terminal_ebitda: float = 0.0
    terminal_value: float = 0.0
    pv_terminal_value: float = 0.0
    # Diagnostic: back-solved long-run growth implied by the chosen multiple.
    # Damodaran's standard caveat is to sanity-check this number.
    implied_terminal_growth: float = 0.0
    enterprise_value: float = 0.0
    equity_value: float = 0.0
    fair_value_per_share: float = 0.0
