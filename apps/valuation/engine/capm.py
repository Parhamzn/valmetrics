"""Capital Asset Pricing Model (CAPM) — cost of equity.

Ke = Rf + beta * ERP
"""

from __future__ import annotations

from apps.valuation.engine.types import CAPMInputs, CAPMOutputs


def capm_cost_of_equity(inputs: CAPMInputs) -> CAPMOutputs:
    """Return the CAPM cost of equity for the given inputs."""
    ke = inputs.risk_free_rate + inputs.beta * inputs.equity_risk_premium
    return CAPMOutputs(cost_of_equity=ke)
