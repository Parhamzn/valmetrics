"""Valuation engine: pure-Python canonical valuation models.

This package contains the core financial valuation primitives used by the
DCF Clone project. The implementations are intentionally stdlib-only so they
can be exercised in notebooks, scripts, and unit tests without Django, pandas,
yfinance, or any network dependency.

Entrypoints:
    - dcf_perpetual_growth: Discounted cash flow with perpetual terminal growth.
    - simple_ddm:           Gordon growth dividend discount model.
    - two_stage_ddm:        Two-stage dividend discount model.
    - capm_cost_of_equity:  CAPM cost-of-equity calculation.
    - wacc:                 Weighted-average cost of capital.
"""

from apps.valuation.engine.capm import capm_cost_of_equity
from apps.valuation.engine.dcf import dcf_perpetual_growth
from apps.valuation.engine.ddm import simple_ddm, two_stage_ddm
from apps.valuation.engine.types import (
    CAPMInputs,
    CAPMOutputs,
    DCFInputs,
    DCFOutputs,
    ProjectionYear,
    SimpleDDMInputs,
    SimpleDDMOutputs,
    TwoStageDDMInputs,
    TwoStageDDMOutputs,
    WACCInputs,
    WACCOutputs,
)
from apps.valuation.engine.wacc import wacc

__all__ = [
    "capm_cost_of_equity",
    "dcf_perpetual_growth",
    "simple_ddm",
    "two_stage_ddm",
    "wacc",
    "CAPMInputs",
    "CAPMOutputs",
    "DCFInputs",
    "DCFOutputs",
    "ProjectionYear",
    "SimpleDDMInputs",
    "SimpleDDMOutputs",
    "TwoStageDDMInputs",
    "TwoStageDDMOutputs",
    "WACCInputs",
    "WACCOutputs",
]
