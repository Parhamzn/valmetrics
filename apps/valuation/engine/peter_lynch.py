"""Peter Lynch fair-value model (PEG / PEGY heuristic).

Lynch's rule of thumb (*One Up on Wall Street*, 1989) is that the P/E of a
fairly priced growth company should roughly equal its earnings growth rate
in percentage points. The PEGY extension adds dividend yield so that
dividend-paying growers aren't penalized:

    Fair Value = EPS * (growth_rate_pct + dividend_yield_pct)

Best suited to "growth at a reasonable price" names with predictable growth in
the 5-20% range; it breaks down for hyper-growth (>25%) and loss-makers.

Source: Lynch, *One Up on Wall Street*, ch. 10; Investopedia PEG ratio
(https://www.investopedia.com/terms/p/pegratio.asp).
"""

from __future__ import annotations

from apps.valuation.engine.types_peter_lynch import (
    PeterLynchInputs,
    PeterLynchOutputs,
)


# Hyper-growth threshold above which Lynch's formula stops being predictive
# (the implied P/E becomes implausible for any sustainable business).
_HYPER_GROWTH_THRESHOLD = 0.25


# Source: Lynch, "One Up on Wall Street" (1989); Investopedia PEG explainer.
def peter_lynch_fair_value(inputs: PeterLynchInputs) -> PeterLynchOutputs:
    """Compute the Lynch / PEGY fair value for ``inputs``.

    Algorithm:
        combined     = growth_rate + dividend_yield   (both decimals)
        fair_pe      = combined * 100                  (decimal -> percent points)
        fair_value   = eps * fair_pe

    The function never raises: it returns whatever the math gives and surfaces
    domain caveats via the ``warning`` field. That lets callers (views, tests)
    decide whether to show or hide the number.
    """
    combined = inputs.growth_rate + inputs.dividend_yield
    fair_pe = combined * 100.0
    fair_value = inputs.eps * fair_pe

    warning: str | None = None

    # Order matters: surface the most severe issue first. EPS being non-positive
    # is the most "the formula doesn't apply at all" case, so check it first.
    if inputs.eps <= 0:
        warning = (
            "Loss-making company; Lynch's formula requires positive earnings."
        )
    elif combined <= 0:
        warning = (
            "Negative growth+yield makes Lynch's formula inapplicable."
        )
    elif combined > _HYPER_GROWTH_THRESHOLD:
        warning = (
            "Lynch's formula is unreliable for hyper-growth (>25%); "
            f"P/E ratio of {fair_pe:.1f} is implausible."
        )

    return PeterLynchOutputs(
        fair_pe=fair_pe,
        fair_value_per_share=fair_value,
        warning=warning,
    )
