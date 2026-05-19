"""Tests for the EV/Sales Multiple valuation engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable
directly as a script::

    python apps/valuation/engine/tests_ev_sales.py
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

from apps.valuation.engine.ev_sales import ev_sales_valuation  # noqa: E402
from apps.valuation.engine.types_ev_sales import EVSalesInputs  # noqa: E402


def _make_inputs(**overrides) -> EVSalesInputs:
    defaults: dict = dict(
        ticker="TEST",
        revenue=1000.0,
        target_ev_sales=3.0,
        net_debt=500.0,
        shares_outstanding=100.0,
    )
    defaults.update(overrides)
    return EVSalesInputs(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_ev_sales_basic() -> None:
    """Hand-computed example.

    revenue=1000, target=3.0 -> implied EV = 3000
    less net_debt 500                  = 2500 equity
    / shares 100                       = 25.00
    """
    out = ev_sales_valuation(_make_inputs())

    assert abs(out.implied_enterprise_value - 3000.0) < 1e-9, out.implied_enterprise_value
    assert abs(out.implied_equity_value - 2500.0) < 1e-9, out.implied_equity_value
    assert abs(out.fair_value_per_share - 25.0) < 1e-9, out.fair_value_per_share
    assert out.current_multiple is None


def test_ev_sales_passes_through_current_multiple() -> None:
    out = ev_sales_valuation(_make_inputs(), current_multiple=4.25)
    assert out.current_multiple == 4.25, out.current_multiple


def test_ev_sales_zero_net_debt() -> None:
    out = ev_sales_valuation(_make_inputs(net_debt=0.0))
    assert abs(out.implied_equity_value - out.implied_enterprise_value) < 1e-9


def test_ev_sales_negative_equity_allowed() -> None:
    """Heavy net debt can drive equity negative — engine must NOT raise."""
    out = ev_sales_valuation(_make_inputs(net_debt=50_000.0))
    assert out.implied_enterprise_value > 0
    assert out.implied_equity_value < 0
    assert out.fair_value_per_share < 0


def test_ev_sales_handles_negative_ebitda_scenario() -> None:
    """EV/Sales doesn't care about EBITDA — only revenue and shares matter.

    A loss-making SaaS firm with revenue=500, target=10x (typical SaaS
    multiple), no debt, 50 shares should compute cleanly to $100/share.
    """
    out = ev_sales_valuation(
        _make_inputs(revenue=500.0, target_ev_sales=10.0, net_debt=0.0, shares_outstanding=50.0)
    )
    assert abs(out.implied_enterprise_value - 5000.0) < 1e-9
    assert abs(out.fair_value_per_share - 100.0) < 1e-9


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_ev_sales_zero_revenue_raises() -> None:
    try:
        ev_sales_valuation(_make_inputs(revenue=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when revenue <= 0")


def test_ev_sales_negative_revenue_raises() -> None:
    # Almost never happens in practice (reversed sales / refunds-heavy firms),
    # but we should still reject it.
    try:
        ev_sales_valuation(_make_inputs(revenue=-1.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when revenue <= 0")


def test_ev_sales_zero_shares_raises() -> None:
    try:
        ev_sales_valuation(_make_inputs(shares_outstanding=0.0))
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
