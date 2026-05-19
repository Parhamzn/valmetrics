"""Tests for the Peter Lynch fair-value engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    python apps/valuation/engine/tests_peter_lynch.py

which executes every ``test_*`` function and prints PASS/FAIL for each.
"""

from __future__ import annotations

# NOTE: We must adjust sys.path BEFORE importing anything else, because when
# this file is run directly Python puts ``apps/valuation/engine/`` on sys.path
# first, where local ``types.py`` could shadow the stdlib. Mirror the trick
# used in ``tests.py`` / ``tests_epv.py``.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.peter_lynch import peter_lynch_fair_value  # noqa: E402
from apps.valuation.engine.types_peter_lynch import PeterLynchInputs  # noqa: E402


def _make_inputs(**overrides) -> PeterLynchInputs:
    defaults: dict = dict(
        ticker="TEST",
        eps=5.0,
        growth_rate=0.15,
        dividend_yield=0.02,
    )
    defaults.update(overrides)
    return PeterLynchInputs(**defaults)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_peter_lynch_standard_case() -> None:
    """Hand-computed Lynch / PEGY example.

    EPS=$5, growth=15%, yield=2% ->
        combined = 0.17, fair_pe = 17, fair_value = 5 * 17 = $85.
    """
    out = peter_lynch_fair_value(_make_inputs())

    assert abs(out.fair_pe - 17.0) < 1e-9, out.fair_pe
    assert abs(out.fair_value_per_share - 85.0) < 1e-9, out.fair_value_per_share
    assert out.warning is None, out.warning


def test_peter_lynch_zero_yield_falls_back_to_plain_peg() -> None:
    """With dividend_yield=0 the formula collapses to Fair Value = EPS * growth%."""
    out = peter_lynch_fair_value(_make_inputs(growth_rate=0.10, dividend_yield=0.0))
    assert abs(out.fair_pe - 10.0) < 1e-9, out.fair_pe
    assert abs(out.fair_value_per_share - 50.0) < 1e-9, out.fair_value_per_share
    assert out.warning is None


# ---------------------------------------------------------------------------
# Warning triggers
# ---------------------------------------------------------------------------


def test_peter_lynch_hyper_growth_warns() -> None:
    """growth+yield > 25% should warn but still return a number."""
    out = peter_lynch_fair_value(
        _make_inputs(growth_rate=0.30, dividend_yield=0.0)
    )
    # Math still computes: fair_pe = 30, fair_value = 5 * 30 = 150.
    assert abs(out.fair_pe - 30.0) < 1e-9, out.fair_pe
    assert abs(out.fair_value_per_share - 150.0) < 1e-9, out.fair_value_per_share
    assert out.warning is not None
    assert "hyper-growth" in out.warning, out.warning


def test_peter_lynch_negative_combined_warns() -> None:
    """Negative growth+yield should warn (formula inapplicable)."""
    out = peter_lynch_fair_value(
        _make_inputs(growth_rate=-0.05, dividend_yield=0.0)
    )
    # Math: fair_pe = -5, fair_value = 5 * -5 = -25.
    assert abs(out.fair_pe + 5.0) < 1e-9, out.fair_pe
    assert abs(out.fair_value_per_share + 25.0) < 1e-9, out.fair_value_per_share
    assert out.warning is not None
    assert "Negative" in out.warning, out.warning


def test_peter_lynch_zero_combined_warns() -> None:
    """Exactly zero combined is also "inapplicable" per the spec."""
    out = peter_lynch_fair_value(
        _make_inputs(growth_rate=0.0, dividend_yield=0.0)
    )
    assert out.warning is not None
    assert "inapplicable" in out.warning.lower(), out.warning


def test_peter_lynch_negative_eps_warns() -> None:
    """Negative EPS triggers the "loss-making" warning; math still returns."""
    out = peter_lynch_fair_value(
        _make_inputs(eps=-2.0, growth_rate=0.10, dividend_yield=0.0)
    )
    # fair_pe still 10; fair_value = -2 * 10 = -20.
    assert abs(out.fair_pe - 10.0) < 1e-9, out.fair_pe
    assert abs(out.fair_value_per_share + 20.0) < 1e-9, out.fair_value_per_share
    assert out.warning is not None
    assert "Loss" in out.warning, out.warning


def test_peter_lynch_zero_eps_warns() -> None:
    """Zero EPS counts as "loss-making" — formula needs positive earnings."""
    out = peter_lynch_fair_value(
        _make_inputs(eps=0.0, growth_rate=0.10, dividend_yield=0.0)
    )
    assert abs(out.fair_value_per_share) < 1e-9, out.fair_value_per_share
    assert out.warning is not None
    assert "Loss" in out.warning, out.warning


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
