"""Default-assumption derivation for Weighted-Average Cost of Capital (WACC).

WACC = (E / V) * Ke + (D / V) * Kd * (1 - t)
  where V = E + D, Ke is CAPM cost of equity, Kd is pre-tax cost of debt,
  and t is the marginal/effective tax rate.

Defaults:
  * Ke is derived via CAPM (see ``defaults_capm.derive_capm_defaults``).
  * Kd is interest expense / total debt from the most recent annual filings.
  * Tax rate follows the same logic as ``defaults.py`` for the DCF model.
  * Equity market value uses profile.market_cap; debt market value uses
    book debt as a practitioner shortcut (Damodaran calls this an acceptable
    approximation when debt does not trade at a large discount).

Source: Damodaran, "Estimating Risk-Free Rates and Risk Premiums"; Damodaran
cost-of-capital lecture notes for the book-value-of-debt approximation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.defaults_capm import derive_capm_defaults
from apps.valuation.engine.capm import capm_cost_of_equity
from apps.valuation.engine.types import WACCInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------

FALLBACK_COST_OF_EQUITY = 0.089  # ~Rf + 1.0 * ERP using our CAPM defaults
FALLBACK_COST_OF_DEBT = 0.05
FALLBACK_TAX_RATE = 0.21
FALLBACK_MARKET_VALUE_EQUITY = 1.0e9
FALLBACK_MARKET_VALUE_DEBT = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


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


# Source: Damodaran cost-of-capital lecture notes; book-value-of-debt proxy.
def derive_wacc_defaults(provider, ticker, profile, quote) -> WACCInputs:
    """Pull statements via ``provider`` and synthesize default WACC inputs.

    The function is forgiving: any provider failure or missing field is
    handled with a fallback so this never raises on patchy upstream data.
    """

    # --- Fetch statements, swallowing provider errors ----------------------
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

    # --- Cost of equity from CAPM defaults ---------------------------------
    try:
        capm_inputs = derive_capm_defaults(provider, ticker, profile, quote)
        cost_of_equity = capm_cost_of_equity(capm_inputs).cost_of_equity
    except Exception:
        cost_of_equity = FALLBACK_COST_OF_EQUITY

    # --- Total debt from balance sheet (book proxy for market value) -------
    total_debt = _safe_float(latest_bs.get("total_debt"))
    if total_debt is None:
        ltd = _safe_float(latest_bs.get("long_term_debt")) or 0.0
        cd = _safe_float(latest_bs.get("current_debt")) or 0.0
        total_debt = ltd + cd

    # --- Pre-tax cost of debt: interest expense / total debt ---------------
    # yfinance reports interest_expense as a (negative) cost on the income
    # statement; we use abs() so the resulting Kd is positive.
    interest_expense = _safe_float(latest_income.get("interest_expense"))
    cost_of_debt = FALLBACK_COST_OF_DEBT
    if interest_expense is not None and total_debt and total_debt > 0:
        kd = abs(interest_expense) / total_debt
        # Clamp to a sane band — IRS imputed-interest-rate territory at the
        # low end, distressed-debt yields at the high end.
        cost_of_debt = _clamp(kd, 0.0, 0.20)

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

    # --- Market value of equity: prefer profile.market_cap -----------------
    mve = _safe_float(getattr(profile, "market_cap", None)) if profile else None
    if not mve or mve <= 0:
        # Fall back to price * diluted_average_shares if we can reconstruct.
        px = _safe_float(getattr(quote, "price", None)) if quote else None
        shares = _safe_float(latest_income.get("diluted_average_shares"))
        if px and shares and shares > 0:
            mve = px * shares
        else:
            mve = FALLBACK_MARKET_VALUE_EQUITY

    # --- Market value of debt: use book debt (Damodaran-approved proxy) ----
    mvd = total_debt if total_debt is not None else FALLBACK_MARKET_VALUE_DEBT
    if mvd < 0:
        mvd = 0.0

    return WACCInputs(
        cost_of_equity=cost_of_equity,
        cost_of_debt=cost_of_debt,
        tax_rate=tax_rate,
        market_value_equity=mve,
        market_value_debt=mvd,
    )


# Fields the user may override via the request querydict.
_FLOAT_OVERRIDES = (
    "cost_of_equity",
    "cost_of_debt",
    "tax_rate",
    "market_value_equity",
    "market_value_debt",
)


def apply_wacc_overrides(inputs: WACCInputs, query) -> WACCInputs:
    """Replace user-overridable WACC fields using values from ``query``.

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

    if not overrides:
        return inputs
    return replace(inputs, **overrides)
