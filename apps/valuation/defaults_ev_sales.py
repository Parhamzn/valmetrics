"""Default-assumption derivation for the EV/Sales Multiple valuation model.

Mirrors :mod:`apps.valuation.defaults_ev_ebitda`: pull fundamentals from the
provider, normalize into an :class:`EVSalesInputs` payload, fall back to
constants on missing fields.

The default ``target_ev_sales`` is the company's *current* trading multiple,
computed from ``(market_cap + net_debt) / revenue`` — anchoring on status quo
lets the user flex up/down to model multiple expansion or compression.

Source: Damodaran ch. 20 (Revenue Multiples).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_ev_sales import EVSalesInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

# 3x is a rough mature-firm centroid. SaaS / high-growth tech routinely
# trades at 8x-15x; mature retail or utility names sit at <2x.
FALLBACK_TARGET_EV_SALES = 3.0
FALLBACK_SHARES = 1.0e9

# Clamp range for target_ev_sales. Below 0.5x is essentially distressed;
# above 20x is exotic hyper-growth / pre-revenue territory.
TARGET_MULTIPLE_MIN = 0.5
TARGET_MULTIPLE_MAX = 20.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


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


def _latest_items(statement) -> dict[str, float | None]:
    if statement is None:
        return {}
    lines = getattr(statement, "lines", None) or []
    if not lines:
        return {}
    return dict(lines[0].items or {})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_ev_sales_defaults(provider, ticker, profile, quote) -> EVSalesInputs:
    """Pull statements via ``provider`` and synthesize default EV/Sales inputs.

    ``target_ev_sales`` is anchored on the firm's current trading EV/Sales —
    derived from market cap + net debt / revenue. ``ratios.price_to_sales`` is
    not used for the *target* because P/S is equity-side (market cap / revenue)
    rather than EV-side; we surface P/S separately in the view as a diagnostic.

    Source: Damodaran ch. 20 (Revenue Multiples).
    """
    income = None
    balance = None
    try:
        income = provider.get_income_statement(ticker, period="annual")
    except DataProviderError:
        income = None
    try:
        balance = provider.get_balance_sheet(ticker, period="annual")
    except DataProviderError:
        balance = None

    latest_income = _latest_items(income)
    latest_bs = _latest_items(balance)

    # --- Revenue -----------------------------------------------------------
    revenue = _safe_float(latest_income.get("total_revenue")) or 0.0

    # --- Net debt ----------------------------------------------------------
    ltd = _safe_float(latest_bs.get("long_term_debt")) or 0.0
    cd = _safe_float(latest_bs.get("current_debt")) or 0.0
    cash = _safe_float(latest_bs.get("cash_and_cash_equivalents")) or 0.0
    net_debt = ltd + cd - cash

    # --- Target multiple --------------------------------------------------
    # Use the current trading EV/Sales as the default starting point so the
    # user begins at status quo.
    target_ev_sales = FALLBACK_TARGET_EV_SALES
    market_cap = _safe_float(getattr(profile, "market_cap", None)) if profile else None
    if market_cap is not None and revenue > 0:
        current_ev_sales = (market_cap + net_debt) / revenue
        if current_ev_sales > 0:
            target_ev_sales = _clamp(current_ev_sales, TARGET_MULTIPLE_MIN, TARGET_MULTIPLE_MAX)

    # --- Shares outstanding ------------------------------------------------
    shares = _safe_float(latest_income.get("diluted_average_shares"))
    if shares is None or shares <= 0:
        px = _safe_float(getattr(quote, "price", None)) if quote else None
        if market_cap and px and px > 0:
            shares = market_cap / px
        else:
            shares = FALLBACK_SHARES

    return EVSalesInputs(
        ticker=ticker,
        revenue=revenue,
        target_ev_sales=target_ev_sales,
        net_debt=net_debt,
        shares_outstanding=shares,
    )


# Fields the user may override via the request querydict.
_FLOAT_OVERRIDES = (
    "target_ev_sales",
    "revenue",
    "net_debt",
)


def apply_ev_sales_overrides(inputs: EVSalesInputs, query) -> EVSalesInputs:
    """Replace user-overridable fields on ``inputs`` using values from ``query``."""
    overrides: dict[str, Any] = {}
    for field_name in _FLOAT_OVERRIDES:
        raw = query.get(field_name)
        if raw is None or raw == "":
            continue
        parsed = _safe_float(raw)
        if parsed is None:
            continue
        overrides[field_name] = parsed

    if not overrides:
        return inputs
    return replace(inputs, **overrides)
