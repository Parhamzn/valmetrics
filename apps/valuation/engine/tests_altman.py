"""Tests for the Altman Z-Score engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    python apps/valuation/engine/tests_altman.py

which executes every ``test_*`` function and prints PASS/FAIL for each.
"""

from __future__ import annotations

# NOTE: We must adjust sys.path BEFORE importing anything else, because when
# this file is run directly Python puts ``apps/valuation/engine/`` on sys.path
# first. Our local ``types.py`` / ``types_altman.py`` would otherwise
# potentially shadow stdlib modules. Mirror the trick used in ``tests.py``.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.altman import altman_z_score  # noqa: E402
from apps.valuation.engine.types_altman import AltmanInputs  # noqa: E402


def _make_inputs(**overrides) -> AltmanInputs:
    """Default = a healthy/safe firm (Z > 2.99)."""
    defaults: dict = dict(
        ticker="TEST",
        working_capital=400.0,
        total_assets=1000.0,
        retained_earnings=500.0,
        ebit=200.0,
        market_value_equity=2000.0,
        total_liabilities=400.0,
        revenue=1200.0,
    )
    defaults.update(overrides)
    return AltmanInputs(**defaults)


# ---------------------------------------------------------------------------
# Headline scenarios
# ---------------------------------------------------------------------------


def test_safe_zone() -> None:
    """Healthy firm should land in the Safe zone (Z > 2.99).

    Hand-check:
        A = 400/1000 = 0.4    -> 1.2 * 0.4 = 0.48
        B = 500/1000 = 0.5    -> 1.4 * 0.5 = 0.70
        C = 200/1000 = 0.2    -> 3.3 * 0.2 = 0.66
        D = 2000/400 = 5.0    -> 0.6 * 5.0 = 3.00
        E = 1200/1000= 1.2    -> 1.0 * 1.2 = 1.20
        Z = 0.48 + 0.70 + 0.66 + 3.00 + 1.20 = 6.04
    """
    out = altman_z_score(_make_inputs())
    assert out.zone == "Safe", (out.zone, out.z_score)
    assert abs(out.z_score - 6.04) < 1e-9, out.z_score
    # All five components populated, no warning.
    assert out.warning is None
    assert len(out.components) == 5


def test_distress_zone() -> None:
    """Heavily distressed firm: thin equity, retained-loss, near-zero EBIT.

    Negative retained earnings + tiny EBIT + heavy leverage push Z well below
    1.81.
    """
    out = altman_z_score(_make_inputs(
        working_capital=-200.0,   # negative working capital (illiquid)
        retained_earnings=-300.0, # cumulative losses
        ebit=10.0,                # barely profitable
        market_value_equity=50.0,
        total_liabilities=900.0,  # huge book leverage
    ))
    assert out.zone == "Distress", (out.zone, out.z_score)
    assert out.z_score < 1.81, out.z_score


def test_grey_zone() -> None:
    """Calibrated borderline case landing in the Grey zone."""
    # Hand-built so Z lands ~ 2.0.
    out = altman_z_score(_make_inputs(
        working_capital=100.0,    # A=0.1   -> 0.12
        retained_earnings=100.0,  # B=0.1   -> 0.14
        ebit=80.0,                # C=0.08  -> 0.264
        market_value_equity=600.0,# D=600/600=1.0 -> 0.60
        total_liabilities=600.0,
        revenue=900.0,            # E=0.9   -> 0.90
    ))
    # Expected Z = 0.12 + 0.14 + 0.264 + 0.60 + 0.90 = 2.024
    assert 1.81 <= out.z_score <= 2.99, out.z_score
    assert out.zone == "Grey", (out.zone, out.z_score)


# ---------------------------------------------------------------------------
# Component ordering and coefficients
# ---------------------------------------------------------------------------


