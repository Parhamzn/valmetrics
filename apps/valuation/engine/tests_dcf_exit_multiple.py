"""Tests for the DCF — Exit Multiple engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    .venv/bin/python apps/valuation/engine/tests_dcf_exit_multiple.py
"""

from __future__ import annotations

# Path-juggling matches the pattern used by tests_epv.py / tests_excess_return.py:
# running this file directly puts ``apps/valuation/engine/`` on sys.path[0],
# which could shadow stdlib modules via our local ``types_*.py`` siblings.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.dcf_exit_multiple import dcf_exit_multiple  # noqa: E402
from apps.valuation.engine.types_dcf_exit_multiple import (  # noqa: E402
    DCFExitMultipleInputs,
)


def _make_inputs(**overrides) -> DCFExitMultipleInputs:
    """Canonical test inputs; tests override specific fields per case."""
    defaults: dict = dict(
        ticker="TEST",
        base_revenue=1000.0,
        base_ebitda=250.0,
        projection_years=3,
        revenue_growth_rate=0.10,
        ebit_margin=0.20,
        ebitda_margin=0.25,
        tax_rate=0.25,
        reinvestment_rate=0.30,
        wacc=0.10,
        exit_ev_ebitda=10.0,
        net_debt=200.0,
        shares_outstanding=100.0,
    )
    defaults.update(overrides)
    return DCFExitMultipleInputs(**defaults)


# ---------------------------------------------------------------------------
# Happy path — hand-computed example
# ---------------------------------------------------------------------------


def test_dcf_exit_multiple_basic() -> None:
    """Hand-computed reference (also reproduced by a Python one-liner).

    base_revenue=1000, growth=10%, ebit_m=20%, ebitda_m=25%, tax=25%,
    reinvestment=30%, wacc=10%, exit_ev_ebitda=10, N=3, net_debt=200,
    shares=100:

        Year 1: rev=1100, ebit=220, ebitda=275, fcff=115.50, pv_fcff=105.00
        Year 2: rev=1210, ebit=242, ebitda=302.50, fcff=127.05, pv_fcff=105.00
        Year 3: rev=1331, ebit=266.2, ebitda=332.75, fcff=139.755, pv_fcff=105.00
        SumPV          = 315.00
        TerminalEBITDA = 332.75
        TV             = 332.75 * 10 = 3327.50
        PV(TV)         = 3327.50 / 1.1^3 = 2500.00
        EV             = 315 + 2500 = 2815.00
        Equity         = 2815 - 200 = 2615.00
        FV / share     = 26.15
        Implied g      = 0.10 - 139.755 / 3327.50 = 0.0580
    """
    out = dcf_exit_multiple(_make_inputs())

    assert len(out.projections) == 3
    assert abs(out.projections[0].revenue - 1100.0) < 1e-6
    assert abs(out.projections[2].ebitda - 332.75) < 1e-6
    assert abs(out.projections[2].fcff - 139.755) < 1e-6
    # PV(FCFF) is constant by construction (growth = wacc here).
    for p in out.projections:
        assert abs(p.pv_fcff - 105.0) < 1e-6, p.pv_fcff

    assert abs(out.terminal_ebitda - 332.75) < 1e-6
    assert abs(out.terminal_value - 3327.5) < 1e-6
    assert abs(out.pv_terminal_value - 2500.0) < 1e-6
    assert abs(out.enterprise_value - 2815.0) < 1e-6
    assert abs(out.equity_value - 2615.0) < 1e-6
    assert abs(out.fair_value_per_share - 26.15) < 1e-6
    assert abs(out.implied_terminal_growth - 0.0580) < 1e-4


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_zero_multiple_raises() -> None:
    try:
        dcf_exit_multiple(_make_inputs(exit_ev_ebitda=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when exit_ev_ebitda <= 0")


def test_negative_multiple_raises() -> None:
    try:
        dcf_exit_multiple(_make_inputs(exit_ev_ebitda=-5.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when exit_ev_ebitda <= 0")


def test_zero_shares_raises() -> None:
    try:
        dcf_exit_multiple(_make_inputs(shares_outstanding=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when shares_outstanding <= 0")


# ---------------------------------------------------------------------------
# Behavioral checks
# ---------------------------------------------------------------------------


def test_higher_multiple_yields_higher_value() -> None:
    """Doubling the exit multiple should strictly raise per-share fair value."""
    low = dcf_exit_multiple(_make_inputs(exit_ev_ebitda=8.0))
    high = dcf_exit_multiple(_make_inputs(exit_ev_ebitda=16.0))
    assert high.fair_value_per_share > low.fair_value_per_share
    # TV scales linearly with the multiple; PV(TV) does too.
    assert abs(high.terminal_value / low.terminal_value - 2.0) < 1e-9


def test_implied_growth_diagnostic_within_range() -> None:
    """Implied perpetual growth should be < wacc and a finite real number."""
    out = dcf_exit_multiple(_make_inputs())
    assert out.implied_terminal_growth < _make_inputs().wacc
    # For our canonical inputs it's ~0.058, well below WACC (0.10).
    assert -0.5 < out.implied_terminal_growth < 0.5


# ---------------------------------------------------------------------------
# Script entrypoint
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
