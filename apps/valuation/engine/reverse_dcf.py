"""Reverse-DCF: solve for the revenue growth rate implied by the market price.

Standard DCF asks "what's the right price given an assumed growth rate?".
Reverse DCF inverts the question: given today's market price, what growth
rate must the model assume to produce that price as its fair value? The
answer is the *implied* growth — i.e. what the market is currently pricing
in. If the implied growth is wildly above what's plausible for the
business, the stock may be priced for perfection.

We do the inversion with bisection. The DCF fair value is monotonically
increasing in ``revenue_growth_rate`` for fixed margins / WACC / terminal,
so bisection is well-behaved within any [lo, hi] where the function is
defined.

Source: Damodaran, "Implied Growth" / "Price-Implied Valuation" notes
(https://pages.stern.nyu.edu/~adamodar/); Corporate Finance Institute,
*Reverse DCF* (https://corporatefinanceinstitute.com/resources/valuation/
reverse-dcf-model/).
"""

from __future__ import annotations

from dataclasses import replace

from apps.valuation.engine.dcf import dcf_perpetual_growth as dcf_engine
from apps.valuation.engine.types import DCFInputs
from apps.valuation.engine.types_reverse_dcf import (
    ReverseDCFInputs,
    ReverseDCFOutputs,
)


_MAX_ITERATIONS = 50
_PRICE_TOLERANCE = 0.01  # currency units (e.g. dollars per share)

# Implied-growth zones outside which we surface a warning to the user.
_EXTREME_HIGH = 0.30
_EXTREME_LOW = -0.05


def _build_dcf_inputs(rev_in: ReverseDCFInputs, growth: float) -> DCFInputs:
    """Project a ReverseDCFInputs onto a DCFInputs with ``growth`` plugged in."""
    return DCFInputs(
        ticker=rev_in.ticker,
        base_revenue=rev_in.base_revenue,
        base_fcff=rev_in.base_fcff,
        projection_years=rev_in.projection_years,
        revenue_growth_rate=growth,
        ebit_margin=rev_in.ebit_margin,
        tax_rate=rev_in.tax_rate,
        reinvestment_rate=rev_in.reinvestment_rate,
        terminal_growth=rev_in.terminal_growth,
        wacc=rev_in.wacc,
        net_debt=rev_in.net_debt,
        shares_outstanding=rev_in.shares_outstanding,
    )


def _evaluate(rev_in: ReverseDCFInputs, growth: float) -> float | None:
    """Return the DCF fair value per share at ``growth``, or None if the
    engine couldn't compute (e.g. wacc <= terminal_growth, bad shares)."""
    try:
        out = dcf_engine(_build_dcf_inputs(rev_in, growth))
    except (ValueError, ZeroDivisionError):
        return None
    return out.fair_value_per_share


