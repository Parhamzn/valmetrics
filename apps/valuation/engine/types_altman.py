"""Input/output dataclasses for the Altman Z-Score model.

Kept separate from ``types.py`` so this file can be authored without colliding
with concurrent edits to the main engine types module. The original Altman
Z-Score is a weighted combination of five ratios calibrated to predict
bankruptcy among public manufacturers within two years.

Source: Altman, E.I., "Financial Ratios, Discriminant Analysis and the
Prediction of Corporate Bankruptcy", Journal of Finance, 1968; Investopedia
"Altman Z-Score" entry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AltmanInputs:
    """Raw fundamentals feeding the five Altman ratios.

    Attributes:
        ticker: Display identifier.
        working_capital: Current assets - current liabilities (provider may
            return it directly; otherwise computed from siblings).
        total_assets: Total assets (denominator for A, B, C, E).
        retained_earnings: Cumulative retained earnings on the balance sheet.
        ebit: Earnings before interest and taxes (or operating income proxy).
        market_value_equity: Market capitalization (price * shares).
        total_liabilities: Sum of all liabilities (Altman uses book value of
            total liabilities as the denominator of D).
        revenue: Trailing total revenue / sales.
    """

    ticker: str
    working_capital: float | None
    total_assets: float | None
    retained_earnings: float | None
    ebit: float | None
    market_value_equity: float | None
    total_liabilities: float | None
    revenue: float | None


@dataclass(frozen=True)
class AltmanComponent:
    """One of the five (A-E) Z-score components.

    Attributes:
        name: The ratio's human-readable description, e.g.
            "Working capital / Total assets".
        coefficient: Altman's weighting — 1.2, 1.4, 3.3, 0.6, or 1.0.
        ratio: The computed ratio (None if any input was missing or the
            denominator was zero).
        weighted: ``coefficient * ratio`` (None when ratio is None — the
            engine treats this as 0 contribution to the total z_score).
    """

    name: str   # e.g., "Working capital / Total assets"
    coefficient: float    # 1.2, 1.4, 3.3, 0.6, 1.0
    ratio: float | None
    weighted: float | None   # coefficient * ratio


@dataclass(frozen=True)
class AltmanOutputs:
    """Final Z-score plus per-component breakdown.

    Attributes:
        components: The five :class:`AltmanComponent` rows in canonical order
            A, B, C, D, E.
        z_score: Sum of all non-None weighted contributions. Missing
            components contribute 0 (and are flagged in ``warning``).
        zone: "Safe" (z > 2.99), "Grey" (1.81 <= z <= 2.99), or "Distress"
            (z < 1.81).
        warning: Comma-separated list of missing-input fields if any, else
            None. Lets the UI render a caveat banner.
    """

    components: list  # of AltmanComponent in order A, B, C, D, E
    z_score: float
    zone: str         # "Safe", "Grey", "Distress"
    warning: str | None   # if any input was missing
