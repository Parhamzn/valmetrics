"""Default-assumption derivation for the Peter Lynch fair-value model.

Mirrors the style of :mod:`apps.valuation.defaults` (DCF defaults). Pulls
EPS, an empirical growth-rate CAGR, and a trailing dividend yield, falling
back to sensible constants whenever a field is missing.

Source: Lynch, *One Up on Wall Street* (1989); Investopedia PEG explainer
(https://www.investopedia.com/terms/p/pegratio.asp).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_peter_lynch import PeterLynchInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

FALLBACK_EPS = 0.0
FALLBACK_GROWTH = 0.10
FALLBACK_DIVIDEND_YIELD = 0.0

# Lynch's heuristic is calibrated to "growth at a reasonable price" names;
# clamp the empirical CAGR to a similar window so we don't render an
# obviously-broken default for hyper-growth or sharply declining companies.
GROWTH_CLAMP = (-0.20, 0.30)


# ---------------------------------------------------------------------------
# Helpers (private)
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


def _collect_eps(statement) -> list[float]:
    """Collect per-period diluted EPS values in chronological (oldest-first) order.

    Tries the direct ``diluted_eps`` field first, then falls back to deriving
    EPS from net_income / diluted_average_shares per line.
    """
    if statement is None:
        return []
    lines = getattr(statement, "lines", None) or []
    out: list[float] = []
    for line in lines:
        items = line.items or {}
        eps = _safe_float(items.get("diluted_eps"))
        if eps is None:
            ni = _safe_float(items.get("net_income"))
            sh = _safe_float(items.get("diluted_average_shares"))
            if ni is not None and sh is not None and sh > 0:
                eps = ni / sh
        if eps is not None:
            out.append(eps)
    out.reverse()  # provider returns most-recent first
    return out


def _collect_net_income(statement) -> list[float]:
    """Collect non-None net income values in chronological order."""
    if statement is None:
        return []
    lines = getattr(statement, "lines", None) or []
    out: list[float] = []
    for line in lines:
        ni = _safe_float((line.items or {}).get("net_income"))
        if ni is not None:
            out.append(ni)
    out.reverse()
    return out


def _cagr(series: list[float]) -> float | None:
    """CAGR over the available history. Requires endpoints both positive.

    Returns None on insufficient/invalid data so the caller can fall back.
    """
    if len(series) < 2:
        return None
    first, last = series[0], series[-1]
    if first <= 0 or last <= 0:
        return None
    n = len(series) - 1
    if n <= 0:
        return None
    try:
        return (last / first) ** (1.0 / n) - 1.0
    except (ValueError, ZeroDivisionError):
        return None


def _fetch_dividends(provider, ticker) -> list:
    try:
        divs = provider.get_dividends(ticker) or []
    except DataProviderError:
        return []
    return [
        d for d in divs
        if getattr(d, "date", None) is not None
        and _safe_float(getattr(d, "amount", None)) is not None
    ]


def _ttm_dividend(dividends, today: date | None = None) -> float:
    """Sum of dividends paid in the trailing 365 days."""
    if not dividends:
        return 0.0
    today = today or date.today()
    cutoff = today - timedelta(days=365)
    total = 0.0
    for d in dividends:
        if d.date >= cutoff:
            amt = _safe_float(d.amount) or 0.0
            total += amt
    return total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_peter_lynch_defaults(provider, ticker, profile, quote) -> PeterLynchInputs:
    """Pull statements via ``provider`` and synthesize default Lynch inputs.

    Robust to missing fields — every numeric is wrapped in try/except or a
    fallback so this never raises on incomplete upstream data.

    Source: Lynch, *One Up on Wall Street* (1989); Investopedia PEG explainer.
    """
    # --- Statements (swallow provider errors) -------------------------------
    income = None
    try:
        income = provider.get_income_statement(ticker, period="annual")
    except DataProviderError:
        income = None

    latest_income = _latest_items(income)

    # --- EPS: prefer reported diluted EPS, else net_income / diluted shares -
    eps = _safe_float(latest_income.get("diluted_eps"))
    if eps is None:
        ni = _safe_float(latest_income.get("net_income"))
        sh = _safe_float(latest_income.get("diluted_average_shares"))
        if ni is not None and sh is not None and sh > 0:
            eps = ni / sh
    if eps is None:
        eps = FALLBACK_EPS

    # --- Growth rate: EPS CAGR over available history, else NI CAGR ---------
    growth: float | None = None
    eps_series = _collect_eps(income)
    if len(eps_series) >= 2:
        growth = _cagr(eps_series)
    if growth is None:
        ni_series = _collect_net_income(income)
        if len(ni_series) >= 2:
            growth = _cagr(ni_series)
    if growth is None:
        growth = FALLBACK_GROWTH
    growth = _clamp(growth, GROWTH_CLAMP[0], GROWTH_CLAMP[1])

    # --- Trailing dividend yield (sum of last 365 days / current price) -----
    dividend_yield = FALLBACK_DIVIDEND_YIELD
    price = _safe_float(getattr(quote, "price", None)) if quote else None
    if price is not None and price > 0:
        ttm = _ttm_dividend(_fetch_dividends(provider, ticker))
        if ttm > 0:
            dividend_yield = ttm / price

    return PeterLynchInputs(
        ticker=ticker,
        eps=eps,
        growth_rate=growth,
        dividend_yield=dividend_yield,
    )


# Fields the user is allowed to override via the request querydict.
_FLOAT_OVERRIDES = ("eps", "growth_rate", "dividend_yield")


def apply_peter_lynch_overrides(inputs: PeterLynchInputs, query) -> PeterLynchInputs:
    """Replace user-overridable fields on ``inputs`` using values from ``query``.

    Silently skips any field whose value is missing, empty, or unparseable.
    ``query`` may be a QueryDict or a plain dict.
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
    if not overrides:
        return inputs
    return replace(inputs, **overrides)
