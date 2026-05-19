"""Input/output dataclasses for the Earnings Power Value (EPV) model.

Kept separate from ``types.py`` so this file can be authored without colliding
with concurrent edits to the main engine types module. Greenwald-style EPV
values the firm assuming it earns its current normalized earnings forever with
no growth; the inputs reflect that no-growth, normalized stance.

Source: Greenwald et al., *Value Investing: From Graham to Buffett and Beyond*,
ch. 6 ("Earnings Power Value"); CFI EPV explainer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EPVInputs:
    """Normalized inputs for a Greenwald-style EPV calculation.

    Attributes:
        ticker: Display identifier.
        normalized_ebit: Average EBIT over a full business cycle (>=5y ideal).
            The user can override this on the form.
        tax_rate: Effective tax rate as a decimal (e.g. 0.21).
        maintenance_capex: Capex required just to sustain existing earnings
            power. Greenwald's heuristic for mature firms is to use D&A as the
            proxy; the form lets the user override.
        depreciation_amortization: Latest (or normalized) D&A. The EPV form
            adds D&A back, then subtracts maintenance capex; for stable firms
            those roughly cancel.
        wacc: Discount rate (weighted-average cost of capital).
        net_debt: Total debt minus cash & equivalents. Used to bridge from
            enterprise value to equity value.
        shares_outstanding: Diluted share count for the per-share figure.
        years_of_history: How many years of EBIT went into ``normalized_ebit``;
            carried through for display, not used in math.
    """

    ticker: str
    normalized_ebit: float
    tax_rate: float
    maintenance_capex: float
    depreciation_amortization: float
    wacc: float
    net_debt: float
    shares_outstanding: float
    years_of_history: int


@dataclass(frozen=True)
class EPVOutputs:
    """Computed Greenwald EPV breakdown.

    Attributes:
        adjusted_ebit: normalized_ebit + D&A - maintenance_capex.
        nopat: adjusted_ebit * (1 - tax_rate).
        enterprise_value: nopat / wacc.
        equity_value: enterprise_value - net_debt. Can be negative (legitimate
            result: equity is worthless at this earnings level).
        epv_per_share: equity_value / shares_outstanding.
    """

    adjusted_ebit: float
    nopat: float
    enterprise_value: float
    equity_value: float
    epv_per_share: float
