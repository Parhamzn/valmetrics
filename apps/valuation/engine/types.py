"""Structured input/output dataclasses for the valuation engine.

All types are frozen dataclasses to keep model results immutable and hashable
once produced. Floats default to 0.0 where a particular model does not use the
field, so the same ProjectionYear schema can carry data from richer models in
future without breaking callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectionYear:
    """A single year of projected cash-flow line items.

    Not every model populates every field. Models that do not separately track
    capex / depreciation / working-capital changes should set those fields to
    0.0 and use a combined reinvestment figure inside fcff.
    """

    year: int
    revenue: float
    ebit: float
    tax_paid: float
    nopat: float
    dep_amort: float
    capex: float
    change_in_wc: float
    fcff: float
    discount_factor: float
    pv_fcff: float


# ---------------------------------------------------------------------------
# DCF (perpetual growth)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DCFInputs:
    """Inputs for the perpetual-growth DCF model.

    Attributes:
        ticker: Identifier for the security being valued (display only).
        base_revenue: Revenue in the trailing/base year (year 0).
        base_fcff: FCFF in the trailing/base year (year 0). Provided for context;
            forward FCFF is rebuilt from revenue * margins * (1 - reinvest).
        projection_years: Number of explicit forecast years (default 5).
        revenue_growth_rate: Annual revenue growth in the explicit period.
        ebit_margin: EBIT / revenue.
        tax_rate: Effective tax rate applied to positive EBIT.
        reinvestment_rate: Net reinvestment as a fraction of NOPAT
            (capex + change in WC - D&A) / NOPAT. Set 0.0 to imply FCFF == NOPAT.
        terminal_growth: Perpetual growth rate beyond the explicit period.
        wacc: Weighted-average cost of capital, used as the discount rate.
        net_debt: Total debt minus cash & equivalents (bridge to equity).
        shares_outstanding: Diluted share count for per-share fair value.
    """

    ticker: str
    base_revenue: float
    base_fcff: float
    projection_years: int = 5
    revenue_growth_rate: float = 0.0
    ebit_margin: float = 0.0
    tax_rate: float = 0.0
    reinvestment_rate: float = 0.0
    terminal_growth: float = 0.0
    wacc: float = 0.0
    net_debt: float = 0.0
    shares_outstanding: float = 0.0


@dataclass(frozen=True)
class DCFOutputs:
    projections: List[ProjectionYear] = field(default_factory=list)
    terminal_value: float = 0.0
    pv_terminal_value: float = 0.0
    enterprise_value: float = 0.0
    equity_value: float = 0.0
    fair_value_per_share: float = 0.0


# ---------------------------------------------------------------------------
# Dividend discount models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimpleDDMInputs:
    """Gordon-growth DDM inputs (single-stage)."""

    current_dividend: float
    growth_rate: float
    required_return: float


@dataclass(frozen=True)
class SimpleDDMOutputs:
    fair_value: float


@dataclass(frozen=True)
class TwoStageDDMInputs:
    """Two-stage DDM: explicit high-growth period then perpetual stable growth."""

    current_dividend: float
    high_growth_rate: float
    high_growth_years: int
    terminal_growth_rate: float
    required_return: float


@dataclass(frozen=True)
class TwoStageDDMOutputs:
    # Each tuple: (year, dividend, pv_of_dividend)
    projections: List[Tuple[int, float, float]] = field(default_factory=list)
    terminal_value: float = 0.0
    pv_terminal_value: float = 0.0
    fair_value: float = 0.0


# ---------------------------------------------------------------------------
# WACC / CAPM
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CAPMInputs:
    risk_free_rate: float
    beta: float
    equity_risk_premium: float


@dataclass(frozen=True)
class CAPMOutputs:
    cost_of_equity: float


@dataclass(frozen=True)
class WACCInputs:
    cost_of_equity: float
    cost_of_debt: float
    tax_rate: float
    market_value_equity: float
    market_value_debt: float


@dataclass(frozen=True)
class WACCOutputs:
    wacc: float
    equity_weight: float
    debt_weight: float
