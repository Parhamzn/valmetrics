"""Tests for the Earnings Power Value (EPV) engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    python apps/valuation/engine/tests_epv.py

which executes every ``test_*`` function and prints PASS/FAIL for each.
"""

from __future__ import annotations

# NOTE: We must adjust sys.path BEFORE importing anything else, because when
# this file is run directly Python puts ``apps/valuation/engine/`` on sys.path
# first. Our local ``types.py`` / ``types_epv.py`` would otherwise potentially
# shadow stdlib modules. Mirror the trick used in ``tests.py``.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.epv import earnings_power_value  # noqa: E402
from apps.valuation.engine.types_epv import EPVInputs  # noqa: E402


def _make_inputs(**overrides) -> EPVInputs:
    """Build an EPVInputs with the canonical test defaults; override per case."""
    defaults: dict = dict(
        ticker="TEST",
        normalized_ebit=200.0,
        tax_rate=0.21,
        maintenance_capex=40.0,
        depreciation_amortization=50.0,
        wacc=0.08,
        net_debt=300.0,
        shares_outstanding=100.0,
        years_of_history=5,
    )
    defaults.update(overrides)
    return EPVInputs(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_epv_basic() -> None:
    """Hand-computed example.

    normalized_ebit=200, D&A=50, maint_capex=40 -> adjusted_ebit = 210
    nopat = 210 * (1 - 0.21) = 165.90
    EV    = 165.90 / 0.08    = 2073.75
    equity= 2073.75 - 300    = 1773.75
    /shares 100              = 17.7375 ~= 17.74
    """
    out = earnings_power_value(_make_inputs())

    assert abs(out.adjusted_ebit - 210.0) < 1e-9, out.adjusted_ebit
    assert abs(out.nopat - 165.9) < 1e-9, out.nopat
    assert abs(out.enterprise_value - 2073.75) < 1e-9, out.enterprise_value
    assert abs(out.equity_value - 1773.75) < 1e-9, out.equity_value
    assert abs(out.epv_per_share - 17.7375) < 0.01, out.epv_per_share


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_epv_zero_wacc_raises() -> None:
    try:
        earnings_power_value(_make_inputs(wacc=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when wacc <= 0")


def test_epv_negative_wacc_raises() -> None:
    try:
        earnings_power_value(_make_inputs(wacc=-0.01))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when wacc <= 0")


def test_epv_zero_shares_raises() -> None:
    try:
        earnings_power_value(_make_inputs(shares_outstanding=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when shares_outstanding <= 0")


# ---------------------------------------------------------------------------
# Negative equity is a legitimate, non-raising result
# ---------------------------------------------------------------------------


def test_epv_negative_equity() -> None:
    """Huge net debt drives equity negative; engine must NOT raise."""
    out = earnings_power_value(_make_inputs(net_debt=10_000.0))
    # EV is still positive (nopat / wacc), only equity goes negative.
    assert out.enterprise_value > 0, out.enterprise_value
    assert out.equity_value < 0, out.equity_value
    assert out.epv_per_share < 0, out.epv_per_share


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
