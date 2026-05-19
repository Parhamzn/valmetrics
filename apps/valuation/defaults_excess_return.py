"""Default-assumption derivation for the Simple Excess Return model.

Mirrors :mod:`apps.valuation.defaults` (DCF) and
:mod:`apps.valuation.defaults_ddm` (DDM) in style. Each helper pulls whatever
balance-sheet / income-statement / ratios data the provider can produce and
distills it into a :class:`SimpleExcessReturnInputs` payload, falling back to
sensible constants whenever a particular field is missing or unparseable.

Reference: Damodaran, "Valuing Financial Service Firms" (NYU Stern),
https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/finfirm09.pdf

Key Damodaran notes that drive the defaults below:
    * For excess-return models on financial firms, the discount rate is the
      cost of equity (Ke), not WACC: a bank's debt is operational raw
      material, not financing, so it shouldn't enter the discount rate.
    * ROE should be a *sustainable* figure — we average across the available
      annual history rather than using one volatile year.
    * Stable-phase growth must stay strictly below Ke; we apply a small
      buffer so the very first render of the page doesn't blow up the
      Gordon denominator when the user pushes g toward Ke.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_excess_return import SimpleExcessReturnInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

# CAPM components (no beta surfaced on Ratios yet, so we assume beta = 1.0).
FALLBACK_RISK_FREE_RATE = 0.04
FALLBACK_EQUITY_RISK_PREMIUM = 0.05
FALLBACK_BETA = 1.0
FALLBACK_COST_OF_EQUITY = (
    FALLBACK_RISK_FREE_RATE + FALLBACK_BETA * FALLBACK_EQUITY_RISK_PREMIUM
)  # = 0.09

FALLBACK_ROE = 0.10
FALLBACK_GROWTH = 0.025               # long-run nominal GDP proxy
FALLBACK_BOOK_VALUE_PER_SHARE = 1.0   # sentinel so engine still runs
FALLBACK_SHARES = 1.0e9

# Constraints from theory.
GROWTH_BUFFER = 0.005  # require g <= Ke - GROWTH_BUFFER
ROE_CLAMP = (-0.5, 1.0)

# Max history length to average ROE over (years). Damodaran recommends a
# multi-year window to smooth noise; 5 years is the typical annual depth
# yfinance returns.
ROE_HISTORY_YEARS = 5


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


def _all_items(statement) -> list[dict[str, float | None]]:
    """Return all period item dicts, most-recent first (provider ordering)."""
    if statement is None:
        return []
    lines = getattr(statement, "lines", None) or []
    return [dict(line.items or {}) for line in lines]


def _historical_roe(income_lines, balance_lines, max_years: int) -> float | None:
    """Average ROE across up to ``max_years`` of annual data.

    ROE for each year = net_income_t / common_stock_equity_t. We pair
    income-statement and balance-sheet rows positionally (both are
    most-recent-first), which matches yfinance's annual cadence. Years
    with missing inputs, zero/negative equity, or NaN figures are skipped.
    """
    if not income_lines or not balance_lines:
        return None

    roes: list[float] = []
    # Damodaran's "sustainable" ROE: average over multiple years to smooth
    # one-off charges / windfalls. We pair the two statements positionally
    # because yfinance returns matching annual snapshots.
    for i in range(min(len(income_lines), len(balance_lines), max_years)):
        ni = _safe_float(income_lines[i].get("net_income"))
        equity = _safe_float(balance_lines[i].get("common_stock_equity"))
        if equity is None or equity == 0:
            equity = _safe_float(
                balance_lines[i].get("total_equity_gross_minority_interest")
            )
        if ni is None or equity is None or equity <= 0:
            continue
        roes.append(ni / equity)

    if not roes:
        return None
    return sum(roes) / len(roes)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_simple_excess_return_defaults(
    provider, ticker, profile, quote
) -> SimpleExcessReturnInputs:
    """Pull balance sheet + income statement + ratios; build default inputs.

    Damodaran, "Valuing Financial Service Firms": for excess-return models on
    financial firms, use Ke (CAPM) — not WACC — and prefer a multi-year
    average ROE so the assumption represents the firm's sustainable return.
    """
    # --- Fetch statements / ratios, swallowing provider errors --------------
    income = None
    balance = None
    ratios = None
    try:
        income = provider.get_income_statement(ticker, period="annual")
    except DataProviderError:
        income = None
    try:
        balance = provider.get_balance_sheet(ticker, period="annual")
    except DataProviderError:
        balance = None
    try:
        ratios = provider.get_ratios(ticker)
    except DataProviderError:
        ratios = None

    latest_income = _latest_items(income)
    latest_balance = _latest_items(balance)
    income_lines = _all_items(income)
    balance_lines = _all_items(balance)

    # --- Book value (total common equity) -----------------------------------
    book_value = _safe_float(latest_balance.get("common_stock_equity"))
    if book_value is None:
        book_value = _safe_float(
            latest_balance.get("total_equity_gross_minority_interest")
        )
    if book_value is None:
        book_value = 0.0

    # --- Shares outstanding -------------------------------------------------
    shares = _safe_float(latest_income.get("diluted_average_shares"))
    if shares is None or shares <= 0:
        mc = _safe_float(getattr(profile, "market_cap", None)) if profile else None
        px = _safe_float(getattr(quote, "price", None)) if quote else None
        if mc and px and px > 0:
            shares = mc / px
        else:
            shares = FALLBACK_SHARES

    # --- Book value per share ----------------------------------------------
    if shares > 0 and book_value > 0:
        book_value_per_share = book_value / shares
    else:
        # Engine will raise on this, but we still return a usable inputs
        # object so the view can surface the error cleanly.
        book_value_per_share = FALLBACK_BOOK_VALUE_PER_SHARE

    # --- ROE: multi-year average preferred, ratios as fallback --------------
    roe = _historical_roe(income_lines, balance_lines, ROE_HISTORY_YEARS)
    if roe is None and ratios is not None:
        roe = _safe_float(getattr(ratios, "return_on_equity", None))
    if roe is None:
        roe = FALLBACK_ROE
    roe = _clamp(roe, ROE_CLAMP[0], ROE_CLAMP[1])

    # --- Cost of equity: CAPM (no beta exposed; assume 1.0) -----------------
    # TODO: surface beta on Ratios and read it here.
    cost_of_equity = FALLBACK_COST_OF_EQUITY

    # --- Growth: long-run nominal GDP, capped strictly below Ke -------------
    growth_rate = FALLBACK_GROWTH
    max_growth = cost_of_equity - GROWTH_BUFFER
    if growth_rate > max_growth:
        growth_rate = max_growth

    return SimpleExcessReturnInputs(
        ticker=ticker,
        book_value_per_share=book_value_per_share,
        return_on_equity=roe,
        cost_of_equity=cost_of_equity,
        growth_rate=growth_rate,
    )


# Fields the user is allowed to override via the request querydict.
_FLOAT_OVERRIDES = (
    "book_value_per_share",
    "return_on_equity",
    "cost_of_equity",
    "growth_rate",
)


def apply_simple_excess_return_overrides(
    inputs: SimpleExcessReturnInputs, query
) -> SimpleExcessReturnInputs:
    """Replace user-overridable fields on ``inputs`` using values from ``query``.

    Silently skips any field whose value is missing, empty, or unparseable.
    ``query`` may be a Django QueryDict or a plain dict.
    """
    overrides: dict[str, Any] = {}
    for field in _FLOAT_OVERRIDES:
        raw = query.get(field)
        if raw is None or raw == "":
            continue
        parsed = _safe_float(raw)
        if parsed is None:
            continue
        overrides[field] = parsed

    if not overrides:
        return inputs
    return replace(inputs, **overrides)
