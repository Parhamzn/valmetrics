"""Earnings Power Value (EPV) — Bruce Greenwald's no-growth valuation.

Values the firm assuming current normalized earnings persist forever with no
growth. Comparing EPV against asset reproduction value tells you how much of
the firm's value comes from franchise/moat; this MVP shows EPV only.

Source: Greenwald et al., *Value Investing*, ch. 6; Corporate Finance Institute
EPV explainer (https://corporatefinanceinstitute.com/resources/valuation/
earnings-power-value-epv/).
"""

from __future__ import annotations

from apps.valuation.engine.types_epv import EPVInputs, EPVOutputs


# TODO: Future addition — implement Greenwald-style asset reproduction value
# (book value adjusted to replacement cost) so we can compare EPV vs reproduction
# value and flag franchise/moat strength. Requires firm-specific adjustments to
# the balance sheet, so it's deferred from the MVP.


def earnings_power_value(inputs: EPVInputs) -> EPVOutputs:
    """Greenwald-style EPV. Returns the no-growth valuation.

    Algorithm:
        adjusted_ebit    = normalized_ebit + D&A - maintenance_capex
        nopat            = adjusted_ebit * (1 - tax_rate)
        enterprise_value = nopat / wacc
        equity_value     = enterprise_value - net_debt
        epv_per_share    = equity_value / shares_outstanding

    Negative ``equity_value`` is allowed (and meaningful: it means the firm's
    normalized earnings power can't service its net debt).

    Source: Greenwald et al., *Value Investing*, ch. 6; CFI EPV explainer.

    Raises:
        ValueError: if ``wacc <= 0`` (perpetuity undefined / negative EV).
        ValueError: if ``shares_outstanding <= 0`` (per-share undefined).
    """
    adjusted_ebit = (
        inputs.normalized_ebit
        + inputs.depreciation_amortization
        - inputs.maintenance_capex
    )
    nopat = adjusted_ebit * (1.0 - inputs.tax_rate)

    if inputs.wacc <= 0:
        raise ValueError(
            f"EPV requires wacc > 0; got wacc={inputs.wacc}."
        )

    enterprise_value = nopat / inputs.wacc
    equity_value = enterprise_value - inputs.net_debt

    if inputs.shares_outstanding <= 0:
        raise ValueError(
            f"shares_outstanding must be > 0; got {inputs.shares_outstanding}."
        )

    epv_per_share = equity_value / inputs.shares_outstanding

    return EPVOutputs(
        adjusted_ebit=adjusted_ebit,
        nopat=nopat,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        epv_per_share=epv_per_share,
    )
