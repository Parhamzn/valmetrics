"""Default-assumption derivation for valuation models.

These helpers pull whatever fundamentals the data provider can give us and
distill them into a :class:`DCFInputs` payload, falling back to sensible
constants whenever a particular field is missing or unparseable. The goal is
that ``derive_dcf_defaults`` *always* returns a usable input object, even for
tickers with patchy upstream data.

``apply_query_overrides`` then layers any user-supplied numbers (typically from
the request's GET querydict) on top of those defaults so the same view can
serve both the initial render and form-driven re-renders.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types import DCFInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

FALLBACK_REVENUE_GROWTH = 0.05
FALLBACK_EBIT_MARGIN = 0.15
FALLBACK_TAX_RATE = 0.21
FALLBACK_REINVESTMENT = 0.30
FALLBACK_TERMINAL_GROWTH = 0.025
FALLBACK_WACC = 0.08
FALLBACK_PROJECTION_YEARS = 5
FALLBACK_SHARES = 1.0e9


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` into the inclusive range ``[lo, hi]``."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _safe_float(value: Any) -> float | None:
    """Best-effort float coercion. Returns None on failure or non-finite."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # Reject NaN / inf so downstream math stays well-defined.
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _latest_items(statement) -> dict[str, float | None]:
    """Pull the most-recent ``items`` dict from a statement, or {} on miss."""
    if statement is None:
        return {}
    lines = getattr(statement, "lines", None) or []
    if not lines:
        return {}
    return dict(lines[0].items or {})


def _historical_revenues(statement) -> list[float]:
    """Return non-None ``total_revenue`` values in chronological order.

    The provider's ``lines`` are most-recent-first, so we reverse them so the
    oldest year is first — convenient for CAGR math.
    """
    if statement is None:
        return []
    lines = getattr(statement, "lines", None) or []
    revs: list[float] = []
    for line in lines:
        v = _safe_float((line.items or {}).get("total_revenue"))
        if v is not None:
            revs.append(v)
    revs.reverse()
    return revs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_dcf_defaults(provider, ticker, profile, quote) -> DCFInputs:
    """Pull statements via ``provider`` and synthesize a default DCFInputs.

    Robust to missing fields — every numeric is wrapped in a try/except or a
    fallback so this never raises on incomplete upstream data.
    """

    # --- Fetch statements, swallowing provider errors -----------------------
    income = None
    cashflow = None
    balance = None
    try:
        income = provider.get_income_statement(ticker, period="annual")
    except DataProviderError:
        income = None
    try:
        cashflow = provider.get_cash_flow(ticker, period="annual")
    except DataProviderError:
        cashflow = None
    try:
        balance = provider.get_balance_sheet(ticker, period="annual")
    except DataProviderError:
        balance = None

    latest_income = _latest_items(income)
    latest_cf = _latest_items(cashflow)
    latest_bs = _latest_items(balance)

    # --- Base revenue -------------------------------------------------------
    base_revenue = _safe_float(latest_income.get("total_revenue")) or 0.0

    # --- Base FCFF ----------------------------------------------------------
    fcff_direct = _safe_float(latest_cf.get("free_cash_flow"))
    if fcff_direct is not None:
        base_fcff = fcff_direct
    else:
        ocf = _safe_float(latest_cf.get("operating_cash_flow")) or 0.0
        # yfinance reports capex as a negative number, so addition gives FCFF.
        capex_cf = _safe_float(latest_cf.get("capital_expenditure")) or 0.0
        base_fcff = ocf + capex_cf

    # --- Shares outstanding -------------------------------------------------
    shares = _safe_float(latest_income.get("diluted_average_shares"))
    if shares is None or shares <= 0:
        mc = _safe_float(getattr(profile, "market_cap", None)) if profile else None
        px = _safe_float(getattr(quote, "price", None)) if quote else None
        if mc and px and px > 0:
            shares = mc / px
        else:
            shares = FALLBACK_SHARES

    # --- Revenue growth (CAGR over available history) -----------------------
    revs = _historical_revenues(income)
    growth = FALLBACK_REVENUE_GROWTH
    if len(revs) >= 2 and revs[0] > 0 and revs[-1] > 0:
        n_periods = len(revs) - 1
        try:
            cagr = (revs[-1] / revs[0]) ** (1.0 / n_periods) - 1.0
            growth = _clamp(cagr, -0.2, 0.3)
        except (ValueError, ZeroDivisionError):
            growth = FALLBACK_REVENUE_GROWTH

    # --- EBIT margin --------------------------------------------------------
    ebit_val = _safe_float(latest_income.get("ebit"))
    if ebit_val is None:
        ebit_val = _safe_float(latest_income.get("operating_income"))
    if ebit_val is not None and base_revenue > 0:
        ebit_margin = _clamp(ebit_val / base_revenue, 0.0, 0.6)
    else:
        ebit_margin = FALLBACK_EBIT_MARGIN

    # --- Tax rate -----------------------------------------------------------
    tax_rate = FALLBACK_TAX_RATE
    direct_tax = _safe_float(latest_income.get("tax_rate_for_calcs"))
    if direct_tax is not None:
        tax_rate = _clamp(direct_tax, 0.0, 0.5)
    else:
        tp = _safe_float(latest_income.get("tax_provision"))
        pi = _safe_float(latest_income.get("pretax_income"))
        if tp is not None and pi is not None and pi != 0:
            tax_rate = _clamp(tp / pi, 0.0, 0.5)

    # --- Reinvestment rate --------------------------------------------------
    reinvest_rate = FALLBACK_REINVESTMENT
    capex = _safe_float(latest_cf.get("capital_expenditure"))
    if capex is not None and ebit_val is not None:
        nopat = ebit_val * (1.0 - tax_rate)
        if nopat > 0:
            reinvest_rate = _clamp(abs(capex) / nopat, 0.0, 0.8)

    # --- Net debt -----------------------------------------------------------
    ltd = _safe_float(latest_bs.get("long_term_debt")) or 0.0
    cd = _safe_float(latest_bs.get("current_debt")) or 0.0
    cash = _safe_float(latest_bs.get("cash_and_cash_equivalents")) or 0.0
    net_debt = ltd + cd - cash

    return DCFInputs(
        ticker=ticker,
        base_revenue=base_revenue,
        base_fcff=base_fcff,
        projection_years=FALLBACK_PROJECTION_YEARS,
        revenue_growth_rate=growth,
        ebit_margin=ebit_margin,
        tax_rate=tax_rate,
        reinvestment_rate=reinvest_rate,
        terminal_growth=FALLBACK_TERMINAL_GROWTH,
        wacc=FALLBACK_WACC,
        net_debt=net_debt,
        shares_outstanding=shares,
    )


# Fields the user is allowed to override via the request querydict.
_FLOAT_OVERRIDES = (
    "revenue_growth_rate",
    "ebit_margin",
    "tax_rate",
    "reinvestment_rate",
    "terminal_growth",
    "wacc",
)


def apply_query_overrides(inputs: DCFInputs, query) -> DCFInputs:
    """Replace user-overridable fields on ``inputs`` using values from ``query``.

    Silently skips any field whose value is missing, empty, or unparseable.
    ``query`` may be a QueryDict or a plain dict.
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

    raw_years = query.get("projection_years")
    if raw_years not in (None, ""):
        parsed_years = _safe_int(raw_years)
        if parsed_years is not None:
            overrides["projection_years"] = max(1, min(20, parsed_years))

    if not overrides:
        return inputs
    return replace(inputs, **overrides)
