"""Tests for the valuation engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    python apps/valuation/engine/tests.py

which executes every ``test_*`` function and prints PASS/FAIL for each.
"""

from __future__ import annotations

# NOTE: We must adjust sys.path BEFORE importing anything else, because when
# this file is run directly Python puts ``apps/valuation/engine/`` on sys.path
# first. Our local ``types.py`` would then shadow the stdlib ``types`` module,
# breaking ``import traceback`` (and many others). We fix this by (a) removing
# the script's directory from sys.path and (b) prepending the repo root so
# ``apps.valuation.engine.*`` imports resolve as a package.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
# Drop any sys.path entries pointing at the engine dir (the script-dir entry
# Python adds when invoked as ``python path/to/tests.py``).
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine import (  # noqa: E402
    CAPMInputs,
    DCFInputs,
    SimpleDDMInputs,
    TwoStageDDMInputs,
    WACCInputs,
    capm_cost_of_equity,
    dcf_perpetual_growth,
    simple_ddm,
    two_stage_ddm,
    wacc,
)


# ---------------------------------------------------------------------------
# CAPM
# ---------------------------------------------------------------------------


def test_capm_basic() -> None:
    out = capm_cost_of_equity(
        CAPMInputs(risk_free_rate=0.04, beta=1.2, equity_risk_premium=0.05)
    )
    # 0.04 + 1.2 * 0.05 = 0.10
    assert abs(out.cost_of_equity - 0.10) < 1e-9, out.cost_of_equity


# ---------------------------------------------------------------------------
# WACC
# ---------------------------------------------------------------------------


def test_wacc_basic() -> None:
    out = wacc(
        WACCInputs(
            cost_of_equity=0.10,
            cost_of_debt=0.05,
            tax_rate=0.21,
            market_value_equity=800.0,
            market_value_debt=200.0,
        )
    )
    # 0.8 * 0.10 + 0.2 * 0.05 * (1 - 0.21) = 0.08 + 0.0079 = 0.0879
    assert abs(out.wacc - 0.0879) < 1e-6, out.wacc
    assert abs(out.equity_weight - 0.8) < 1e-9
    assert abs(out.debt_weight - 0.2) < 1e-9


