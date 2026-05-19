"""Tests for the EV/EBITDA Multiple valuation engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable
directly as a script::

    python apps/valuation/engine/tests_ev_ebitda.py
"""

from __future__ import annotations

# Adjust sys.path BEFORE importing anything else so this script can be run
# directly without engine/ shadowing stdlib (mirrors tests_epv.py).
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.ev_ebitda import ev_ebitda_valuation  # noqa: E402
from apps.valuation.engine.types_ev_ebitda import EVEBITDAInputs  # noqa: E402


def _make_inputs(**overrides) -> EVEBITDAInputs:
    """Build EVEBITDAInputs with canonical test defaults; override per case."""
    defaults: dict = dict(
        ticker="TEST",
        ebitda=200.0,
        target_ev_ebitda=12.0,
        net_debt=300.0,
        shares_outstanding=100.0,
    )
    defaults.update(overrides)
    return EVEBITDAInputs(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_ev_ebitda_basic() -> None:
    """Hand-computed example.

    ebitda=200, target=12.0 -> implied EV = 2400
    less net_debt 300                  = 2100  equity
    / shares 100                       = 21.00
    """
    out = ev_ebitda_valuation(_make_inputs())

    assert abs(out.implied_enterprise_value - 2400.0) < 1e-9, out.implied_enterprise_value
    assert abs(out.implied_equity_value - 2100.0) < 1e-9, out.implied_equity_value
    assert abs(out.fair_value_per_share - 21.0) < 1e-9, out.fair_value_per_share
    assert out.current_multiple is None


def test_ev_ebitda_passes_through_current_multiple() -> None:
    """The engine should echo back the diagnostic current_multiple unchanged."""
    out = ev_ebitda_valuation(_make_inputs(), current_multiple=15.5)
    assert out.current_multiple == 15.5, out.current_multiple


def test_ev_ebitda_zero_net_debt() -> None:
    """With no net debt, equity == EV."""
    out = ev_ebitda_valuation(_make_inputs(net_debt=0.0))
    assert abs(out.implied_equity_value - out.implied_enterprise_value) < 1e-9


def test_ev_ebitda_negative_equity_allowed() -> None:
    """Heavy net debt can drive equity negative — engine must NOT raise."""
    out = ev_ebitda_valuation(_make_inputs(net_debt=10_000.0))
    assert out.implied_enterprise_value > 0, out.implied_enterprise_value
    assert out.implied_equity_value < 0, out.implied_equity_value
    assert out.fair_value_per_share < 0, out.fair_value_per_share


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_ev_ebitda_zero_ebitda_raises() -> None:
    try:
        ev_ebitda_valuation(_make_inputs(ebitda=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when ebitda <= 0")


def test_ev_ebitda_negative_ebitda_raises() -> None:
    try:
        ev_ebitda_valuation(_make_inputs(ebitda=-50.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when ebitda <= 0")


def test_ev_ebitda_zero_shares_raises() -> None:
    try:
        ev_ebitda_valuation(_make_inputs(shares_outstanding=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when shares_outstanding <= 0")


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
