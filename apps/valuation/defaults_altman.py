"""Default-input derivation for the Altman Z-Score model.

Pulls fundamentals from the data provider and packages them into an
:class:`AltmanInputs`. There are no *assumptions* — Altman's Z is a fixed
weighted formula — so the engine never gets fallback constants; missing
inputs come through as ``None`` and the engine flags them in ``warning``.

Source: Altman (1968), Journal of Finance; Investopedia "Altman Z-Score"
entry.
"""

from __future__ import annotations

from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types_altman import AltmanInputs


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


def _latest_items(statement) -> dict[str, float | None]:
    if statement is None:
        return {}
    lines = getattr(statement, "lines", None) or []
    if not lines:
        return {}
    return dict(lines[0].items or {})


def _get(items: dict, *keys: str) -> float | None:
    """First non-None safe float among the given keys, else None."""
    for k in keys:
        v = _safe_float(items.get(k))
        if v is not None:
            return v
    return None


def _working_capital(items: dict) -> float | None:
    """Prefer the explicit ``working_capital`` line; else CA - CL.

    yfinance is inconsistent about exposing the working_capital line directly
    on the balance sheet — sometimes present, sometimes not. We compute it
    from current_assets - current_liabilities whenever the direct field is
    absent; both inputs missing -> None.
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


def derive_altman_defaults(provider, ticker, profile, quote) -> AltmanInputs:
    """Pull annual statements + market cap and synthesize :class:`AltmanInputs`.

    Field map:
        working_capital   -> balance ``working_capital`` (or CA - CL)
        total_assets      -> balance ``total_assets``
        retained_earnings -> balance ``retained_earnings``
        ebit              -> income ``ebit`` (else ``operating_income``)
        market_value_equity -> ``profile.market_cap``
        total_liabilities -> balance ``total_liabilities_net_minority_interest``
        revenue           -> income ``total_revenue``

    Each field may be ``None`` if upstream didn't return it; the engine
    surfaces those as warnings rather than raising.

    Source: Altman (1968), Journal of Finance.
    """
    del quote  # not used; signature parity with other derive_* helpers

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

    market_cap = _safe_float(getattr(profile, "market_cap", None)) if profile else None

    return AltmanInputs(
        ticker=ticker,
        working_capital=_working_capital(latest_bs),
        total_assets=_get(latest_bs, "total_assets"),
        retained_earnings=_get(latest_bs, "retained_earnings"),
        ebit=_get(latest_income, "ebit", "operating_income"),
        market_value_equity=market_cap,
        total_liabilities=_get(
            latest_bs,
            "total_liabilities_net_minority_interest",
            "total_liabilities",
        ),
        revenue=_get(latest_income, "total_revenue", "operating_revenue"),
    )


# No overrides for Altman Z — it's a fixed scoring formula.
