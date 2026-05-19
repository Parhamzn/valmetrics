"""Tests for the Reverse DCF engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable as a
script::

    python apps/valuation/engine/tests_reverse_dcf.py

The headline test (``test_recover_known_growth``) is a round-trip check: pick
a known growth rate, run the forward DCF to get its fair value, then ask the
reverse DCF what growth that fair value implies — we should get the original
back within tolerance.
"""

from __future__ import annotations

# NOTE: We must adjust sys.path BEFORE importing anything else, because when
# this file is run directly Python puts ``apps/valuation/engine/`` on sys.path
# first, where local ``types.py`` could shadow stdlib modules. Mirror the
# trick used in ``tests.py`` / ``tests_epv.py``.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.dcf import dcf_perpetual_growth  # noqa: E402
from apps.valuation.engine.reverse_dcf import reverse_dcf  # noqa: E402
from apps.valuation.engine.types import DCFInputs  # noqa: E402
from apps.valuation.engine.types_reverse_dcf import ReverseDCFInputs  # noqa: E402


def _make_dcf_inputs(**overrides) -> DCFInputs:
    """Build a canonical DCFInputs object; ``overrides`` swaps individual fields."""
    defaults: dict = dict(
        ticker="TEST",
        base_revenue=1000.0,
        base_fcff=120.0,
        projection_years=5,
        revenue_growth_rate=0.10,
        ebit_margin=0.20,
        tax_rate=0.21,
        reinvestment_rate=0.30,
        terminal_growth=0.025,
        wacc=0.08,
        net_debt=200.0,
        shares_outstanding=100.0,
    )
    defaults.update(overrides)
    return DCFInputs(**defaults)


def _to_reverse(dcf: DCFInputs, current_price: float, **overrides) -> ReverseDCFInputs:
    """Build a ReverseDCFInputs from a DCFInputs + a target price."""
    fields = dict(
        ticker=dcf.ticker,
        current_price=current_price,
        base_revenue=dcf.base_revenue,
        base_fcff=dcf.base_fcff,
        projection_years=dcf.projection_years,
        ebit_margin=dcf.ebit_margin,
        tax_rate=dcf.tax_rate,
        reinvestment_rate=dcf.reinvestment_rate,
        terminal_growth=dcf.terminal_growth,
        wacc=dcf.wacc,
        net_debt=dcf.net_debt,
        shares_outstanding=dcf.shares_outstanding,
        search_lower=-0.10,
        search_upper=0.50,
    )
    fields.update(overrides)
    return ReverseDCFInputs(**fields)


# ---------------------------------------------------------------------------
# Round-trip: forward DCF at known growth -> reverse DCF should recover it
# ---------------------------------------------------------------------------


def test_recover_known_growth() -> None:
    """Forward DCF at growth=10% yields some fair_value V. Reverse DCF asked
    "what growth implies V?" must give back ~10%."""
    dcf_in = _make_dcf_inputs(revenue_growth_rate=0.10)
    fv = dcf_perpetual_growth(dcf_in).fair_value_per_share

    rev_in = _to_reverse(dcf_in, current_price=fv)
    out = reverse_dcf(rev_in)

    assert out.converged, f"did not converge, iterations={out.iterations}"
    assert out.implied_revenue_growth is not None
    # Within 0.1% absolute is plenty for bisection-to-cent precision.
    assert abs(out.implied_revenue_growth - 0.10) < 0.001, out.implied_revenue_growth
    # Final fair value should be within tolerance of the target.
    assert abs(out.final_fair_value - fv) < 0.02, out.final_fair_value


def test_recover_low_growth() -> None:
    """Same idea, but with a near-flat growth rate to exercise the lower half."""
    dcf_in = _make_dcf_inputs(revenue_growth_rate=0.02)
    fv = dcf_perpetual_growth(dcf_in).fair_value_per_share

    out = reverse_dcf(_to_reverse(dcf_in, current_price=fv))

    assert out.converged, out.iterations
    assert abs(out.implied_revenue_growth - 0.02) < 0.001, out.implied_revenue_growth


