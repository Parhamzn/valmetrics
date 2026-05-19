"""Margin Analysis engine — historical gross / operating / net margin trend.

This is an operational page: it summarizes the firm's profitability over time
without producing a per-share fair value. The output is a small time series
that a chart and a trend indicator can consume directly.

Trend rule (chosen deliberately, see ``_classify_trend``):
    With <3 data points -> "insufficient data".
    Otherwise we fit a tiny least-squares line through the per-year margin
    series (oldest -> newest, x = year index). The slope sign is compared
    against a 50 bps threshold:
        slope >  +0.005  -> "expanding"
        slope <  -0.005  -> "compressing"
        else            -> "stable"
    A linear slope is more robust than the "first half vs second half" diff
    when companies have one or two noisy years, which is common for cyclicals.

Source: Corporate Finance Institute, "Profit Margin"
(https://corporatefinanceinstitute.com/resources/accounting/profit-margin/).
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from apps.valuation.engine.types_margin_analysis import (
    MarginAnalysisInputs,
    MarginAnalysisOutputs,
    MarginPoint,
)

# Trend classification threshold: 50 bps per year of slope. Anything inside
# the band [-0.005, +0.005] reads as essentially flat to a human eye.
_TREND_BAND = 0.005


def _safe_float(value) -> float | None:
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


def _safe_div(num: float | None, den: float | None) -> float | None:
    """Divide; return None if either side is missing/zero/non-finite."""
    if num is None or den is None:
        return None
    if den == 0:
        return None
    out = num / den
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _classify_trend(values: list[float | None]) -> str:
    """Classify a margin series (oldest-first) as expanding/stable/compressing.

    Uses the slope of an ordinary least-squares fit; see module docstring.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return "insufficient data"

    n = len(clean)
    xs = list(range(n))  # 0, 1, ..., n-1 (one unit per year)
    mean_x = sum(xs) / n
    mean_y = sum(clean) / n

    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, clean))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return "stable"
    slope = num / den  # change in margin per year

    if slope > _TREND_BAND:
        return "expanding"
    if slope < -_TREND_BAND:
        return "compressing"
    return "stable"


def _mean(values: Iterable[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _build_point(line) -> MarginPoint:
    """Turn one provider ``StatementLine`` into a :class:`MarginPoint`.

    Falls back to ``ebit`` for operating margin when ``operating_income`` is
    absent, which mirrors how the EPV defaults treat the same pair.
    """
    items = line.items or {}
    revenue = _safe_float(items.get("total_revenue"))
    gross = _safe_float(items.get("gross_profit"))
    op = _safe_float(items.get("operating_income"))
    if op is None:
        op = _safe_float(items.get("ebit"))
    net = _safe_float(items.get("net_income"))

    period_end = getattr(line, "period_end", None)
    if not isinstance(period_end, date):
        # Defensive: the engine shouldn't blow up if a row is malformed.
        period_end = date.today()

    return MarginPoint(
        period_end=period_end,
        gross_margin=_safe_div(gross, revenue),
        operating_margin=_safe_div(op, revenue),
        profit_margin=_safe_div(net, revenue),
    )


# Source: CFI "Profit Margin" definitions for gross/operating/net margin.
def margin_analysis(inputs: MarginAnalysisInputs) -> MarginAnalysisOutputs:
    """Compute the historical margin series and trend classification.

    The input ``annual_periods`` is the provider's most-recent-first list of
    income-statement rows. We compute a :class:`MarginPoint` per row, then
    sort the output **oldest-first** so charts can render left-to-right.

    Empty / malformed input is tolerated: we return a single empty point with
    today's date and ``insufficient data`` trends so the view layer always
    has something to render.
    """
    lines = list(inputs.annual_periods or [])

    if not lines:
        empty = MarginPoint(
            period_end=date.today(),
            gross_margin=None,
            operating_margin=None,
            profit_margin=None,
        )
        return MarginAnalysisOutputs(
            points=[],
            latest=empty,
            avg_gross_margin=None,
            avg_operating_margin=None,
            avg_profit_margin=None,
            trend_gross="insufficient data",
            trend_operating="insufficient data",
            trend_profit="insufficient data",
        )

    # Provider yields most-recent-first; we want oldest-first for charting.
    points = [_build_point(line) for line in lines]
    points.sort(key=lambda p: p.period_end)

    gross_series = [p.gross_margin for p in points]
    op_series = [p.operating_margin for p in points]
    net_series = [p.profit_margin for p in points]

    return MarginAnalysisOutputs(
        points=points,
        latest=points[-1],
        avg_gross_margin=_mean(gross_series),
        avg_operating_margin=_mean(op_series),
        avg_profit_margin=_mean(net_series),
        trend_gross=_classify_trend(gross_series),
        trend_operating=_classify_trend(op_series),
        trend_profit=_classify_trend(net_series),
    )
