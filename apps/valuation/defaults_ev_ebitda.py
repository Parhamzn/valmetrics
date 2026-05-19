"""Default-assumption derivation for the EV/EBITDA Multiple valuation model.

Mirrors the structure of :mod:`apps.valuation.defaults` (DCF defaults): pull
fundamentals from the provider, distill them into an :class:`EVEBITDAInputs`
payload, and fall back to constants whenever a field is missing.

The default for ``target_ev_ebitda`` is the company's *current* trading multiple
(from ``ratios.ev_to_ebitda``) — that way the user starts at the status-quo
valuation and can flex up/down to see sensitivity to multiple expansion or
compression.

Source: Corporate Finance Institute — "EV/EBITDA"
(https://corporatefinanceinstitute.com/resources/valuation/ev-ebitda/).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_ev_ebitda import EVEBITDAInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

# Loose industry-neutral midpoint. CFI notes EV/EBITDA "typically falls between
# 5x and 15x" for most mature firms; 12x is a reasonable centroid.
FALLBACK_TARGET_EV_EBITDA = 12.0
FALLBACK_SHARES = 1.0e9

# Clamp range for target_ev_ebitda. Below ~3x is essentially a distress sale;
# above ~35x implies hyper-growth premiums that rarely persist.
TARGET_MULTIPLE_MIN = 3.0
TARGET_MULTIPLE_MAX = 35.0


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
    """Best-effort float coercion. Returns None on failure or non-finite."""
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


def derive_ev_ebitda_defaults(provider, ticker, profile, quote) -> EVEBITDAInputs:
    """Pull statements via ``provider`` and synthesize default EV/EBITDA inputs.

    ``target_ev_ebitda`` defaults to ``ratios.ev_to_ebitda`` (the company's
    current trading multiple), clamped to a sane range — the user can flex it
    up or down to model multiple expansion / compression.

    Source: CFI EV/EBITDA explainer.
    """
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

    ratios = None
    try:
        ratios = provider.get_ratios(ticker)
    except DataProviderError:
        ratios = None

    latest_income = _latest_items(income)
    latest_cf = _latest_items(cashflow)
    latest_bs = _latest_items(balance)

    # --- EBITDA ------------------------------------------------------------
    ebitda = _safe_float(latest_income.get("ebitda"))
    if ebitda is None:
        ebitda = _safe_float(latest_income.get("normalized_ebitda"))
    if ebitda is None:
        # Rough proxy: EBIT + D&A. yfinance reports D&A on the cash-flow
        # statement as ``reconciled_depreciation`` (sometimes negative-signed,
        # so take abs).
        ebit = _safe_float(latest_income.get("ebit"))
        if ebit is None:
            ebit = _safe_float(latest_income.get("operating_income"))
        if ebit is not None:
            da = _safe_float(latest_cf.get("reconciled_depreciation")) or 0.0
            ebitda = ebit + abs(da)
    if ebitda is None:
        ebitda = 0.0

    # --- Target multiple ---------------------------------------------------
    # Anchor on the firm's current EV/EBITDA from the ratios endpoint so users
    # start at status-quo and flex from there.
    target_ev_ebitda = FALLBACK_TARGET_EV_EBITDA
    if ratios is not None:
        current = _safe_float(getattr(ratios, "ev_to_ebitda", None))
        if current is not None and current > 0:
            target_ev_ebitda = _clamp(current, TARGET_MULTIPLE_MIN, TARGET_MULTIPLE_MAX)

    # --- Net debt ----------------------------------------------------------
    ltd = _safe_float(latest_bs.get("long_term_debt")) or 0.0
    cd = _safe_float(latest_bs.get("current_debt")) or 0.0
    cash = _safe_float(latest_bs.get("cash_and_cash_equivalents")) or 0.0
    net_debt = ltd + cd - cash

    # --- Shares outstanding ------------------------------------------------
    shares = _safe_float(latest_income.get("diluted_average_shares"))
    if shares is None or shares <= 0:
        mc = _safe_float(getattr(profile, "market_cap", None)) if profile else None
        px = _safe_float(getattr(quote, "price", None)) if quote else None
        if mc and px and px > 0:
            shares = mc / px
        else:
            shares = FALLBACK_SHARES

    return EVEBITDAInputs(
        ticker=ticker,
        ebitda=ebitda,
        target_ev_ebitda=target_ev_ebitda,
        net_debt=net_debt,
        shares_outstanding=shares,
    )


# Fields the user may override via the request querydict.
_FLOAT_OVERRIDES = (
    "target_ev_ebitda",
    "ebitda",
    "net_debt",
)


def apply_ev_ebitda_overrides(inputs: EVEBITDAInputs, query) -> EVEBITDAInputs:
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
