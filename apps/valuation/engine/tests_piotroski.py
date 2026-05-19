"""Tests for the Piotroski F-Score engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable directly
as a script::

    python apps/valuation/engine/tests_piotroski.py

which executes every ``test_*`` function and prints PASS/FAIL for each.
"""

from __future__ import annotations

# NOTE: We must adjust sys.path BEFORE importing anything else, because when
# this file is run directly Python puts ``apps/valuation/engine/`` on sys.path
# first. Our local ``types.py`` / ``types_piotroski.py`` would otherwise
# potentially shadow stdlib modules. Mirror the trick used in ``tests.py``.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402

from apps.valuation.engine.piotroski import piotroski_f_score  # noqa: E402
from apps.valuation.engine.types_piotroski import PiotroskiInputs  # noqa: E402


def _make_inputs(**overrides) -> PiotroskiInputs:
    """Default = a strong-firm scenario that scores 9/9."""
    defaults: dict = dict(
        ticker="TEST",
        # Profitability: NI positive, ROA positive, CFO positive, CFO > NI
        net_income=100.0,
        prior_net_income=80.0,
        total_assets=1000.0,
        prior_total_assets=900.0,
        operating_cash_flow=150.0,
        prior_operating_cash_flow=120.0,
        # Leverage/liquidity/source-of-funds: LTD down, current ratio up,
        # diluted shares flat
        long_term_debt=200.0,
        prior_long_term_debt=300.0,
        current_assets=500.0,
        prior_current_assets=400.0,
        current_liabilities=200.0,
        prior_current_liabilities=200.0,
        diluted_shares=100.0,
        prior_diluted_shares=100.0,
        # Operating efficiency: gross margin up, asset turnover up
        gross_profit=400.0,
        prior_gross_profit=300.0,
        total_revenue=800.0,
        prior_total_revenue=700.0,
    )
    defaults.update(overrides)
    return PiotroskiInputs(**defaults)


# ---------------------------------------------------------------------------
# Full-score example
# ---------------------------------------------------------------------------


def test_full_nine_score() -> None:
    """Canonical 9/9 example — every criterion is satisfied."""
    out = piotroski_f_score(_make_inputs())
    assert out.total_score == 9, [c.score for c in out.criteria]
    assert out.classification == "Strong (8-9)"
    # Every criterion must have its 1-point flag.
    for c in out.criteria:
        assert c.score == 1, f"Criterion failed: {c.name}"


def test_zero_score_weak() -> None:
    """A worst-case firm should score 0/9 and classify Weak."""
    out = piotroski_f_score(_make_inputs(
        net_income=-50.0,
        operating_cash_flow=-100.0,
        long_term_debt=500.0,   # increased vs prior 300
        current_assets=200.0,   # current ratio (1.0) below prior (2.0)
        current_liabilities=200.0,
        diluted_shares=110.0,   # +10% shares issued
        gross_profit=200.0,     # margin 25% vs prior ~43%
        total_revenue=800.0,
        prior_gross_profit=300.0,
        prior_total_revenue=700.0,
        total_assets=2000.0,    # asset turnover 0.4 vs prior 0.78
    ))
    assert out.total_score == 0, [c.score for c in out.criteria]
    assert out.classification == "Weak (0-3)"


# ---------------------------------------------------------------------------
# Individual criteria
# ---------------------------------------------------------------------------


def test_criterion_1_net_income_positive() -> None:
    out = piotroski_f_score(_make_inputs(net_income=10.0))
    assert out.criteria[0].score == 1
    out = piotroski_f_score(_make_inputs(net_income=-1.0))
    assert out.criteria[0].score == 0
    out = piotroski_f_score(_make_inputs(net_income=0.0))
    assert out.criteria[0].score == 0


def test_criterion_2_roa_positive() -> None:
    # NI > 0, TA > 0 -> ROA > 0
    out = piotroski_f_score(_make_inputs(net_income=1.0, total_assets=100.0))
    assert out.criteria[1].score == 1
    # NI < 0 -> ROA < 0
    out = piotroski_f_score(_make_inputs(net_income=-1.0, total_assets=100.0))
    assert out.criteria[1].score == 0


def test_criterion_3_cfo_positive() -> None:
    out = piotroski_f_score(_make_inputs(operating_cash_flow=5.0))
    assert out.criteria[2].score == 1
    out = piotroski_f_score(_make_inputs(operating_cash_flow=-5.0))
    assert out.criteria[2].score == 0


def test_criterion_4_cfo_exceeds_ni() -> None:
    out = piotroski_f_score(_make_inputs(operating_cash_flow=200.0, net_income=100.0))
    assert out.criteria[3].score == 1
    out = piotroski_f_score(_make_inputs(operating_cash_flow=50.0, net_income=100.0))
    assert out.criteria[3].score == 0


