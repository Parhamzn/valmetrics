"""Default-input derivation for the Piotroski F-Score model.

Pulls latest- and prior-year fundamentals from the data provider and packages
them into a :class:`PiotroskiInputs`. Unlike DCF/EPV defaults there are no
*assumptions* to derive (the F-Score is a fixed binary checklist) — every
field is a real reported figure or ``None``. The engine handles ``None`` by
awarding 0 for that criterion.

Source: Piotroski (2000), Journal of Accounting Research; Investopedia
"Piotroski Score" entry.
"""

from __future__ import annotations

from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_piotroski import PiotroskiInputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _items_at(statement, idx: int) -> dict[str, float | None]:
    """Pull the ``items`` dict from the ``idx``-th line, or {} if missing.

    Provider returns lines most-recent-first; idx=0 is latest, idx=1 is prior.
    """
    if statement is None:
        return {}
    lines = getattr(statement, "lines", None) or []
    if len(lines) <= idx:
        return {}
    return dict(lines[idx].items or {})


def _get(items: dict, *keys: str) -> float | None:
    """Try each ``key`` in order; return the first non-None safe float."""
    for k in keys:
        v = _safe_float(items.get(k))
        if v is not None:
            return v
    return None


def _working_capital(items: dict) -> float | None:
    """Working capital straight from balance sheet, else current_assets - cl.

    yfinance occasionally exposes a ``working_capital`` line; when it doesn't,
    Piotroski simply uses CA - CL. Either path returns None if both source
    components are unavailable.
    """
    direct = _safe_float(items.get("working_capital"))
    if direct is not None:
        return direct
    ca = _safe_float(items.get("current_assets"))
    cl = _safe_float(items.get("current_liabilities"))
    if ca is not None and cl is not None:
        return ca - cl
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derive_piotroski_defaults(provider, ticker, profile, quote) -> PiotroskiInputs:
    """Pull annual statements and package them into :class:`PiotroskiInputs`.

    No assumptions, no fallback constants: each field is the reported figure
    from the latest (idx=0) and prior (idx=1) annual line, or ``None`` if the
    provider didn't return it.

    ``profile`` and ``quote`` are accepted for API consistency with the other
    ``derive_*_defaults`` helpers but are not used here (the F-Score reads
    only from statements).

    Source: Piotroski (2000), Journal of Accounting Research.
    """
    del profile, quote  # signature parity; not used

    # --- Fetch statements, swallowing provider errors ----------------------
    income = None
    balance = None
    cashflow = None
    try:
        income = provider.get_income_statement(ticker, period="annual")
    except DataProviderError:
        income = None
    try:
        balance = provider.get_balance_sheet(ticker, period="annual")
    except DataProviderError:
        balance = None
    try:
        cashflow = provider.get_cash_flow(ticker, period="annual")
    except DataProviderError:
        cashflow = None

    inc_now = _items_at(income, 0)
    inc_prior = _items_at(income, 1)
    bs_now = _items_at(balance, 0)
    bs_prior = _items_at(balance, 1)
    cf_now = _items_at(cashflow, 0)
    cf_prior = _items_at(cashflow, 1)

    return PiotroskiInputs(
        ticker=ticker,
        # Profitability inputs
        net_income=_get(inc_now, "net_income", "net_income_common_stockholders"),
        prior_net_income=_get(inc_prior, "net_income", "net_income_common_stockholders"),
        total_assets=_get(bs_now, "total_assets"),
        prior_total_assets=_get(bs_prior, "total_assets"),
        operating_cash_flow=_get(
            cf_now,
            "operating_cash_flow",
            "cash_flow_from_continuing_operating_activities",
            "total_cash_from_operating_activities",
        ),
        prior_operating_cash_flow=_get(
            cf_prior,
            "operating_cash_flow",
            "cash_flow_from_continuing_operating_activities",
            "total_cash_from_operating_activities",
        ),
        # Leverage / liquidity / source of funds
        long_term_debt=_get(bs_now, "long_term_debt"),
        prior_long_term_debt=_get(bs_prior, "long_term_debt"),
        current_assets=_get(bs_now, "current_assets"),
        prior_current_assets=_get(bs_prior, "current_assets"),
        current_liabilities=_get(bs_now, "current_liabilities"),
        prior_current_liabilities=_get(bs_prior, "current_liabilities"),
        diluted_shares=_get(inc_now, "diluted_average_shares", "basic_average_shares"),
        prior_diluted_shares=_get(inc_prior, "diluted_average_shares", "basic_average_shares"),
        # Operating efficiency
        gross_profit=_get(inc_now, "gross_profit"),
        prior_gross_profit=_get(inc_prior, "gross_profit"),
        total_revenue=_get(inc_now, "total_revenue", "operating_revenue"),
        prior_total_revenue=_get(inc_prior, "total_revenue", "operating_revenue"),
    )


# No overrides for Piotroski — it's a fixed computation. (We intentionally do
# not expose an ``apply_*_overrides`` helper here.)
