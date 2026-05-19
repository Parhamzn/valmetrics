"""Default-assumption derivation for the Earnings Power Value (EPV) model.

Mirrors the structure of :mod:`apps.valuation.defaults` (DCF defaults): pull
whatever fundamentals the provider can give us, normalize EBIT over a business
cycle, and fall back to sensible constants whenever a field is missing.

Greenwald's EPV normalizes earnings over a *full* business cycle (he suggests
at least five years) so a single boom or bust year doesn't distort value. For
the maintenance-capex proxy we use trailing D&A — Greenwald's well-known
heuristic for mature firms whose asset base is roughly steady-state.

Source: Greenwald et al., *Value Investing*, ch. 6; CFI EPV explainer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_epv import EPVInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

FALLBACK_TAX_RATE = 0.21
FALLBACK_WACC = 0.08  # TODO: compute via CAPM/WACC in a future iteration
FALLBACK_SHARES = 1.0e9


# ---------------------------------------------------------------------------
# Helpers (kept private; mirror the helper style in defaults.py)
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


def _collect(statement, keys: tuple[str, ...]) -> list[float]:
    """Collect non-None floats across all statement lines.

    Tries each key in ``keys`` per line and uses the first that resolves; this
    handles yfinance's tendency to vary labels between companies (e.g. ``ebit``
    vs ``operating_income``).
    """
    if statement is None:
        return []
    lines = getattr(statement, "lines", None) or []
    values: list[float] = []
    for line in lines:
        items = line.items or {}
        for k in keys:
            v = _safe_float(items.get(k))
            if v is not None:
                values.append(v)
                break
    return values


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_epv_defaults(provider, ticker, profile, quote) -> EPVInputs:
    """Pull statements via ``provider`` and synthesize default EPV inputs.

    Greenwald normalizes EBIT over the full business cycle and uses D&A as the
    maintenance-capex proxy for stable firms. We follow that convention here;
    the user can override every assumption via the form.

    Source: Greenwald et al., *Value Investing*, ch. 6.
    """

    # --- Fetch statements, swallowing provider errors ----------------------
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
    latest_bs = _latest_items(balance)

    # --- Normalized EBIT (mean across all available annual periods) --------
    # Greenwald asks for >=5 years over a business cycle; we use whatever the
    # provider returns and surface the count via ``years_of_history``.
    historical_ebits = _collect(income, ("ebit", "operating_income"))
    normalized_ebit = _mean(historical_ebits)
    if normalized_ebit is None:
        # Fall back to the single latest figure, then to zero.
        normalized_ebit = (
            _safe_float(latest_income.get("ebit"))
            or _safe_float(latest_income.get("operating_income"))
            or 0.0
        )
        years_of_history = 1 if normalized_ebit else 0
    else:
        years_of_history = len(historical_ebits)

    # --- Tax rate ----------------------------------------------------------
    tax_rate = FALLBACK_TAX_RATE
    direct_tax = _safe_float(latest_income.get("tax_rate_for_calcs"))
    if direct_tax is not None:
        tax_rate = _clamp(direct_tax, 0.0, 0.5)
    else:
        tp = _safe_float(latest_income.get("tax_provision"))
        pi = _safe_float(latest_income.get("pretax_income"))
        if tp is not None and pi is not None and pi != 0:
            tax_rate = _clamp(tp / pi, 0.0, 0.5)

    # --- D&A (mean across cash-flow history) -------------------------------
    historical_da = _collect(
        cashflow,
        ("reconciled_depreciation", "depreciation_and_amortization", "depreciation"),
    )
    da_mean = _mean(historical_da)
    depreciation_amortization = abs(da_mean) if da_mean is not None else 0.0

    # --- Maintenance capex -------------------------------------------------
    # Greenwald heuristic: for a steady-state firm, maintenance capex ~= D&A.
    # The user can override; the form labels this explicitly.
    maintenance_capex = depreciation_amortization

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

    return EPVInputs(
        ticker=ticker,
        normalized_ebit=normalized_ebit,
        tax_rate=tax_rate,
        maintenance_capex=maintenance_capex,
        depreciation_amortization=depreciation_amortization,
        wacc=FALLBACK_WACC,
        net_debt=net_debt,
        shares_outstanding=shares,
        years_of_history=years_of_history,
    )


# Fields the user may override via the request querydict.
_FLOAT_OVERRIDES = (
    "normalized_ebit",
    "tax_rate",
    "maintenance_capex",
    "depreciation_amortization",
    "wacc",
)


def apply_epv_overrides(inputs: EPVInputs, query) -> EPVInputs:
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
