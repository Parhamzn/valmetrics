"""ROIC (Return on Invested Capital) engine.

Computes a per-year time series of NOPAT, Invested Capital, and ROIC, plus a
trend classification and a value-creation judgement vs the WACC estimate.

Variant choices (documented per Damodaran, "Return on Capital, Return on
Invested Capital, and Return on Equity"):

    NOPAT
        EBIT * (1 - effective_tax_rate). Falls back to ``operating_income``
        when ``ebit`` is missing. Effective tax rate is derived per-year from
        the income statement: prefer the provider's ``tax_rate_for_calcs``,
        else ``tax_provision / pretax_income``, else a 21% fallback.

    Invested Capital  (cash-exclusion variant)
        common_stock_equity + long_term_debt + current_debt - cash_and_cash_equivalents

        Damodaran lists several variants — book-vs-market, including/excluding
        cash, end-of-period vs averaged. We use **book values** (yfinance gives
        us books, not market values for debt) and **exclude cash**: excluding
        excess cash isolates operating capital so ROIC reflects how
        efficiently the *business* converts capital to profit, not how big the
        treasury balance is. This matches Investopedia's recommended
        practitioner formula.

    ROIC
        NOPAT / Invested Capital. Returns ``None`` when invested capital is
        zero or negative (mathematically defined but economically nonsensical
        — a leveraged buyout with negative book equity, etc.).

Trend rule: identical to margin analysis (slope of OLS line vs +/- 50 bps band)
so the two pages feel consistent.

Sources:
    * Damodaran, returnmeasures.pdf (NYU Stern).
    * Investopedia, "Return on Invested Capital".
"""

from __future__ import annotations

from datetime import date

from apps.valuation.engine.types_roic import ROICInputs, ROICOutputs, ROICPoint

# Trend band: 50 bps / yr matches margin_analysis for consistent UX.
_TREND_BAND = 0.005

# Fallback tax rate matches defaults_epv.FALLBACK_TAX_RATE (21% US federal).
_FALLBACK_TAX_RATE = 0.21


def _safe_float(value) -> float | None:
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


def _effective_tax_rate(items: dict) -> float:
    """Per-year effective tax rate, mirroring defaults_epv's logic.

    Priority: ``tax_rate_for_calcs`` -> ``tax_provision / pretax_income``
    -> the 21% fallback. Clamped to [0, 0.5] to absorb yfinance outliers.
    """
    direct = _safe_float(items.get("tax_rate_for_calcs"))
    if direct is not None:
        return _clamp(direct, 0.0, 0.5)
    tp = _safe_float(items.get("tax_provision"))
    pi = _safe_float(items.get("pretax_income"))
    if tp is not None and pi is not None and pi != 0:
        return _clamp(tp / pi, 0.0, 0.5)
    return _FALLBACK_TAX_RATE


def _compute_point(income_line, balance_line) -> ROICPoint:
    """Build one :class:`ROICPoint` from paired income/balance rows."""
    income_items = (getattr(income_line, "items", None) or {}) if income_line else {}
    balance_items = (getattr(balance_line, "items", None) or {}) if balance_line else {}

    period_end = None
    if income_line is not None and isinstance(getattr(income_line, "period_end", None), date):
        period_end = income_line.period_end
    elif balance_line is not None and isinstance(getattr(balance_line, "period_end", None), date):
        period_end = balance_line.period_end
    else:
        period_end = date.today()

    # --- NOPAT --------------------------------------------------------------
    ebit = _safe_float(income_items.get("ebit"))
    if ebit is None:
        ebit = _safe_float(income_items.get("operating_income"))

    nopat: float | None = None
    if ebit is not None:
        tax_rate = _effective_tax_rate(income_items)
        nopat = ebit * (1.0 - tax_rate)

    # --- Invested capital (book equity + debt - cash) -----------------------
    equity = _safe_float(balance_items.get("common_stock_equity"))
    if equity is None:
        equity = _safe_float(
            balance_items.get("total_equity_gross_minority_interest")
        )
    ltd = _safe_float(balance_items.get("long_term_debt"))
    cd = _safe_float(balance_items.get("current_debt"))
    cash = _safe_float(balance_items.get("cash_and_cash_equivalents"))

    invested_capital: float | None = None
    if equity is not None or ltd is not None or cd is not None:
        invested_capital = (
            (equity or 0.0)
            + (ltd or 0.0)
            + (cd or 0.0)
            - (cash or 0.0)
        )

    # --- ROIC ---------------------------------------------------------------
    roic: float | None = None
    if (
        nopat is not None
        and invested_capital is not None
        and invested_capital > 0  # guard against zero / negative denominators
    ):
        roic = nopat / invested_capital

    return ROICPoint(
        period_end=period_end,
        nopat=nopat,
        invested_capital=invested_capital,
        roic=roic,
    )


def _classify_trend(values: list[float | None]) -> str:
    """Same OLS-slope rule as ``margin_analysis._classify_trend``."""
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return "insufficient data"
    n = len(clean)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(clean) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, clean))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return "stable"
    slope = num / den
    if slope > _TREND_BAND:
        return "expanding"
    if slope < -_TREND_BAND:
        return "compressing"
    return "stable"


def _mean(values) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


# Source: Damodaran, "Return on Capital, Return on Invested Capital..." (NYU).
def compute_roic(inputs: ROICInputs) -> ROICOutputs:
    """Build the historical ROIC series and value-creation verdict.

    ``annual_periods`` is expected most-recent-first as a list of
    ``(income_line, balance_line)`` tuples; the output is sorted oldest-first
    so a chart can render years left-to-right.

    Empty input is tolerated and produces a safe empty result instead of
    raising.
    """
    pairs = list(inputs.annual_periods or [])

    if not pairs:
        empty = ROICPoint(
            period_end=date.today(),
            nopat=None,
            invested_capital=None,
            roic=None,
        )
        return ROICOutputs(
            points=[],
            latest=empty,
            avg_roic=None,
            trend="insufficient data",
            wacc_estimate=inputs.wacc_estimate,
            creates_value=None,
        )

    points = [_compute_point(i, b) for i, b in pairs]
    points.sort(key=lambda p: p.period_end)

    roic_series = [p.roic for p in points]
    avg = _mean(roic_series)
    trend = _classify_trend(roic_series)

    latest = points[-1]
    creates_value: bool | None
    if latest.roic is None:
        creates_value = None
    else:
        creates_value = latest.roic > inputs.wacc_estimate

    return ROICOutputs(
        points=points,
        latest=latest,
        avg_roic=avg,
        trend=trend,
        wacc_estimate=inputs.wacc_estimate,
        creates_value=creates_value,
    )
