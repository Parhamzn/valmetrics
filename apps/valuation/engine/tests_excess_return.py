"""Tests for the Simple Excess Return engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    .venv/bin/python apps/valuation/engine/tests_excess_return.py

which executes every ``test_*`` function and prints PASS/FAIL for each.
"""

from __future__ import annotations

# NOTE: We must adjust sys.path BEFORE importing anything else, because when
# this file is run directly Python puts ``apps/valuation/engine/`` on sys.path
# first. Our local ``types.py`` would then shadow the stdlib ``types`` module,
# breaking ``import traceback`` (and many others). Fix is the same pattern as
# ``tests.py`` in this folder.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.excess_return import simple_excess_return  # noqa: E402
from apps.valuation.engine.types_excess_return import (  # noqa: E402
    SimpleExcessReturnInputs,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_basic() -> None:
    """Hand-computed example.

    BV = 10, ROE = 15%, Ke = 10%, g = 3%.

        excess = (0.15 − 0.10) × 10                = 0.50
        pv     = 0.50 × 1.03 / (0.10 − 0.03)
               = 0.515 / 0.07                       = 7.357142857...
        fair   = 10 + 7.357142857                   = 17.357142857...
    """
    out = simple_excess_return(
        SimpleExcessReturnInputs(
            ticker="TEST",
            book_value_per_share=10.0,
            return_on_equity=0.15,
            cost_of_equity=0.10,
            growth_rate=0.03,
        )
    )
    assert abs(out.excess_return_per_share - 0.50) < 1e-9, out.excess_return_per_share
    assert abs(out.pv_perpetual_excess - (0.515 / 0.07)) < 1e-9, out.pv_perpetual_excess
    assert abs(out.fair_value_per_share - 17.357142857142858) < 1e-9, out.fair_value_per_share
    # Spec asks for 17.36 within 0.01.
    assert abs(out.fair_value_per_share - 17.36) < 0.01, out.fair_value_per_share


def test_value_destruction() -> None:
    """ROE below Ke: excess negative, fair value below book."""
    out = simple_excess_return(
        SimpleExcessReturnInputs(
            ticker="TEST",
            book_value_per_share=10.0,
            return_on_equity=0.05,
            cost_of_equity=0.10,
            growth_rate=0.03,
        )
    )
    # excess = (0.05 - 0.10) * 10 = -0.50; pv = -0.50 * 1.03 / 0.07 = -7.357
    # fair = 10 - 7.357 = 2.643
    assert out.excess_return_per_share < 0, out.excess_return_per_share
    assert out.pv_perpetual_excess < 0, out.pv_perpetual_excess
    assert out.fair_value_per_share < 10.0, out.fair_value_per_share


def test_growth_too_high_raises() -> None:
    """g = 11% >= Ke = 10% must raise."""
    try:
        simple_excess_return(
            SimpleExcessReturnInputs(
                ticker="BAD",
                book_value_per_share=10.0,
                return_on_equity=0.15,
                cost_of_equity=0.10,
                growth_rate=0.11,
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError when growth_rate >= cost_of_equity")


def test_growth_equal_ke_raises() -> None:
    """Boundary: g == Ke must also raise (denominator is zero)."""
    try:
        simple_excess_return(
            SimpleExcessReturnInputs(
                ticker="BAD",
                book_value_per_share=10.0,
                return_on_equity=0.15,
                cost_of_equity=0.10,
                growth_rate=0.10,
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError when growth_rate == cost_of_equity")


def test_negative_book_value_raises() -> None:
    """BV <= 0 is meaningless for this model."""
    try:
        simple_excess_return(
            SimpleExcessReturnInputs(
                ticker="BAD",
                book_value_per_share=-5.0,
                return_on_equity=0.15,
                cost_of_equity=0.10,
                growth_rate=0.03,
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError when book_value_per_share <= 0")


def test_zero_book_value_raises() -> None:
    try:
        simple_excess_return(
            SimpleExcessReturnInputs(
                ticker="BAD",
                book_value_per_share=0.0,
                return_on_equity=0.15,
                cost_of_equity=0.10,
                growth_rate=0.03,
            )
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError when book_value_per_share == 0")


def test_roe_equals_ke_yields_book_value() -> None:
    """When ROE == Ke, excess is exactly zero, fair value == book value."""
    out = simple_excess_return(
        SimpleExcessReturnInputs(
            ticker="TEST",
            book_value_per_share=20.0,
            return_on_equity=0.10,
            cost_of_equity=0.10,
            growth_rate=0.03,
        )
    )
    assert abs(out.excess_return_per_share) < 1e-12, out.excess_return_per_share
    assert abs(out.pv_perpetual_excess) < 1e-12, out.pv_perpetual_excess
    assert abs(out.fair_value_per_share - 20.0) < 1e-9, out.fair_value_per_share


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
