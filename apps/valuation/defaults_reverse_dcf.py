"""Default-assumption derivation for the Reverse DCF model.

We reuse the DCF defaults (:func:`apps.valuation.defaults.derive_dcf_defaults`)
to populate every fundamentals-driven field, then bolt on ``current_price``
from the live quote plus default search bounds.

Source: Damodaran, "Implied Growth" / "Price-Implied Valuation" notes;
Corporate Finance Institute, *Reverse DCF*
(https://corporatefinanceinstitute.com/resources/valuation/reverse-dcf-model/).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.valuation.defaults import derive_dcf_defaults
from apps.valuation.engine.types_reverse_dcf import ReverseDCFInputs


# Default bisection bounds.
FALLBACK_SEARCH_LOWER = -0.10
FALLBACK_SEARCH_UPPER = 0.50


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def derive_reverse_dcf_defaults(provider, ticker, profile, quote) -> ReverseDCFInputs | None:
    """Build a :class:`ReverseDCFInputs` by reusing the DCF defaults.

    Returns ``None`` if no usable current price is available — the view
    surfaces a friendly error in that case (we can't invert against an
    unknown price).
    """
    price = _safe_float(getattr(quote, "price", None)) if quote else None
    if price is None or price <= 0:
        return None

    dcf_in = derive_dcf_defaults(provider, ticker, profile, quote)

    return ReverseDCFInputs(
        ticker=ticker,
        current_price=price,
        base_revenue=dcf_in.base_revenue,
        base_fcff=dcf_in.base_fcff,
        projection_years=dcf_in.projection_years,
        ebit_margin=dcf_in.ebit_margin,
        tax_rate=dcf_in.tax_rate,
        reinvestment_rate=dcf_in.reinvestment_rate,
        terminal_growth=dcf_in.terminal_growth,
        wacc=dcf_in.wacc,
        net_debt=dcf_in.net_debt,
        shares_outstanding=dcf_in.shares_outstanding,
        search_lower=FALLBACK_SEARCH_LOWER,
        search_upper=FALLBACK_SEARCH_UPPER,
    )


# Fields the user is allowed to override via the request querydict.
_FLOAT_OVERRIDES = (
    "ebit_margin",
    "tax_rate",
    "reinvestment_rate",
    "terminal_growth",
    "wacc",
    "search_lower",
    "search_upper",
)


def apply_reverse_dcf_overrides(inputs: ReverseDCFInputs, query) -> ReverseDCFInputs:
    """Replace user-overridable fields on ``inputs`` using values from ``query``.

    Silently skips any field whose value is missing, empty, or unparseable.
    """
    overrides: dict[str, Any] = {}
    for field_name in _FLOAT_OVERRIDES:
        raw = query.get(field_name)
        if raw is None or raw == "":
            continue
        parsed = _safe_float(raw)
        if parsed is None:
            continue
        overrides[field_name] = parsed

    raw_years = query.get("projection_years")
    if raw_years not in (None, ""):
        parsed_years = _safe_int(raw_years)
        if parsed_years is not None:
            overrides["projection_years"] = max(1, min(20, parsed_years))

    if not overrides:
        return inputs
    return replace(inputs, **overrides)
