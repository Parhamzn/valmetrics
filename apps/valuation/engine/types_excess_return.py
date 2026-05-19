"""Input/output dataclasses for the Simple Excess Return model.

Kept in a dedicated module (rather than ``types.py``) so the model can be
developed and tested independently while other agents extend the main
``types.py`` for DDM/EPV/etc.

Reference: Damodaran, "Valuing Financial Service Firms" (NYU Stern),
https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/finfirm09.pdf
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimpleExcessReturnInputs:
    """Inputs for the constant-growth Simple Excess Return model.

    Attributes:
        ticker: Identifier for the security (display only).
        book_value_per_share: Current equity book value per share (BV0).
        return_on_equity: Sustainable ROE (decimal, e.g., 0.12 = 12%).
        cost_of_equity: Required return on equity (Ke); decimal.
        growth_rate: Perpetual growth rate (g); decimal. Must be < Ke.
    """

    ticker: str
    book_value_per_share: float
    return_on_equity: float       # decimal, e.g., 0.12
    cost_of_equity: float         # Ke; decimal
    growth_rate: float            # g; decimal; must be < Ke


@dataclass(frozen=True)
class SimpleExcessReturnOutputs:
    """Outputs of the constant-growth Simple Excess Return model."""

    excess_return_per_share: float    # (ROE − Ke) × BV
    pv_perpetual_excess: float        # excess × (1+g) / (Ke − g)
    fair_value_per_share: float       # BV + pv_perpetual_excess
