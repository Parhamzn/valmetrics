"""Input/output dataclasses for the EV/EBITDA Multiple valuation model.

Kept in its own module (parallel to ``types_epv.py`` / ``types_excess_return.py``)
so this multiples model can be authored without touching the shared ``types.py``.

The model is a *relative* valuation: apply a target EV/EBITDA multiple — usually
sourced from a peer group or industry median — to the company's current EBITDA,
derive an implied enterprise value, then bridge to equity via net debt.

Source: Corporate Finance Institute — "EV/EBITDA"
(https://corporatefinanceinstitute.com/resources/valuation/ev-ebitda/);
Damodaran, *Investment Valuation* (Wiley) on enterprise-value multiples.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EVEBITDAInputs:
    """Inputs for the EV/EBITDA multiple valuation.

    Attributes:
        ticker: Display identifier.
        ebitda: Current (trailing) EBITDA in the firm's reporting currency.
            EBITDA <= 0 makes the model meaningless and the engine raises.
        target_ev_ebitda: User-supplied target multiple — the "what if this
            traded at peer-group X" question.
        net_debt: Total debt minus cash & equivalents. Bridges from
            implied enterprise value to implied equity value.
        shares_outstanding: Diluted share count for the per-share figure.
    """

    ticker: str
    ebitda: float
    target_ev_ebitda: float
    net_debt: float
    shares_outstanding: float


@dataclass(frozen=True)
class EVEBITDAOutputs:
    """Computed EV/EBITDA multiple valuation breakdown.

    Attributes:
        implied_enterprise_value: ``ebitda * target_ev_ebitda``.
        implied_equity_value: ``implied_enterprise_value - net_debt``. May be
            negative for distressed firms with heavy net debt.
        fair_value_per_share: ``implied_equity_value / shares_outstanding``.
        current_multiple: Diagnostic — the company's *current* trading
            EV/EBITDA, computed as ``(market_cap + net_debt) / ebitda``.
            ``None`` if market cap isn't available. Filled in by the view
            (the engine has no access to ``market_cap``).
    """

    implied_enterprise_value: float
    implied_equity_value: float
    fair_value_per_share: float
    current_multiple: float | None = None
