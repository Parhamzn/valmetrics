"""Input/output dataclasses for the EV/Sales (EV/Revenue) Multiple model.

Kept in its own module so this multiples model can be authored without
touching the shared ``types.py``. EV/Sales is the go-to multiple for
unprofitable or pre-profit companies (early-stage tech, SaaS, biotech) where
EBITDA-based multiples don't work — revenue exists even when earnings don't.

Source: Damodaran, *Investment Valuation* ch. 20 "Revenue Multiples & Sector-
Specific Multiples" (https://pages.stern.nyu.edu/~adamodar/pdfiles/val3ed/c20.pdf);
Corporate Finance Institute multiples resources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EVSalesInputs:
    """Inputs for the EV/Sales multiple valuation.

    Attributes:
        ticker: Display identifier.
        revenue: Trailing (or normalized) total revenue. ``revenue <= 0`` will
            cause the engine to raise — rare but possible for pre-revenue
            biotechs.
        target_ev_sales: User-supplied target EV/Sales multiple — "what if
            this traded at peer-group X times revenue".
        net_debt: Total debt minus cash & equivalents (bridge to equity).
        shares_outstanding: Diluted share count for the per-share figure.
    """

    ticker: str
    revenue: float
    target_ev_sales: float
    net_debt: float
    shares_outstanding: float


@dataclass(frozen=True)
class EVSalesOutputs:
    """Computed EV/Sales multiple valuation breakdown.

    Attributes:
        implied_enterprise_value: ``revenue * target_ev_sales``.
        implied_equity_value: ``implied_enterprise_value - net_debt``. May
            be negative for heavily levered firms with thin revenue.
        fair_value_per_share: ``implied_equity_value / shares_outstanding``.
        current_multiple: Diagnostic — the firm's current trading EV/Sales,
            computed as ``(market_cap + net_debt) / revenue``. Filled in by
            the view since the engine has no access to ``market_cap``.
    """

    implied_enterprise_value: float
    implied_equity_value: float
    fair_value_per_share: float
    current_multiple: float | None = None
