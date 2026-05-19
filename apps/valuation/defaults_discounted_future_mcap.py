"""Default-assumption derivation for the Discounted Future Market Cap model.

Mirrors the structure of :mod:`apps.valuation.defaults` (perpetual-growth DCF):
pull whatever fundamentals the provider can give us and fall back to sensible
constants whenever a field is missing.

Loss-making companies (negative trailing net income) are a known weakness of
the P/E framework: the multiplied figure becomes meaningless. We still derive
a default (so the page renders) but the view template will surface a warning
when ``base_net_income <= 0``.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_discounted_future_mcap import DFMCInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

FALLBACK_NI_GROWTH = 0.08
FALLBACK_TERMINAL_PE = 18.0
FALLBACK_DISCOUNT_RATE = 0.08
FALLBACK_PROJECTION_YEARS = 5
FALLBACK_SHARES = 1.0e9


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


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _latest_items(statement) -> dict[str, float | None]:
    if statement is None:
        return {}
    lines = getattr(statement, "lines", None) or []
    if not lines:
        return {}
    return dict(lines[0].items or {})


def _historical_net_incomes(statement) -> list[float]:
    """Return non-None ``net_income`` values chronologically (oldest first)."""
    if statement is None:
        return []
    lines = getattr(statement, "lines", None) or []
    nis: list[float] = []
    for line in lines:
        v = _safe_float((line.items or {}).get("net_income"))
        if v is not None:
            nis.append(v)
    nis.reverse()
    return nis


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_dfmc_defaults(provider, ticker, profile, quote) -> DFMCInputs:
    """Pull statements via ``provider`` and synthesize default DFMC inputs.

    The CAGR helper requires both endpoints to be positive to be meaningful, so
    when trailing NI turns negative we fall back to the constant default and
    let the view warn the user.
    """

    # --- Fetch statements, swallowing provider errors -----------------------
    income = None
    ratios = None
    try:
        income = provider.get_income_statement(ticker, period="annual")
    except DataProviderError:
        income = None
    try:
        ratios = provider.get_ratios(ticker)
    except DataProviderError:
        ratios = None

    latest_income = _latest_items(income)

    # --- Base net income ----------------------------------------------------
    base_ni = _safe_float(latest_income.get("net_income")) or 0.0

    # --- NI growth (CAGR over available positive history) -------------------
    nis = _historical_net_incomes(income)
    growth = FALLBACK_NI_GROWTH
    # CAGR only defined when both endpoints are positive and same sign.
    if len(nis) >= 2 and nis[0] > 0 and nis[-1] > 0:
        n_periods = len(nis) - 1
        try:
            cagr = (nis[-1] / nis[0]) ** (1.0 / n_periods) - 1.0
            growth = _clamp(cagr, -0.20, 0.30)
        except (ValueError, ZeroDivisionError):
            growth = FALLBACK_NI_GROWTH

    # --- Terminal P/E -------------------------------------------------------
    terminal_pe = FALLBACK_TERMINAL_PE
    if ratios is not None:
        candidate = _safe_float(getattr(ratios, "pe", None))
        # Only use current P/E if it's positive (negative => loss-making, not
        # meaningful as a future multiple).
        if candidate is not None and candidate > 0:
            terminal_pe = _clamp(candidate, 8.0, 35.0)

    # --- Discount rate ------------------------------------------------------
    # MVP: a sensible constant. Future iteration could route through CAPM /
    # WACC; tracked in TODO below.
    # TODO: replace with CAPM cost-of-equity if a beta is available.
    discount_rate = FALLBACK_DISCOUNT_RATE

    # --- Shares outstanding -------------------------------------------------
    shares = _safe_float(latest_income.get("diluted_average_shares"))
    if shares is None or shares <= 0:
        mc = _safe_float(getattr(profile, "market_cap", None)) if profile else None
        px = _safe_float(getattr(quote, "price", None)) if quote else None
        if mc and px and px > 0:
            shares = mc / px
        else:
            shares = FALLBACK_SHARES

    return DFMCInputs(
        ticker=ticker,
        base_net_income=base_ni,
        projection_years=FALLBACK_PROJECTION_YEARS,
        net_income_growth_rate=growth,
        terminal_pe=terminal_pe,
        discount_rate=discount_rate,
        shares_outstanding=shares,
    )


# Fields the user may override via the request querydict.
_FLOAT_OVERRIDES = (
    "net_income_growth_rate",
    "terminal_pe",
    "discount_rate",
)


def apply_dfmc_overrides(inputs: DFMCInputs, query) -> DFMCInputs:
    """Replace user-overridable fields on ``inputs`` from ``query``.

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
