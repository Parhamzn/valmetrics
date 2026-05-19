"""Default-assumption derivation for Dividend Discount Models.

Mirrors the style of :mod:`apps.valuation.defaults` for the DCF model.
Each ``derive_*`` helper pulls whatever dividend / fundamentals data the
provider can give us and distills it into the relevant Inputs dataclass,
falling back to sensible constants when individual fields are missing.
The companion ``apply_*_overrides`` helpers layer user-supplied query
values on top so the same view can serve both initial render and
form-driven re-renders.

Canonical guidance (Damodaran, "DCF Valuation"
https://pages.stern.nyu.edu/~adamodar/pdfiles/eqnotes/dcfallOld.pdf):
    * DDM is appropriate for stable, mature firms whose dividends
      approximate FCFE.
    * In a stable / terminal phase, growth must not exceed the
      risk-free rate or long-run nominal GDP.
    * Required return is the cost of equity, usually computed via CAPM
      (rf + beta * ERP).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types import SimpleDDMInputs, TwoStageDDMInputs


# ---------------------------------------------------------------------------
# Fallback constants (Damodaran-style: rf ~ 10y UST, ERP ~ 5%)
# ---------------------------------------------------------------------------

FALLBACK_RISK_FREE_RATE = 0.04
FALLBACK_EQUITY_RISK_PREMIUM = 0.05
FALLBACK_BETA = 1.0  # Beta isn't currently exposed on the Ratios dataclass;
# revisit once provider surfaces a `beta` field (see TODO below).

FALLBACK_CURRENT_DIVIDEND = 1.0  # Sentinel so DDM is still computable; the
# view should show a "no dividend" warning to the user.
FALLBACK_DIVIDEND_GROWTH = 0.04
FALLBACK_REQUIRED_RETURN = 0.09
FALLBACK_TERMINAL_GROWTH = 0.025  # Long-run nominal GDP / inflation proxy.
FALLBACK_HIGH_GROWTH_YEARS = 5
FALLBACK_HIGH_GROWTH_RATE = 0.08

# Clamp bands
GROWTH_CLAMP = (-0.10, 0.20)
REQUIRED_RETURN_CLAMP = (0.05, 0.20)


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


def _fetch_dividends(provider, ticker) -> list:
    """Best-effort dividend fetch; swallow provider failures."""
    try:
        divs = provider.get_dividends(ticker) or []
    except DataProviderError:
        return []
    # Defensive: drop any entries without a usable amount/date.
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


def _annual_dividend_totals(dividends) -> list[tuple[int, float]]:
    """Bucket dividends by calendar year, return ``[(year, total), ...]``
    sorted oldest-first.

    Years with no payment are *not* synthesized — gaps in the underlying
    history simply collapse, since the CAGR computation only uses the
    first and last years of the available series.
    """
    if not dividends:
        return []
    by_year: dict[int, float] = {}
    for d in dividends:
        amt = _safe_float(d.amount)
        if amt is None:
            continue
        try:
            yr = d.date.year
        except AttributeError:
            continue
        by_year[yr] = by_year.get(yr, 0.0) + amt
    return sorted(by_year.items())


def _dividend_cagr(dividends, today: date | None = None) -> float | None:
    """CAGR of *full* calendar-year dividend totals over available history.

    Notes on the non-obvious handling:
      * We *exclude* the current (partial) calendar year so the endpoint
        is a complete annual figure rather than a year-to-date stub.
      * If we have fewer than two complete years, return None and let the
        caller fall back.
      * Gaps in the history (years where the company skipped a payment)
        collapse out; CAGR is computed only across years that actually
        had a dividend.
    """
    if not dividends:
        return None
    today = today or date.today()
    totals = _annual_dividend_totals(dividends)
    # Drop the in-progress current year so we compare complete years only.
    totals = [(y, v) for (y, v) in totals if y < today.year]
    if len(totals) < 2:
        return None
    first_year, first_val = totals[0]
    last_year, last_val = totals[-1]
    if first_val <= 0 or last_val <= 0:
        return None
    n_periods = last_year - first_year
    if n_periods <= 0:
        return None
    try:
        return (last_val / first_val) ** (1.0 / n_periods) - 1.0
    except (ValueError, ZeroDivisionError):
        return None


def _capm_required_return(provider, ticker) -> float:
    """Estimate required return via CAPM with safe fallbacks.

    Beta is currently hardcoded to 1.0 because neither ``CompanyProfile``
    nor ``Ratios`` exposes it on this project; a follow-up should add a
    ``beta`` field to ``Ratios`` and read it here.
    """
    rf = FALLBACK_RISK_FREE_RATE
    erp = FALLBACK_EQUITY_RISK_PREMIUM
    beta = FALLBACK_BETA  # TODO: lift from Ratios once exposed.

    # If the provider unexpectedly fails on get_ratios we still fall back
    # to the default beta; no need to surface the error.
    try:
        _ = provider.get_ratios(ticker)
    except DataProviderError:
        pass

    coe = rf + beta * erp
    return _clamp(coe, REQUIRED_RETURN_CLAMP[0], REQUIRED_RETURN_CLAMP[1])


# ---------------------------------------------------------------------------
# Public API: derive defaults
# ---------------------------------------------------------------------------


def derive_simple_ddm_defaults(provider, ticker, profile, quote) -> SimpleDDMInputs:
    """Build a :class:`SimpleDDMInputs` with safe defaults.

    Damodaran, DCF notes: Gordon-growth DDM is appropriate for stable
    dividend payers where g <= rf (long-run GDP) and r = CAPM cost of
    equity.
    """
    dividends = _fetch_dividends(provider, ticker)

    ttm = _ttm_dividend(dividends)
    current_dividend = ttm if ttm > 0 else FALLBACK_CURRENT_DIVIDEND

    cagr = _dividend_cagr(dividends)
    if cagr is None:
        growth_rate = FALLBACK_DIVIDEND_GROWTH
    else:
        growth_rate = _clamp(cagr, GROWTH_CLAMP[0], GROWTH_CLAMP[1])

    required_return = _capm_required_return(provider, ticker)

    # Keep g strictly below r so simple_ddm() doesn't immediately raise
    # on the first render; user can still override either field.
    if growth_rate >= required_return:
        growth_rate = max(GROWTH_CLAMP[0], required_return - 0.01)

    return SimpleDDMInputs(
        current_dividend=current_dividend,
        growth_rate=growth_rate,
        required_return=required_return,
    )


def derive_two_stage_ddm_defaults(provider, ticker, profile, quote) -> TwoStageDDMInputs:
    """Build a :class:`TwoStageDDMInputs` with safe defaults.

    Damodaran, DCF notes: explicit high-growth phase followed by stable
    perpetual growth; stable-phase g <= rf / long-run GDP.
    """
    dividends = _fetch_dividends(provider, ticker)

    ttm = _ttm_dividend(dividends)
    current_dividend = ttm if ttm > 0 else FALLBACK_CURRENT_DIVIDEND

    required_return = _capm_required_return(provider, ticker)

    # Terminal growth: long-run GDP/inflation proxy, capped strictly
    # below required_return so the Gordon denominator stays positive.
    terminal_growth_rate = min(
        FALLBACK_TERMINAL_GROWTH, max(0.0, required_return - 0.01)
    )

    # High-growth: prefer the empirical CAGR, but only if it's meaningfully
    # above the terminal rate; otherwise default to 8%.
    cagr = _dividend_cagr(dividends)
    if cagr is not None:
        cagr_clamped = _clamp(cagr, GROWTH_CLAMP[0], GROWTH_CLAMP[1])
        if cagr_clamped > terminal_growth_rate + 0.02:
            high_growth_rate = cagr_clamped
        else:
            high_growth_rate = FALLBACK_HIGH_GROWTH_RATE
    else:
        high_growth_rate = FALLBACK_HIGH_GROWTH_RATE

    return TwoStageDDMInputs(
        current_dividend=current_dividend,
        high_growth_rate=high_growth_rate,
        high_growth_years=FALLBACK_HIGH_GROWTH_YEARS,
        terminal_growth_rate=terminal_growth_rate,
        required_return=required_return,
    )


# ---------------------------------------------------------------------------
# Public API: apply query overrides
# ---------------------------------------------------------------------------

_SIMPLE_FLOAT_OVERRIDES = (
    "current_dividend",
    "growth_rate",
    "required_return",
)

_TWO_STAGE_FLOAT_OVERRIDES = (
    "current_dividend",
    "high_growth_rate",
    "terminal_growth_rate",
    "required_return",
)


def apply_simple_ddm_overrides(inputs: SimpleDDMInputs, query) -> SimpleDDMInputs:
    """Layer user overrides from ``query`` onto a SimpleDDMInputs.

    Silently skips missing / unparseable values.
    """
    overrides: dict[str, Any] = {}
    for field in _SIMPLE_FLOAT_OVERRIDES:
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


def apply_two_stage_ddm_overrides(inputs: TwoStageDDMInputs, query) -> TwoStageDDMInputs:
    """Layer user overrides from ``query`` onto a TwoStageDDMInputs."""
    overrides: dict[str, Any] = {}
    for field in _TWO_STAGE_FLOAT_OVERRIDES:
        raw = query.get(field)
        if raw is None or raw == "":
            continue
        parsed = _safe_float(raw)
        if parsed is None:
            continue
        overrides[field] = parsed

    raw_years = query.get("high_growth_years")
    if raw_years not in (None, ""):
        parsed_years = _safe_int(raw_years)
        if parsed_years is not None:
            overrides["high_growth_years"] = max(1, min(30, parsed_years))

    if not overrides:
        return inputs
    return replace(inputs, **overrides)