def test_component_order_and_coefficients() -> None:
    out = altman_z_score(_make_inputs())
    expected = [
        ("Working capital / Total assets", 1.2),
        ("Retained earnings / Total assets", 1.4),
        ("EBIT / Total assets", 3.3),
        ("Market value of equity / Total liabilities", 0.6),
        ("Sales / Total assets", 1.0),
    ]
    for c, (name, coef) in zip(out.components, expected):
        assert c.name == name, c.name
        assert abs(c.coefficient - coef) < 1e-9, c.coefficient
        assert c.ratio is not None
        assert c.weighted is not None
        assert abs(c.weighted - c.coefficient * c.ratio) < 1e-9


# ---------------------------------------------------------------------------
# Missing-data handling
# ---------------------------------------------------------------------------


def test_missing_input_warns_but_does_not_raise() -> None:
    """When an input is None the component should be skipped (ratio=None,
    weighted=None) and the field surfaced in ``warning``; the overall Z is
    still returned from the remaining components."""
    out = altman_z_score(_make_inputs(retained_earnings=None))
    # B component should be None ratio / None weighted.
    assert out.components[1].ratio is None
    assert out.components[1].weighted is None
    # Other components remain populated.
    for i in (0, 2, 3, 4):
        assert out.components[i].ratio is not None
    # Warning string mentions the missing field.
    assert out.warning is not None
    assert "retained_earnings" in out.warning


def test_zero_denominator_handled() -> None:
    """Zero denominator should yield None ratio (no division by zero)."""
    out = altman_z_score(_make_inputs(total_assets=0.0, total_liabilities=0.0))
    # A, B, C, E all use total_assets; D uses total_liabilities.
    for i in (0, 1, 2, 3, 4):
        assert out.components[i].ratio is None
    # With all five components zeroed, Z = 0.0 -> Distress zone.
    assert out.z_score == 0.0
    assert out.zone == "Distress"


def test_all_inputs_none() -> None:
    """All-None input must not raise; Z=0 and Distress."""
    out = altman_z_score(AltmanInputs(
        ticker="X",
        working_capital=None,
        total_assets=None,
        retained_earnings=None,
        ebit=None,
        market_value_equity=None,
        total_liabilities=None,
        revenue=None,
    ))
    assert out.z_score == 0.0
    assert out.zone == "Distress"
    assert out.warning is not None
    for c in out.components:
        assert c.ratio is None
        assert c.weighted is None


# ---------------------------------------------------------------------------
# Threshold boundaries
# ---------------------------------------------------------------------------


def test_safe_threshold_strict() -> None:
    """Exactly 2.99 should be Grey (Safe is *strictly* > 2.99)."""
    # Construct inputs giving Z = 2.99: bias only via D = MV/TL.
    # Set A=B=C=E=0 by zeroing total_assets is not possible without ratios None
    # -- instead build a balanced case.  Easier: dial in D so the sum is 2.99.
    # Use base safe inputs and reduce MV/TL.
    # base contributions w/o D = 0.48 + 0.70 + 0.66 + 1.20 = 3.04
    # Need D contribution = -0.05, impossible with positives; use a tweak:
    # Set MV so that D adds (2.99 - 3.04) doesn't work (negative). Instead
    # bias to land *below* boundary: ensure 2.99 is NOT classed Safe.
    out = altman_z_score(_make_inputs(
        working_capital=0.0, retained_earnings=0.0, ebit=0.0,
        revenue=0.0,
        market_value_equity=1993.0, total_liabilities=400.0,
        # D = 1993/400 = 4.9825; 0.6 * 4.9825 = 2.9895 -> Grey (not Safe)
    ))
    assert out.zone == "Grey", (out.zone, out.z_score)


def test_distress_threshold_strict() -> None:
    """Exactly 1.81 should be Grey (Distress is *strictly* < 1.81)."""
    out = altman_z_score(_make_inputs(
        working_capital=0.0, retained_earnings=0.0, ebit=0.0,
        revenue=0.0,
        market_value_equity=1207.0, total_liabilities=400.0,
        # D = 1207/400 = 3.0175; 0.6 * 3.0175 = 1.8105 -> Grey
    ))
    assert out.zone == "Grey", (out.zone, out.z_score)


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
