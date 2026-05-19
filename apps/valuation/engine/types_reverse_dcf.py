"""Input/output dataclasses for the Reverse DCF model.

Reverse DCF inverts the canonical DCF question. Instead of "what's the right
price given an assumed growth rate?", it asks: "what revenue growth rate
makes the DCF fair value equal the current market price?". The answer tells
you what the market is implicitly pricing in.

Source: Damodaran, "Implied Growth" / "Price-Implied Valuation" notes
(https://pages.stern.nyu.edu/~adamodar/); Corporate Finance Institute,
*Reverse DCF* (https://corporatefinanceinstitute.com/resources/valuation/
reverse-dcf-model/).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReverseDCFInputs:
    """Inputs for a reverse-DCF run.

    Everything except ``search_lower`` / ``search_upper`` is the standard
    DCF assumption bundle; the algorithm holds them all fixed and solves
    only for ``revenue_growth_rate``. The user can adjust the search bounds
    if they want to interrogate extreme regimes.

    Attributes:
        ticker: Display identifier.
        current_price: Live market price per share — the value we are
            inverting against.
        base_revenue: Trailing-year revenue (year 0).
        base_fcff: Trailing-year FCFF (year 0). Carried for context; forward
            FCFF is rebuilt from revenue * margin * (1 - reinvest).
        projection_years: Number of explicit forecast years.
        ebit_margin: EBIT / revenue (held fixed across the projection).
        tax_rate: Effective tax rate.
        reinvestment_rate: Net reinvestment as a fraction of NOPAT.
        terminal_growth: Perpetual growth beyond the explicit period.
        wacc: Discount rate.
        net_debt: Total debt minus cash & equivalents.
        shares_outstanding: Diluted share count.
        search_lower: Lower bound for the bisection (default -0.10 = -10%).
        search_upper: Upper bound for the bisection (default 0.50 = +50%).
    """

    ticker: str
    current_price: float
    base_revenue: float
    base_fcff: float
    projection_years: int = 5
    ebit_margin: float = 0.0
    tax_rate: float = 0.0
    reinvestment_rate: float = 0.0
    terminal_growth: float = 0.0
    wacc: float = 0.0
    net_debt: float = 0.0
    shares_outstanding: float = 0.0
    search_lower: float = -0.10
    search_upper: float = 0.50


@dataclass(frozen=True)
class ReverseDCFOutputs:
    """Result of a reverse-DCF run.

    Attributes:
        implied_revenue_growth: The growth rate that makes the DCF value
            match ``current_price``. ``None`` only if the search couldn't
            return a usable answer (very rare; both bounds-clipped and
            failure modes still return a clamped bound here with a warning).
        converged: True if the bisection terminated on ``|diff| < $0.01``.
            False if the algorithm hit the iteration cap *or* the answer
            lay outside the search bounds.
        iterations: Number of bisection steps actually executed.
        final_fair_value: DCF fair value at ``implied_revenue_growth``.
            Should be ~= ``current_price`` when ``converged`` is True.
        warning: Human-readable caveat (extreme implied growth, search
            saturated, etc.); ``None`` when the result is unremarkable.
    """

    implied_revenue_growth: float | None
    converged: bool
    iterations: int
    final_fair_value: float
    warning: str | None