def test_wacc_invalid_capital() -> None:
    try:
        wacc(
            WACCInputs(
                cost_of_equity=0.10,
                cost_of_debt=0.05,
                tax_rate=0.21,
                market_value_equity=0.0,
                market_value_debt=0.0,
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError for non-positive total capital")


# ---------------------------------------------------------------------------
# Simple DDM
# ---------------------------------------------------------------------------


def test_simple_ddm_basic() -> None:
    out = simple_ddm(
        SimpleDDMInputs(current_dividend=2.0, growth_rate=0.03, required_return=0.08)
    )
    # D1 = 2 * 1.03 = 2.06; FV = 2.06 / (0.08 - 0.03) = 2.06 / 0.05 = 41.2
    assert abs(out.fair_value - 41.2) < 1e-6, out.fair_value


def test_simple_ddm_invalid() -> None:
    try:
        simple_ddm(
            SimpleDDMInputs(
                current_dividend=2.0, growth_rate=0.10, required_return=0.08
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError when growth_rate >= required_return")


# ---------------------------------------------------------------------------
# Two-stage DDM
# ---------------------------------------------------------------------------


def test_two_stage_ddm() -> None:
    # Hand-computed small example.
    #
    # D0 = 1.00, g1 = 10%, N = 3, g_term = 4%, r = 10%
    #
    # Phase 1 dividends and PVs (r = 0.10):
    #   D1 = 1.10        PV1 = 1.10 / 1.10    = 1.0
    #   D2 = 1.21        PV2 = 1.21 / 1.21    = 1.0
    #   D3 = 1.331       PV3 = 1.331 / 1.331  = 1.0
    #   Sum PV dividends = 3.0
    #
    # D4 = D3 * (1 + g_term) = 1.331 * 1.04 = 1.38424
    # TV at end of year 3 = D4 / (r - g_term) = 1.38424 / 0.06 = 23.0706666...
    # PV(TV) = 23.0706666... / 1.331 = 17.33333...
    #
    # Fair value = 3.0 + 17.33333... = 20.33333...
    out = two_stage_ddm(
        TwoStageDDMInputs(
            current_dividend=1.0,
            high_growth_rate=0.10,
            high_growth_years=3,
            terminal_growth_rate=0.04,
            required_return=0.10,
        )
    )

    # Phase-1 PVs: each should be exactly 1.0 because g1 == r.
    assert len(out.projections) == 3
    for (year, dividend, pv), expected_div in zip(
        out.projections, [1.10, 1.21, 1.331]
    ):
        assert abs(dividend - expected_div) < 1e-9, (year, dividend, expected_div)
        assert abs(pv - 1.0) < 1e-9, (year, pv)

    expected_tv = 1.38424 / 0.06
    assert abs(out.terminal_value - expected_tv) < 1e-6, out.terminal_value

    expected_pv_tv = expected_tv / (1.10 ** 3)
    assert abs(out.pv_terminal_value - expected_pv_tv) < 1e-6, out.pv_terminal_value

    expected_fv = 3.0 + expected_pv_tv
    assert abs(out.fair_value - expected_fv) < 1e-6, out.fair_value


def test_two_stage_ddm_invalid() -> None:
    try:
        two_stage_ddm(
            TwoStageDDMInputs(
                current_dividend=1.0,
                high_growth_rate=0.10,
                high_growth_years=3,
                terminal_growth_rate=0.12,
                required_return=0.10,
            )
        )
    except ValueError:
        return
    raise AssertionError(
        "Expected ValueError when terminal_growth_rate >= required_return"
    )


# ---------------------------------------------------------------------------
# DCF
# ---------------------------------------------------------------------------


def test_dcf_perpetual_growth_basic() -> None:
    """Concrete DCF example with hand-computed expected enterprise value.

    Inputs:
        base_revenue = 1000, base_fcff = 100 (base_fcff not used in math here),
        revenue_growth = 5%, ebit_margin = 20%, tax = 25%, reinvest = 30%,
        terminal_growth = 2%, wacc = 8%, net_debt = 200, shares = 100, years = 5.

    Per-year FCFF (all flow at 5% from year 1's 110.25 because margins/tax/
    reinvest are constant):

        Y1  rev=1050.0000   ebit=210.0000   nopat=157.5000   fcff=110.250000
        Y2  rev=1102.5000   ebit=220.5000   nopat=165.3750   fcff=115.762500
        Y3  rev=1157.6250   ebit=231.5250   nopat=173.6438   fcff=121.550625
        Y4  rev=1215.5063   ebit=243.1013   nopat=182.3259   fcff=127.628156
        Y5  rev=1276.2816   ebit=255.2563   nopat=191.4422   fcff=134.009564

    Discounted at 8%:

        PV1 = 110.250000 / 1.08              = 102.083333
        PV2 = 115.762500 / 1.1664            =  99.247685
        PV3 = 121.550625 / 1.259712          =  96.490828
        PV4 = 127.628156 / 1.36048896        =  93.810862
        PV5 = 134.009564 / 1.4693280768      =  91.205838
        Sum PV FCFF                          = 482.838546

    Terminal value:
        FCFF_6 = 134.009564 * 1.02           = 136.689756
        TV     = 136.689756 / (0.08 - 0.02)  = 2278.162588
        PV(TV) = 2278.162588 / 1.4693280768  = 1550.481244

    Enterprise value = 482.838546 + 1550.481244 = 2033.319790
    Equity value     = 2033.319790 - 200       = 1833.319790
    Per-share value  = 1833.319790 / 100       =   18.333198
    """
    out = dcf_perpetual_growth(
        DCFInputs(
            ticker="TEST",
            base_revenue=1000.0,
            base_fcff=100.0,
            projection_years=5,
            revenue_growth_rate=0.05,
            ebit_margin=0.20,
            tax_rate=0.25,
            reinvestment_rate=0.30,
            terminal_growth=0.02,
            wacc=0.08,
            net_debt=200.0,
            shares_outstanding=100.0,
        )
    )

    assert len(out.projections) == 5
    # Spot-check year 1 line items.
    y1 = out.projections[0]
    assert y1.year == 1
    assert abs(y1.revenue - 1050.0) < 1e-9
    assert abs(y1.ebit - 210.0) < 1e-9
    assert abs(y1.tax_paid - 52.5) < 1e-9
    assert abs(y1.nopat - 157.5) < 1e-9
    assert abs(y1.fcff - 110.25) < 1e-9

    # Hand-computed expected values.
    expected_ev = 2033.319790
    expected_equity = expected_ev - 200.0
    expected_per_share = expected_equity / 100.0

    assert abs(out.enterprise_value - expected_ev) < 1.0, out.enterprise_value
    assert abs(out.equity_value - expected_equity) < 1.0, out.equity_value
    assert abs(out.fair_value_per_share - expected_per_share) < 0.01, (
        out.fair_value_per_share
    )

    # Sanity: terminal value should dominate enterprise value here.
    assert out.pv_terminal_value > 0
    assert out.terminal_value > out.pv_terminal_value


def test_dcf_terminal_growth_too_high() -> None:
    try:
        dcf_perpetual_growth(
            DCFInputs(
                ticker="BAD",
                base_revenue=1000.0,
                base_fcff=100.0,
                projection_years=5,
                revenue_growth_rate=0.05,
                ebit_margin=0.20,
                tax_rate=0.25,
                reinvestment_rate=0.30,
                terminal_growth=0.10,  # >= wacc
                wacc=0.08,
                net_debt=0.0,
                shares_outstanding=100.0,
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError when wacc <= terminal_growth")


def test_dcf_zero_shares_raises() -> None:
    try:
        dcf_perpetual_growth(
            DCFInputs(
                ticker="BAD",
                base_revenue=1000.0,
                base_fcff=100.0,
                projection_years=5,
                revenue_growth_rate=0.05,
                ebit_margin=0.20,
                tax_rate=0.25,
                reinvestment_rate=0.30,
                terminal_growth=0.02,
                wacc=0.08,
                net_debt=0.0,
                shares_outstanding=0.0,
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError when shares_outstanding <= 0")


# ---------------------------------------------------------------------------
# Script entrypoint: run every test_* function, print PASS/FAIL.
# ---------------------------------------------------------------------------


def _run_all() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}")
            traceback.print_exc()
        else:
            print(f"PASS {name}")
    print()
    print(f"{len(tests) - failures}/{len(tests)} passed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_all())
