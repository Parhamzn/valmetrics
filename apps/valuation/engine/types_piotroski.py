"""Input/output dataclasses for the Piotroski F-Score model.

Kept separate from ``types.py`` so this file can be authored without colliding
with concurrent edits to the main engine types module. The F-Score is a 9-point
checklist comparing a firm's most-recent annual statements against the prior
year on profitability, leverage/liquidity, and operating efficiency signals.

Source: Piotroski, J., "Value Investing: The Use of Historical Financial
Statement Information to Separate Winners from Losers", Journal of Accounting
Research, 2000; Investopedia "Piotroski Score" entry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PiotroskiCriterion:
    """One row of the 9-criterion F-Score table.

    Attributes:
        name: Short label for the criterion (e.g. "Positive net income").
        description: Longer human-readable description used in templates.
        score: 0 or 1 — Piotroski awards a single point per criterion met.
        value: The most-recent-period metric value (e.g. current ROA), or None
            if a required input was missing.
        prior_value: The prior-period comparison value, or None for level
            (non-YoY) criteria or when missing.
        explanation: One-line human description, e.g.
            "Net income improved from $X to $Y" or "Data unavailable".
    """

    name: str
    description: str
    score: int           # 0 or 1
    value: float | None  # the metric value
    prior_value: float | None
    explanation: str     # one-line "Y improved from X to Z" or "Net income is positive at $X"


@dataclass(frozen=True)
class PiotroskiInputs:
    """All raw fundamentals needed to compute a Piotroski F-Score.

    Latest- and prior-period values for each of the inputs feed the nine
    criteria. Any field may be ``None`` if the provider didn't return the
    underlying line; the engine then awards 0 for that criterion and reports
    "Data unavailable".
    """

    ticker: str
    # latest and prior period values for all the inputs:
    net_income: float | None
    prior_net_income: float | None
    total_assets: float | None
    prior_total_assets: float | None
    operating_cash_flow: float | None
    prior_operating_cash_flow: float | None
    long_term_debt: float | None
    prior_long_term_debt: float | None
    current_assets: float | None
    prior_current_assets: float | None
    current_liabilities: float | None
    prior_current_liabilities: float | None
    diluted_shares: float | None
    prior_diluted_shares: float | None
    gross_profit: float | None
    prior_gross_profit: float | None
    total_revenue: float | None
    prior_total_revenue: float | None


@dataclass(frozen=True)
class PiotroskiOutputs:
    """Final score plus per-criterion breakdown.

    Attributes:
        criteria: The nine :class:`PiotroskiCriterion` rows in their canonical
            (numbered) order — profitability first, then leverage/liquidity,
            then operating efficiency.
        total_score: Sum of the nine 0/1 scores (0-9).
        classification: Bucketed label — "Strong (8-9)", "Neutral (4-7)",
            or "Weak (0-3)".
    """

    criteria: list  # of PiotroskiCriterion, in numbered order
    total_score: int
    classification: str  # "Strong (8-9)", "Neutral (4-7)", "Weak (0-3)"
