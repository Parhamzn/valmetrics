"""Default-assumption derivation for the Capital Asset Pricing Model (CAPM).

CAPM gives the required return on equity (cost of equity, Ke) as

    Ke = Rf + beta * ERP

where Rf is the risk-free rate (10-year US Treasury proxy in practice),
beta is the stock's systematic-risk loading, and ERP is the equity risk
premium investors demand over the risk-free asset.

Source: Damodaran, "Estimating Risk-Free Rates and Risk Premiums" and his
country/ERP datafile (https://pages.stern.nyu.edu/~adamodar/New_Home_Page/
datafile/ctryprem.html). The default US ERP we use here, 4.6%, is in line
with Damodaran's January 2026 estimate of 4.46% for the mature US market.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from apps.data.base import DataProviderError
from apps.valuation.engine.types import CAPMInputs


# ---------------------------------------------------------------------------
# Fallback constants
# ---------------------------------------------------------------------------
#
# Source: 10-year US Treasury constant maturity yield (FRED ticker DGS10) for
# the risk-free rate; Damodaran's most recent country-ERP table for the ERP.
# These are static defaults — a future iteration could pull a live yield and
# refresh the ERP from the Damodaran datafile.
#
FALLBACK_RISK_FREE_RATE = 0.043  # 10-year US Treasury yield proxy
FALLBACK_EQUITY_RISK_PREMIUM = 0.046  # Damodaran recent US ERP estimate
FALLBACK_BETA = 1.0  # market-equivalent risk if no provider value available


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


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Source: Damodaran's ctryprem datafile + 10y Treasury yield as Rf proxy.
def derive_capm_defaults(provider, ticker, profile, quote) -> CAPMInputs:
    """Damodaran-style CAPM defaults: rf = 10-year US Treasury proxy, ERP = 4.6%.

    Beta is sourced from the provider's ratios (yfinance's ``info.beta``,
    typically a 5-year monthly regression against the S&P 500). If the
    provider has no beta for the ticker, we fall back to 1.0 — i.e., assume
    the stock moves with the market — which is the conventional placeholder.
    """

    # --- Beta from ratios (provider may not expose it for every ticker) ---
    beta = FALLBACK_BETA
    try:
        ratios = provider.get_ratios(ticker)
    except DataProviderError:
        ratios = None
    if ratios is not None:
        b = _safe_float(getattr(ratios, "beta", None))
        if b is not None:
            # Clamp to a reasonable range so a noisy yfinance value can't
            # produce nonsense (e.g. a leveraged ETF). Real-world equity
            # betas live roughly between -1 and 4.
            beta = _clamp(b, -1.0, 4.0)

    # --- Rf / ERP are static defaults; the form lets users override -------
    risk_free_rate = FALLBACK_RISK_FREE_RATE
    equity_risk_premium = FALLBACK_EQUITY_RISK_PREMIUM

    return CAPMInputs(
        risk_free_rate=risk_free_rate,
        beta=beta,
        equity_risk_premium=equity_risk_premium,
    )


# Fields the user may override via the request querydict.
_FLOAT_OVERRIDES = (
    "risk_free_rate",
    "beta",
    "equity_risk_premium",
)


def apply_capm_overrides(inputs: CAPMInputs, query) -> CAPMInputs:
    """Replace user-overridable CAPM fields using values from ``query``.

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
