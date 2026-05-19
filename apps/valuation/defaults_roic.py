"""Default-input derivation for the ROIC operational page.

Pulls annual income statement + balance sheet from the provider and pairs them
positionally. yfinance returns both most-recent-first with one row per fiscal
year, so positional alignment yields matching (income, balance) pairs.

User can override ``wacc_estimate`` via the request querydict; the underlying
historical inputs are not user-editable (it's analysis, not forecasting).

Sources:
    * Damodaran, "Return on Capital, Return on Invested Capital, and Return
      on Equity: Measurement and Implications" (NYU Stern).
    * Investopedia, "Return on Invested Capital".
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_roic import ROICInputs

FALLBACK_WACC = 0.08


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


def derive_roic_defaults(provider, ticker, profile=None, quote=None) -> ROICInputs:
    """Fetch annual income + balance sheet; pair them positionally.

    Both statements are most-recent-first by provider convention. We zip them
    together up to the shorter length so any year missing from either side is
    simply omitted from the analysis.
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

    income_lines = list(getattr(income, "lines", None) or []) if income else []
    balance_lines = list(getattr(balance, "lines", None) or []) if balance else []

    pairs = list(zip(income_lines, balance_lines))

    return ROICInputs(
        ticker=ticker,
        annual_periods=pairs,
        wacc_estimate=FALLBACK_WACC,
    )


def apply_roic_overrides(inputs: ROICInputs, query) -> ROICInputs:
    """Allow ``wacc_estimate`` override from the request querydict.

    Silently skips missing / unparseable values. ``query`` may be a
    Django QueryDict or a plain dict.
    """
    raw = query.get("wacc_estimate") if query is not None else None
    if raw is None or raw == "":
        return inputs
    parsed = _safe_float(raw)
    if parsed is None:
        return inputs
    return replace(inputs, wacc_estimate=parsed)