def test_criterion_5_ltd_decrease() -> None:
    out = piotroski_f_score(_make_inputs(long_term_debt=100.0, prior_long_term_debt=200.0))
    assert out.criteria[4].score == 1
    out = piotroski_f_score(_make_inputs(long_term_debt=300.0, prior_long_term_debt=200.0))
    assert out.criteria[4].score == 0


def test_criterion_6_current_ratio_improved() -> None:
    out = piotroski_f_score(_make_inputs(
        current_assets=400.0, current_liabilities=100.0,
        prior_current_assets=200.0, prior_current_liabilities=100.0,
    ))
    # current ratio: 4.0 vs prior 2.0
    assert out.criteria[5].score == 1
    out = piotroski_f_score(_make_inputs(
        current_assets=100.0, current_liabilities=100.0,
        prior_current_assets=300.0, prior_current_liabilities=100.0,
    ))
    assert out.criteria[5].score == 0


def test_criterion_7_no_new_shares() -> None:
    out = piotroski_f_score(_make_inputs(diluted_shares=99.0, prior_diluted_shares=100.0))
    assert out.criteria[6].score == 1
    # Tolerance band: 101 / 100 = 1.01 -> still 1
    out = piotroski_f_score(_make_inputs(diluted_shares=101.0, prior_diluted_shares=100.0))
    assert out.criteria[6].score == 1
    # Above the tolerance buffer -> 0
    out = piotroski_f_score(_make_inputs(diluted_shares=105.0, prior_diluted_shares=100.0))
    assert out.criteria[6].score == 0


def test_criterion_8_gross_margin_improved() -> None:
    # 60% vs prior 50%
    out = piotroski_f_score(_make_inputs(
        gross_profit=600.0, total_revenue=1000.0,
        prior_gross_profit=500.0, prior_total_revenue=1000.0,
    ))
    assert out.criteria[7].score == 1
    out = piotroski_f_score(_make_inputs(
        gross_profit=400.0, total_revenue=1000.0,
        prior_gross_profit=500.0, prior_total_revenue=1000.0,
    ))
    assert out.criteria[7].score == 0


def test_criterion_9_asset_turnover_improved() -> None:
    # 1000/500=2.0 vs prior 1000/1000=1.0
    out = piotroski_f_score(_make_inputs(
        total_revenue=1000.0, total_assets=500.0,
        prior_total_revenue=1000.0, prior_total_assets=1000.0,
    ))
    assert out.criteria[8].score == 1
    # 1000/2000=0.5 vs prior 1.0
    out = piotroski_f_score(_make_inputs(
        total_revenue=1000.0, total_assets=2000.0,
        prior_total_revenue=1000.0, prior_total_assets=1000.0,
    ))
    assert out.criteria[8].score == 0


# ---------------------------------------------------------------------------
# Missing-data handling
# ---------------------------------------------------------------------------


def test_missing_data_scores_zero_not_raises() -> None:
    """Any None input should score 0 on the affected criterion, no exceptions."""
    out = piotroski_f_score(_make_inputs(
        net_income=None,
        operating_cash_flow=None,
        long_term_debt=None,
        current_assets=None,
        diluted_shares=None,
        gross_profit=None,
        total_assets=None,
    ))
    # All criteria with missing data should score 0 with explanation
    # "Data unavailable".
    for c in out.criteria:
        if c.explanation == "Data unavailable":
            assert c.score == 0


def test_missing_data_partial_full_inputs() -> None:
    """Just NI missing -> criteria 1, 2, 4 fail; the rest still score normally."""
    out = piotroski_f_score(_make_inputs(net_income=None))
    assert out.criteria[0].score == 0
    assert out.criteria[1].score == 0
    assert out.criteria[3].score == 0
    # CFO criterion (3) doesn't depend on NI.
    assert out.criteria[2].score == 1


def test_classification_bands() -> None:
    """Spot-check the classifier at the band boundaries."""
    # An inputs object where you can dial total_score by swapping fields is
    # tedious; instead, do partial inputs and confirm the buckets are mapped
    # right using a tiny synthetic.
    out = piotroski_f_score(_make_inputs())
    assert out.classification == "Strong (8-9)"
    # Force a 4-criterion-met scenario:
    out = piotroski_f_score(_make_inputs(
        long_term_debt=500.0,  # fail #5
        current_assets=200.0,  # fail #6 (ratio drops)
        diluted_shares=110.0,  # fail #7
        gross_profit=200.0, total_revenue=800.0,  # fail #8
        total_assets=2000.0,  # fail #9
    ))
    # Failures: 5,6,7,8,9. Passes: 1,2,3,4 -> total 4 = Neutral
    assert out.total_score == 4, [c.score for c in out.criteria]
    assert out.classification == "Neutral (4-7)"


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
