"""Input/output dataclasses for the ROIC (Return on Invested Capital) page.

ROIC is an operational metric: it measures how efficiently a firm turns its
invested capital into operating profit. There's no per-share fair value; the
page is a chart + a comparison to WACC.

Chosen formulas (see ``roic.py`` for the full rationale):
    NOPAT            = EBIT * (1 - effective_tax_rate)
    Invested Capital = Total Equity + Long-term Debt + Short-term Debt - Cash
    ROIC             = NOPAT / Invested Capital

The cash-exclusion variant of Invested Capital is the standard practitioner
choice; excluding excess cash isolates operating capital so the ratio reflects
operating-business efficiency rather than treasury management.

Sources:
    * Damodaran, "Return on Capital, Return on Invested Capital, and Return
      on Equity: Measurement and Implications"
      (https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/returnmeasures.pdf)
    * Investopedia, "Return on Invested Capital"
      (https://www.investopedia.com/terms/r/returnoninvestmentcapital.asp)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ROICPoint:
    """A single annual ROIC observation.

    Fields are ``None`` when the underlying inputs were missing or when the
    invested-capital denominator collapsed to zero / negative (which can
    happen on highly leveraged firms with negative book equity).
    """

    period_end: date
    nopat: float | None
    invested_capital: float | None
    roic: float | None


@dataclass(frozen=True)
class ROICInputs:
    """Inputs to :func:`compute_roic`.

    Attributes:
        ticker: Display identifier.
        annual_periods: List of ``(income_line, balance_line)`` tuples, each
            pair sharing the same fiscal year. The list is most-recent-first
            (the provider's native order).
        wacc_estimate: Discount-rate benchmark for value-creation judgement.
            Defaults to 8% if the caller doesn't supply one; the form on the
            view layer can override it.
    """

    ticker: str
    annual_periods: list  # list[tuple[StatementLine, StatementLine]]
    wacc_estimate: float = 0.08


@dataclass(frozen=True)
class ROICOutputs:
    """Outputs from :func:`compute_roic`.

    Attributes:
        points: Per-year :class:`ROICPoint` list, **oldest-first** (chart-ready).
        latest: The most recent ROICPoint (last element of ``points``).
        avg_roic: Mean ROIC across all years that produced a non-None value.
        trend: One of ``"expanding"``, ``"stable"``, ``"compressing"``,
            or ``"insufficient data"``.
        wacc_estimate: Echoed from inputs for template convenience.
        creates_value: ``True`` if ``latest.roic`` strictly exceeds the WACC
            estimate, ``False`` if it doesn't, ``None`` when the latest ROIC
            isn't available.
    """

    points: list  # list[ROICPoint], oldest-first
    latest: ROICPoint
    avg_roic: float | None
    trend: str
    wacc_estimate: float
    creates_value: bool | None
