"""Default-assumption derivation for the DCF — Exit Multiple model.

Mirrors the structure of :mod:`apps.valuation.defaults` (perpetual-growth DCF):
pull whatever fundamentals the provider can give us and fall back to sensible
constants whenever a field is missing. The only meaningful differences are:

* We also compute a ``base_ebitda`` and ``ebitda_margin`` so we can project
  Year N EBITDA, which is what the terminal multiple acts on.
* We seed the ``exit_ev_ebitda`` field from the company's *current*
  EV/EBITDA ratio (clamped to a sensible band) so users start from a number
  that's at least consistent with where the market is right now.

Source: Damodaran, DCF notes — encourages picking an exit multiple consistent
with peer comparables and back-testing against the implied perpetual-growth
sanity check (handled in the engine, not here).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_dcf_exit_multiple import DCFExitMultipleInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

FALLBACK_REVENUE_GROWTH = 0.05
FALLBACK_EBIT_MARGIN = 0.15
FALLBACK_EBITDA_MARGIN = 0.25
FALLBACK_TAX_RATE = 0.21
FALLBACK_REINVESTMENT = 0.30
FALLBACK_WACC = 0.08
FALLBACK_EXIT_EV_EBITDA = 12.0
FALLBACK_PROJECTION_YEARS = 5
FALLBACK_SHARES = 1.0e9


# ---------------------------------------------------------------------------
# Helpers (private; mirror the helper style in defaults.py)
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


def _historical_revenues(statement) -> list[float]:
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


def derive_dcf_exit_multiple_defaults(
    provider, ticker, profile, quote
) -> DCFExitMultipleInputs:
    """Pull statements via ``provider`` and synthesize default exit-multiple DCF
    inputs. Robust to missing fields — every numeric is wrapped in a fallback.
    """

    # --- Fetch statements, swallowing provider errors -----------------------
    income = None
    cashflow = None
    balance = None
    ratios = None
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
    try:
        ratios = provider.get_ratios(ticker)
    except DataProviderError:
        ratios = None

    latest_income = _latest_items(income)
    latest_cf = _latest_items(cashflow)
    latest_bs = _latest_items(balance)

    # --- Base revenue -------------------------------------------------------
    base_revenue = _safe_float(latest_income.get("total_revenue")) or 0.0

    # --- Base EBITDA --------------------------------------------------------
    base_ebitda = _safe_float(latest_income.get("ebitda"))
    if base_ebitda is None:
        base_ebitda = _safe_float(latest_income.get("normalized_ebitda"))
    if base_ebitda is None:
        # Fallback: EBIT + D&A from cash flow.
        ebit_val_for_ebitda = _safe_float(latest_income.get("ebit"))
        if ebit_val_for_ebitda is None:
            ebit_val_for_ebitda = _safe_float(latest_income.get("operating_income"))
        da = None
        for k in (
            "reconciled_depreciation",
            "depreciation_and_amortization",
            "depreciation",
        ):
            da = _safe_float(latest_cf.get(k))
            if da is not None:
                break
        if ebit_val_for_ebitda is not None:
            base_ebitda = ebit_val_for_ebitda + abs(da or 0.0)
        else:
            base_ebitda = 0.0

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

    # --- EBITDA margin ------------------------------------------------------
    if base_ebitda and base_revenue > 0:
        ebitda_margin = _clamp(base_ebitda / base_revenue, 0.0, 0.7)
    else:
        ebitda_margin = FALLBACK_EBITDA_MARGIN

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

    # --- Exit EV/EBITDA -----------------------------------------------------
    # Seed from the ticker's current EV/EBITDA, clamped to a sane band. Users
    # can override on the form; the engine surfaces an implied-growth check.
    exit_multiple = FALLBACK_EXIT_EV_EBITDA
    if ratios is not None:
        candidate = _safe_float(getattr(ratios, "ev_to_ebitda", None))
        if candidate is not None:
            exit_multiple = _clamp(candidate, 5.0, 25.0)

    # --- Net debt -----------------------------------------------------------
    ltd = _safe_float(latest_bs.get("long_term_debt")) or 0.0
    cd = _safe_float(latest_bs.get("current_debt")) or 0.0
    cash = _safe_float(latest_bs.get("cash_and_cash_equivalents")) or 0.0
    net_debt = ltd + cd - cash

    return DCFExitMultipleInputs(
        ticker=ticker,
        base_revenue=base_revenue,
        base_ebitda=base_ebitda,
        projection_years=FALLBACK_PROJECTION_YEARS,
        revenue_growth_rate=growth,
        ebit_margin=ebit_margin,
        ebitda_margin=ebitda_margin,
        tax_rate=tax_rate,
        reinvestment_rate=reinvest_rate,
        wacc=FALLBACK_WACC,
        exit_ev_ebitda=exit_multiple,
        net_debt=net_debt,
        shares_outstanding=shares,
    )


# Fields the user may override via the request querydict.
_FLOAT_OVERRIDES = (
    "revenue_growth_rate",
    "ebit_margin",
    "ebitda_margin",
    "tax_rate",
    "reinvestment_rate",
    "wacc",
    "exit_ev_ebitda",
)


def apply_dcf_exit_multiple_overrides(
    inputs: DCFExitMultipleInputs, query
) -> DCFExitMultipleInputs:
    """Replace user-overridable fields on ``inputs`` from ``query``.

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

    raw_years = query.get("projection_years")
    if raw_years not in (None, ""):
        parsed_years = _safe_int(raw_years)
        if parsed_years is not None:
            overrides["projection_years"] = max(1, min(20, parsed_years))

    if not overrides:
        return inputs
    return replace(inputs, **overrides)
