"""Altman Z-Score — bankruptcy-prediction discriminant model.

Edward Altman's original (1968) Z-Score combines five accounting ratios into a
single discriminant value calibrated on a sample of public manufacturers; it
remains the most-cited single-equation bankruptcy predictor in finance:

    Z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E

where the ratios are:
    A = Working capital / Total assets       (liquidity)
    B = Retained earnings / Total assets     (cumulative profitability / age)
    C = EBIT / Total assets                  (operating profitability)
    D = Market value of equity / Total liabilities  (solvency / market view)
    E = Sales / Total assets                 (asset turnover)

Standard zone thresholds:
    Z > 2.99            -> "Safe"      (low bankruptcy probability)
    1.81 <= Z <= 2.99   -> "Grey"      (indeterminate / monitor)
    Z < 1.81            -> "Distress"  (elevated bankruptcy probability)

Source: Altman, E.I., "Financial Ratios, Discriminant Analysis and the
Prediction of Corporate Bankruptcy", Journal of Finance 23(4), 1968, pp. 589-
609; https://www.investopedia.com/terms/a/altman.asp.
"""

from __future__ import annotations

from apps.valuation.engine.types_altman import (
    AltmanComponent,
    AltmanInputs,
    AltmanOutputs,
)


# Altman's original (1968) zone thresholds for the public-manufacturer model.
_SAFE_THRESHOLD = 2.99
_DISTRESS_THRESHOLD = 1.81

# Component definitions, in canonical (A, B, C, D, E) order. Each tuple is
# (descriptive name, coefficient, numerator field, denominator field).
_COMPONENT_SPEC = (
    ("Working capital / Total assets", 1.2, "working_capital", "total_assets"),
    ("Retained earnings / Total assets", 1.4, "retained_earnings", "total_assets"),
    ("EBIT / Total assets", 3.3, "ebit", "total_assets"),
    ("Market value of equity / Total liabilities", 0.6, "market_value_equity", "total_liabilities"),
    ("Sales / Total assets", 1.0, "revenue", "total_assets"),
)


def _zone(z: float) -> str:
    """Classify Z into Altman's three zones."""
    if z > _SAFE_THRESHOLD:
        return "Safe"
    if z < _DISTRESS_THRESHOLD:
        return "Distress"
    return "Grey"


def altman_z_score(inputs: AltmanInputs) -> AltmanOutputs:
    """Compute the original Altman Z and per-component breakdown.

    Missing-data handling: if either the numerator is ``None`` or the
    denominator is ``None``/zero, the component's ratio is set to ``None``,
    its weighted contribution is 0, and the field name is appended to the
    returned ``warning`` string. The Z-score is still computed from the
    remaining components so callers can render *something*; the warning lets
    the UI flag the partial result.

    Source: Altman (1968), Journal of Finance.
    """
    missing: list[str] = []
    components: list[AltmanComponent] = []
    z_score = 0.0

    for name, coef, num_field, den_field in _COMPONENT_SPEC:
        numerator = getattr(inputs, num_field)
        denominator = getattr(inputs, den_field)

        if numerator is None:
            missing.append(num_field)
        if denominator is None:
            missing.append(den_field)

        if (
            numerator is None
            or denominator is None
            or denominator == 0
        ):
            components.append(AltmanComponent(
                name=name, coefficient=coef, ratio=None, weighted=None,
            ))
            continue

        ratio = numerator / denominator
        weighted = coef * ratio
        z_score += weighted
        components.append(AltmanComponent(
            name=name, coefficient=coef, ratio=ratio, weighted=weighted,
        ))

    # De-duplicate while preserving order so the warning reads cleanly.
    seen: set[str] = set()
    deduped: list[str] = []
    for f in missing:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    warning = (
        f"Missing inputs (treated as 0 contribution): {', '.join(deduped)}"
        if deduped else None
    )

    return AltmanOutputs(
        components=components,
        z_score=z_score,
        zone=_zone(z_score),
        warning=warning,
    )