# Source: Damodaran "Implied Growth"; CFI Reverse DCF explainer.
def reverse_dcf(inputs: ReverseDCFInputs) -> ReverseDCFOutputs:
    """Bisect over ``revenue_growth_rate`` to match ``current_price``.

    Algorithm:
        1. Probe the two search bounds. The DCF value is (in practice)
           monotone-increasing in growth.
        2. If the price is below the value at the lower bound, the market is
           pricing in contraction beyond our search range — clip and warn.
        3. If the price is above the value at the upper bound, the market is
           pricing in growth above our search range — clip and warn.
        4. Otherwise bisect; stop when ``|fair_value - current_price| < $0.01``
           or after ``_MAX_ITERATIONS``.

    Edge case — non-defined DCF at a candidate growth: we treat that as if
    the candidate were "too high" (most often the engine fails because
    ``wacc <= terminal_growth``, which is unrelated to growth and won't be
    fixed by varying it — but if a future enhancement makes the engine raise
    on growth specifically, narrowing the upper bound is the safe move).

    Edge case — negative base FCFF: bisection still works because the engine
    rebuilds forward FCFF from ``revenue * margin * (1 - reinvest)``. The
    terminal value uses the *projected* last-period FCFF, not the base.
    """
    lo = inputs.search_lower
    hi = inputs.search_upper
    price = inputs.current_price

    lo_value = _evaluate(inputs, lo)
    hi_value = _evaluate(inputs, hi)

    # If we can't compute the DCF at either endpoint, narrow the offending
    # bound until we can. This guards against a misconfigured wacc/terminal
    # combo silently breaking the algorithm.
    safety = 0
    while hi_value is None and hi > lo and safety < 20:
        hi = (lo + hi) / 2.0
        hi_value = _evaluate(inputs, hi)
        safety += 1
    safety = 0
    while lo_value is None and hi > lo and safety < 20:
        lo = (lo + hi) / 2.0
        lo_value = _evaluate(inputs, lo)
        safety += 1

    if lo_value is None or hi_value is None:
        return ReverseDCFOutputs(
            implied_revenue_growth=None,
            converged=False,
            iterations=0,
            final_fair_value=0.0,
            warning=(
                "DCF engine could not evaluate within the search bounds; "
                "check wacc / terminal_growth / shares inputs."
            ),
        )

    # If the function is monotone-increasing (the usual case) we can check
    # whether the target falls outside [lo_value, hi_value]. Pin to whichever
    # endpoint is "closer" and warn the caller that the market is outside
    # what our search range can model.
    if price <= lo_value:
        # Market price is at or below the DCF value at the lowest growth we
        # were willing to try — i.e. the market implies even sharper
        # contraction than our lower bound.
        return ReverseDCFOutputs(
            implied_revenue_growth=lo,
            converged=False,
            iterations=0,
            final_fair_value=lo_value,
            warning=(
                "Market price implies revenue contraction beyond search "
                f"bounds (<= {lo:.0%})."
            ),
        )
    if price >= hi_value:
        return ReverseDCFOutputs(
            implied_revenue_growth=hi,
            converged=False,
            iterations=0,
            final_fair_value=hi_value,
            warning=(
                "Market price implies revenue growth above search bounds "
                f"(>= {hi:.0%}); priced for extreme growth."
            ),
        )

    # --- Standard bisection ----------------------------------------------
    iterations = 0
    mid = (lo + hi) / 2.0
    mid_value = _evaluate(inputs, mid)
    converged = False

    while iterations < _MAX_ITERATIONS:
        iterations += 1

        if mid_value is None:
            # Treat undefined DCF at the midpoint as "candidate too high"
            # and shrink the upper bound. This won't normally fire because
            # the only ValueError paths in the engine are independent of
            # revenue growth, but it keeps the algorithm robust.
            hi = mid
            mid = (lo + hi) / 2.0
            mid_value = _evaluate(inputs, mid)
            continue

        diff = mid_value - price
        if abs(diff) < _PRICE_TOLERANCE:
            converged = True
            break

        # Monotone-increasing in growth: if fair value > price, growth too
        # high; if fair value < price, growth too low.
        if diff > 0:
            hi = mid
        else:
            lo = mid

        mid = (lo + hi) / 2.0
        mid_value = _evaluate(inputs, mid)

    # If mid_value somehow ended up None after the cap (unlikely), backfill
    # with the latest known value so the dataclass field stays a real float.
    final_value = mid_value if mid_value is not None else 0.0

    # Surface a warning for "extreme" implied growth, even when converged.
    warning: str | None = None
    if mid > _EXTREME_HIGH:
        warning = (
            f"Implied growth ~{mid:.1%} exceeds 30% — market is pricing in "
            "extreme growth; check business plausibility."
        )
    elif mid < _EXTREME_LOW:
        warning = (
            f"Implied growth ~{mid:.1%} implies meaningful contraction; "
            "market expects shrinking revenue."
        )

    return ReverseDCFOutputs(
        implied_revenue_growth=mid,
        converged=converged,
        iterations=iterations,
        final_fair_value=final_value,
        warning=warning,
    )
