"""Tests for the Margin Analysis engine.

Pytest-compatible (plain ``assert`` and ``def test_*``). Also runnable
directly as a script::

    python apps/valuation/engine/tests_margin_analysis.py
"""

from __future__ import annotations

# NOTE: mirror the sys.path trick in tests_epv.py so direct invocation works
# without ``apps/valuation/engine/`` shadowing stdlib modules.
import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir, os.pardir, os.pardir))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import traceback  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import date  # noqa: E402

from apps.valuation.engine.margin_analysis import margin_analysis  # noqa: E402
from apps.valuation.engine.types_margin_analysis import (  # noqa: E402
    MarginAnalysisInputs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class FakeLine:
    """Minimal stand-in for apps.data.types.StatementLine."""

    period_end: date
    items: dict


def _make_lines(years_revenue_gross_op_net):
    """Build a provider-style most-recent-first list of fake lines.

    Each tuple is (year, revenue, gross_profit, operating_income, net_income).
    """
    lines = []
    for year, rev, gp, op, ni in years_revenue_gross_op_net:
        lines.append(
            FakeLine(
                period_end=date(year, 12, 31),
                items={
                    "total_revenue": rev,
                    "gross_profit": gp,
                    "operating_income": op,
                    "net_income": ni,
                },
            )
        )
    # Provider returns most-recent-first; descending year order.
    lines.sort(key=lambda L: L.period_end, reverse=True)
    return lines


# ---------------------------------------------------------------------------
# Trend cases
# ---------------------------------------------------------------------------


def test_clearly_expanding_trend() -> None:
    """Margins climb noticeably year-over-year -> 'expanding' on all three."""
    # Gross margin: 40 -> 44 -> 48 -> 52 -> 56 (slope ~ +0.04/yr)
    rows = [
        (2020, 1000.0, 400.0, 200.0, 100.0),  # 40 / 20 / 10
        (2021, 1000.0, 440.0, 240.0, 140.0),  # 44 / 24 / 14
        (2022, 1000.0, 480.0, 280.0, 180.0),  # 48 / 28 / 18
        (2023, 1000.0, 520.0, 320.0, 220.0),  # 52 / 32 / 22
        (2024, 1000.0, 560.0, 360.0, 260.0),  # 56 / 36 / 26
    ]
    out = margin_analysis(
        MarginAnalysisInputs(ticker="EXP", annual_periods=_make_lines(rows))
    )

    assert len(out.points) == 5
    # Oldest-first ordering.
    assert out.points[0].period_end == date(2020, 12, 31)
    assert out.points[-1].period_end == date(2024, 12, 31)
    assert out.latest.period_end == date(2024, 12, 31)

    assert out.trend_gross == "expanding", out.trend_gross
    assert out.trend_operating == "expanding", out.trend_operating
    assert out.trend_profit == "expanding", out.trend_profit

    # Averages: gross = (.40+.44+.48+.52+.56)/5 = 0.48
    assert abs(out.avg_gross_margin - 0.48) < 1e-9, out.avg_gross_margin
    assert abs(out.avg_operating_margin - 0.28) < 1e-9, out.avg_operating_margin
    assert abs(out.avg_profit_margin - 0.18) < 1e-9, out.avg_profit_margin


def test_clearly_compressing_trend() -> None:
    """Margins fall hard year-over-year -> 'compressing'."""
    rows = [
        (2020, 1000.0, 560.0, 360.0, 260.0),
        (2021, 1000.0, 520.0, 320.0, 220.0),
        (2022, 1000.0, 480.0, 280.0, 180.0),
        (2023, 1000.0, 440.0, 240.0, 140.0),
        (2024, 1000.0, 400.0, 200.0, 100.0),
    ]
    out = margin_analysis(
        MarginAnalysisInputs(ticker="COMP", annual_periods=_make_lines(rows))
    )

    assert out.trend_gross == "compressing", out.trend_gross
    assert out.trend_operating == "compressing", out.trend_operating
    assert out.trend_profit == "compressing", out.trend_profit
    # Latest is the worst year (oldest-first sort means the most-recent year
    # is at index -1).
    assert abs(out.latest.gross_margin - 0.40) < 1e-9


def test_stable_trend_small_noise() -> None:
    """Margins jitter inside the +/- 50 bps band -> 'stable'."""
    rows = [
        (2020, 1000.0, 500.0, 200.0, 100.0),  # .50 / .20 / .10
        (2021, 1000.0, 502.0, 199.0, 101.0),
        (2022, 1000.0, 498.0, 201.0, 99.0),
        (2023, 1000.0, 501.0, 200.0, 100.0),
        (2024, 1000.0, 499.0, 200.0, 100.0),
    ]
    out = margin_analysis(
        MarginAnalysisInputs(ticker="STAB", annual_periods=_make_lines(rows))
    )
    assert out.trend_gross == "stable", out.trend_gross
    assert out.trend_operating == "stable", out.trend_operating
    assert out.trend_profit == "stable", out.trend_profit


def test_mixed_directions_per_line() -> None:
    """Different margins can move different directions independently."""
    # Gross steady, operating expands, profit compresses.
    rows = [
        (2020, 1000.0, 500.0, 100.0, 200.0),  # gm .50  om .10  pm .20
        (2021, 1000.0, 500.0, 130.0, 170.0),  # gm .50  om .13  pm .17
        (2022, 1000.0, 500.0, 160.0, 140.0),  # gm .50  om .16  pm .14
        (2023, 1000.0, 500.0, 190.0, 110.0),  # gm .50  om .19  pm .11
        (2024, 1000.0, 500.0, 220.0, 80.0),   # gm .50  om .22  pm .08
    ]
    out = margin_analysis(
        MarginAnalysisInputs(ticker="MIX", annual_periods=_make_lines(rows))
    )
    assert out.trend_gross == "stable", out.trend_gross
    assert out.trend_operating == "expanding", out.trend_operating
    assert out.trend_profit == "compressing", out.trend_profit


# ---------------------------------------------------------------------------
# Missing-data handling
# ---------------------------------------------------------------------------


def test_missing_revenue_yields_none_point() -> None:
    """Zero / missing revenue -> all margins on that point should be None."""
    lines = [
        FakeLine(
            period_end=date(2024, 12, 31),
            items={
                "total_revenue": None,
                "gross_profit": 100.0,
                "operating_income": 50.0,
                "net_income": 20.0,
            },
        ),
        FakeLine(
            period_end=date(2023, 12, 31),
            items={
                "total_revenue": 0,  # zero -> no division
                "gross_profit": 100.0,
                "operating_income": 50.0,
                "net_income": 20.0,
            },
        ),
    ]
    out = margin_analysis(
        MarginAnalysisInputs(ticker="MISS", annual_periods=lines)
    )
    for p in out.points:
        assert p.gross_margin is None, p
        assert p.operating_margin is None, p
        assert p.profit_margin is None, p
    # No usable values -> averages None and trend "insufficient data".
    assert out.avg_gross_margin is None
    assert out.avg_operating_margin is None
    assert out.avg_profit_margin is None
    assert out.trend_gross == "insufficient data"


def test_operating_income_fallback_to_ebit() -> None:
    """When operating_income is missing, engine should fall back to ebit."""
    lines = [
        FakeLine(
            period_end=date(2024, 12, 31),
            items={
                "total_revenue": 1000.0,
                "gross_profit": 500.0,
                "operating_income": None,
                "ebit": 250.0,
                "net_income": 150.0,
            },
        ),
    ]
    out = margin_analysis(
        MarginAnalysisInputs(ticker="EBIT", annual_periods=lines)
    )
    assert abs(out.latest.operating_margin - 0.25) < 1e-9, out.latest


def test_too_few_points_for_trend() -> None:
    """With <3 usable points the trend label must be 'insufficient data'."""
    rows = [
        (2023, 1000.0, 500.0, 200.0, 100.0),
        (2024, 1000.0, 600.0, 300.0, 200.0),
    ]
    out = margin_analysis(
        MarginAnalysisInputs(ticker="THIN", annual_periods=_make_lines(rows))
    )
    assert len(out.points) == 2
    assert out.trend_gross == "insufficient data"
    assert out.trend_operating == "insufficient data"
    assert out.trend_profit == "insufficient data"


def test_empty_input() -> None:
    """No periods at all -> safe empty output, no exception."""
    out = margin_analysis(MarginAnalysisInputs(ticker="EMPTY", annual_periods=[]))
    assert out.points == []
    assert out.avg_gross_margin is None
    assert out.trend_gross == "insufficient data"
    assert out.latest.gross_margin is None


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
