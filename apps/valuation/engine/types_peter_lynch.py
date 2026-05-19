"""Input/output dataclasses for the Peter Lynch fair-value model.

Kept separate from ``types.py`` so this file can be authored without colliding
with concurrent edits to the main engine types module. Peter Lynch's heuristic
(canonically stated in *One Up on Wall Street*, ch. 10) is that the P/E ratio
of a fairly priced growth company should roughly equal its earnings growth
rate. The PEGY extension adds dividend yield onto the growth term so that
dividend-paying growers aren't penalized.

Source: Lynch, *One Up on Wall Street* (1989); Investopedia PEG ratio explainer
(https://www.investopedia.com/terms/p/pegratio.asp).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PeterLynchInputs:
    """Inputs for Peter Lynch's PEG/PEGY fair-value approximation.

    Attributes:
        ticker: Display identifier.
        eps: Trailing diluted earnings per share (in reporting currency).
        growth_rate: Expected annualized earnings growth as a *decimal*
            (e.g. 0.15 means 15%/yr). Lynch's heuristic treats the
            growth-as-percent number directly as the "fair" P/E.
        dividend_yield: Trailing dividend yield as a *decimal* (e.g. 0.02 for
            2%). Pass 0 to use the plain "fair P/E = growth" form; any non-zero
            value applies the PEGY extension (Fair P/E = growth + yield).
    """

    ticker: str
    eps: float
    growth_rate: float
    dividend_yield: float


@dataclass(frozen=True)
class PeterLynchOutputs:
    """Computed Lynch fair-value breakdown.

    Attributes:
        fair_pe: The implied "fair" P/E multiple. Equal to
            ``(growth_rate + dividend_yield) * 100`` — i.e. converting the
            combined decimal into a percentage-points number that Lynch
            treats as a P/E ratio.
        fair_value_per_share: ``eps * fair_pe``.
        warning: Human-readable caveat when the formula's assumptions
            break down (hyper-growth, non-positive combined yield, or
            negative EPS). ``None`` when the result is on solid footing.
    """

    fair_pe: float
    fair_value_per_share: float
    warning: str | None
