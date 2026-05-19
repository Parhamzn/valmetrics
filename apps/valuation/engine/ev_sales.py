"""EV/Sales (EV/Revenue) Multiple valuation — relative-multiples model.

Applies a user-specified target EV/Sales multiple to the company's current
revenue, derives an implied enterprise value, then bridges to equity. This is
the workhorse multiple for valuing companies whose EBITDA or earnings are
negative or near zero — early-stage tech, SaaS, biotech — because revenue is
almost always positive even when EBITDA isn't.

Unlike EV/EBITDA, this engine does NOT guard against negative EBITDA. That's
the entire point: it works for unprofitable companies. It does guard against
``revenue <= 0`` though, which is possible for pre-commercial biotechs.

Source: Damodaran, *Investment Valuation* ch. 20 "Revenue Multiples"
(https://pages.stern.nyu.edu/~adamodar/pdfiles/val3ed/c20.pdf).
"""

from __future__ import annotations

from apps.valuation.engine.types_ev_sales import EVSalesInputs, EVSalesOutputs


# EV/Sales = Enterprise Value / Revenue; common for unprofitable / pre-profit firms.
# Source: Damodaran, Investment Valuation ch. 20 (Revenue Multiples).
def ev_sales_valuation(
    inputs: EVSalesInputs,
    current_multiple: float | None = None,
) -> EVSalesOutputs:
    """Apply a target EV/Sales multiple to current revenue and bridge to equity.

    Algorithm:
        implied_ev    = revenue * target_ev_sales
        implied_equity = implied_ev - net_debt
        per_share     = implied_equity / shares_outstanding

    Args:
        inputs: model inputs (see :class:`EVSalesInputs`).
        current_multiple: optional diagnostic — the firm's *current* trading
            multiple ``(market_cap + net_debt) / revenue``. Passed through to
            outputs so templates can render "Current: 3.2x / Target: 5.0x".
            The view supplies it (engine has no access to ``market_cap``).

    Raises:
        ValueError: if ``revenue <= 0`` (e.g. pre-revenue biotech — use rNPV
            or a milestone-driven model instead).
        ValueError: if ``shares_outstanding <= 0``.
    """
    if inputs.revenue <= 0:
        raise ValueError(
            "EV/Sales model requires revenue > 0; "
            f"got revenue={inputs.revenue}. "
            "For pre-revenue firms, use an rNPV / milestone model."
        )
    if inputs.shares_outstanding <= 0:
        raise ValueError(
            f"shares_outstanding must be > 0; got {inputs.shares_outstanding}."
        )

    implied_ev = inputs.revenue * inputs.target_ev_sales
    implied_equity = implied_ev - inputs.net_debt
    fair_value_per_share = implied_equity / inputs.shares_outstanding

    return EVSalesOutputs(
        implied_enterprise_value=implied_ev,
        implied_equity_value=implied_equity,
        fair_value_per_share=fair_value_per_share,
        current_multiple=current_multiple,
    )
