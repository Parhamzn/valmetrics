"""Input/output dataclasses for the Margin Analysis operational page.

This page is an *operational* metric, not a valuation. It tracks the three
canonical profit-margin lines (gross / operating / net) across the firm's
available annual history so a reader can quickly see whether the business is
gaining or losing pricing power.

There is no ``fair_value_per_share`` here on purpose: margin analysis is
display-only, supporting a chart and a trend judgement.

Source: Corporate Finance Institute, "Profit Margin"
(https://corporatefinanceinstitute.com/resources/accounting/profit-margin/).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MarginPoint:
    """A single annual margin observation.

    Each field is a decimal fraction (e.g. ``0.42`` for 42%) or ``None`` when
    the underlying line item was missing or non-finite. ``period_end`` is the
    fiscal-period end date that the income statement reports.
    """

    period_end: date
    gross_margin: float | None
    operating_margin: float | None
    profit_margin: float | None


@dataclass(frozen=True)
class MarginAnalysisInputs:
    """Inputs to :func:`margin_analysis`.

    Attributes:
        ticker: Display identifier.
        annual_periods: List of ``StatementLine`` rows from the annual income
            statement, ordered most-recent-first (matching the provider's
            native ordering — yfinance returns latest year at index 0).
    """

    ticker: str
    annual_periods: list  # list[StatementLine] (kept loose to avoid coupling)


@dataclass(frozen=True)
class MarginAnalysisOutputs:
    """Outputs from :func:`margin_analysis`.

    Attributes:
        points: List of :class:`MarginPoint`, **oldest-first** so a chart can
            render years left-to-right without re-sorting.
        latest: The most recent :class:`MarginPoint` (last element of
            ``points``). Surfaced as a convenience for templates.
        avg_gross_margin: Mean gross margin across all years that had a
            non-None value, or ``None`` if no data.
        avg_operating_margin: As above, for operating margin.
        avg_profit_margin: As above, for net profit margin.
        trend_gross: One of ``"expanding"``, ``"stable"``, ``"compressing"``,
            or ``"insufficient data"``. See :func:`margin_analysis` for the
            decision rule.
        trend_operating: As above, for operating margin.
        trend_profit: As above, for net profit margin.
    """

    points: list  # list[MarginPoint], oldest-first
    latest: MarginPoint
    avg_gross_margin: float | None
    avg_operating_margin: float | None
    avg_profit_margin: float | None
    trend_gross: str
    trend_operating: str
    trend_profit: str
