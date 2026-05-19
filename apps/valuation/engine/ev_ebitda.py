"""EV/EBITDA Multiple valuation — relative-multiples model.

Applies a user-specified target EV/EBITDA multiple to the company's current
EBITDA to derive an implied enterprise value, then subtracts net debt and
divides by shares to get an implied fair value per share. This is the canonical
"if this company traded at peer-group X times EBITDA, what would the stock be
worth?" calculation used in equity research and M&A.

EV/EBITDA is the most widely cited enterprise-value multiple because it is
capital-structure neutral and removes the noise that depreciation policy
introduces into the P/E ratio — but it is meaningless for firms with negative
EBITDA, hence the guard below.

Source: Corporate Finance Institute — "EV/EBITDA"
(https://corporatefinanceinstitute.com/resources/valuation/ev-ebitda/).
"""

from __future__ import annotations

from apps.valuation.engine.types_ev_ebitda import EVEBITDAInputs, EVEBITDAOutputs


# EV/EBITDA = Enterprise Value / EBITDA where EV = market cap + debt − cash.
# Source: CFI EV/EBITDA (https://corporatefinanceinstitute.com/resources/valuation/ev-ebitda/).
def ev_ebitda_valuation(
    inputs: EVEBITDAInputs,
    current_multiple: float | None = None,
) -> EVEBITDAOutputs:
    """Apply a target EV/EBITDA multiple to current EBITDA and bridge to equity.

    Algorithm:
        implied_ev    = ebitda * target_ev_ebitda
        implied_equity = implied_ev - net_debt
        per_share     = implied_equity / shares_outstanding

    Args:
        inputs: model inputs (see :class:`EVEBITDAInputs`).
        current_multiple: optional diagnostic — the firm's *current* trading
            multiple ``(market_cap + net_debt) / ebitda``. Passed through to
            outputs so templates can render "Current: 12.4x / Target: 10.0x".
            The engine cannot compute it itself because it has no access to
            ``market_cap``; the view supplies it.

    Raises:
        ValueError: if ``ebitda <= 0`` (the multiple is meaningless for firms
            without positive EBITDA — typical of distressed names or early-stage
            biotechs; use EV/Sales instead).
        ValueError: if ``shares_outstanding <= 0``.
    """
    if inputs.ebitda <= 0:
        raise ValueError(
            "EV/EBITDA model requires ebitda > 0; "
            f"got ebitda={inputs.ebitda}. "
            "For unprofitable firms, use EV/Sales instead."
        )
    if inputs.shares_outstanding <= 0:
        raise ValueError(
            f"shares_outstanding must be > 0; got {inputs.shares_outstanding}."
        )

    implied_ev = inputs.ebitda * inputs.target_ev_ebitda
    implied_equity = implied_ev - inputs.net_debt
    fair_value_per_share = implied_equity / inputs.shares_outstanding

    return EVEBITDAOutputs(
        implied_enterprise_value=implied_ev,
        implied_equity_value=implied_equity,
        fair_value_per_share=fair_value_per_share,
        current_multiple=current_multiple,
    )
