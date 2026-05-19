"""Input/output dataclasses for the Discounted Future Market Cap model.

A simple multiples-driven intrinsic-value approach:

    1. Project net income for N years at a fixed growth rate.
    2. Apply a terminal P/E to the year-N net income to estimate the future
       market cap.
    3. Discount that future market cap back to today and divide by current
       diluted shares.

Source: Corporate Finance Institute, "Terminal Value" (exit-multiple variant —
P/E applied to earnings is the equity-side analogue of EV/EBITDA applied to
EBITDA), and the standard treatment in any equity-research primer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class DFMCInputs:
    """Inputs for the Discounted Future Market Cap model.

    Attributes:
        ticker: Display identifier.
        base_net_income: Latest annual net income (can be negative — see notes
            in the engine for the loss-making case).
        projection_years: Number of explicit forecast years (default 5).
        net_income_growth_rate: Annual NI growth.
        terminal_pe: P/E multiple to apply to Year N net income. Must be > 0.
        discount_rate: Required return (WACC or cost of equity).
        shares_outstanding: Diluted share count for per-share fair value.
    """

    ticker: str
    base_net_income: float
    projection_years: int = 5
    net_income_growth_rate: float = 0.0
    terminal_pe: float = 0.0
    discount_rate: float = 0.0
    shares_outstanding: float = 0.0


@dataclass(frozen=True)
class DFMCOutputs:
    """Computed DFMC breakdown.

    Attributes:
        projected_net_incomes: List of (year, net_income) tuples for years 1..N.
        terminal_net_income: NI at year N (engine uses year N directly, not N+1
            — keeps the model simple and easy to reason about).
        future_market_cap: terminal_net_income * terminal_pe.
        pv_future_market_cap: future_market_cap discounted by discount_rate
            over N years.
        fair_value_per_share: pv_future_market_cap / shares_outstanding.
    """

    projected_net_incomes: List[Tuple[int, float]] = field(default_factory=list)
    terminal_net_income: float = 0.0
    future_market_cap: float = 0.0
    pv_future_market_cap: float = 0.0
    fair_value_per_share: float = 0.0