def test_recover_high_growth() -> None:
    """Round-trip at 25% growth — well inside the default upper bound (50%)."""
    dcf_in = _make_dcf_inputs(revenue_growth_rate=0.25)
    fv = dcf_perpetual_growth(dcf_in).fair_value_per_share

    out = reverse_dcf(_to_reverse(dcf_in, current_price=fv))

    assert out.converged, out.iterations
    assert abs(out.implied_revenue_growth - 0.25) < 0.001, out.implied_revenue_growth
    # 25% lies in the "extreme" warning band (>0.30 is the trigger), so no
    # warning expected here — verify.
    assert out.warning is None, out.warning


# ---------------------------------------------------------------------------
# Edge: price outside search bounds
# ---------------------------------------------------------------------------


def test_price_below_lower_bound_clips_and_warns() -> None:
    """If the market price is below the DCF value at search_lower (i.e. the
    market is pricing in even sharper contraction than -10%), return the
    lower bound and warn."""
    dcf_in = _make_dcf_inputs()
    # Find what the DCF says at the lower bound, then go strictly below it.
    fv_at_lower = dcf_perpetual_growth(
        _make_dcf_inputs(revenue_growth_rate=-0.10)
    ).fair_value_per_share
    target = fv_at_lower - 5.0  # well below

    out = reverse_dcf(_to_reverse(dcf_in, current_price=target))

    assert not out.converged
    assert out.implied_revenue_growth == -0.10
    assert out.warning is not None
    assert "contraction" in out.warning.lower(), out.warning


def test_price_above_upper_bound_clips_and_warns() -> None:
    """If price > DCF value at search_upper, clip to upper bound and warn."""
    dcf_in = _make_dcf_inputs()
    fv_at_upper = dcf_perpetual_growth(
        _make_dcf_inputs(revenue_growth_rate=0.50)
    ).fair_value_per_share
    target = fv_at_upper + 10.0

    out = reverse_dcf(_to_reverse(dcf_in, current_price=target))

    assert not out.converged
    assert out.implied_revenue_growth == 0.50
    assert out.warning is not None
    assert "extreme" in out.warning.lower() or "above" in out.warning.lower(), out.warning


# ---------------------------------------------------------------------------
# Edge: extreme-growth warning when converged
# ---------------------------------------------------------------------------


def test_extreme_implied_growth_warning() -> None:
    """If the implied growth converges above 30%, the result must carry a warning."""
    dcf_in = _make_dcf_inputs(revenue_growth_rate=0.35)
    fv = dcf_perpetual_growth(dcf_in).fair_value_per_share

    # Push search_upper out so we can converge instead of clipping.
    out = reverse_dcf(_to_reverse(dcf_in, current_price=fv, search_upper=0.60))

    assert out.converged
    assert out.implied_revenue_growth is not None and out.implied_revenue_growth > 0.30
    assert out.warning is not None
    assert "30%" in out.warning or "extreme" in out.warning.lower(), out.warning


# ---------------------------------------------------------------------------
# Edge: negative-base-FCFF company. Engine rebuilds forward FCFF from
# revenue * margin * (1 - reinvest), so base_fcff being negative shouldn't
# break the bisection.
# ---------------------------------------------------------------------------


def test_negative_base_fcff_round_trip() -> None:
    dcf_in = _make_dcf_inputs(base_fcff=-50.0, revenue_growth_rate=0.12)
    fv = dcf_perpetual_growth(dcf_in).fair_value_per_share

    out = reverse_dcf(_to_reverse(dcf_in, current_price=fv))

    assert out.converged, out.iterations
    assert abs(out.implied_revenue_growth - 0.12) < 0.001, out.implied_revenue_growth


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
