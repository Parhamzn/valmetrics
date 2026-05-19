"""Tests for the Discounted Future Market Cap engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    .venv/bin/python apps/valuation/engine/tests_discounted_future_mcap.py
"""

from __future__ import annotations

# Path-juggling matches the pattern used by sibling test modules in this
# folder: running directly puts the engine dir on sys.path[0] which could
# shadow stdlib via our local types_*.py siblings.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.discounted_future_mcap import (  # noqa: E402
    discounted_future_mcap,
)
from apps.valuation.engine.types_discounted_future_mcap import (  # noqa: E402
    DFMCInputs,
)


def _make_inputs(**overrides) -> DFMCInputs:
    """Canonical test inputs."""
    defaults: dict = dict(
        ticker="TEST",
        base_net_income=100.0,
        projection_years=5,
        net_income_growth_rate=0.10,
        terminal_pe=15.0,
        discount_rate=0.08,
        shares_outstanding=10.0,
    )
    defaults.update(overrides)
    return DFMCInputs(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_dfmc_basic() -> None:
    """Hand-computed example.

    base_ni=100, g=10%, N=5, terminal_pe=15, discount=8%, shares=10:

        ni_5         = 100 * 1.10^5 = 161.051
        future_mc    = 161.051 * 15 = 2415.765
        (1+r)^N      = 1.08^5       = 1.469328...
        pv_future_mc = 2415.765 / 1.469328 = 1644.129067...
        fv/share     = 164.412906...
    """
    out = discounted_future_mcap(_make_inputs())

    assert len(out.projected_net_incomes) == 5
    # Year 1 NI = 110, Year 5 NI = 161.051
    assert abs(out.projected_net_incomes[0][1] - 110.0) < 1e-9
    assert abs(out.projected_net_incomes[-1][1] - 161.051) < 1e-6
    assert abs(out.terminal_net_income - 161.051) < 1e-6
    assert abs(out.future_market_cap - 2415.765) < 1e-6
    assert abs(out.pv_future_market_cap - 1644.129066) < 1e-3
    assert abs(out.fair_value_per_share - 164.4129) < 1e-3


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_zero_pe_raises() -> None:
    try:
        discounted_future_mcap(_make_inputs(terminal_pe=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when terminal_pe <= 0")


def test_negative_pe_raises() -> None:
    try:
        discounted_future_mcap(_make_inputs(terminal_pe=-12.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when terminal_pe <= 0")


def test_zero_shares_raises() -> None:
    try:
        discounted_future_mcap(_make_inputs(shares_outstanding=0.0))
    except ValueError:
        return
    raise AssertionError("Expected ValueError when shares_outstanding <= 0")


# ---------------------------------------------------------------------------
# Behavioral
# ---------------------------------------------------------------------------


def test_loss_making_returns_negative_fv() -> None:
    """Negative base NI -> the engine still runs but returns a non-positive
    per-share value. The view layer is responsible for warning the user; the
    pure engine stays silent so callers can choose how to surface it.
    """
    out = discounted_future_mcap(_make_inputs(base_net_income=-100.0))
    assert out.terminal_net_income < 0
    assert out.future_market_cap < 0
    assert out.pv_future_market_cap < 0
    assert out.fair_value_per_share < 0


def test_higher_growth_yields_higher_value() -> None:
    """Holding everything else fixed, faster NI growth -> larger fair value."""
    low = discounted_future_mcap(_make_inputs(net_income_growth_rate=0.05))
    high = discounted_future_mcap(_make_inputs(net_income_growth_rate=0.15))
    assert high.fair_value_per_share > low.fair_value_per_share


def test_higher_discount_rate_yields_lower_value() -> None:
    cheap = discounted_future_mcap(_make_inputs(discount_rate=0.05))
    pricey = discounted_future_mcap(_make_inputs(discount_rate=0.15))
    assert pricey.fair_value_per_share < cheap.fair_value_per_share


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
